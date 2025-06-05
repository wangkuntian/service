"""ProcessLauncher性能测试

这个模块包含了ProcessLauncher类的性能测试，包括：
- 启动时间测试
- 并发处理能力测试
- 内存使用量测试
- 响应时间测试
- 负载测试
"""

import asyncio
import gc
import os
import psutil
import signal
import time
import pytest
import threading
from unittest.mock import patch, MagicMock, AsyncMock
from concurrent.futures import ThreadPoolExecutor

from service import ServiceBase
from service.config.common import ConfigOpts
from service.launchers.process_launcher import ProcessLauncher, ServiceWrapper


class PerformanceTestService(ServiceBase):
    """性能测试用服务"""

    def __init__(self, start_delay=0, stop_delay=0, cpu_intensive=False):
        self.start_delay = start_delay
        self.stop_delay = stop_delay
        self.cpu_intensive = cpu_intensive
        self.started = False
        self.stopped = False
        self.start_time = None
        self.stop_time = None
        self.work_done = 0

    async def start(self):
        """启动服务"""
        self.start_time = time.time()
        if self.start_delay > 0:
            await asyncio.sleep(self.start_delay)

        self.started = True

        # 如果是CPU密集型，做一些计算
        if self.cpu_intensive:
            await self._cpu_intensive_work()

    async def stop(self):
        """停止服务"""
        if self.stop_delay > 0:
            await asyncio.sleep(self.stop_delay)

        self.stopped = True
        self.stop_time = time.time()

    async def wait(self):
        """等待服务完成"""
        while self.started and not self.stopped:
            await asyncio.sleep(0.001)

    async def reset(self):
        """重置服务"""
        self.started = False
        self.stopped = False
        self.start_time = None
        self.stop_time = None
        self.work_done = 0

    async def _cpu_intensive_work(self):
        """CPU密集型工作"""
        for i in range(10000):
            self.work_done += i * i % 1000
            if i % 1000 == 0:
                await asyncio.sleep(0.001)  # 让出控制权


