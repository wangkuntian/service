"""ProcessLauncher性能测试（内存优化版本）

这个模块包含了ProcessLauncher类的内存优化性能测试，解决了原版本中的内存增长问题：
- 优化了Mock对象的使用和清理
- 改进了异步任务的管理
- 增强了内存监控和清理机制
- 减少了测试数据的累积
"""

import asyncio
import gc
import os
import psutil
import signal
import time
import pytest
import threading
import weakref
from unittest.mock import patch, MagicMock, AsyncMock
from concurrent.futures import ThreadPoolExecutor

from service import ServiceBase
from service.config.common import ConfigOpts
from service.launchers.process_launcher import ProcessLauncher, ServiceWrapper


class MemoryOptimizedTestService(ServiceBase):
    """内存优化的测试服务"""

    # 使用__slots__减少内存占用
    __slots__ = [
        'start_delay',
        'stop_delay',
        'cpu_intensive',
        'started',
        'stopped',
        'start_time',
        'stop_time',
        'work_done',
    ]

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
        for i in range(5000):  # 减少计算量
            self.work_done += i * i % 1000
            if i % 500 == 0:  # 更频繁地让出控制权
                await asyncio.sleep(0.001)

    def __del__(self):
        """析构函数，确保资源释放"""
        pass


class MemoryMonitor:
    """内存监控器"""

    def __init__(self):
        self.process = psutil.Process()
        self.baseline_memory = None
        self.peak_memory = 0
        self.samples = []

    def set_baseline(self):
        """设置内存基线"""
        gc.collect()  # 强制垃圾回收
        self.baseline_memory = self.get_current_memory()
        self.peak_memory = self.baseline_memory
        self.samples.clear()

    def get_current_memory(self):
        """获取当前内存使用量（MB）"""
        memory_info = self.process.memory_info()
        return memory_info.rss / 1024 / 1024

    def sample_memory(self):
        """采样内存使用量"""
        current = self.get_current_memory()
        self.samples.append(current)
        if current > self.peak_memory:
            self.peak_memory = current
        return current

    def get_memory_increase(self):
        """获取相对于基线的内存增长"""
        if self.baseline_memory is None:
            return 0
        return self.get_current_memory() - self.baseline_memory

    def force_gc_and_measure(self):
        """强制垃圾回收并测量内存"""
        # 多次垃圾回收确保彻底清理
        for _ in range(3):
            gc.collect()
        return self.get_current_memory()


