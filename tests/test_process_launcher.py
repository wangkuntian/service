"""ProcessLauncher单元测试

这个模块包含了ProcessLauncher类的全面单元测试，包括：
- 异步启动和停止
- 信号处理
- 子进程管理
- 错误处理
- 重启机制
"""

import asyncio
import os
import signal
import time
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from service import ServiceBase
from service.config.common import ConfigOpts
from service.launchers.process_launcher import (
    ProcessLauncher,
    ServiceWrapper,
    SignalExit,
    _is_sighup_and_daemon,
    _check_service_base,
)


class MockService(ServiceBase):
    """测试用的模拟服务"""

    def __init__(self):
        self.started = False
        self.stopped = False
        self.reset_called = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def wait(self):
        pass

    async def reset(self):
        self.reset_called = True


class TestProcessLauncher:
    """ProcessLauncher单元测试类"""

    @pytest.fixture
    def mock_service(self):
        """创建模拟服务实例"""
        return MockService()

    @pytest.fixture
    def config(self):
        """创建测试配置"""
        conf = ConfigOpts()
        conf.child_monitor_interval = 0.01
        conf.graceful_shutdown_timeout = 5
        conf.log_options = False
        return conf

    @pytest.fixture
    def launcher(self, config):
        """创建ProcessLauncher实例"""
        with patch('os.pipe') as mock_pipe:
            mock_pipe.return_value = (0, 1)
            with patch('os.fdopen') as mock_fdopen:
                mock_fdopen.return_value = MagicMock()
                launcher = ProcessLauncher(config)
                return launcher

    def test_init(self, config):
        """测试ProcessLauncher初始化"""
        with patch('os.pipe') as mock_pipe:
            mock_pipe.return_value = (0, 1)
            with patch('os.fdopen') as mock_fdopen:
                mock_fdopen.return_value = MagicMock()
                launcher = ProcessLauncher(config)

                assert launcher.conf == config
                assert launcher.children == {}
                assert launcher.sigcaught is None
                assert launcher.running is True
                assert launcher.wait_interval == 0.01

    def test_init_pipe_error(self, config):
        """测试管道创建失败的情况"""
        with patch('os.pipe', side_effect=OSError('Pipe creation failed')):
            with pytest.raises(OSError):
                ProcessLauncher(config)

    def test_is_sighup_and_daemon(self):
        """测试SIGHUP信号检测函数"""
        assert _is_sighup_and_daemon(signal.SIGHUP) is True
        assert _is_sighup_and_daemon(signal.SIGTERM) is False
        assert _is_sighup_and_daemon(signal.SIGINT) is False

    def test_check_service_base_valid(self, mock_service):
        """测试有效服务检查"""
        # 不应该抛出异常
        _check_service_base(mock_service)

    def test_check_service_base_invalid(self):
        """测试无效服务检查"""
        with pytest.raises(TypeError):
            _check_service_base('not a service')

    def test_signal_exit(self):
        """测试SignalExit异常类"""
        exit_exc = SignalExit(signal.SIGTERM, 1)
        assert exit_exc.signo == signal.SIGTERM
        assert exit_exc.code == 1

    def test_service_wrapper(self, mock_service):
        """测试ServiceWrapper类"""
        wrapper = ServiceWrapper(mock_service, 2)
        assert wrapper.service == mock_service
        assert wrapper.workers == 2
        assert wrapper.children == set()
        assert wrapper.forktimes == []

    @pytest.mark.asyncio
    async def test_setup_async_signal_handlers(self, launcher):
        """测试异步信号处理器设置"""
        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            await launcher._setup_async_signal_handlers()

            # 验证信号处理器被设置
            assert mock_event_loop.add_signal_handler.call_count >= 3
            assert launcher._signal_handlers_setup is True

    @pytest.mark.asyncio
    async def test_setup_async_signal_handlers_already_setup(self, launcher):
        """测试重复设置信号处理器"""
        launcher._signal_handlers_setup = True

        with patch('asyncio.get_running_loop') as mock_loop:
            await launcher._setup_async_signal_handlers()

            # 不应该再次调用
            mock_loop.assert_not_called()

    def test_handle_term(self, launcher):
        """测试TERM信号处理"""
        launcher._handle_term()

        assert launcher.sigcaught == signal.SIGTERM
        assert launcher.running is False
        assert launcher._shutdown_event.is_set()

    def test_handle_hup(self, launcher):
        """测试HUP信号处理"""
        launcher._handle_hup()

        assert launcher.sigcaught == signal.SIGHUP
        assert launcher.running is False
        assert launcher._restart_event.is_set()

    @patch('os._exit')
    def test_handle_int(self, mock_exit, launcher):
        """测试INT信号处理"""
        launcher._handle_int()
        mock_exit.assert_called_once_with(1)

    @patch('os._exit')
    def test_handle_alarm(self, mock_exit, launcher):
        """测试ALARM信号处理"""
        launcher._handle_alarm()
        mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_start_child_success(self, launcher, mock_service):
        """测试成功启动子进程"""
        wrap = ServiceWrapper(mock_service, 1)

        with patch('os.fork', return_value=123):
            with patch('time.time', return_value=1000):
                pid = await launcher._start_child(wrap)

                assert pid == 123
                assert 123 in wrap.children
                assert 123 in launcher.children
                assert launcher.children[123] == wrap

    @pytest.mark.asyncio
    async def test_start_child_fork_limit(self, launcher, mock_service):
        """测试fork速率限制"""
        wrap = ServiceWrapper(mock_service, 1)
        wrap.forktimes = [time.time() - 0.5]  # 最近有fork

        with patch('os.fork', return_value=123):
            with patch('asyncio.sleep') as mock_sleep:
                with patch('time.time', return_value=time.time()):
                    await launcher._start_child(wrap)

                    # 应该有异步等待
                    mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_start_child_retry_on_eagain(self, launcher, mock_service):
        """测试EAGAIN错误重试"""
        wrap = ServiceWrapper(mock_service, 1)

        eagain_error = OSError()
        eagain_error.errno = 11  # EAGAIN

        with patch('os.fork', side_effect=[eagain_error, 123]):
            with patch('asyncio.sleep') as mock_sleep:
                with patch('time.time', return_value=1000):
                    pid = await launcher._start_child(wrap)

                    assert pid == 123
                    mock_sleep.assert_called()

    @pytest.mark.asyncio
    async def test_start_child_max_retries_exceeded(
        self, launcher, mock_service
    ):
        """测试超过最大重试次数"""
        wrap = ServiceWrapper(mock_service, 1)
        launcher.conf.child_start_max_retries = 1

        eagain_error = OSError()
        eagain_error.errno = 11  # EAGAIN

        with patch('os.fork', side_effect=eagain_error):
            with pytest.raises(OSError):
                await launcher._start_child(wrap)

    @pytest.mark.asyncio
    async def test_monitor_children(self, launcher):
        """测试子进程监控"""
        launcher.running = True

        # 模拟一个死掉的子进程
        mock_wrap = MagicMock()
        mock_wrap.children = set()
        mock_wrap.workers = 1

        with patch.object(
            launcher, '_wait_child', side_effect=[mock_wrap, None]
        ):
            with patch.object(launcher, '_start_child') as mock_start:
                with patch('asyncio.sleep') as mock_sleep:
                    # 运行一次循环
                    launcher.running = False
                    await launcher._monitor_children()

                    mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_child_setup_async_signals(self, launcher):
        """测试子进程异步信号设置"""
        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            await launcher._child_setup_async_signals()

            # 验证子进程信号处理器被设置
            assert mock_event_loop.add_signal_handler.call_count == 3

    def test_child_handle_term(self, launcher):
        """测试子进程TERM信号处理"""
        launcher.launcher = AsyncMock()

        launcher._child_handle_term()

        # 应该创建停止任务

    def test_child_handle_hup(self, launcher):
        """测试子进程HUP信号处理"""
        with pytest.raises(SignalExit) as exc_info:
            launcher._child_handle_hup()

        assert exc_info.value.signo == signal.SIGHUP

    @patch('os._exit')
    def test_child_handle_int(self, mock_exit, launcher):
        """测试子进程INT信号处理"""
        launcher._child_handle_int()
        mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_child_wait_for_exit_or_signal_normal(self, launcher):
        """测试子进程正常等待退出"""
        mock_launcher = AsyncMock()

        status, signo = await launcher._child_wait_for_exit_or_signal(
            mock_launcher
        )

        assert status == 0
        assert signo == 0
        mock_launcher.wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_child_wait_for_exit_or_signal_signal_exit(self, launcher):
        """测试子进程信号退出"""
        mock_launcher = AsyncMock()
        mock_launcher.wait.side_effect = SignalExit(signal.SIGHUP, 1)

        status, signo = await launcher._child_wait_for_exit_or_signal(
            mock_launcher
        )

        assert status == 1
        assert signo == signal.SIGHUP

    @pytest.mark.asyncio
    async def test_child_wait_for_exit_or_signal_system_exit(self, launcher):
        """测试子进程系统退出"""
        mock_launcher = AsyncMock()
        mock_launcher.wait.side_effect = SystemExit(2)

        status, signo = await launcher._child_wait_for_exit_or_signal(
            mock_launcher
        )

        assert status == 2
        assert signo == 0
        mock_launcher.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_child_process_async(self, launcher, mock_service):
        """测试异步子进程创建"""
        with patch.object(
            launcher, '_child_setup_async_signals'
        ) as mock_setup:
            with patch('os.close') as mock_close:
                with patch('threading.Thread') as mock_thread:
                    with patch('random.seed') as mock_seed:
                        with patch(
                            'service.launchers.base.Launcher'
                        ) as mock_launcher_class:
                            mock_launcher = AsyncMock()
                            mock_launcher_class.return_value = mock_launcher

                            result = await launcher._child_process_async(
                                mock_service
                            )

                            assert result == mock_launcher
                            mock_setup.assert_called_once()
                            mock_close.assert_called_once()
                            mock_thread.assert_called_once()
                            mock_seed.assert_called_once()
                            mock_launcher.launch_service.assert_called_once_with(
                                mock_service
                            )

    def test_wait_child_no_child(self, launcher):
        """测试没有子进程退出的情况"""
        with patch('os.waitpid', return_value=(0, 0)):
            result = launcher._wait_child()
            assert result is None

    def test_wait_child_unknown_pid(self, launcher):
        """测试未知PID的情况"""
        with patch('os.waitpid', return_value=(999, 0)):
            result = launcher._wait_child()
            assert result is None

    def test_wait_child_known_pid(self, launcher, mock_service):
        """测试已知PID退出"""
        wrap = ServiceWrapper(mock_service, 1)
        wrap.children.add(123)
        launcher.children[123] = wrap

        with patch('os.waitpid', return_value=(123, 0)):
            with patch('os.WIFSIGNALED', return_value=False):
                with patch('os.WEXITSTATUS', return_value=0):
                    result = launcher._wait_child()

                    assert result == wrap
                    assert 123 not in wrap.children
                    assert 123 not in launcher.children

    def test_wait_child_signaled(self, launcher, mock_service):
        """测试子进程被信号杀死"""
        wrap = ServiceWrapper(mock_service, 1)
        wrap.children.add(123)
        launcher.children[123] = wrap

        with patch('os.waitpid', return_value=(123, 256)):
            with patch('os.WIFSIGNALED', return_value=True):
                with patch('os.WTERMSIG', return_value=signal.SIGTERM):
                    result = launcher._wait_child()

                    assert result == wrap

    def test_wait_child_eintr(self, launcher):
        """测试EINTR错误"""
        error = OSError()
        error.errno = 4  # EINTR

        with patch('os.waitpid', side_effect=error):
            result = launcher._wait_child()
            assert result is None

    @pytest.mark.asyncio
    async def test_launch_service(self, launcher, mock_service):
        """测试启动服务"""
        with patch('gc.freeze') as mock_freeze:
            with patch.object(
                launcher, '_setup_async_signal_handlers'
            ) as mock_setup:
                with patch.object(
                    launcher, '_start_child', return_value=123
                ) as mock_start:
                    with patch('asyncio.create_task') as mock_create_task:
                        mock_task = AsyncMock()
                        mock_create_task.return_value = mock_task

                        await launcher.launch_service(mock_service, workers=2)

                        mock_freeze.assert_called_once()
                        mock_setup.assert_called_once()
                        # 应该启动2个工作进程
                        assert mock_start.call_count == 2

    @pytest.mark.asyncio
    async def test_launch_service_invalid_service(self, launcher):
        """测试启动无效服务"""
        with pytest.raises(TypeError):
            await launcher.launch_service('not a service')

    @pytest.mark.asyncio
    async def test_wait_shutdown_event(self, launcher):
        """测试等待关闭事件"""
        launcher.conf.log_options = False

        with patch('service.systemd.notify_once') as mock_notify:
            # 立即设置关闭事件
            launcher._shutdown_event.set()
            launcher.running = True

            result = await launcher.wait()

            assert result == 0
            mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_restart_event(self, launcher):
        """测试等待重启事件"""
        launcher.conf.log_options = False
        launcher.sigcaught = signal.SIGHUP

        with patch('service.systemd.notify_once') as mock_notify:
            with patch.object(launcher, '_restart_services') as mock_restart:
                with patch.object(launcher, 'stop') as mock_stop:
                    # 设置重启事件
                    launcher._restart_event.set()
                    launcher.running = True

                    result = await launcher.wait()

                    assert result == 0
                    mock_restart.assert_called_once()

    @pytest.mark.asyncio
    async def test_restart_services(self, launcher, mock_service):
        """测试重启服务"""
        wrap = ServiceWrapper(mock_service, 1)
        launcher.children[123] = wrap

        with patch('os.kill') as mock_kill:
            await launcher._restart_services()

            mock_kill.assert_called_once_with(123, signal.SIGTERM)
            assert mock_service.reset_called
            assert launcher.running is True
            assert launcher.sigcaught is None

    @pytest.mark.asyncio
    async def test_stop(self, launcher, mock_service):
        """测试停止所有服务"""
        # 设置监控任务
        launcher._child_monitor_task = AsyncMock()

        # 添加子进程
        wrap = ServiceWrapper(mock_service, 1)
        launcher.children[123] = wrap

        with patch('os.kill') as mock_kill:
            with patch.object(launcher, '_wait_child') as mock_wait:
                with patch.object(
                    launcher, '_cleanup_signal_handlers'
                ) as mock_cleanup:
                    with patch(
                        'time.time', side_effect=[0, 1]
                    ):  # 模拟时间流逝
                        await launcher.stop()

                        assert launcher.running is False
                        mock_kill.assert_called_with(123, signal.SIGTERM)
                        mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_force_kill(self, launcher, mock_service):
        """测试强制杀死子进程"""
        launcher._child_monitor_task = None

        # 添加子进程
        wrap = ServiceWrapper(mock_service, 1)
        launcher.children[123] = wrap

        with patch('os.kill') as mock_kill:
            with patch.object(
                launcher, '_wait_child', return_value=None
            ):  # 子进程不退出
                with patch.object(launcher, '_cleanup_signal_handlers'):
                    with patch('time.time', side_effect=[0, 35]):  # 超时
                        await launcher.stop()

                        # 应该调用SIGTERM和SIGKILL
                        calls = mock_kill.call_args_list
                        assert call(123, signal.SIGTERM) in calls
                        assert call(123, signal.SIGKILL) in calls

    @pytest.mark.asyncio
    async def test_cleanup_signal_handlers(self, launcher):
        """测试清理信号处理器"""
        launcher._signal_handlers_setup = True

        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            await launcher._cleanup_signal_handlers()

            # 验证信号处理器被移除
            assert mock_event_loop.remove_signal_handler.call_count >= 3
            assert launcher._signal_handlers_setup is False

    @pytest.mark.asyncio
    async def test_cleanup_signal_handlers_not_setup(self, launcher):
        """测试清理未设置的信号处理器"""
        launcher._signal_handlers_setup = False

        with patch('asyncio.get_running_loop') as mock_loop:
            await launcher._cleanup_signal_handlers()

            # 不应该调用loop
            mock_loop.assert_not_called()


