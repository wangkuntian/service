"""ServiceLauncher 单元测试模块

这个模块包含针对 ServiceLauncher 类的全面单元测试，
测试其异步功能、信号处理、健康检查等核心功能。
"""

import asyncio
import os
import signal
import time
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import pytest

from service.config.common import ConfigOpts
from service.launchers.service_launcher import ServiceLauncher
from service import ServiceBase, Services


class MockService(ServiceBase):
    """用于测试的Mock服务类"""
    
    def __init__(self):
        super().__init__()
        self.started = False
        self.stopped = False
        
    async def start(self):
        self.started = True
        
    async def stop(self):
        self.stopped = True
        
    async def reset(self):
        self.started = False
        self.stopped = False


@pytest.fixture
def config():
    """配置测试fixture"""
    conf = ConfigOpts()
    conf.service_wait_timeout = 5
    conf.graceful_shutdown_timeout = 3
    conf.health_check_interval = 1
    return conf


@pytest.fixture
def mock_service():
    """模拟服务fixture"""
    return MockService()


@pytest.fixture
def service_launcher(config):
    """ServiceLauncher实例fixture"""
    return ServiceLauncher(config)


class TestServiceLauncherInit:
    """测试ServiceLauncher初始化"""
    
    @pytest.mark.unit
    def test_init_with_config(self, config):
        """测试使用配置初始化ServiceLauncher"""
        launcher = ServiceLauncher(config)
        
        assert launcher.conf == config
        assert launcher._wait_timeout == config.service_wait_timeout
        assert launcher._shutdown_timeout == config.graceful_shutdown_timeout
        assert launcher._health_check_interval == config.health_check_interval
        assert isinstance(launcher._shutdown_event, asyncio.Event)
        assert isinstance(launcher._restart_event, asyncio.Event)
        assert launcher._restart_count == 0
        assert isinstance(launcher._metrics, dict)
    
    @pytest.mark.unit
    def test_init_metrics_structure(self, service_launcher):
        """测试初始化时指标结构的正确性"""
        expected_metrics = {
            'restart_count': 0,
            'uptime_seconds': 0,
            'last_health_check': None,
            'signal_count': 0,
            'error_count': 0,
        }
        
        assert service_launcher._metrics == expected_metrics


class TestServiceLauncherSignalHandling:
    """测试ServiceLauncher信号处理"""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_graceful_shutdown(self, service_launcher):
        """测试优雅关闭信号处理"""
        initial_signal_count = service_launcher._metrics['signal_count']
        
        service_launcher._graceful_shutdown()
        
        assert service_launcher._shutdown_event.is_set()
        assert service_launcher._metrics['signal_count'] == initial_signal_count + 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reload_service(self, service_launcher):
        """测试服务重载信号处理"""
        initial_signal_count = service_launcher._metrics['signal_count']
        
        service_launcher._async_reload_service()
        
        assert service_launcher._restart_event.is_set()
        assert service_launcher._metrics['signal_count'] == initial_signal_count + 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_fast_exit(self, service_launcher):
        """测试快速退出信号处理"""
        initial_signal_count = service_launcher._metrics['signal_count']
        
        with patch('os._exit') as mock_exit:
            service_launcher._async_fast_exit()
            
            assert service_launcher._metrics['signal_count'] == initial_signal_count + 1
            mock_exit.assert_called_once_with(1)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_timeout_exit(self, service_launcher):
        """测试超时退出信号处理"""
        with patch('os._exit') as mock_exit:
            service_launcher._async_timeout_exit()
            mock_exit.assert_called_once_with(1)


