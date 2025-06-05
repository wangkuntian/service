# ServiceLauncher 测试套件

本目录包含针对 `ServiceLauncher` 类的完整测试套件，包括单元测试和性能测试。

## 📁 文件结构

```
tests/
├── __init__.py                           # 测试包初始化
├── pytest.ini                           # pytest 配置文件
├── conftest.py                          # pytest 全局配置和 fixtures
├── test_service_launcher.py             # ServiceLauncher 单元测试
├── test_service_launcher_performance.py # ServiceLauncher 性能测试
├── run_tests.py                         # 测试运行脚本
└── README.md                            # 本文档
```

## 🧪 测试类型

### 1. 单元测试 (`test_service_launcher.py`)

包含对 ServiceLauncher 类的全面单元测试：

- **初始化测试**: 验证类的正确初始化
- **信号处理测试**: 测试各种信号（SIGTERM、SIGHUP、SIGINT）的处理
- **健康检查测试**: 测试健康检查和指标更新功能
- **服务管理测试**: 测试服务启动、停止、重启功能
- **异步等待测试**: 测试异步等待和事件处理
- **工具方法测试**: 测试各种辅助方法
- **边缘情况测试**: 测试异常情况和边界条件
- **集成测试**: 测试完整的服务生命周期

### 2. 性能测试 (`test_service_launcher_performance.py`)

包含性能基准测试和压力测试：

- **启动性能测试**: 测试初始化和服务启动时间
- **信号处理性能**: 测试信号处理的响应时间
- **健康检查性能**: 测试健康检查的执行效率
- **内存性能测试**: 测试内存使用和泄漏检测
- **并发性能测试**: 测试高并发场景下的性能
- **可扩展性测试**: 测试大规模服务管理的性能
- **资源使用测试**: 测试CPU和文件描述符使用情况
- **性能基准测试**: 综合性能评估

## 🚀 运行测试

### 使用测试脚本（推荐）

```bash
# 运行所有测试
python run_tests.py --all

# 只运行单元测试
python run_tests.py --unit

# 只运行性能测试
python run_tests.py --performance

# 运行性能基准测试
python run_tests.py --benchmark

# 运行测试并生成覆盖率报告
python run_tests.py --unit --coverage

# 包含慢速测试
python run_tests.py --all --slow

# 详细输出
python run_tests.py --unit --verbose
```

### 直接使用 pytest

```bash
# 运行所有测试
pytest

# 运行单元测试
pytest -m unit

# 运行性能测试
pytest -m performance

# 运行集成测试
pytest -m integration

# 排除慢速测试
pytest -m "not slow"

# 运行特定测试文件
pytest test_service_launcher.py

# 运行特定测试类
pytest test_service_launcher.py::TestServiceLauncherInit

# 运行特定测试方法
pytest test_service_launcher.py::TestServiceLauncherInit::test_init_with_config

# 生成覆盖率报告
pytest --cov=service.launchers.service_launcher --cov-report=html
```

## 📊 测试标记

测试使用以下标记进行分类：

- `@pytest.mark.unit`: 单元测试
- `@pytest.mark.integration`: 集成测试  
- `@pytest.mark.performance`: 性能测试
- `@pytest.mark.slow`: 慢速测试（运行时间较长）
- `@pytest.mark.asyncio`: 异步测试

## 🔧 测试配置

### pytest.ini 配置

- 自动发现测试文件和函数
- 配置异步测试模式
- 设置测试标记
- 配置日志输出

### conftest.py 配置

- 全局 fixtures
- 异步事件循环管理
- 测试环境设置和清理
- 性能测试工具
- Mock 工具

## 📈 性能基准

性能测试包含以下基准：

| 指标 | 阈值 | 说明 |
|------|------|------|
| 初始化时间 | < 5ms | ServiceLauncher 实例化时间 |
| 服务启动时间 | < 10ms | 单个服务启动时间 |
| 信号处理时间 | < 1ms | 信号处理响应时间 |
| 健康检查时间 | < 5ms | 单次健康检查时间 |
| 内存使用 | < 50MB | 基线内存使用量 |

## 🛠️ 扩展测试

### 添加新的单元测试

1. 在 `test_service_launcher.py` 中添加新的测试类或方法
2. 使用适当的 pytest 标记
3. 编写清晰的测试文档字符串

