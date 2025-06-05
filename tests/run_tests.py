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