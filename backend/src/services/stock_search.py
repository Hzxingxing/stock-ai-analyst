"""
股票搜索服务
使用AKShare搜索A股市场股票
"""
import akshare as ak
import pandas as pd
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


class StockSearchService:
    """股票搜索服务（带持久化缓存）"""

    def __init__(self, cache_dir: str = None):
        self._stock_list_cache: Optional[pd.DataFrame] = None

        # 缓存文件路径
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "cache"
        else:
            cache_dir = Path(cache_dir)

        cache_dir.mkdir(exist_ok=True)
        self._cache_file = cache_dir / "stock_list_cache.pkl"
        self._cache_time_file = cache_dir / "stock_list_cache_time.txt"

        # 缓存有效期（小时）
        self._cache_valid_hours = 24

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self._cache_time_file.exists():
            return False

        try:
            cache_time_str = self._cache_time_file.read_text()
            cache_time = datetime.fromisoformat(cache_time_str)

            # 检查是否过期
            age = datetime.now() - cache_time
            return age < timedelta(hours=self._cache_valid_hours)
        except Exception as e:
            logger.warning(f"读取缓存时间失败: {e}")
            return False

    def _load_cache_from_disk(self) -> Optional[pd.DataFrame]:
        """从磁盘加载缓存"""
        if not self._cache_file.exists():
            return None

        if not self._is_cache_valid():
            logger.info("缓存已过期")
            return None

        try:
            with open(self._cache_file, 'rb') as f:
                df = pickle.load(f)
            logger.info(f"从缓存加载 {len(df)} 只股票")
            return df
        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
            return None

    def _save_cache_to_disk(self, df: pd.DataFrame):
        """保存缓存到磁盘"""
        try:
            with open(self._cache_file, 'wb') as f:
                pickle.dump(df, f)

            # 保存缓存时间
            self._cache_time_file.write_text(datetime.now().isoformat())

            logger.info(f"缓存已保存: {len(df)} 只股票")
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    def _get_stock_list(self) -> pd.DataFrame:
        """
        获取A股股票列表(带持久化缓存)

        Returns:
            股票列表DataFrame
        """
        # 1. 检查内存缓存
        if self._stock_list_cache is not None:
            return self._stock_list_cache

        # 2. 尝试从磁盘加载
        df = self._load_cache_from_disk()
        if df is not None:
            self._stock_list_cache = df
            return df

        # 3. 从AKShare获取（慢）
        try:
            logger.info("首次获取股票列表，可能需要10-30秒...")
            df = ak.stock_info_a_code_name()

            # 保存到缓存
            self._stock_list_cache = df
            self._save_cache_to_disk(df)

            logger.success(f"成功获取 {len(df)} 只股票")
            return df
        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            raise

    def search_stocks(self, keyword: str, limit: int = 20) -> List[Dict[str, str]]:
        """
        搜索股票

        Args:
            keyword: 搜索关键词(股票代码或名称)
            limit: 返回结果数量限制

        Returns:
            股票列表,每个元素包含code, name, market
        """
        if not keyword:
            return []

        try:
            df = self._get_stock_list()

            # 搜索代码或名称包含关键词的股票
            mask = (
                df['code'].astype(str).str.contains(keyword, case=False, na=False) |
                df['name'].str.contains(keyword, case=False, na=False)
            )

            results_df = df[mask].head(limit)

            results = []
            for _, row in results_df.iterrows():
                code = str(row['code'])
                # 判断市场
                if code.startswith('6'):
                    market = 'SH'
                elif code.startswith(('0', '3')):
                    market = 'SZ'
                else:
                    market = 'SH'  # 默认上海

                results.append({
                    'code': code,
                    'name': row['name'],
                    'market': market
                })

            return results

        except Exception as e:
            logger.error(f"搜索股票失败: {e}")
            return []

    def get_stock_info(self, stock_code: str) -> Optional[Dict[str, str]]:
        """
        获取单只股票信息

        Args:
            stock_code: 股票代码

        Returns:
            股票信息字典或None
        """
        try:
            df = self._get_stock_list()
            stock = df[df['code'].astype(str) == stock_code]

            if stock.empty:
                return None

            row = stock.iloc[0]
            code = str(row['code'])

            # 判断市场
            if code.startswith('6'):
                market = 'SH'
            elif code.startswith(('0', '3')):
                market = 'SZ'
            else:
                market = 'SH'

            return {
                'code': code,
                'name': row['name'],
                'market': market
            }

        except Exception as e:
            logger.error(f"获取股票信息失败: {e}")
            return None

    def refresh_cache(self):
        """刷新缓存（强制重新获取）"""
        self._stock_list_cache = None
        if self._cache_file.exists():
            self._cache_file.unlink()
        if self._cache_time_file.exists():
            self._cache_time_file.unlink()
        logger.info("股票列表缓存已清空")

    def preload(self):
        """预加载股票列表（异步后台加载）"""
        try:
            self._get_stock_list()
            logger.success("股票列表预加载完成")
        except Exception as e:
            logger.error(f"股票列表预加载失败: {e}")


# 全局单例
_stock_search_service = None


def get_stock_search_service() -> StockSearchService:
    """
    获取股票搜索服务单例

    Returns:
        StockSearchService实例
    """
    global _stock_search_service
    if _stock_search_service is None:
        _stock_search_service = StockSearchService()
    return _stock_search_service


if __name__ == "__main__":
    # 测试
    service = get_stock_search_service()

    print("=== 搜索'茅台' ===")
    results = service.search_stocks("茅台")
    for stock in results:
        print(f"{stock['code']} - {stock['name']} ({stock['market']})")

    print("\n=== 搜索'6005' ===")
    results = service.search_stocks("6005", limit=10)
    for stock in results:
        print(f"{stock['code']} - {stock['name']} ({stock['market']})")

    print("\n=== 获取600519信息 ===")
    info = service.get_stock_info("600519")
    if info:
        print(f"{info['code']} - {info['name']} ({info['market']})")
