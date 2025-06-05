"""ServiceLauncher 性能测试模块

这个模块包含针对 ServiceLauncher 类的性能测试，
包括启动时间、响应时间、内存使用、并发处理等性能指标测试。
"""

import asyncio
import time
import psutil
import gc
from unittest.mock import AsyncMock, Mock, patch
import pytest

from service.config.common import ConfigOpts
from service.launchers.service_launcher import ServiceLauncher
from service import ServiceBase


class PerformanceService(ServiceBase):
    """用于性能测试的服务类"""

    def __init__(self, delay=0):
        super().__init__()
        self.delay = delay
        self.start_time = None
        self.stop_time = None

    async def start(self):
        self.start_time = time.time()
        if self.delay:
            await asyncio.sleep(self.delay)

    async def stop(self):
        self.stop_time = time.time()
        if self.delay:
            await asyncio.sleep(self.delay)


@pytest.fixture
def performance_config():
    """性能测试配置fixture"""
    conf = ConfigOpts()
    conf.service_wait_timeout = 30
    conf.graceful_shutdown_timeout = 10
    conf.health_check_interval = 0.1  # 快速健康检查用于性能测试
    return conf


@pytest.fixture
def performance_launcher(performance_config):
    """性能测试用的ServiceLauncher实例"""
    return ServiceLauncher(performance_config)


class TestServiceLauncherStartupPerformance:
    """测试ServiceLauncher启动性能"""

    @pytest.mark.performance
    def test_init_performance(self, performance_config):
        """测试初始化性能 - 应该在1ms内完成"""
        start_time = time.perf_counter()

        launcher = ServiceLauncher(performance_config)

        end_time = time.perf_counter()
        init_duration = (end_time - start_time) * 1000  # 转换为毫秒

        assert init_duration < 1.0, (
            f'初始化耗时 {init_duration:.2f}ms，超过1ms阈值'
        )
        assert launcher is not None

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_service_launch_performance(self, performance_launcher):
        """测试服务启动性能 - 单个服务应该在10ms内启动"""
        service = PerformanceService()

        start_time = time.perf_counter()

        with patch.object(
            performance_launcher.services, 'add', new_callable=AsyncMock
        ) as mock_add:
            await performance_launcher.launch_service(service)

        end_time = time.perf_counter()
        launch_duration = (end_time - start_time) * 1000

        assert launch_duration < 10.0, (
            f'服务启动耗时 {launch_duration:.2f}ms，超过10ms阈值'
        )
        mock_add.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_multiple_services_launch_performance(
        self, performance_launcher
    ):
        """测试多服务启动性能 - 10个服务应该在100ms内启动"""
        services = [PerformanceService() for _ in range(10)]

        start_time = time.perf_counter()

        with patch.object(
            performance_launcher.services, 'add', new_callable=AsyncMock
        ):
            for service in services:
                await performance_launcher.launch_service(service)

        end_time = time.perf_counter()
        total_duration = (end_time - start_time) * 1000

        assert total_duration < 100.0, (
            f'10个服务启动耗时 {total_duration:.2f}ms，超过100ms阈值'
        )


class TestServiceLauncherSignalPerformance:
    """测试ServiceLauncher信号处理性能"""

    @pytest.mark.performance
    def test_signal_handling_performance(self, performance_launcher):
        """测试信号处理性能 - 信号处理应该在1ms内完成"""
        # 测试优雅关闭信号
        start_time = time.perf_counter()

        performance_launcher._graceful_shutdown()

        end_time = time.perf_counter()
        signal_duration = (end_time - start_time) * 1000

        assert signal_duration < 1.0, (
            f'信号处理耗时 {signal_duration:.2f}ms，超过1ms阈值'
        )
        assert performance_launcher._shutdown_event.is_set()

    @pytest.mark.performance
    def test_multiple_signals_performance(self, performance_launcher):
        """测试多次信号处理性能 - 1000次信号处理应该在100ms内完成"""
        signal_count = 1000

        start_time = time.perf_counter()

        for _ in range(signal_count):
            performance_launcher._graceful_shutdown()
            performance_launcher._shutdown_event.clear()  # 重置事件

        end_time = time.perf_counter()
        total_duration = (end_time - start_time) * 1000
        avg_duration = total_duration / signal_count

        assert total_duration < 100.0, (
            f'{signal_count}次信号处理耗时 {total_duration:.2f}ms，超过100ms阈值'
        )
        assert avg_duration < 0.1, (
            f'平均信号处理耗时 {avg_duration:.3f}ms，超过0.1ms阈值'
        )