class TestProcessLauncherPerformance:
    """ProcessLauncher性能测试类"""

    @pytest.fixture
    def config(self):
        """创建性能测试配置"""
        conf = ConfigOpts()
        conf.child_monitor_interval = 0.001  # 更频繁的监控
        conf.graceful_shutdown_timeout = 10
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

    def get_memory_usage(self):
        """获取当前内存使用量（MB）"""
        process = psutil.Process()
        memory_info = process.memory_info()
        return memory_info.rss / 1024 / 1024  # 转换为MB

    def get_cpu_percent(self):
        """获取CPU使用率"""
        return psutil.cpu_percent(interval=0.1)

    @pytest.mark.asyncio
    async def test_startup_time_performance(self, launcher):
        """测试启动时间性能"""
        service = PerformanceTestService()

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    start_time = time.time()
                    await launcher.launch_service(service, workers=1)
                    end_time = time.time()

                    startup_time = end_time - start_time

                    # 启动时间应该小于100ms
                    assert startup_time < 0.1, (
                        f'启动时间过长: {startup_time:.3f}s'
                    )
                    print(f'启动时间: {startup_time:.3f}s')

    @pytest.mark.asyncio
    async def test_multiple_workers_startup_time(self, launcher):
        """测试多个工作进程启动时间"""
        service = PerformanceTestService()
        worker_counts = [1, 5, 10, 20]

        for workers in worker_counts:
            with patch('os.fork', return_value=lambda: 123 + workers):
                with patch('os.waitpid', return_value=(0, 0)):
                    with patch('asyncio.get_running_loop') as mock_loop:
                        mock_event_loop = MagicMock()
                        mock_loop.return_value = mock_event_loop

                        # 清理之前的状态
                        launcher.children.clear()
                        launcher.running = True

                        start_time = time.time()
                        await launcher.launch_service(service, workers=workers)
                        end_time = time.time()

                        startup_time = end_time - start_time

                        # 启动时间应该随worker数量线性增长，但不应该超过合理范围
                        max_expected_time = (
                            0.05 * workers
                        )  # 每个worker最多50ms
                        assert startup_time < max_expected_time, (
                            f'{workers}个工作进程启动时间过长: {startup_time:.3f}s'
                        )

                        print(
                            f'{workers}个工作进程启动时间: {startup_time:.3f}s'
                        )

    @pytest.mark.asyncio
    async def test_memory_usage_with_multiple_workers(self, launcher):
        """测试多工作进程内存使用"""
        service = PerformanceTestService()
        initial_memory = self.get_memory_usage()

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    await launcher.launch_service(service, workers=10)

                    # 等待一段时间让内存稳定
                    await asyncio.sleep(0.1)

                    memory_after_launch = self.get_memory_usage()
                    memory_increase = memory_after_launch - initial_memory

                    # 内存增长应该在合理范围内（小于100MB）
                    assert memory_increase < 100, (
                        f'内存使用量增长过多: {memory_increase:.2f}MB'
                    )

                    print(
                        f'启动10个工作进程后内存增长: {memory_increase:.2f}MB'
                    )

    @pytest.mark.asyncio
    async def test_signal_handling_performance(self, launcher):
        """测试信号处理性能"""
        service = PerformanceTestService()

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    await launcher.launch_service(service, workers=5)

                    # 测试信号处理时间
                    signal_times = []

                    for _ in range(10):
                        start_time = time.time()
                        launcher._handle_term()
                        end_time = time.time()

                        signal_time = end_time - start_time
                        signal_times.append(signal_time)

                        # 重置状态
                        launcher.running = True
                        launcher.sigcaught = None
                        launcher._shutdown_event.clear()

                    avg_signal_time = sum(signal_times) / len(signal_times)
                    max_signal_time = max(signal_times)

                    # 信号处理应该非常快
                    assert avg_signal_time < 0.001, (
                        f'平均信号处理时间过长: {avg_signal_time:.6f}s'
                    )
                    assert max_signal_time < 0.005, (
                        f'最大信号处理时间过长: {max_signal_time:.6f}s'
                    )

                    print(f'平均信号处理时间: {avg_signal_time:.6f}s')
                    print(f'最大信号处理时间: {max_signal_time:.6f}s')

    @pytest.mark.asyncio
    async def test_child_monitoring_performance(self, launcher):
        """测试子进程监控性能"""
        service = PerformanceTestService()

        with patch('os.fork', return_value=123):
            with patch('asyncio.get_running_loop') as mock_loop:
                mock_event_loop = MagicMock()
                mock_loop.return_value = mock_event_loop

                # 添加多个模拟的子进程
                for i in range(20):
                    wrap = ServiceWrapper(service, 1)
                    pid = 1000 + i
                    wrap.children.add(pid)
                    launcher.children[pid] = wrap

                monitor_times = []

                # 测试监控循环性能
                for _ in range(100):
                    with patch(
                        'os.waitpid', return_value=(0, 0)
                    ):  # 无子进程退出
                        start_time = time.time()

                        # 模拟一次监控循环
                        launcher._wait_child()

                        end_time = time.time()
                        monitor_time = end_time - start_time
                        monitor_times.append(monitor_time)

                avg_monitor_time = sum(monitor_times) / len(monitor_times)
                max_monitor_time = max(monitor_times)

                # 监控应该很快
                assert avg_monitor_time < 0.001, (
                    f'平均监控时间过长: {avg_monitor_time:.6f}s'
                )
                assert max_monitor_time < 0.005, (
                    f'最大监控时间过长: {max_monitor_time:.6f}s'
                )

                print(f'平均监控时间: {avg_monitor_time:.6f}s')
                print(f'最大监控时间: {max_monitor_time:.6f}s')

    @pytest.mark.asyncio
    async def test_concurrent_stop_start_performance(self, launcher):
        """测试并发停止/启动性能"""
        service = PerformanceTestService(start_delay=0.01, stop_delay=0.01)

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('os.kill') as mock_kill:
                    with patch('asyncio.get_running_loop') as mock_loop:
                        mock_event_loop = MagicMock()
                        mock_loop.return_value = mock_event_loop

                        # 启动服务
                        await launcher.launch_service(service, workers=5)

                        # 测试并发停止性能
                        start_time = time.time()
                        await launcher.stop()
                        stop_time = time.time()

                        stop_duration = stop_time - start_time

                        # 停止时间应该在合理范围内
                        assert stop_duration < 1.0, (
                            f'停止时间过长: {stop_duration:.3f}s'
                        )

                        print(f'停止5个工作进程时间: {stop_duration:.3f}s')

    @pytest.mark.asyncio
    async def test_restart_performance(self, launcher):
        """测试重启性能"""
        service = PerformanceTestService()

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('os.kill') as mock_kill:
                    with patch('asyncio.get_running_loop') as mock_loop:
                        mock_event_loop = MagicMock()
                        mock_loop.return_value = mock_event_loop

                        # 启动服务
                        await launcher.launch_service(service, workers=3)

                        # 添加模拟的子进程
                        wrap = ServiceWrapper(service, 3)
                        for i in range(3):
                            pid = 1000 + i
                            wrap.children.add(pid)
                            launcher.children[pid] = wrap

                        # 测试重启性能
                        restart_times = []

                        for _ in range(5):
                            start_time = time.time()
                            await launcher._restart_services()
                            end_time = time.time()

                            restart_time = end_time - start_time
                            restart_times.append(restart_time)

                        avg_restart_time = sum(restart_times) / len(
                            restart_times
                        )
                        max_restart_time = max(restart_times)

                        # 重启应该很快
                        assert avg_restart_time < 0.1, (
                            f'平均重启时间过长: {avg_restart_time:.3f}s'
                        )
                        assert max_restart_time < 0.2, (
                            f'最大重启时间过长: {max_restart_time:.3f}s'
                        )

                        print(f'平均重启时间: {avg_restart_time:.3f}s')
                        print(f'最大重启时间: {max_restart_time:.3f}s')

    @pytest.mark.asyncio
    async def test_fork_rate_limiting_performance(self, launcher):
        """测试fork速率限制性能"""
        service = PerformanceTestService()

        with patch('os.fork', return_value=123):
            with patch('time.time') as mock_time:
                # 模拟时间快速推进
                current_time = 1000.0
                mock_time.return_value = current_time

                wrap = ServiceWrapper(service, 5)

                # 填满forktimes触发速率限制
                for i in range(6):
                    wrap.forktimes.append(current_time - i * 0.1)

                rate_limit_times = []

                # 测试速率限制下的启动时间
                for _ in range(10):
                    start_time = time.time()
                    pid = await launcher._start_child(wrap)
                    end_time = time.time()

                    rate_limit_time = end_time - start_time
                    rate_limit_times.append(rate_limit_time)

                    assert pid == 123

                avg_rate_limit_time = sum(rate_limit_times) / len(
                    rate_limit_times
                )

                # 即使有速率限制，时间也应该合理
                assert avg_rate_limit_time < 0.1, (
                    f'速率限制下平均启动时间过长: {avg_rate_limit_time:.3f}s'
                )

                print(f'速率限制下平均启动时间: {avg_rate_limit_time:.3f}s')

    @pytest.mark.asyncio
    async def test_memory_leak_during_restart_cycles(self, launcher):
        """测试重启循环中的内存泄漏"""
        service = PerformanceTestService()
        initial_memory = self.get_memory_usage()

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('os.kill') as mock_kill:
                    with patch('asyncio.get_running_loop') as mock_loop:
                        mock_event_loop = MagicMock()
                        mock_loop.return_value = mock_event_loop

                        memory_samples = []

                        # 进行多次重启循环
                        for cycle in range(10):
                            await launcher.launch_service(service, workers=2)

                            # 添加模拟的子进程
                            wrap = ServiceWrapper(service, 2)
                            for i in range(2):
                                pid = 2000 + cycle * 2 + i
                                wrap.children.add(pid)
                                launcher.children[pid] = wrap

                            await launcher._restart_services()

                            # 强制垃圾回收
                            gc.collect()

                            current_memory = self.get_memory_usage()
                            memory_samples.append(current_memory)

                            # 清理状态
                            launcher.children.clear()
                            launcher.running = True

                        final_memory = self.get_memory_usage()
                        memory_increase = final_memory - initial_memory

                        # 内存增长应该很小（考虑到测试框架开销）
                        assert memory_increase < 50, (
                            f'重启循环后内存泄漏: {memory_increase:.2f}MB'
                        )

                        print(
                            f'10次重启循环后内存增长: {memory_increase:.2f}MB'
                        )
                        print(f'内存样本: {memory_samples}')

    @pytest.mark.asyncio
    async def test_high_frequency_signal_handling(self, launcher):
        """测试高频信号处理"""
        service = PerformanceTestService()

        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            await launcher.launch_service(service, workers=1)

            # 高频信号处理测试
            signal_count = 1000
            start_time = time.time()

            for i in range(signal_count):
                if i % 2 == 0:
                    launcher._handle_term()
                else:
                    launcher._handle_hup()

                # 重置状态以便下次测试
                launcher.running = True
                launcher.sigcaught = None
                launcher._shutdown_event.clear()
                launcher._restart_event.clear()

            end_time = time.time()
            total_time = end_time - start_time

            avg_signal_time = total_time / signal_count

            # 高频信号处理应该很快
            assert avg_signal_time < 0.001, (
                f'高频信号处理平均时间过长: {avg_signal_time:.6f}s'
            )

            print(f'处理{signal_count}个信号总时间: {total_time:.3f}s')
            print(f'平均每个信号处理时间: {avg_signal_time:.6f}s')

    @pytest.mark.asyncio
    async def test_asyncio_task_performance(self, launcher):
        """测试asyncio任务性能"""
        service = PerformanceTestService()

        with patch('os.fork', return_value=123):
            with patch('asyncio.get_running_loop') as mock_loop:
                mock_event_loop = MagicMock()
                mock_loop.return_value = mock_event_loop

                # 测试并发任务创建性能
                task_count = 100
                start_time = time.time()

                tasks = []
                for _ in range(task_count):
                    task = asyncio.create_task(
                        launcher._start_child(ServiceWrapper(service, 1))
                    )
                    tasks.append(task)

                # 等待所有任务完成
                await asyncio.gather(*tasks, return_exceptions=True)

                end_time = time.time()
                total_time = end_time - start_time

                avg_task_time = total_time / task_count

                # 任务创建和执行应该很快
                assert avg_task_time < 0.01, (
                    f'平均任务时间过长: {avg_task_time:.6f}s'
                )

                print(f'创建并执行{task_count}个任务总时间: {total_time:.3f}s')
                print(f'平均每个任务时间: {avg_task_time:.6f}s')

    @pytest.mark.asyncio
    async def test_stress_test_many_workers(self, launcher):
        """压力测试：大量工作进程"""
        service = PerformanceTestService()
        worker_count = 100

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    start_time = time.time()
                    initial_memory = self.get_memory_usage()

                    await launcher.launch_service(
                        service, workers=worker_count
                    )

                    end_time = time.time()
                    final_memory = self.get_memory_usage()

                    startup_time = end_time - start_time
                    memory_increase = final_memory - initial_memory

                    # 即使有大量worker，启动时间也应该合理
                    assert startup_time < 10.0, (
                        f'启动{worker_count}个工作进程时间过长: {startup_time:.3f}s'
                    )

                    # 内存使用应该线性增长但不过多
                    assert memory_increase < 500, (
                        f'启动{worker_count}个工作进程内存增长过多: {memory_increase:.2f}MB'
                    )

                    print(f'启动{worker_count}个工作进程:')
                    print(f'  启动时间: {startup_time:.3f}s')
                    print(f'  内存增长: {memory_increase:.2f}MB')
                    print(
                        f'  平均每个worker时间: {startup_time / worker_count:.6f}s'
                    )

    @pytest.mark.asyncio
    async def test_event_loop_efficiency(self, launcher):
        """测试事件循环效率"""
        service = PerformanceTestService()

        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            # 测试事件等待效率
            wait_times = []

            for _ in range(100):
                start_time = time.time()

                # 立即设置事件然后等待
                launcher._shutdown_event.set()

                # 模拟等待逻辑
                done, pending = await asyncio.wait(
                    [asyncio.create_task(launcher._shutdown_event.wait())],
                    timeout=0.001,
                )

                # 清理
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                end_time = time.time()
                wait_time = end_time - start_time
                wait_times.append(wait_time)

                launcher._shutdown_event.clear()

            avg_wait_time = sum(wait_times) / len(wait_times)
            max_wait_time = max(wait_times)

            # 事件等待应该很快
            assert avg_wait_time < 0.005, (
                f'平均事件等待时间过长: {avg_wait_time:.6f}s'
            )
            assert max_wait_time < 0.01, (
                f'最大事件等待时间过长: {max_wait_time:.6f}s'
            )

            print(f'平均事件等待时间: {avg_wait_time:.6f}s')
            print(f'最大事件等待时间: {max_wait_time:.6f}s')


