"""
日志配置模块
使用loguru实现结构化日志
"""
import os
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 日志配置
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_DIR = Path(__file__).parent.parent.parent / 'logs'

# 确保日志目录存在
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 移除默认的logger
logger.remove()

# 添加控制台输出
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    colorize=True
)

# 添加文件输出（按天分割）
logger.add(
    LOG_DIR / "stock_analysis_{time:YYYY-MM-DD}.log",
    level=LOG_LEVEL,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="00:00",  # 每天0点轮转
    retention="30 days",  # 保留30天
    compression="zip",  # 压缩旧日志
    encoding="utf-8"
)

# 添加错误日志文件
logger.add(
    LOG_DIR / "error_{time:YYYY-MM-DD}.log",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="00:00",
    retention="90 days",
    compression="zip",
    encoding="utf-8"
)


def get_logger(name: str = None):
    """
    获取logger实例
    Args:
        name: logger名称（通常使用__name__）
    Returns:
        logger实例
    """
    if name:
        return logger.bind(name=name)
    return logger


# 导出logger
__all__ = ['logger', 'get_logger']


if __name__ == '__main__':
    # 测试日志功能
    test_logger = get_logger(__name__)
    test_logger.debug("这是DEBUG级别日志")
    test_logger.info("这是INFO级别日志")
    test_logger.warning("这是WARNING级别日志")
    test_logger.error("这是ERROR级别日志")
    test_logger.success("这是SUCCESS级别日志")
