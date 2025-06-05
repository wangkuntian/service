#!/usr/bin/env python3
"""测试运行脚本

这个脚本提供了便捷的方式来运行不同类型的测试：
- 单元测试
- 性能测试
- 集成测试
- 全部测试

使用方法:
    python run_tests.py [选项]

选项:
    --unit          只运行单元测试
    --performance   只运行性能测试
    --integration   只运行集成测试
    --slow          包含慢速测试
    --all           运行所有测试（默认）
    --coverage      生成覆盖率报告
    --benchmark     运行性能基准测试
    --help          显示帮助信息
"""

import sys
import subprocess
import argparse
import os
from pathlib import Path


def run_command(cmd, description=''):
    """运行命令并显示结果"""
    print(f'\n🚀 {description}')
    print(f'执行命令: {" ".join(cmd)}')
    print('-' * 60)

    try:
        result = subprocess.run(cmd, capture_output=False, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f'❌ 命令执行失败: {e}')
        return False


def main():
    parser = argparse.ArgumentParser(
        description='ServiceLauncher 测试运行脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument('--unit', action='store_true', help='只运行单元测试')
    parser.add_argument(
        '--performance', action='store_true', help='只运行性能测试'
    )
    parser.add_argument(
        '--integration', action='store_true', help='只运行集成测试'
    )
    parser.add_argument('--slow', action='store_true', help='包含慢速测试')
    parser.add_argument(
        '--all', action='store_true', help='运行所有测试（默认）'
    )
    parser.add_argument(
        '--coverage', action='store_true', help='生成覆盖率报告'
    )
    parser.add_argument(
        '--benchmark', action='store_true', help='只运行性能基准测试'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true', help='详细输出'
    )
    parser.add_argument(
        '--parallel', '-j', type=int, default=1, help='并行运行测试的进程数'
    )

    args = parser.parse_args()

    # 确保在tests目录中运行
    script_dir = Path(__file__).parent
    os.chdir(script_dir)

    # 基础pytest命令
    base_cmd = ['python', '-m', 'pytest']

    # 添加详细输出
    if args.verbose:
        base_cmd.extend(['-v', '-s'])

    # 添加并行处理
    if args.parallel > 1:
        base_cmd.extend(['-n', str(args.parallel)])

    # 确定要运行的测试类型
    test_types = []

    if args.unit:
        test_types.append('unit')
    if args.performance:
        test_types.append('performance')
    if args.integration:
        test_types.append('integration')
    if args.benchmark:
        test_types.append('performance')
        # 只运行基准测试
        base_cmd.extend(['-k', 'benchmark'])

    # 如果没有指定特定类型，或指定了--all，运行所有测试
    if not test_types or args.all:
        test_types = ['unit', 'performance', 'integration']

    # 构建标记表达式
    if test_types and not args.all:
        mark_expr = ' or '.join(test_types)
        base_cmd.extend(['-m', mark_expr])

    # 处理慢速测试
    if not args.slow and not args.benchmark:
        if '-m' in base_cmd:
            # 如果已经有标记表达式，添加排除slow的条件
            mark_index = base_cmd.index('-m') + 1
            current_marks = base_cmd[mark_index]
            base_cmd[mark_index] = f'({current_marks}) and not slow'
        else:
            # 如果没有标记表达式，只排除slow
            base_cmd.extend(['-m', 'not slow'])

    # 添加覆盖率
    if args.coverage:
        base_cmd.extend(
            [
                '--cov=service.launchers.service_launcher',
                '--cov-report=html:htmlcov',
                '--cov-report=term-missing',
                '--cov-report=xml',
            ]
        )

    # 运行测试
    success = True

    print('=' * 60)
    print('🧪 ServiceLauncher 测试套件')
    print('=' * 60)

    if args.unit or args.all:
        print('\n📋 运行单元测试...')
        unit_cmd = base_cmd + ['test_service_launcher.py']
        if not args.all:
            unit_cmd.extend(
                ['-m', 'unit and not slow']
            ) if not args.slow else unit_cmd.extend(['-m', 'unit'])
        success &= run_command(unit_cmd, '单元测试')

    if args.performance or args.benchmark or args.all:
        print('\n⚡ 运行性能测试...')
        perf_cmd = base_cmd + ['test_service_launcher_performance.py']
        if args.benchmark:
            perf_cmd.extend(['-k', 'benchmark'])
        elif not args.all:
            perf_cmd.extend(
                ['-m', 'performance and not slow']
            ) if not args.slow else perf_cmd.extend(['-m', 'performance'])
        success &= run_command(perf_cmd, '性能测试')

    if args.integration or args.all:
        print('\n🔗 运行集成测试...')
        int_cmd = base_cmd + ['-m', 'integration']
        if not args.slow:
            int_cmd = base_cmd + ['-m', 'integration and not slow']
        success &= run_command(int_cmd, '集成测试')

    # 显示结果摘要
    print('\n' + '=' * 60)
    if success:
        print('✅ 所有测试通过！')

        if args.coverage:
            print('\n📊 覆盖率报告已生成:')
            print('   - HTML报告: htmlcov/index.html')
            print('   - XML报告: coverage.xml')

        if args.performance or args.benchmark:
            print('\n⚡ 性能测试完成，请查看详细的性能指标输出')
    else:
        print('❌ 部分测试失败，请查看上述输出了解详情')
        return 1

    print('=' * 60)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n\n⚠️  测试被用户中断')
        sys.exit(1)
    except Exception as e:
        print(f'\n\n❌ 运行测试时发生错误: {e}')
        sys.exit(1)
