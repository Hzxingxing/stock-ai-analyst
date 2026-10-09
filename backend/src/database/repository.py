"""
数据访问层(Repository)
提供数据库CRUD操作的统一接口
"""
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from src.database.models import (
    Stock, StockKLine, StockChipDistribution, StockFinancial,
    StockAnnouncement, StockNews, GeminiAnalysis, ClaudeReport
)


class StockRepository:
    """股票数据仓库"""

    @staticmethod
    def get_all_active_stocks(session: Session) -> List[Stock]:
        """
        获取所有启用的股票

        Args:
            session: 数据库会话

        Returns:
            股票列表
        """
        return session.query(Stock).filter(Stock.is_active == 1).all()

    @staticmethod
    def get_stock_by_code(session: Session, stock_code: str) -> Optional[Stock]:
        """
        根据股票代码获取股票

        Args:
            session: 数据库会话
            stock_code: 股票代码

        Returns:
            Stock对象或None
        """
        return session.query(Stock).filter(Stock.stock_code == stock_code).first()

    @staticmethod
    def create_stock(session: Session, stock_code: str, stock_name: str, market: str) -> Stock:
        """
        创建新股票

        Args:
            session: 数据库会话
            stock_code: 股票代码
            stock_name: 股票名称
            market: 市场(SH/SZ)

        Returns:
            Stock对象
        """
        stock = Stock(
            stock_code=stock_code,
            stock_name=stock_name,
            market=market,
            is_active=1
        )
        session.add(stock)
        session.commit()
        session.refresh(stock)
        return stock

    @staticmethod
    def update_stock(session: Session, stock_code: str, **kwargs) -> Optional[Stock]:
        """
        更新股票信息

        Args:
            session: 数据库会话
            stock_code: 股票代码
            **kwargs: 要更新的字段

        Returns:
            Stock对象或None
        """
        stock = session.query(Stock).filter(Stock.stock_code == stock_code).first()
        if stock:
            for key, value in kwargs.items():
                if hasattr(stock, key):
                    setattr(stock, key, value)
            stock.updated_at = datetime.now()
            session.commit()
            session.refresh(stock)
        return stock

    @staticmethod
    def delete_stock(session: Session, stock_code: str) -> bool:
        """
        硬删除股票（真正删除记录及关联数据）

        Args:
            session: 数据库会话
            stock_code: 股票代码

        Returns:
            是否成功
        """
        stock = session.query(Stock).filter(Stock.stock_code == stock_code).first()
        if stock:
            # 级联删除会自动删除关联的K线、财务、公告、新闻、分析等数据
            session.delete(stock)
            session.commit()
            return True
        return False

    @staticmethod
    def search_stocks(session: Session, keyword: str = None, market: str = None) -> List[Stock]:
        """
        搜索股票

        Args:
            session: 数据库会话
            keyword: 关键词(代码或名称)
            market: 市场(SH/SZ)

        Returns:
            股票列表
        """
        query = session.query(Stock)

        conditions = []
        if keyword:
            conditions.append(
                or_(
                    Stock.stock_code.like(f"%{keyword}%"),
                    Stock.stock_name.like(f"%{keyword}%")
                )
            )
        if market:
            conditions.append(Stock.market == market)

        if conditions:
            query = query.filter(and_(*conditions))

        return query.all()


class KLineRepository:
    """K线数据仓库"""

    @staticmethod
    def get_latest_date(session: Session, stock_code: str) -> Optional[date]:
        """
        获取股票最新K线日期

        Args:
            session: 数据库会话
            stock_code: 股票代码

        Returns:
            最新日期或None
        """
        result = session.query(StockKLine.date).filter(
            StockKLine.stock_code == stock_code
        ).order_by(desc(StockKLine.date)).first()

        return result[0] if result else None

    @staticmethod
    def get_recent_klines(session: Session, stock_code: str, days: int = 60) -> List[StockKLine]:
        """
        获取最近N天的K线数据

        Args:
            session: 数据库会话
            stock_code: 股票代码
            days: 天数

        Returns:
            K线数据列表
        """
        return session.query(StockKLine).filter(
            StockKLine.stock_code == stock_code
        ).order_by(desc(StockKLine.date)).limit(days).all()


class AnalysisRepository:
    """分析结果仓库"""

    @staticmethod
    def get_analysis_by_date(session: Session, stock_code: str, analysis_date: date) -> Optional[GeminiAnalysis]:
        """
        获取指定日期的分析结果

        Args:
            session: 数据库会话
            stock_code: 股票代码
            analysis_date: 分析日期

        Returns:
            GeminiAnalysis对象或None
        """
        return session.query(GeminiAnalysis).filter(
            and_(
                GeminiAnalysis.stock_code == stock_code,
                GeminiAnalysis.analysis_date == analysis_date
            )
        ).first()

    @staticmethod
    def save_analysis(
        session: Session,
        stock_code: str,
        analysis_date: date,
        model_name: str,
        analysis_result: Dict[str, Any],
        prompt_tokens: int = 0,
        completion_tokens: int = 0
    ) -> GeminiAnalysis:
        """
        保存分析结果

        Args:
            session: 数据库会话
            stock_code: 股票代码
            analysis_date: 分析日期
            model_name: 模型名称
            analysis_result: 分析结果(字典)
            prompt_tokens: Prompt消耗Token
            completion_tokens: Completion消耗Token

        Returns:
            GeminiAnalysis对象
        """
        # 检查是否已存在
        existing = AnalysisRepository.get_analysis_by_date(session, stock_code, analysis_date)

        if existing:
            # 更新
            existing.model_name = model_name
            existing.analysis_result = analysis_result
            existing.prompt_tokens = prompt_tokens
            existing.completion_tokens = completion_tokens
            existing.created_at = datetime.now()
            session.commit()
            session.refresh(existing)
            return existing
        else:
            # 新建
            analysis = GeminiAnalysis(
                stock_code=stock_code,
                analysis_date=analysis_date,
                model_name=model_name,
                analysis_result=analysis_result,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens
            )
            session.add(analysis)
            session.commit()
            session.refresh(analysis)
            return analysis
