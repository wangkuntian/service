"""性能测试内存优化技巧和修复建议

这个文件展示了原性能测试中的内存问题和相应的修复方案。
"""

import asyncio
import gc
import pytest
from unittest.mock import patch, MagicMock
from contextlib import contextmanager

from service.config.common import ConfigOpts
from service.launchers.process_launcher import ProcessLauncher


# ===== 问题示例 =====


class ProblematicTest:
    """有内存问题的测试示例"""

    def test_memory_leak_example(self):
        """内存泄漏示例"""
        # 问题1: 大量Mock对象不清理
        mocks = []
        for i in range(1000):  # 创建过多Mock
            mock = MagicMock()
            mock.configure_mock(
                **{f'attr_{j}': j for j in range(50)}
            )  # 复杂配置
            mocks.append(mock)

        # 问题2: 没有及时清理
        # mocks.clear()  # 这行被注释了，导致内存泄漏

        # 问题3: 大量异步任务不清理
        async def create_tasks():
            tasks = []
            for i in range(100):
                task = asyncio.create_task(asyncio.sleep(0.001))
                tasks.append(task)
            # 没有等待或取消任务
            return tasks

        asyncio.run(create_tasks())


# ===== 修复方案 =====


class OptimizedTest:
    """内存优化的测试示例"""

    @contextmanager
    def managed_mocks(self, count=10):
        """Mock对象上下文管理器"""
        mocks = []
        try:
            for i in range(count):
                mock = MagicMock()
                # 只配置必要的属性
                mock.return_value = i
                mocks.append(mock)
            yield mocks
        finally:
            # 确保清理
            mocks.clear()
            gc.collect()

    def test_memory_optimized_example(self):
        """内存优化示例"""
        # 修复1: 使用上下文管理器管理Mock
        with self.managed_mocks(count=10) as mocks:  # 减少数量
            # 使用Mock对象
            for mock in mocks:
                mock()

        # 修复2: 正确清理异步任务
        async def create_and_cleanup_tasks():
            tasks = []
            try:
                for i in range(10):  # 减少任务数量
                    task = asyncio.create_task(asyncio.sleep(0.001))
                    tasks.append(task)

                # 等待所有任务完成
                await asyncio.gather(*tasks, return_exceptions=True)

            finally:
                # 确保所有任务都被清理
                for task in tasks:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

        asyncio.run(create_and_cleanup_tasks())


# ===== 内存监控装饰器 =====


def monitor_memory(threshold_mb=10):
    """内存监控装饰器"""

    def decorator(func):
        import psutil

        def wrapper(*args, **kwargs):
            process = psutil.Process()

            # 测试前内存
            gc.collect()
            memory_before = process.memory_info().rss / 1024 / 1024

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                # 测试后内存
                gc.collect()
                memory_after = process.memory_info().rss / 1024 / 1024
                memory_increase = memory_after - memory_before

                print(
                    f'内存使用: {memory_before:.2f}MB -> {memory_after:.2f}MB '
                    f'(+{memory_increase:.2f}MB)'
                )

                if memory_increase > threshold_mb:
                    print(
                        f'⚠️ 内存增长超过阈值: {memory_increase:.2f}MB > {threshold_mb}MB'
                    )

        return wrapper

    return decorator


# ===== 优化的ProcessLauncher测试 =====


