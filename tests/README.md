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
4. 查看 pytest 文档 