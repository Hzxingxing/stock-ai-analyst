"""
配置管理模块
统一管理系统配置,从config.yaml和环境变量加载
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any
from functools import lru_cache


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = None):
        """
        初始化配置管理器

        Args:
            config_path: 配置文件路径,默认为backend/config/config.yaml
        """
        if config_path is None:
            backend_dir = Path(__file__).parent.parent.parent
            config_path = backend_dir / "config" / "config.yaml"

        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self):
        """加载YAML配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f) or {}

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项
        支持点分隔符访问嵌套配置,如: mysql.host

        Args:
            key: 配置键,支持点分隔符
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def get_env(self, key: str, default: str = None) -> str:
        """
        获取环境变量

        Args:
            key: 环境变量键
            default: 默认值

        Returns:
            环境变量值
        """
        return os.getenv(key, default)

    def get_mysql_config(self) -> Dict[str, Any]:
        """
        获取MySQL配置
        密码从环境变量读取

        Returns:
            MySQL配置字典
        """
        mysql_config = self.get('mysql', {})
        mysql_config['password'] = self.get_env('MYSQL_PASSWORD', '')
        return mysql_config

    def get_gemini_config(self) -> Dict[str, Any]:
        """
        获取Gemini配置
        API密钥和端点从环境变量读取

        Returns:
            Gemini配置字典
        """
        gemini_config = self.get('gemini', {})
        gemini_config['api_key'] = self.get_env('NEWAPI_KEY', '')
        gemini_config['endpoint'] = self.get_env('NEWAPI_ENDPOINT', '')
        return gemini_config

    def get_app_config(self) -> Dict[str, Any]:
        """
        获取应用配置

        Returns:
            应用配置字典
        """
        return self.get('app', {})

    def get_scheduler_config(self) -> Dict[str, Any]:
        """
        获取定时任务配置

        Returns:
            定时任务配置字典
        """
        return self.get('scheduler', {})

    def get_data_update_config(self) -> Dict[str, Any]:
        """
        获取数据更新配置

        Returns:
            数据更新配置字典
        """
        return self.get('data_update', {})


@lru_cache(maxsize=1)
def get_config_manager() -> ConfigManager:
    """
    获取全局配置管理器单例
    使用lru_cache确保单例模式

    Returns:
        ConfigManager实例
    """
    return ConfigManager()


# 便捷函数
def get_mysql_url() -> str:
    """
    获取MySQL连接URL

    Returns:
        SQLAlchemy连接URL
    """
    config = get_config_manager().get_mysql_config()
    return (
        f"mysql+pymysql://{config['user']}:{config['password']}"
        f"@{config['host']}:{config['port']}/{config['database']}"
        f"?charset={config['charset']}"
    )


def get_gemini_client_config() -> Dict[str, Any]:
    """
    获取Gemini客户端配置

    Returns:
        包含api_key, base_url, model等的配置字典
    """
    return get_config_manager().get_gemini_config()


if __name__ == "__main__":
    # 测试配置加载
    manager = get_config_manager()

    print("=== MySQL配置 ===")
    mysql_config = manager.get_mysql_config()
    for k, v in mysql_config.items():
        if k == 'password':
            print(f"{k}: {'*' * 8}")
        else:
            print(f"{k}: {v}")

    print("\n=== Gemini配置 ===")
    gemini_config = manager.get_gemini_config()
    for k, v in gemini_config.items():
        if k in ['api_key', 'endpoint']:
            print(f"{k}: {'*' * 10}")
        else:
            print(f"{k}: {v}")

    print("\n=== MySQL URL ===")
    print(get_mysql_url().replace(mysql_config['password'], '***'))