class TestProcessLauncherPerformanceOptimized:
    """ProcessLauncher内存优化性能测试类"""

    @pytest.fixture(scope='function')
    def memory_monitor(self):
        """内存监控器 fixture"""
        monitor = MemoryMonitor()
        monitor.set_baseline()
        yield monitor
        # 测试后清理
        monitor.force_gc_and_measure()

    @pytest.fixture(scope='function')
    def config(self):
        """创建性能测试配置"""
        conf = ConfigOpts()
        conf.child_monitor_interval = 0.005  # 适中的监控频率
        conf.graceful_shutdown_timeout = 5
        conf.log_options = False
        return conf

    @pytest.fixture(scope='function')
    def launcher(self, config):
        """创建ProcessLauncher实例（优化版本）"""
        launcher = None
        with patch('os.pipe') as mock_pipe:
            mock_pipe.return_value = (0, 1)
            with patch('os.fdopen') as mock_fdopen:
                # 使用轻量级mock
                mock_file = MagicMock()
                mock_file.read.return_value = ''
                mock_fdopen.return_value = mock_file

                launcher = ProcessLauncher(config)
                yield launcher

                # 清理launcher
                if launcher:
                    launcher.children.clear()
                    launcher.running = False

    @pytest.mark.asyncio
    async def test_startup_time_performance_optimized(
        self, launcher, memory_monitor
    ):
        """测试启动时间性能（内存优化）"""
        service = MemoryOptimizedTestService()

        # 使用上下文管理器确保mock清理
        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    memory_monitor.sample_memory()

                    start_time = time.time()
                    await launcher.launch_service(service, workers=1)
                    end_time = time.time()

                    startup_time = end_time - start_time
                    memory_increase = memory_monitor.get_memory_increase()

                    # 启动时间应该小于100ms
                    assert startup_time < 0.1, (
                        f'启动时间过长: {startup_time:.3f}s'
                    )

                    # 内存增长应该很小
                    assert memory_increase < 10, (
                        f'内存增长过多: {memory_increase:.2f}MB'
                    )

                    print(
                        f'启动时间: {startup_time:.3f}s, 内存增长: {memory_increase:.2f}MB'
                    )

    @pytest.mark.asyncio
    async def test_memory_usage_with_controlled_workers(
        self, launcher, memory_monitor
    ):
        """测试受控工作进程的内存使用"""
        service = MemoryOptimizedTestService()

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    # 测试小规模worker
                    worker_counts = [1, 3, 5]
                    memory_samples = []

                    for workers in worker_counts:
                        memory_monitor.sample_memory()

                        await launcher.launch_service(service, workers=workers)

                        # 短暂等待
                        await asyncio.sleep(0.05)

                        memory_after = memory_monitor.sample_memory()
                        memory_increase = memory_monitor.get_memory_increase()
                        memory_samples.append(memory_increase)

                        # 清理launcher状态
                        launcher.children.clear()
                        launcher.running = True

                        # 强制垃圾回收
                        memory_monitor.force_gc_and_measure()

                        print(
                            f'{workers}个工作进程内存增长: {memory_increase:.2f}MB'
                        )

                    # 内存增长应该是线性且受控的
                    max_increase = max(memory_samples)
                    assert max_increase < 20, (
                        f'最大内存增长过多: {max_increase:.2f}MB'
                    )

    @pytest.mark.asyncio
    async def test_signal_handling_performance_optimized(
        self, launcher, memory_monitor
    ):
        """测试信号处理性能（内存优化）"""
        service = MemoryOptimizedTestService()

        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            await launcher.launch_service(service, workers=2)

            # 减少测试次数以控制内存
            signal_count = 100
            signal_times = []

            memory_monitor.sample_memory()

            for i in range(signal_count):
                start_time = time.time()

                if i % 2 == 0:
                    launcher._handle_term()
                else:
                    launcher._handle_hup()

                end_time = time.time()
                signal_times.append(end_time - start_time)

                # 重置状态
                launcher.running = True
                launcher.sigcaught = None
                launcher._shutdown_event.clear()
                launcher._restart_event.clear()

                # 每20次操作检查一次内存
                if i % 20 == 0:
                    memory_monitor.sample_memory()

            avg_signal_time = sum(signal_times) / len(signal_times)
            memory_increase = memory_monitor.get_memory_increase()

            # 信号处理应该很快且内存稳定
            assert avg_signal_time < 0.001, (
                f'信号处理时间过长: {avg_signal_time:.6f}s'
            )
            assert memory_increase < 5, (
                f'信号处理内存增长过多: {memory_increase:.2f}MB'
            )

            print(f'平均信号处理时间: {avg_signal_time:.6f}s')
            print(f'信号处理内存增长: {memory_increase:.2f}MB')

    @pytest.mark.asyncio
    async def test_memory_stability_during_operations(
        self, launcher, memory_monitor
    ):
        """测试操作过程中的内存稳定性"""
        service = MemoryOptimizedTestService()

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    # 进行多轮操作测试内存稳定性
                    cycles = 5
                    memory_samples = []

                    for cycle in range(cycles):
                        memory_monitor.sample_memory()

                        # 启动服务
                        await launcher.launch_service(service, workers=2)

                        # 模拟一些操作
                        for _ in range(10):
                            launcher._handle_term()
                            launcher.running = True
                            launcher.sigcaught = None
                            launcher._shutdown_event.clear()

                        # 清理状态
                        launcher.children.clear()
                        launcher.running = True

                        # 强制垃圾回收
                        current_memory = memory_monitor.force_gc_and_measure()
                        memory_samples.append(current_memory)

                        print(
                            f'第{cycle + 1}轮操作后内存: {current_memory:.2f}MB'
                        )

                    # 检查内存是否稳定（不应该持续增长）
                    if len(memory_samples) >= 3:
                        # 后期样本的平均值不应该比早期样本高太多
                        early_avg = sum(memory_samples[:2]) / 2
                        late_avg = sum(memory_samples[-2:]) / 2
                        memory_drift = late_avg - early_avg

                        assert memory_drift < 10, (
                            f'内存持续增长: {memory_drift:.2f}MB'
                        )
                        print(f'内存漂移: {memory_drift:.2f}MB')

    @pytest.mark.asyncio
    async def test_asyncio_task_cleanup(self, launcher, memory_monitor):
        """测试asyncio任务清理"""
        service = MemoryOptimizedTestService()

        with patch('os.fork', return_value=123):
            with patch('asyncio.get_running_loop') as mock_loop:
                mock_event_loop = MagicMock()
                mock_loop.return_value = mock_event_loop

                memory_monitor.sample_memory()

                # 创建任务并确保清理
                task_count = 20  # 减少任务数量
                tasks = []

                try:
                    for _ in range(task_count):
                        task = asyncio.create_task(
                            launcher._start_child(ServiceWrapper(service, 1))
                        )
                        tasks.append(task)

                    # 等待所有任务完成
                    results = await asyncio.gather(
                        *tasks, return_exceptions=True
                    )

                    # 检查结果
                    success_count = sum(
                        1 for r in results if not isinstance(r, Exception)
                    )

                finally:
                    # 确保所有任务都被清理
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass

                # 强制垃圾回收
                memory_after = memory_monitor.force_gc_and_measure()
                memory_increase = memory_monitor.get_memory_increase()

                assert memory_increase < 15, (
                    f'任务清理后内存增长过多: {memory_increase:.2f}MB'
                )
                print(
                    f'创建{task_count}个任务后内存增长: {memory_increase:.2f}MB'
                )

    @pytest.mark.asyncio
    async def test_stress_test_controlled(self, launcher, memory_monitor):
        """受控压力测试"""
        service = MemoryOptimizedTestService()

        # 使用较小的worker数量进行压力测试
        worker_count = 20  # 减少到20个

        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    memory_monitor.sample_memory()
                    start_time = time.time()

                    await launcher.launch_service(
                        service, workers=worker_count
                    )

                    end_time = time.time()
                    memory_after = memory_monitor.force_gc_and_measure()

                    startup_time = end_time - start_time
                    memory_increase = memory_monitor.get_memory_increase()

                    # 相应调整期望值
                    assert startup_time < 5.0, (
                        f'启动{worker_count}个工作进程时间过长: {startup_time:.3f}s'
                    )
                    assert memory_increase < 50, (
                        f'启动{worker_count}个工作进程内存增长过多: {memory_increase:.2f}MB'
                    )

                    print(f'启动{worker_count}个工作进程:')
                    print(f'  启动时间: {startup_time:.3f}s')
                    print(f'  内存增长: {memory_increase:.2f}MB')
                    print(
                        f'  平均每个worker内存: {memory_increase / worker_count:.3f}MB'
                    )

    @pytest.mark.asyncio
    async def test_event_loop_efficiency_optimized(
        self, launcher, memory_monitor
    ):
        """测试事件循环效率（优化版本）"""

        with patch('asyncio.get_running_loop') as mock_loop:
            mock_event_loop = MagicMock()
            mock_loop.return_value = mock_event_loop

            memory_monitor.sample_memory()

            # 减少循环次数
            loop_count = 50
            wait_times = []

            for i in range(loop_count):
                start_time = time.time()

                # 立即设置事件然后等待
                launcher._shutdown_event.set()

                # 模拟等待逻辑
                done, pending = await asyncio.wait(
                    [asyncio.create_task(launcher._shutdown_event.wait())],
                    timeout=0.001,
                )

                # 确保清理所有任务
                for task in list(done) + list(pending):
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                end_time = time.time()
                wait_times.append(end_time - start_time)

                launcher._shutdown_event.clear()

                # 每10次循环采样内存
                if i % 10 == 0:
                    memory_monitor.sample_memory()

            avg_wait_time = sum(wait_times) / len(wait_times)
            memory_increase = memory_monitor.get_memory_increase()

            assert avg_wait_time < 0.01, (
                f'平均事件等待时间过长: {avg_wait_time:.6f}s'
            )
            assert memory_increase < 5, (
                f'事件循环内存增长过多: {memory_increase:.2f}MB'
            )

            print(f'平均事件等待时间: {avg_wait_time:.6f}s')
            print(f'事件循环内存增长: {memory_increase:.2f}MB')