class TestServiceLauncherHealthCheck:
    """测试ServiceLauncher健康检查功能"""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_update_health_metrics(self, service_launcher):
        """测试健康指标更新"""
        start_time = time.time()
        service_launcher._start_time = start_time
        
        await service_launcher._update_health_metrics()
        
        assert service_launcher._metrics['uptime_seconds'] > 0
        assert service_launcher._metrics['last_health_check'] is not None
        assert service_launcher._metrics['last_health_check'] >= start_time
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_perform_health_check_no_services(self, service_launcher):
        """测试无服务时的健康检查"""
        initial_error_count = service_launcher._metrics['error_count']
        
        await service_launcher._perform_health_check()
        
        assert service_launcher._metrics['error_count'] == initial_error_count + 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_perform_health_check_with_services(self, service_launcher, mock_service):
        """测试有服务时的健康检查"""
        # 模拟添加服务
        with patch.object(service_launcher.services, 'services', [mock_service]):
            initial_error_count = service_launcher._metrics['error_count']
            
            await service_launcher._perform_health_check()
            
            # 有服务时不应该增加错误计数
            assert service_launcher._metrics['error_count'] == initial_error_count
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_perform_health_check_exception(self, service_launcher):
        """测试健康检查异常处理"""
        initial_error_count = service_launcher._metrics['error_count']
        
        with patch.object(service_launcher.services, 'services', side_effect=Exception("Health check error")):
            await service_launcher._perform_health_check()
            
            assert service_launcher._metrics['error_count'] == initial_error_count + 1


class TestServiceLauncherServiceManagement:
    """测试ServiceLauncher服务管理功能"""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_launch_service(self, service_launcher, mock_service):
        """测试启动服务"""
        with patch.object(service_launcher.services, 'add', new_callable=AsyncMock) as mock_add:
            await service_launcher.launch_service(mock_service)
            mock_add.assert_called_once_with(mock_service)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_launch_service_multiple_workers_error(self, service_launcher, mock_service):
        """测试启动多个工作进程时抛出错误"""
        with pytest.raises(ValueError, match="Launcher asked to start multiple workers"):
            await service_launcher.launch_service(mock_service, workers=2)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_stop(self, service_launcher):
        """测试停止服务"""
        with patch.object(service_launcher.services, 'stop', new_callable=AsyncMock) as mock_stop:
            await service_launcher.stop()
            mock_stop.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_restart(self, service_launcher):
        """测试重启服务"""
        with patch.object(service_launcher.services, 'restart', new_callable=AsyncMock) as mock_restart:
            await service_launcher.restart()
            mock_restart.assert_called_once()


class TestServiceLauncherWaitAndRun:
    """测试ServiceLauncher等待和运行功能"""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_wait_with_timeout(self, service_launcher):
        """测试带超时的等待功能"""
        # 模拟超时场景
        with patch('asyncio.wait', return_value=(set(), set())) as mock_wait:
            with patch.object(service_launcher, 'stop', new_callable=AsyncMock) as mock_stop:
                status, signo = await service_launcher._wait_for_exit_or_signal()
                
                assert status == 124  # 标准超时退出代码
                mock_stop.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_wait_shutdown_event(self, service_launcher):
        """测试关闭事件等待"""
        # 设置关闭事件
        service_launcher._shutdown_event.set()
        
        with patch.object(service_launcher, 'stop', new_callable=AsyncMock) as mock_stop:
            with patch('asyncio.wait') as mock_wait:
                # 模拟shutdown事件完成
                shutdown_task = asyncio.create_task(service_launcher._shutdown_event.wait())
                shutdown_task.set_result(None)
                mock_wait.return_value = ({shutdown_task}, set())
                
                status, signo = await service_launcher._wait_for_exit_or_signal()
                
                mock_stop.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_run_method(self, service_launcher):
        """测试运行方法"""
        with patch.object(service_launcher, 'wait', return_value=0) as mock_wait:
            result = await service_launcher.run()
            
            assert result == 0
            mock_wait.assert_called_once()


