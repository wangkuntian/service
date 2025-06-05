#!/usr/bin/env python3
"""内存问题诊断工具

这个工具用于诊断和分析ProcessLauncher性能测试中的内存增长问题，提供详细的内存使用分析和优化建议。
"""

import gc
import os
import psutil
import sys
import time
import tracemalloc
from typing import Dict, List, Tuple
import weakref
from unittest.mock import patch, MagicMock

from service.config.common import ConfigOpts
from service.launchers.process_launcher import ProcessLauncher


class MemoryDiagnostic:
    """内存诊断器"""

    def __init__(self):
        self.process = psutil.Process()
        self.snapshots = []
        self.objects_before = None
        self.objects_after = None

    def start_tracking(self):
        """开始内存跟踪"""
        # 启动tracemalloc
        tracemalloc.start()

        # 记录初始对象数量
        gc.collect()
        self.objects_before = len(gc.get_objects())

        # 记录初始内存快照
        self.snapshots.append(
            {
                'timestamp': time.time(),
                'memory_mb': self.get_memory_usage(),
                'objects_count': self.objects_before,
                'description': 'baseline',
            }
        )

        print(
            f'开始内存跟踪 - 初始内存: {self.get_memory_usage():.2f}MB, 对象数: {self.objects_before}'
        )

    def take_snapshot(self, description=''):
        """拍摄内存快照"""
        gc.collect()
        current_memory = self.get_memory_usage()
        current_objects = len(gc.get_objects())

        snapshot = {
            'timestamp': time.time(),
            'memory_mb': current_memory,
            'objects_count': current_objects,
            'description': description,
        }

        self.snapshots.append(snapshot)

        if len(self.snapshots) > 1:
            prev = self.snapshots[-2]
            memory_diff = current_memory - prev['memory_mb']
            objects_diff = current_objects - prev['objects_count']

            print(
                f"快照 '{description}': 内存={current_memory:.2f}MB (+{memory_diff:.2f}), "
                f'对象={current_objects} (+{objects_diff})'
            )

        return snapshot

    def stop_tracking(self):
        """停止内存跟踪"""
        gc.collect()
        self.objects_after = len(gc.get_objects())

        # 获取内存跟踪结果
        if tracemalloc.is_tracing():
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            print(
                f'停止内存跟踪 - 当前traced内存: {current / 1024 / 1024:.2f}MB, '
                f'峰值: {peak / 1024 / 1024:.2f}MB'
            )

        return self.generate_report()

    def get_memory_usage(self):
        """获取当前内存使用量（MB）"""
        memory_info = self.process.memory_info()
        return memory_info.rss / 1024 / 1024

    def analyze_objects(self):
        """分析对象增长"""
        if self.objects_before is None or self.objects_after is None:
            return {}

        objects_diff = self.objects_after - self.objects_before

        # 获取对象类型统计
        objects = gc.get_objects()
        type_counts = {}

        for obj in objects:
            obj_type = type(obj).__name__
            type_counts[obj_type] = type_counts.get(obj_type, 0) + 1

        # 按数量排序
        sorted_types = sorted(
            type_counts.items(), key=lambda x: x[1], reverse=True
        )

        return {
            'objects_increase': objects_diff,
            'top_object_types': sorted_types[:10],
            'total_objects': len(objects),
        }

    def generate_report(self):
        """生成诊断报告"""
        if len(self.snapshots) < 2:
            return '快照数量不足，无法生成报告'

        baseline = self.snapshots[0]
        final = self.snapshots[-1]

        total_memory_increase = final['memory_mb'] - baseline['memory_mb']
        total_objects_increase = (
            final['objects_count'] - baseline['objects_count']
        )

        report = f"""
=== 内存诊断报告 ===

基线信息:
- 初始内存: {baseline['memory_mb']:.2f}MB
- 初始对象数: {baseline['objects_count']}

最终信息:
- 最终内存: {final['memory_mb']:.2f}MB
- 最终对象数: {final['objects_count']}

总体变化:
- 内存增长: {total_memory_increase:.2f}MB
- 对象增长: {total_objects_increase}

快照历史:
"""

        for i, snapshot in enumerate(self.snapshots):
            if i == 0:
                report += f'  {i + 1}. {snapshot["description"]}: {snapshot["memory_mb"]:.2f}MB, {snapshot["objects_count"]}对象\n'
            else:
                prev = self.snapshots[i - 1]
                mem_diff = snapshot['memory_mb'] - prev['memory_mb']
                obj_diff = snapshot['objects_count'] - prev['objects_count']
                report += f'  {i + 1}. {snapshot["description"]}: {snapshot["memory_mb"]:.2f}MB (+{mem_diff:.2f}), {snapshot["objects_count"]}对象 (+{obj_diff})\n'

        # 对象分析
        obj_analysis = self.analyze_objects()
        if obj_analysis:
            report += f'\n对象分析:\n'
            report += f'- 对象总增长: {obj_analysis["objects_increase"]}\n'
            report += f'- 当前对象总数: {obj_analysis["total_objects"]}\n'
            report += f'- 主要对象类型:\n'

            for obj_type, count in obj_analysis['top_object_types']:
                report += f'  - {obj_type}: {count}\n'

        # 内存问题诊断
        report += self._diagnose_memory_issues(
            total_memory_increase, total_objects_increase
        )

        return report

    def _diagnose_memory_issues(self, memory_increase, objects_increase):
        """诊断内存问题"""
        diagnosis = '\n内存问题诊断:\n'

        if memory_increase > 50:
            diagnosis += '❌ 内存增长过多 (>50MB)\n'
            diagnosis += '  建议: 检查是否有大对象未释放，减少测试规模\n'
        elif memory_increase > 20:
            diagnosis += '⚠️  内存增长较多 (>20MB)\n'
            diagnosis += '  建议: 优化测试代码，增加垃圾回收\n'
        elif memory_increase > 5:
            diagnosis += '⚠️  内存增长适中 (>5MB)\n'
            diagnosis += '  建议: 监控内存使用模式\n'
        else:
            diagnosis += '✅ 内存增长在合理范围内\n'

        if objects_increase > 1000:
            diagnosis += '❌ 对象增长过多 (>1000)\n'
            diagnosis += '  建议: 检查循环引用，优化对象生命周期\n'
        elif objects_increase > 500:
            diagnosis += '⚠️  对象增长较多 (>500)\n'
            diagnosis += '  建议: 及时清理临时对象\n'
        else:
            diagnosis += '✅ 对象增长在合理范围内\n'

        diagnosis += '\n优化建议:\n'
        diagnosis += '1. 使用__slots__减少对象内存占用\n'
        diagnosis += '2. 及时清理Mock对象和patch\n'
        diagnosis += '3. 确保异步任务正确取消\n'
        diagnosis += '4. 使用weakref避免循环引用\n'
        diagnosis += '5. 定期调用gc.collect()\n'
        diagnosis += '6. 减少测试数据规模\n'
        diagnosis += '7. 使用上下文管理器确保资源清理\n'

        return diagnosis