@pytest.mark.asyncio
async def test_performance_benchmarks():
    """性能基准测试"""
    print('\n=== ProcessLauncher性能基准测试 ===')

    config = ConfigOpts()
    config.child_monitor_interval = 0.001
    config.log_options = False

    with patch('os.pipe') as mock_pipe:
        mock_pipe.return_value = (0, 1)
        with patch('os.fdopen') as mock_fdopen:
            mock_fdopen.return_value = MagicMock()
            launcher = ProcessLauncher(config)

    service = PerformanceTestService()

    # 基准测试1: 单个worker启动时间
    with patch('os.fork', return_value=123):
        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            times = []
            for _ in range(10):
                launcher.children.clear()
                launcher.running = True

                start = time.time()
                await launcher.launch_service(service, workers=1)
                end = time.time()

                times.append(end - start)

            avg_time = sum(times) / len(times)
            print(
                f'单worker启动时间: {avg_time:.6f}s (±{max(times) - min(times):.6f}s)'
            )

    # 基准测试2: 信号处理延迟
    signal_times = []
    for _ in range(1000):
        start = time.time()
        launcher._handle_term()
        end = time.time()
        signal_times.append(end - start)

        # 重置状态
        launcher.running = True
        launcher.sigcaught = None
        launcher._shutdown_event.clear()

    avg_signal_time = sum(signal_times) / len(signal_times)
    print(f'信号处理延迟: {avg_signal_time:.9f}s')

    # 基准测试3: 内存使用效率
    process = psutil.Process()
    memory_before = process.memory_info().rss / 1024 / 1024

    # 模拟工作负载
    launchers = []
    for _ in range(10):
        with patch('os.pipe') as mock_pipe:
            mock_pipe.return_value = (0, 1)
            with patch('os.fdopen') as mock_fdopen:
                mock_fdopen.return_value = MagicMock()
                launcher_instance = ProcessLauncher(config)
                launchers.append(launcher_instance)

    memory_after = process.memory_info().rss / 1024 / 1024
    memory_per_launcher = (memory_after - memory_before) / 10

    print(f'每个launcher内存开销: {memory_per_launcher:.2f}MB')

    print('=== 性能基准测试完成 ===\n')


if __name__ == '__main__':
    # 可以直接运行性能测试
    import pytest

    pytest.main([__file__, '-v', '-s'])