class TestServiceLauncherHealthCheckPerformance:
    """测试ServiceLauncher健康检查性能"""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_health_check_performance(self, performance_launcher):
        """测试健康检查性能 - 单次健康检查应该在5ms内完成"""
        start_time = time.perf_counter()

        await performance_launcher._perform_health_check()

        end_time = time.perf_counter()
        check_duration = (end_time - start_time) * 1000

        assert check_duration < 5.0, (
            f'健康检查耗时 {check_duration:.2f}ms，超过5ms阈值'
        )

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_health_metrics_update_performance(
        self, performance_launcher
    ):
        """测试健康指标更新性能 - 指标更新应该在1ms内完成"""
        performance_launcher._start_time = time.time()

        start_time = time.perf_counter()

        await performance_launcher._update_health_metrics()

        end_time = time.perf_counter()
        update_duration = (end_time - start_time) * 1000

        assert update_duration < 1.0, (
            f'健康指标更新耗时 {update_duration:.2f}ms，超过1ms阈值'
        )

    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_continuous_health_checks_performance(
        self, performance_launcher
    ):
        """测试连续健康检查性能 - 100次健康检查应该在500ms内完成"""
        check_count = 100
        performance_launcher._start_time = time.time()

        start_time = time.perf_counter()

        for _ in range(check_count):
            await performance_launcher._perform_health_check()
            await performance_launcher._update_health_metrics()

        end_time = time.perf_counter()
        total_duration = (end_time - start_time) * 1000
        avg_duration = total_duration / check_count

        assert total_duration < 500.0, (
            f'{check_count}次健康检查耗时 {total_duration:.2f}ms，超过500ms阈值'
        )
        assert avg_duration < 5.0, (
            f'平均健康检查耗时 {avg_duration:.2f}ms，超过5ms阈值'
        )


class TestServiceLauncherMemoryPerformance:
    """测试ServiceLauncher内存性能"""

    @pytest.mark.performance
    def test_memory_usage_baseline(self, performance_config):
        """测试基线内存使用 - ServiceLauncher实例应该占用少于10MB内存"""
        gc.collect()  # 强制垃圾回收
        process = psutil.Process()
        memory_before = process.memory_info().rss / (1024 * 1024)  # MB

        launcher = ServiceLauncher(performance_config)

        gc.collect()
        memory_after = process.memory_info().rss / (1024 * 1024)  # MB
        memory_used = memory_after - memory_before

        assert memory_used < 10.0, (
            f'ServiceLauncher占用内存 {memory_used:.2f}MB，超过10MB阈值'
        )

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_memory_leak_detection(self, performance_launcher):
        """测试内存泄漏 - 重复操作不应该导致内存持续增长"""
        gc.collect()
        process = psutil.Process()

        # 记录初始内存
        initial_memory = process.memory_info().rss / (1024 * 1024)

        # 执行多次操作
        for i in range(100):
            service = PerformanceService()
            with patch.object(
                performance_launcher.services, 'add', new_callable=AsyncMock
            ):
                await performance_launcher.launch_service(service)

            # 模拟信号处理
            performance_launcher._graceful_shutdown()
            performance_launcher._shutdown_event.clear()

            # 健康检查
            await performance_launcher._perform_health_check()
            await performance_launcher._update_health_metrics()

            # 每10次操作检查一次内存
            if i % 10 == 9:
                gc.collect()
                current_memory = process.memory_info().rss / (1024 * 1024)
                memory_growth = current_memory - initial_memory

                # 内存增长不应该超过50MB
                assert memory_growth < 50.0, (
                    f'操作{i + 1}次后内存增长 {memory_growth:.2f}MB，可能存在内存泄漏'
                )