def diagnose_performance_test():
    """诊断性能测试内存问题"""
    print('=== ProcessLauncher性能测试内存诊断 ===\n')

    diagnostic = MemoryDiagnostic()
    diagnostic.start_tracking()

    try:
        # 模拟性能测试的主要操作
        config = ConfigOpts()
        config.child_monitor_interval = 0.001
        config.log_options = False

        launchers = []
        services = []

        # 1. 创建多个ProcessLauncher实例
        diagnostic.take_snapshot('创建ProcessLauncher实例前')

        for i in range(3):
            with patch('os.pipe') as mock_pipe:
                mock_pipe.return_value = (0, 1)
                with patch('os.fdopen') as mock_fdopen:
                    mock_fdopen.return_value = MagicMock()
                    launcher = ProcessLauncher(config)
                    launchers.append(launcher)

        diagnostic.take_snapshot('创建3个ProcessLauncher实例后')

        # 2. 创建测试服务
        from tests.test_process_launcher_performance import (
            PerformanceTestService,
        )

        for i in range(5):
            service = PerformanceTestService()
            services.append(service)

        diagnostic.take_snapshot('创建5个测试服务后')

        # 3. 模拟信号处理
        for launcher in launchers:
            for _ in range(100):
                launcher._handle_term()
                launcher.running = True
                launcher.sigcaught = None
                launcher._shutdown_event.clear()

        diagnostic.take_snapshot('执行信号处理后')

        # 4. 模拟Mock对象创建
        mocks = []
        for i in range(50):
            mock = MagicMock()
            mock.return_value = i
            mocks.append(mock)

        diagnostic.take_snapshot('创建50个Mock对象后')

        # 5. 清理Mock对象
        mocks.clear()
        gc.collect()

        diagnostic.take_snapshot('清理Mock对象后')

        # 6. 清理launcher和服务
        launchers.clear()
        services.clear()
        gc.collect()

        diagnostic.take_snapshot('清理所有对象后')

    except Exception as e:
        print(f'诊断过程中出错: {e}')
        import traceback

        traceback.print_exc()

    finally:
        # 生成诊断报告
        report = diagnostic.stop_tracking()
        print(report)


