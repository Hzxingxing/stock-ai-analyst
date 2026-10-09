"""
Alembic环境配置文件
负责加载数据库配置和ORM模型
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make the new backend package importable from an Alembic command run at the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Load only the new research schema. Its baseline is independent of former project migrations.
from app.config import settings
from app.db.models import Base

# Alembic Config对象
config = context.config

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置元数据对象（包含所有表定义）
target_metadata = Base.metadata


# 从环境变量或配置文件获取数据库URL
def get_url():
    return settings.sync_database_url


def run_migrations_offline() -> None:
    """
    离线模式迁移（生成SQL脚本）
    不需要实际连接数据库
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # 比较列类型变化
        compare_server_default=True,  # 比较默认值变化
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    在线模式迁移（直接执行到数据库）
    需要实际连接数据库
    """
    # 使用自定义的database_url
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"init_command": "SET time_zone = '+00:00'"},
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # 比较列类型变化
            compare_server_default=True,  # 比较默认值变化
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