class TestServiceLauncherConcurrencyPerformance:
    """测试ServiceLauncher并发性能"""

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_signal_handling(self, performance_launcher):
        """测试并发信号处理性能 - 并发信号处理不应该相互阻塞"""
        concurrent_count = 50

        async def signal_handler():
            performance_launcher._graceful_shutdown()
            await asyncio.sleep(0.001)  # 模拟少量延迟
            performance_launcher._shutdown_event.clear()

        start_time = time.perf_counter()

        # 并发执行信号处理
        tasks = [signal_handler() for _ in range(concurrent_count)]
        await asyncio.gather(*tasks)

        end_time = time.perf_counter()
        total_duration = (end_time - start_time) * 1000

        # 并发执行应该明显快于串行执行
        serial_estimate = concurrent_count * 1  # 如果串行执行，大约需要50ms
        assert total_duration < serial_estimate * 0.5, (
            f'并发信号处理耗时 {total_duration:.2f}ms，并发性能不佳'
        )

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_concurrent_health_checks(self, performance_launcher):
        """测试并发健康检查性能"""
        concurrent_count = 20

        async def health_check():
            await performance_launcher._perform_health_check()
            await performance_launcher._update_health_metrics()

        start_time = time.perf_counter()

        # 并发执行健康检查
        tasks = [health_check() for _ in range(concurrent_count)]
        await asyncio.gather(*tasks)

        end_time = time.perf_counter()
        total_duration = (end_time - start_time) * 1000

        assert total_duration < 200.0, (
            f'并发健康检查耗时 {total_duration:.2f}ms，超过200ms阈值'
        )

    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_high_concurrency_stress(self, performance_launcher):
        """测试高并发压力 - 模拟高负载场景"""
        concurrent_count = 100
        performance_launcher._start_time = time.time()

        async def mixed_operations():
            # 混合操作：信号处理 + 健康检查 + 服务启动
            service = PerformanceService()

            with patch.object(
                performance_launcher.services, 'add', new_callable=AsyncMock
            ):
                await performance_launcher.launch_service(service)

            performance_launcher._graceful_shutdown()
            performance_launcher._shutdown_event.clear()

            await performance_launcher._perform_health_check()
            await performance_launcher._update_health_metrics()

        start_time = time.perf_counter()

        # 高并发执行混合操作
        tasks = [mixed_operations() for _ in range(concurrent_count)]
        await asyncio.gather(*tasks)

        end_time = time.perf_counter()
        total_duration = (end_time - start_time) * 1000
        avg_duration = total_duration / concurrent_count

        assert total_duration < 2000.0, (
            f'高并发压力测试耗时 {total_duration:.2f}ms，超过2000ms阈值'
        )
        assert avg_duration < 20.0, (
            f'平均操作耗时 {avg_duration:.2f}ms，超过20ms阈值'
        )


class TestServiceLauncherScalabilityPerformance:
    """测试ServiceLauncher可扩展性性能"""

    @pytest.mark.asyncio
    @pytest.mark.performance
    @pytest.mark.slow
    async def test_large_scale_services(self, performance_launcher):
        """测试大规模服务管理性能 - 模拟管理大量服务"""
        service_count = 1000
        services = [PerformanceService() for _ in range(service_count)]

        start_time = time.perf_counter()

        with patch.object(
            performance_launcher.services, 'add', new_callable=AsyncMock
        ):
            # 批量启动服务
            for service in services:
                await performance_launcher.launch_service(service)

        end_time = time.perf_counter()
        total_duration = (end_time - start_time) * 1000
        avg_duration = total_duration / service_count

        assert total_duration < 5000.0, (
            f'启动{service_count}个服务耗时 {total_duration:.2f}ms，超过5000ms阈值'
        )
        assert avg_duration < 5.0, (
            f'平均服务启动耗时 {avg_duration:.3f}ms，超过5ms阈值'
        )

    @pytest.mark.performance
    def test_metrics_scaling_performance(self, performance_launcher):
        """测试指标更新的可扩展性性能"""
        operation_count = 10000

        start_time = time.perf_counter()

        # 大量指标更新操作
        for _ in range(operation_count):
            performance_launcher._metrics['signal_count'] += 1
            performance_launcher._metrics['error_count'] += 1

        end_time = time.perf_counter()
        total_duration = (end_time - start_time) * 1000
        ops_per_ms = operation_count / total_duration

        assert total_duration < 100.0, (
            f'{operation_count}次指标更新耗时 {total_duration:.2f}ms，超过100ms阈值'
        )
        assert ops_per_ms > 100.0, (
            f'指标更新吞吐量 {ops_per_ms:.0f} ops/ms，低于100 ops/ms阈值'
        )