class MemoryEfficientProcessLauncherTest:
    """内存高效的ProcessLauncher测试"""

    @pytest.fixture(scope='function')
    def optimized_launcher(self):
        """优化的launcher fixture"""
        launcher = None
        try:
            with patch('os.pipe', return_value=(0, 1)):
                with patch('os.fdopen') as mock_fdopen:
                    # 使用轻量级mock
                    mock_file = MagicMock()
                    mock_file.read.return_value = ''
                    mock_fdopen.return_value = mock_file

                    config = ConfigOpts()
                    config.child_monitor_interval = 0.01  # 降低监控频率
                    config.log_options = False

                    launcher = ProcessLauncher(config)
                    yield launcher
        finally:
            # 确保清理
            if launcher:
                launcher.children.clear()
                launcher.running = False
            gc.collect()

    @monitor_memory(threshold_mb=5)
    @pytest.mark.asyncio
    async def test_startup_performance_optimized(self, optimized_launcher):
        """优化的启动性能测试"""

        # 使用__slots__优化的服务类
        class OptimizedService:
            __slots__ = ['started', 'stopped']

            def __init__(self):
                self.started = False
                self.stopped = False

            async def start(self):
                self.started = True

            async def stop(self):
                self.stopped = True

            async def wait(self):
                while self.started and not self.stopped:
                    await asyncio.sleep(0.001)

            async def reset(self):
                self.started = False
                self.stopped = False

        service = OptimizedService()

        # 使用上下文管理器确保清理
        with patch('os.fork', return_value=123):
            with patch('os.waitpid', return_value=(0, 0)):
                with patch('asyncio.get_running_loop') as mock_loop:
                    mock_event_loop = MagicMock()
                    mock_loop.return_value = mock_event_loop

                    # 执行测试
                    await optimized_launcher.launch_service(service, workers=2)

                    # 验证结果
                    assert service.started

    @monitor_memory(threshold_mb=3)
    def test_signal_handling_optimized(self, optimized_launcher):
        """优化的信号处理测试"""
        # 减少测试次数
        signal_count = 50  # 从1000减少到50

        for i in range(signal_count):
            optimized_launcher._handle_term()

            # 重置状态
            optimized_launcher.running = True
            optimized_launcher.sigcaught = None
            optimized_launcher._shutdown_event.clear()

            # 每10次清理一次
            if i % 10 == 0:
                gc.collect()


# ===== 内存使用最佳实践 =====


class MemoryBestPractices:
    """内存使用最佳实践"""

    @staticmethod
    def use_context_managers():
        """使用上下文管理器"""

        @contextmanager
        def launcher_context():
            launcher = None
            try:
                with patch('os.pipe', return_value=(0, 1)):
                    with patch('os.fdopen', return_value=MagicMock()):
                        launcher = ProcessLauncher(ConfigOpts())
                        yield launcher
            finally:
                if launcher:
                    launcher.children.clear()
                gc.collect()

    @staticmethod
    def use_slots_classes():
        """使用__slots__类"""

        class SlottedService:
            __slots__ = ['name', 'status', 'data']

            def __init__(self, name):
                self.name = name
                self.status = 'stopped'
                self.data = []

    @staticmethod
    def batch_gc_collection():
        """批量垃圾回收"""

        def process_items(items):
            for i, item in enumerate(items):
                # 处理item
                process_item(item)

                # 每100个item进行一次垃圾回收
                if i % 100 == 0:
                    gc.collect()

    @staticmethod
    def use_weak_references():
        """使用弱引用"""
        import weakref

        class ObjectManager:
            def __init__(self):
                self._objects = weakref.WeakSet()

            def add_object(self, obj):
                self._objects.add(obj)

            def cleanup(self):
                # 弱引用会自动清理已删除的对象
                pass


# ===== 修复建议总结 =====

MEMORY_OPTIMIZATION_TIPS = """
内存优化建议总结:

1. **减少Mock对象数量和复杂性**
   - 使用简单的Mock配置
   - 及时清理Mock对象
   - 使用上下文管理器管理Mock生命周期

2. **优化异步任务管理**
   - 确保所有任务都被等待或取消
   - 使用try/finally确保任务清理
   - 避免创建过多并发任务

3. **使用内存高效的数据结构**
   - 使用__slots__减少对象内存占用
   - 避免不必要的属性存储
   - 使用生成器而不是列表

4. **定期垃圾回收**
   - 在测试循环中定期调用gc.collect()
   - 在fixture的teardown中强制垃圾回收
   - 监控内存使用趋势

5. **减少测试规模**
   - 将大规模测试拆分为小测试
   - 使用合理的测试数据量
   - 避免不必要的重复操作

6. **使用内存监控**
   - 添加内存监控装饰器
   - 设置内存增长阈值
   - 及时发现内存泄漏

7. **正确清理资源**
   - 使用上下文管理器
   - 在fixture中确保资源清理
   - 使用弱引用避免循环引用
"""


def process_item(item):
    """处理单个项目的示例函数"""
    pass


if __name__ == '__main__':
    print(MEMORY_OPTIMIZATION_TIPS)
