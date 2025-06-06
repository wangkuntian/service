import sys

from loguru import logger

format = (
    '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
    '<level><cyan>Process-{process}</cyan></level> | '
    '<level><yellow>Thread-{thread}</yellow></level> | '
    '<level>{level: <8}</level> | '
    '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | '
    '<level>{message}</level>'
)

# 移除默认处理器，避免重复日志
logger.remove()

# 添加自定义处理器
logger.add(
    sys.stdout,
    level='INFO',
    format=format,
)

LOG = logger