class TestServiceLauncherResourceUsage:
    """测试ServiceLauncher资源使用情况"""

    @pytest.mark.performance
    def test_cpu_usage_monitoring(self, performance_config):
        """测试CPU使用情况监控"""
        process = psutil.Process()

        # 记录CPU使用前状态
        cpu_before = process.cpu_percent()

        # 执行一些操作
        launcher = ServiceLauncher(performance_config)

        # 模拟一些工作负载
        for _ in range(1000):
            launcher._handle_shutdown()
            launcher._shutdown_event.clear()

        # 记录CPU使用后状态
        time.sleep(0.1)  # 等待CPU统计更新
        cpu_after = process.cpu_percent()

        # CPU使用率不应该过高（这是一个相对测试）
        print(f'CPU使用率 - 操作前: {cpu_before}%, 操作后: {cpu_after}%')

    @pytest.mark.asyncio
    @pytest.mark.performance
    async def test_file_descriptor_usage(self, performance_launcher):
        """测试文件描述符使用情况"""
        process = psutil.Process()

        # 记录文件描述符使用前状态
        fd_before = process.num_fds() if hasattr(process, 'num_fds') else 0

        # 执行一些异步操作
        tasks = []
        for _ in range(50):
            task = asyncio.create_task(
                performance_launcher._perform_health_check()
            )
            tasks.append(task)

        await asyncio.gather(*tasks)

        # 记录文件描述符使用后状态
        fd_after = process.num_fds() if hasattr(process, 'num_fds') else 0

        if fd_before > 0 and fd_after > 0:
            fd_growth = fd_after - fd_before
            print(
                f'文件描述符使用 - 操作前: {fd_before}, 操作后: {fd_after}, 增长: {fd_growth}'
            )

            # 文件描述符不应该显著增长
            assert fd_growth < 10, (
                f'文件描述符增长 {fd_growth}，可能存在资源泄漏'
            )


@pytest.mark.performance
class TestServiceLauncherBenchmark:
    """ServiceLauncher性能基准测试"""

    @pytest.mark.asyncio
    async def test_overall_performance_benchmark(self, performance_config):
        """整体性能基准测试 - 综合性能评估"""
        print('\n=== ServiceLauncher 性能基准测试 ===')

        # 初始化性能测试
        start_time = time.perf_counter()
        launcher = ServiceLauncher(performance_config)
        init_time = (time.perf_counter() - start_time) * 1000
        print(f'初始化时间: {init_time:.2f}ms')

        # 服务启动性能测试
        start_time = time.perf_counter()
        with patch.object(launcher.services, 'add', new_callable=AsyncMock):
            for _ in range(10):
                service = PerformanceService()
                await launcher.launch_service(service)
        launch_time = (time.perf_counter() - start_time) * 1000
        print(f'10个服务启动时间: {launch_time:.2f}ms')

        # 信号处理性能测试
        start_time = time.perf_counter()
        for _ in range(1000):
            launcher._handle_shutdown()
            launcher._shutdown_event.clear()
        signal_time = (time.perf_counter() - start_time) * 1000
        print(f'1000次信号处理时间: {signal_time:.2f}ms')

        # 健康检查性能测试
        launcher._start_time = time.time()
        start_time = time.perf_counter()
        for _ in range(100):
            await launcher._perform_health_check()
            await launcher._update_health_metrics()
        health_time = (time.perf_counter() - start_time) * 1000
        print(f'100次健康检查时间: {health_time:.2f}ms')

        # 内存使用情况
        process = psutil.Process()
        memory_usage = process.memory_info().rss / (1024 * 1024)
        print(f'内存使用: {memory_usage:.2f}MB')

        print('=== 性能基准测试完成 ===\n')

        # 验证性能指标符合预期
        assert init_time < 5.0, '初始化时间过长'
        assert launch_time < 100.0, '服务启动时间过长'
        assert signal_time < 100.0, '信号处理时间过长'
        assert health_time < 1000.0, '健康检查时间过长'