@pytest.mark.asyncio
async def test_pipe_watcher_integration():
    """测试管道监控器集成"""
    config = ConfigOpts()

    with patch('os.pipe') as mock_pipe:
        mock_pipe.return_value = (0, 1)
        with patch('os.fdopen') as mock_fdopen:
            mock_readpipe = MagicMock()
            mock_readpipe.read.side_effect = Exception('Parent died')
            mock_fdopen.return_value = mock_readpipe

            launcher = ProcessLauncher(config)

            with patch('sys.exit') as mock_exit:
                with patch('asyncio.run') as mock_run:
                    launcher._pipe_watcher()

                    mock_exit.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_full_lifecycle():
    """测试完整生命周期"""
    config = ConfigOpts()
    config.child_monitor_interval = 0.001

    with patch('os.pipe') as mock_pipe:
        mock_pipe.return_value = (0, 1)
        with patch('os.fdopen') as mock_fdopen:
            mock_fdopen.return_value = MagicMock()

            launcher = ProcessLauncher(config)
            service = MockService()

            # 模拟fork成功但立即退出
            with patch('os.fork', return_value=123):
                with patch('os.waitpid', side_effect=[(0, 0), (123, 0)]):
                    with patch('os.WIFSIGNALED', return_value=False):
                        with patch('os.WEXITSTATUS', return_value=0):
                            with patch(
                                'asyncio.get_running_loop'
                            ) as mock_loop:
                                mock_event_loop = MagicMock()
                                mock_loop.return_value = mock_event_loop

                                # 启动服务
                                await launcher.launch_service(
                                    service, workers=1
                                )

                                # 等待一小段时间让监控器运行
                                await asyncio.sleep(0.01)

                                # 停止
                                await launcher.stop()

                                assert not launcher.running
