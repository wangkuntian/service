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
#!/usr/bin/env python3
"""测试运行脚本

这个脚本提供了多种运行ProcessLauncher测试的方式：
- 运行所有测试
- 只运行单元测试
- 只运行性能测试
- 运行带覆盖率的测试
- 生成测试报告
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, description):
    """运行命令并显示描述"""
    print(f"\n{'='*60}")
    print(f"执行: {description}")
    print(f"命令: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.stdout:
        print("标准输出:")
        print(result.stdout)
    
    if result.stderr:
        print("错误输出:")
        print(result.stderr)
    
    if result.returncode != 0:
        print(f"命令执行失败，返回码: {result.returncode}")
        return False
    
    print("命令执行成功!")
    return True


def run_unit_tests():
    """运行单元测试"""
    cmd = [
        "python", "-m", "pytest",
        "tests/test_process_launcher.py",
        "-v",
        "--tb=short",
        "-m", "not performance"
    ]
    return run_command(cmd, "运行ProcessLauncher单元测试")


def run_performance_tests():
    """运行性能测试"""
    cmd = [
        "python", "-m", "pytest", 
        "tests/test_process_launcher_performance.py",
        "-v",
        "--tb=short",
        "-s"  # 显示print输出
    ]
    return run_command(cmd, "运行ProcessLauncher性能测试")


def run_optimized_performance_tests():
    """运行内存优化的性能测试"""
    cmd = [
        "python", "-m", "pytest", 
        "tests/test_process_launcher_performance_optimized.py",
        "-v",
        "--tb=short",
        "-s"
    ]
    return run_command(cmd, "运行内存优化的ProcessLauncher性能测试")


def run_memory_diagnostic():
    """运行内存诊断"""
    cmd = [
        "python", "tests/memory_diagnostic.py", "--test", "performance"
    ]
    return run_command(cmd, "运行内存诊断分析")


def run_all_tests():
    """运行所有测试"""
    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short"
    ]
    return run_command(cmd, "运行所有ProcessLauncher测试")


def run_tests_with_coverage():
    """运行带覆盖率的测试"""
    # 首先检查是否安装了pytest-cov
    try:
        import pytest_cov
    except ImportError:
        print("未安装pytest-cov，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pytest-cov"])
    
    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "--cov=src/service/launchers/process_launcher",
        "--cov-report=html:tests/htmlcov",
        "--cov-report=term-missing",
        "--cov-report=xml:tests/coverage.xml",
        "-v"
    ]
    return run_command(cmd, "运行带覆盖率的测试")


def run_specific_test(test_name):
    """运行特定测试"""
    cmd = [
        "python", "-m", "pytest",
        "-k", test_name,
        "-v",
        "--tb=short",
        "-s"
    ]
    return run_command(cmd, f"运行特定测试: {test_name}")


def generate_test_report():
    """生成测试报告"""
    # 首先检查是否安装了pytest-html
    try:
        import pytest_html
    except ImportError:
        print("未安装pytest-html，正在安装...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pytest-html"])
    
    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "--html=tests/report.html",
        "--self-contained-html",
        "-v"
    ]
    return run_command(cmd, "生成HTML测试报告")


def check_dependencies():
    """检查测试依赖"""
    print("检查测试依赖...")
    
    required_packages = [
        "pytest",
        "pytest-mock", 
        "pytest-asyncio",
        "psutil"
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(f"✓ {package} 已安装")
        except ImportError:
            print(f"✗ {package} 未安装")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n缺少以下依赖包: {', '.join(missing_packages)}")
        print("请运行以下命令安装:")
        print(f"pip install {' '.join(missing_packages)}")
        return False
    
    print("\n所有依赖已满足!")
    return True


def benchmark_tests():
    """运行基准测试"""
    cmd = [
        "python", "-m", "pytest", 
        "tests/test_process_launcher_performance.py::test_performance_benchmarks",
        "-v",
        "-s"
    ]
    return run_command(cmd, "运行性能基准测试")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="ProcessLauncher测试运行脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python run_tests.py --all              # 运行所有测试
  python run_tests.py --unit             # 只运行单元测试
  python run_tests.py --performance      # 只运行性能测试
  python run_tests.py --optimized        # 运行内存优化性能测试
  python run_tests.py --coverage         # 运行带覆盖率的测试
  python run_tests.py --report           # 生成HTML报告
  python run_tests.py --benchmark        # 运行基准测试
  python run_tests.py --diagnostic       # 运行内存诊断
  python run_tests.py --test "signal"    # 运行包含"signal"的测试
  python run_tests.py --check            # 检查依赖
        """
    )
    
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="运行所有测试"
    )
    parser.add_argument(
        "--unit", 
        action="store_true", 
        help="只运行单元测试"
    )
    parser.add_argument(
        "--performance", 
        action="store_true", 
        help="只运行性能测试"
    )
    parser.add_argument(
        "--optimized", 
        action="store_true", 
        help="运行内存优化性能测试"
    )
    parser.add_argument(
        "--coverage", 
        action="store_true", 
        help="运行带覆盖率的测试"
    )
    parser.add_argument(
        "--report", 
        action="store_true", 
        help="生成HTML测试报告"
    )
    parser.add_argument(
        "--benchmark", 
        action="store_true", 
        help="运行性能基准测试"
    )
    parser.add_argument(
        "--diagnostic", 
        action="store_true", 
        help="运行内存诊断"
    )
    parser.add_argument(
        "--test", 
        type=str, 
        help="运行特定测试（按名称匹配）"
    )
    parser.add_argument(
        "--check", 
        action="store_true", 
        help="检查测试依赖"
    )
    
    args = parser.parse_args()
    
    # 切换到项目根目录
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    success = True
    
    if args.check:
        success = check_dependencies()
    elif args.unit:
        success = run_unit_tests()
    elif args.performance:
        success = run_performance_tests()
    elif args.optimized:
        success = run_optimized_performance_tests()
    elif args.coverage:
        success = run_tests_with_coverage()
    elif args.report:
        success = generate_test_report()
    elif args.benchmark:
        success = benchmark_tests()
    elif args.diagnostic:
        success = run_memory_diagnostic()
    elif args.test:
        success = run_specific_test(args.test)
    elif args.all:
        success = run_all_tests()
    else:
        # 默认运行单元测试
        print("未指定测试类型，运行单元测试...")
        success = run_unit_tests()
    
    if success:
        print(f"\n{'='*60}")
        print("测试执行完成!")
        print(f"{'='*60}")
        sys.exit(0)
    else:
        print(f"\n{'='*60}")
        print("测试执行失败!")
        print(f"{'='*60}")
        sys.exit(1)


if __name__ == "__main__":
    main() 