def analyze_original_vs_optimized():
    """对比原版本和优化版本的内存使用"""
    print('=== 原版本 vs 优化版本内存对比 ===\n')

    # 分析原版本
    print('分析原版本性能测试...')
    original_diagnostic = MemoryDiagnostic()
    original_diagnostic.start_tracking()

    try:
        # 模拟原版本的问题：大量对象创建
        objects = []
        for i in range(1000):
            obj = {
                'data': list(range(100)),
                'mock': MagicMock(),
                'timestamp': time.time(),
            }
            objects.append(obj)

        original_diagnostic.take_snapshot('原版本-创建大量对象')

        # 模拟没有及时清理
        original_diagnostic.take_snapshot('原版本-未清理')

    finally:
        original_report = original_diagnostic.stop_tracking()

    # 分析优化版本
    print('\n分析优化版本性能测试...')
    optimized_diagnostic = MemoryDiagnostic()
    optimized_diagnostic.start_tracking()

    try:
        # 模拟优化版本：使用__slots__，及时清理
        class OptimizedObject:
            __slots__ = ['data', 'timestamp']

            def __init__(self, data):
                self.data = data
                self.timestamp = time.time()

        objects = []
        for i in range(1000):
            obj = OptimizedObject(i)
            objects.append(obj)

        optimized_diagnostic.take_snapshot('优化版本-创建优化对象')

        # 及时清理
        objects.clear()
        gc.collect()

        optimized_diagnostic.take_snapshot('优化版本-及时清理')

    finally:
        optimized_report = optimized_diagnostic.stop_tracking()

    print('=== 对比结果 ===')
    print('原版本报告:')
    print(original_report)
    print('\n优化版本报告:')
    print(optimized_report)


def check_mock_memory_usage():
    """检查Mock对象的内存使用"""
    print('=== Mock对象内存使用分析 ===\n')

    diagnostic = MemoryDiagnostic()
    diagnostic.start_tracking()

    # 测试不同Mock使用模式

    # 1. 大量Mock对象
    mocks = []
    for i in range(100):
        mock = MagicMock()
        mock.configure_mock(**{f'attr_{j}': j for j in range(10)})
        mocks.append(mock)

    diagnostic.take_snapshot('创建100个复杂Mock对象')

    # 2. 嵌套Mock
    nested_mocks = []
    for i in range(50):
        mock = MagicMock()
        mock.child1 = MagicMock()
        mock.child1.child2 = MagicMock()
        nested_mocks.append(mock)

    diagnostic.take_snapshot('创建50个嵌套Mock对象')

    # 3. 清理Mock对象
    mocks.clear()
    nested_mocks.clear()
    gc.collect()

    diagnostic.take_snapshot('清理所有Mock对象')

    report = diagnostic.stop_tracking()
    print(report)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='ProcessLauncher内存诊断工具')
    parser.add_argument(
        '--test',
        choices=['performance', 'compare', 'mock'],
        default='performance',
        help='选择诊断类型',
    )

    args = parser.parse_args()

    if args.test == 'performance':
        diagnose_performance_test()
    elif args.test == 'compare':
        analyze_original_vs_optimized()
    elif args.test == 'mock':
        check_mock_memory_usage()


if __name__ == '__main__':
    main()