```python
class TestNewFeature:
    """测试新功能"""
    
    @pytest.mark.unit
    def test_new_method(self, service_launcher):
        """测试新方法的功能"""
        # 测试代码
        pass
```

### 添加性能测试

1. 在 `test_service_launcher_performance.py` 中添加新的性能测试
2. 使用 `@pytest.mark.performance` 标记
3. 设置合理的性能阈值

```python
@pytest.mark.performance
def test_new_performance_metric(self, performance_launcher):
    """测试新的性能指标"""
    start_time = time.perf_counter()
    
    # 执行被测试的操作
    
    end_time = time.perf_counter()
    duration = (end_time - start_time) * 1000
    
    assert duration < THRESHOLD, f"操作耗时过长: {duration:.2f}ms"
```

## 🔍 调试测试

### 运行特定失败的测试

```bash
# 运行最后失败的测试
pytest --lf

# 运行第一个失败就停止
pytest -x

# 详细输出调试信息
pytest -v -s

# 使用 pdb 调试
pytest --pdb
```

### 查看测试覆盖率

```bash
# 生成 HTML 覆盖率报告
pytest --cov=service.launchers.service_launcher --cov-report=html

# 查看报告
open htmlcov/index.html
```

## 📝 最佳实践

1. **测试命名**: 使用描述性的测试名称
2. **测试隔离**: 每个测试应该独立运行
3. **Mock 使用**: 适当使用 Mock 隔离外部依赖
4. **异步测试**: 正确处理异步代码的测试
5. **性能测试**: 设置合理的性能阈值
6. **文档**: 为测试编写清晰的文档字符串

## 🐛 故障排除

### 常见问题

1. **异步测试失败**: 确保使用了正确的 `@pytest.mark.asyncio` 标记
2. **Mock 不工作**: 检查 Mock 的路径是否正确
3. **性能测试不稳定**: 考虑环境因素，适当调整阈值
4. **导入错误**: 确保 PYTHONPATH 设置正确

### 获取帮助

如果遇到测试问题，可以：

1. 查看测试日志输出
2. 运行单个测试进行调试
3. 检查 conftest.py 中的配置
4. 查看 pytest 文档 # ProcessLauncher 测试文档

这个目录包含了 `ProcessLauncher` 类的完整测试套件，包括单元测试和性能测试。

## 测试文件结构

```
tests/
├── README.md                          # 测试文档（本文件）
├── __init__.py                        # 测试包初始化
├── pytest.ini                        # pytest配置文件
├── run_tests.py                       # 测试运行脚本
├── test_process_launcher.py          # 单元测试
└── test_process_launcher_performance.py  # 性能测试
```

## 快速开始

### 1. 安装依赖

首先确保安装了所需的测试依赖：

```bash
# 检查依赖
python tests/run_tests.py --check

# 如果缺少依赖，运行以下命令安装
pip install pytest pytest-mock pytest-asyncio psutil
```

### 2. 运行测试

```bash
# 运行所有测试
python tests/run_tests.py --all

# 只运行单元测试
python tests/run_tests.py --unit

# 只运行性能测试
python tests/run_tests.py --performance

# 运行特定测试
python tests/run_tests.py --test "signal"
```

### 3. 生成报告

```bash
# 生成覆盖率报告
python tests/run_tests.py --coverage

# 生成HTML测试报告
python tests/run_tests.py --report

# 运行性能基准测试
python tests/run_tests.py --benchmark
```

## 测试类型详解

### 单元测试 (`test_process_launcher.py`)

单元测试覆盖了 `ProcessLauncher` 的所有核心功能：

#### 基础功能测试
- 初始化和配置
- 信号处理器设置
- 管道创建和错误处理

#### 信号处理测试
- SIGTERM、SIGHUP、SIGINT、SIGALRM 信号处理
- 异步信号处理器设置和清理
- 高频信号处理

#### 子进程管理测试
- 子进程启动和停止
- 子进程监控和重启
- 进程退出处理（正常退出、信号终止）
- fork 速率限制

#### 服务生命周期测试
- 服务启动和停止
- 优雅关闭和强制终止
- 服务重启
- 错误处理和恢复

#### 异步操作测试
- asyncio 事件循环集成
- 异步任务管理
- 事件驱动的监控

### 性能测试 (`test_process_launcher_performance.py`)

性能测试评估 `ProcessLauncher` 在各种负载下的表现：

