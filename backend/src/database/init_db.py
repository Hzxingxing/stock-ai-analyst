"""
数据库初始化脚本
用于创建表结构和导入初始数据
"""
from src.database.connection import get_db_session, init_database
from src.database.repository import StockRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


def init_default_stocks():
    """
    初始化默认股票列表
    注意: 现在股票由Web界面动态管理,这里只是提供一些默认示例
    """
    default_stocks = [
        {"code": "600519", "name": "贵州茅台", "market": "SH"},
        {"code": "000858", "name": "五粮液", "market": "SZ"},
        {"code": "600036", "name": "招商银行", "market": "SH"},
        {"code": "000333", "name": "美的集团", "market": "SZ"},
        {"code": "601318", "name": "中国平安", "market": "SH"},
    ]

    logger.info("开始初始化默认股票列表...")

    with get_db_session() as session:
        for stock_info in default_stocks:
            existing = StockRepository.get_stock_by_code(session, stock_info['code'])

            if existing:
                logger.info(f"股票 {stock_info['code']} 已存在,跳过")
                continue

            stock = StockRepository.create_stock(
                session,
                stock_info['code'],
                stock_info['name'],
                stock_info['market']
            )
            logger.success(f"添加股票: {stock.stock_name}({stock.stock_code})")

    logger.success("默认股票列表初始化完成!")


if __name__ == "__main__":
    print("=== 股票AI分析系统 - 数据库初始化 ===\n")

    # 1. 创建表结构
    print("步骤1: 创建数据库表结构...")
    init_database()

    # 2. 初始化默认股票
    print("\n步骤2: 初始化默认股票列表...")
    init_default_stocks()

    print("\n=== 初始化完成! ===")
    print("现在你可以:")
    print("1. 启动Web服务: uvicorn src.web.main:app --reload")
    print("2. 访问 http://localhost:8000 管理股票")
