"""
数据库连接管理模块
负责创建SQLAlchemy引擎和Session
"""
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

from .models import Base
from src.utils.config_manager import get_config_manager, get_mysql_url

# 加载环境变量
load_dotenv()

# 全局变量
_engine = None
_SessionLocal = None


def get_database_url():
    """构造数据库连接URL"""
    return get_mysql_url()


def get_engine():
    """获取SQLAlchemy引擎（单例模式）"""
    global _engine
    if _engine is None:
        config_manager = get_config_manager()
        mysql_config = config_manager.get_mysql_config()
        database_url = get_database_url()

        _engine = create_engine(
            database_url,
            poolclass=QueuePool,
            pool_size=mysql_config.get('pool_size', 10),
            max_overflow=mysql_config.get('max_overflow', 20),
            pool_recycle=mysql_config.get('pool_recycle', 3600),
            pool_pre_ping=True,  # 连接池预检查
            echo=False,  # 生产环境关闭SQL日志
        )

        # 添加连接事件监听（可选：用于连接池调试）
        @event.listens_for(_engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """连接建立时的回调"""
            pass

    return _engine


def get_session_local():
    """获取Session工厂（单例模式）"""
    global _SessionLocal
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine
        )
    return _SessionLocal


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    获取数据库Session的上下文管理器
    使用示例:
        with get_db_session() as session:
            # 执行数据库操作
            stocks = session.query(Stock).all()
    """
    SessionLocal = get_session_local()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def init_database():
    """
    初始化数据库（创建所有表）
    注意：生产环境应使用Alembic迁移
    """
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")


def drop_all_tables():
    """
    删除所有表（危险操作！仅用于开发环境）
    """
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    print("All tables dropped!")


def test_connection():
    """测试数据库连接"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            print(f"Database connection successful! Result: {result.scalar()}")
            return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False


if __name__ == '__main__':
    # 测试数据库连接
    test_connection()