#### 启动性能测试
- 单个工作进程启动时间
- 多个工作进程并发启动时间
- 大量工作进程（100+）启动性能

#### 内存性能测试
- 内存使用量监控
- 内存泄漏检测
- 重启循环中的内存稳定性

#### 响应性能测试
- 信号处理延迟
- 子进程监控性能
- 事件循环效率

#### 并发性能测试
- 并发任务处理能力
- 高频操作性能
- 压力测试

#### 基准测试
- 标准性能指标
- 性能回归检测
- 优化效果验证

## 测试覆盖范围

### 功能覆盖
- ✅ 进程启动和管理
- ✅ 信号处理
- ✅ 异步操作
- ✅ 错误处理
- ✅ 资源清理
- ✅ 配置管理

### 场景覆盖
- ✅ 正常操作流程
- ✅ 异常和错误情况
- ✅ 边界条件
- ✅ 并发场景
- ✅ 资源限制
- ✅ 性能极限

### 平台覆盖
- ✅ Unix/Linux 信号处理
- ✅ 进程 fork 操作
- ✅ 异步 I/O 操作
- ✅ 内存管理

## 使用指南

### 运行特定类型的测试

```bash
# 单元测试
pytest tests/test_process_launcher.py -v

# 性能测试
pytest tests/test_process_launcher_performance.py -v -s

# 异步测试
pytest tests/ -v -m asyncio

# 慢速测试（性能测试）
pytest tests/ -v -m slow
```

### 自定义测试运行

```bash
# 运行特定测试方法
pytest tests/test_process_launcher.py::TestProcessLauncher::test_init -v

# 运行包含特定关键字的测试
pytest tests/ -k "signal" -v

# 失败时停止
pytest tests/ -x

# 显示详细输出
pytest tests/ -v -s

# 并行运行测试（需要安装 pytest-xdist）
pytest tests/ -n auto
```

### 生成详细报告

```bash
# 生成 JUnit XML 报告
pytest tests/ --junitxml=tests/junit.xml

# 生成覆盖率报告
pytest tests/ --cov=src/service/launchers/process_launcher --cov-report=html

# 生成性能报告
pytest tests/test_process_launcher_performance.py --benchmark-json=tests/benchmark.json
```

## 测试配置

### pytest.ini 配置

测试配置文件 `pytest.ini` 包含：
- 测试发现规则
- 异步测试配置
- 日志配置
- 警告过滤
- 标记定义

### 环境变量

可以通过环境变量控制测试行为：

```bash
# 设置日志级别
export PYTEST_LOG_LEVEL=DEBUG

# 禁用警告
export PYTHONWARNINGS=ignore

# 设置异步模式
export PYTEST_ASYNCIO_MODE=auto
```

## 常见问题

### Q: 测试运行缓慢怎么办？
A: 性能测试可能需要较长时间。可以使用 `--unit` 只运行单元测试，或使用 `-k` 过滤特定测试。

### Q: 如何跳过性能测试？
A: 使用 `pytest -m "not performance"` 或直接运行单元测试文件。

### Q: 测试失败如何调试？
A: 使用 `-v -s --tb=long` 参数获取详细的失败信息和堆栈跟踪。

### Q: 如何添加新的测试？
A: 在相应的测试文件中添加新的测试方法，遵循现有的命名和结构约定。

### Q: 如何模拟系统调用？
A: 使用 `unittest.mock.patch` 模拟 `os.fork`、`os.waitpid` 等系统调用。

## 最佳实践

### 编写测试时
1. 使用描述性的测试名称
2. 每个测试只验证一个功能点
3. 合理使用 mock 避免真实系统调用
4. 包含正常和异常情况的测试
5. 为异步代码使用 `@pytest.mark.asyncio`

### 运行测试时
1. 定期运行完整测试套件
2. 提交代码前运行相关测试
3. 关注覆盖率报告
4. 监控性能测试结果

### 维护测试时
1. 保持测试代码的简洁和可读性
2. 及时更新过时的测试
3. 添加新功能时同时添加测试
4. 定期审查和重构测试代码

## 贡献指南

如果您要为 `ProcessLauncher` 添加新功能或修复 bug：

1. 确保现有测试通过
2. 为新功能添加相应测试
3. 更新性能测试（如果影响性能）
4. 确保测试覆盖率不降低
5. 更新相关文档

测试是代码质量的重要保障，感谢您的贡献！ 