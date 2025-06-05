"""pytest 配置文件

这个文件包含测试运行的全局配置和共享的fixtures。
"""

import asyncio
import sys
import os
import pytest
from typing import Generator

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def pytest_configure(config):
    """pytest配置函数"""
    # 注册自定义标记
    config.addinivalue_line('markers', 'unit: 单元测试标记')
    config.addinivalue_line('markers', 'integration: 集成测试标记')
    config.addinivalue_line('markers', 'performance: 性能测试标记')
    config.addinivalue_line('markers', 'slow: 慢速测试标记（运行时间较长）')


def pytest_collection_modifyitems(config, items):
    """修改测试收集项目"""
    # 为没有标记的测试添加unit标记
    for item in items:
        if not any(item.iter_markers()):
            item.add_marker(pytest.mark.unit)


@pytest.fixture(scope='session')
def event_loop():
    """
    创建事件循环fixture
    确保所有异步测试使用同一个事件循环
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()

    yield loop

    # 清理待处理的任务
    pending = asyncio.all_tasks(loop)
    if pending:
        loop.run_until_complete(
            asyncio.gather(*pending, return_exceptions=True)
        )

    if not loop.is_closed():
        loop.close()


@pytest.fixture(autouse=True)
def setup_test_environment():
    """
    自动使用的测试环境设置fixture
    在每个测试前后进行环境清理
    """
    # 测试前设置
    original_env = os.environ.copy()

    yield

    # 测试后清理
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def temp_dir(tmp_path):
    """
    提供临时目录的fixture
    """
    return tmp_path


# 性能测试相关的fixtures
@pytest.fixture(scope='session')
def performance_threshold():
    """性能测试阈值配置"""
    return {
        'init_time_ms': 5.0,
        'service_launch_time_ms': 10.0,
        'signal_handling_time_ms': 1.0,
        'health_check_time_ms': 5.0,
        'memory_usage_mb': 50.0,
    }


def pytest_runtest_setup(item):
    """测试运行前的设置"""
    # 检查是否为性能测试，如果是，输出性能测试信息
    if 'performance' in [mark.name for mark in item.iter_markers()]:
        print(f'\n🚀 运行性能测试: {item.name}')


def pytest_runtest_teardown(item):
    """测试运行后的清理"""
    # 强制垃圾回收，确保内存测试的准确性
    import gc

    gc.collect()


# pytest报告钩子
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """终端摘要报告"""
    if hasattr(terminalreporter, 'stats'):
        # 获取各类测试统计
        passed = len(terminalreporter.stats.get('passed', []))
        failed = len(terminalreporter.stats.get('failed', []))
        skipped = len(terminalreporter.stats.get('skipped', []))

        print(f'\n📊 测试统计:')
        print(f'   通过: {passed}')
        print(f'   失败: {failed}')
        print(f'   跳过: {skipped}')

        # 如果有性能测试，显示额外信息
        performance_tests = [
            test
            for test in terminalreporter.stats.get('passed', [])
            if 'performance' in str(test.keywords)
        ]

        if performance_tests:
            print(f'   性能测试: {len(performance_tests)}')


# 异步测试超时配置
@pytest.fixture(autouse=True)
def async_test_timeout():
    """为异步测试设置超时"""
    return 30  # 30秒超时


# 错误处理fixtures
@pytest.fixture
def capture_logs():
    """捕获日志的fixture"""
    import logging
    import io

    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger()
    logger.addHandler(handler)

    yield log_capture

    logger.removeHandler(handler)


# Mock相关的fixtures
@pytest.fixture
def mock_asyncio_sleep():
    """Mock asyncio.sleep以加速测试"""
    import asyncio
    from unittest.mock import patch, AsyncMock

    async def fast_sleep(delay):
        # 快速睡眠，仅等待很短时间
        await asyncio.sleep(0.001)

    with patch('asyncio.sleep', side_effect=fast_sleep):
        yield


# 数据验证fixtures
@pytest.fixture
def assert_performance(performance_threshold):
    """性能断言helper"""

    def _assert_performance(
        metric_name: str, actual_value: float, threshold_key: str = None
    ):
        threshold_key = threshold_key or f'{metric_name}_ms'
        threshold = performance_threshold.get(threshold_key, float('inf'))
        assert actual_value < threshold, (
            f'{metric_name} 耗时 {actual_value:.2f}ms，超过 {threshold}ms 阈值'
        )

    return _assert_performance