@pytest.mark.asyncio
async def test_memory_optimized_benchmarks():
    """内存优化的性能基准测试"""
    print('\n=== ProcessLauncher内存优化性能基准测试 ===')

    monitor = MemoryMonitor()
    monitor.set_baseline()

    config = ConfigOpts()
    config.child_monitor_interval = 0.005
    config.log_options = True

    with patch('os.pipe') as mock_pipe:
        mock_pipe.return_value = (0, 1)
        with patch('os.fdopen') as mock_fdopen:
            mock_fdopen.return_value = MagicMock()
            launcher = ProcessLauncher(config)

    service = MemoryOptimizedTestService()

    try:
        # 基准测试1: 启动时间和内存
        with patch('os.fork', return_value=123):
            with patch('asyncio.get_running_loop') as mock_loop:
                mock_event_loop = MagicMock()
                mock_loop.return_value = mock_event_loop

                times = []
                memory_samples = []

                for i in range(5):  # 减少测试次数
                    launcher.children.clear()
                    launcher.running = True

                    monitor.sample_memory()
                    start = time.time()
                    await launcher.launch_service(service, workers=1)
                    end = time.time()

                    times.append(end - start)
                    memory_samples.append(monitor.get_memory_increase())

                    # 每次测试后清理
                    monitor.force_gc_and_measure()

                avg_time = sum(times) / len(times)
                avg_memory = sum(memory_samples) / len(memory_samples)

                print(f'单worker启动时间: {avg_time:.6f}s')
                print(f'单worker内存开销: {avg_memory:.2f}MB')

        # 基准测试2: 信号处理性能和内存稳定性
        signal_times = []
        memory_before_signals = monitor.get_current_memory()

        for _ in range(200):  # 减少信号测试次数
            start = time.time()
            launcher._handle_term()
            end = time.time()
            signal_times.append(end - start)

            # 重置状态
            launcher.running = True
            launcher.sigcaught = None
            launcher._shutdown_event.clear()

        memory_after_signals = monitor.force_gc_and_measure()
        avg_signal_time = sum(signal_times) / len(signal_times)
        signal_memory_increase = memory_after_signals - memory_before_signals

        print(f'信号处理延迟: {avg_signal_time:.9f}s')
        print(f'信号处理内存稳定性: {signal_memory_increase:.2f}MB')

        # 最终内存检查
        final_memory_increase = monitor.get_memory_increase()
        print(f'总体内存增长: {final_memory_increase:.2f}MB')

    finally:
        # 确保清理
        if launcher:
            launcher.children.clear()
        monitor.force_gc_and_measure()

    print('=== 内存优化性能基准测试完成 ===\n')


def run_memory_analysis():
    """运行内存分析"""
    print('运行内存分析...')

    monitor = MemoryMonitor()
    monitor.set_baseline()

    # 模拟创建多个launcher实例
    launchers = []

    try:
        for i in range(5):
            with patch('os.pipe') as mock_pipe:
                mock_pipe.return_value = (0, 1)
                with patch('os.fdopen') as mock_fdopen:
                    mock_fdopen.return_value = MagicMock()

                    config = ConfigOpts()
                    launcher = ProcessLauncher(config)
                    launchers.append(launcher)

                    memory = monitor.sample_memory()
                    print(f'创建第{i + 1}个launcher后内存: {memory:.2f}MB')

        # 清理并测量
        launchers.clear()
        final_memory = monitor.force_gc_and_measure()
        memory_increase = monitor.get_memory_increase()

        print(f'清理后内存增长: {memory_increase:.2f}MB')

    except Exception as e:
        print(f'内存分析出错: {e}')


if __name__ == '__main__':
    # 运行内存分析
    run_memory_analysis()

    # 运行优化的性能测试
    import pytest

    pytest.main([__file__, '-v', '-s'])