class TestServiceLauncherUtilityMethods:
    """测试ServiceLauncher工具方法"""
    
    @pytest.mark.unit
    def test_get_health_status(self, service_launcher):
        """测试获取健康状态"""
        # 设置一些测试数据
        service_launcher._start_time = time.time() - 10
        service_launcher._metrics['signal_count'] = 5
        service_launcher._metrics['error_count'] = 2
        
        status = service_launcher.get_health_status()
        
        assert 'uptime_seconds' in status
        assert 'metrics' in status
        assert status['metrics']['signal_count'] == 5
        assert status['metrics']['error_count'] == 2
        assert status['restart_count'] == 0
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_cleanup_background_tasks(self, service_launcher):
        """测试清理后台任务"""
        # 创建模拟任务
        mock_task1 = Mock()
        mock_task1.done.return_value = False
        mock_task1.cancel = Mock()
        
        mock_task2 = Mock()
        mock_task2.done.return_value = True
        
        service_launcher._cleanup_tasks = {mock_task1, mock_task2}
        
        with patch('asyncio.gather', new_callable=AsyncMock) as mock_gather:
            await service_launcher._cleanup_background_tasks()
            
            mock_task1.cancel.assert_called_once()
            # 已完成的任务不应该被取消
            assert not hasattr(mock_task2, 'cancel') or not mock_task2.cancel.called
    
    @pytest.mark.unit
    def test_add_cleanup_task(self, service_launcher):
        """测试添加清理任务"""
        mock_task = Mock()
        initial_count = len(service_launcher._cleanup_tasks)
        
        service_launcher.add_cleanup_task(mock_task)
        
        assert len(service_launcher._cleanup_tasks) == initial_count + 1
        assert mock_task in service_launcher._cleanup_tasks


class TestServiceLauncherEdgeCases:
    """测试ServiceLauncher边缘情况"""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_signal_count_update_thread_safety(self, service_launcher):
        """测试信号计数更新的线程安全性"""
        initial_count = service_launcher._metrics['signal_count']
        
        await service_launcher._update_signal_count()
        
        assert service_launcher._metrics['signal_count'] == initial_count + 1
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_schedule_timeout_exit(self, service_launcher):
        """测试计划超时退出"""
        service_launcher._shutdown_timeout = 0.1
        
        with patch.object(service_launcher, '_async_timeout_exit') as mock_timeout_exit:
            await service_launcher._schedule_timeout_exit()
            mock_timeout_exit.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_schedule_timeout_exit_cancelled(self, service_launcher):
        """测试计划超时退出被取消"""
        service_launcher._shutdown_timeout = 10  # 长时间等待
        
        task = asyncio.create_task(service_launcher._schedule_timeout_exit())
        
        # 立即取消任务
        task.cancel()
        
        with pytest.raises(asyncio.CancelledError):
            await task


class TestServiceLauncherIntegration:
    """测试ServiceLauncher集成场景"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_lifecycle(self, service_launcher, mock_service):
        """测试完整的服务生命周期"""
        # 启动服务
        await service_launcher.launch_service(mock_service)
        
        # 模拟运行一段时间
        service_launcher._start_time = time.time()
        await service_launcher._update_health_metrics()
        
        # 检查健康状态
        await service_launcher._perform_health_check()
        
        # 停止服务
        await service_launcher.stop()
        
        # 验证指标
        health_status = service_launcher.get_health_status()
        assert health_status['uptime_seconds'] > 0
        assert health_status['metrics']['last_health_check'] is not None
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_health_monitor_task(self, service_launcher):
        """测试健康监控任务"""
        # 启动健康监控
        service_launcher._start_time = time.time()
        service_launcher._health_check_interval = 0.1  # 快速测试
        
        monitor_task = asyncio.create_task(service_launcher._health_monitor())
        
        # 运行一小段时间
        await asyncio.sleep(0.3)
        
        # 停止监控
        monitor_task.cancel()
        
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        # 验证健康检查被执行
        assert service_launcher._metrics['last_health_check'] is not None 