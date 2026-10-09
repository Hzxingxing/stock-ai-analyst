"""
数据同步服务 - 从AKShare获取股票数据并存入数据库
"""
from datetime import datetime, date, timedelta
from typing import Optional
import pandas as pd

from stock_analyzer.data_fetcher import get_stock_data, get_stock_name
from stock_analyzer.indicators import calculate_all_indicators
from stock_analyzer.notice_fetcher import get_stock_notices
from stock_analyzer.financial_fetcher import get_all_financial_data
from stock_analyzer.market_news import get_stock_news
from stock_analyzer.chip_distribution import get_chip_distribution
from stock_analyzer.market_stats import get_market_statistics
from stock_analyzer.valuation_fetcher import get_full_valuation, get_stock_industry
from stock_analyzer.fund_flow_fetcher import get_stock_fund_flow
from stock_analyzer.holder_fetcher import get_holder_count_change, get_top_holders_summary
from stock_analyzer.industry_compare import get_stock_industry_rank
from src.database.connection import get_db_session
from src.database.models import (
    StockKLine, StockAnnouncement, StockFinancial, StockNews,
    StockChipDistribution, MarketStatistics, StockValuation,
    StockFundFlow, StockHolder
)
from src.database.repository import KLineRepository, StockRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DataSyncService:
    """数据同步服务"""

    @staticmethod
    def sync_all_data(stock_code: str, days: int = 250, years: int = 3) -> dict:
        """
        同步单只股票的所有数据

        Args:
            stock_code: 股票代码
            days: K线获取天数
            years: 公告/财务/新闻获取年限

        Returns:
            同步结果
        """
        results = {
            "success": True,
            "details": {}
        }

        try:
            # 1. 同步K线数据
            logger.info(f"开始同步 {stock_code} K线数据...")
            kline_result = DataSyncService.sync_stock_kline(stock_code, days)
            results["details"]["kline"] = kline_result

            # 2. 同步公告数据
            logger.info(f"开始同步 {stock_code} 公告数据...")
            announcement_result = DataSyncService.sync_stock_announcements(stock_code, years)
            results["details"]["announcements"] = announcement_result

            # 3. 同步财务数据
            logger.info(f"开始同步 {stock_code} 财务数据...")
            financial_result = DataSyncService.sync_stock_financials(stock_code, years)
            results["details"]["financials"] = financial_result

            # 4. 同步新闻数据
            logger.info(f"开始同步 {stock_code} 新闻数据...")
            news_result = DataSyncService.sync_stock_news(stock_code, limit=30)
            results["details"]["news"] = news_result

            # 5. 同步筹码分布数据
            logger.info(f"开始同步 {stock_code} 筹码分布数据...")
            chip_result = DataSyncService.sync_chip_distribution(stock_code)
            results["details"]["chip_distribution"] = chip_result

            # 6. 同步估值指标数据
            logger.info(f"开始同步 {stock_code} 估值指标数据...")
            valuation_result = DataSyncService.sync_stock_valuation(stock_code)
            results["details"]["valuation"] = valuation_result

            # 7. 同步资金流向数据
            logger.info(f"开始同步 {stock_code} 资金流向数据...")
            fund_flow_result = DataSyncService.sync_fund_flow(stock_code)
            results["details"]["fund_flow"] = fund_flow_result

            # 8. 同步股东数据
            logger.info(f"开始同步 {stock_code} 股东数据...")
            holder_result = DataSyncService.sync_stock_holder(stock_code)
            results["details"]["holder"] = holder_result

            # 汇总信息
            total_count = sum([
                kline_result.get("count", 0),
                announcement_result.get("count", 0),
                financial_result.get("count", 0),
                news_result.get("count", 0),
                chip_result.get("count", 0),
                valuation_result.get("count", 0),
                fund_flow_result.get("count", 0),
                holder_result.get("count", 0)
            ])

            results["message"] = f"数据同步完成! K线: {kline_result.get('count', 0)}条, " \
                               f"公告: {announcement_result.get('count', 0)}条, " \
                               f"财务: {financial_result.get('count', 0)}条, " \
                               f"新闻: {news_result.get('count', 0)}条, " \
                               f"筹码: {chip_result.get('count', 0)}条, " \
                               f"估值: {valuation_result.get('count', 0)}条, " \
                               f"资金: {fund_flow_result.get('count', 0)}条, " \
                               f"股东: {holder_result.get('count', 0)}条"
            results["total_count"] = total_count

            logger.success(f"股票 {stock_code} 数据同步完成: 共 {total_count} 条")

        except Exception as e:
            logger.error(f"同步股票 {stock_code} 数据失败: {e}", exc_info=True)
            results["success"] = False
            results["message"] = f"同步失败: {str(e)}"

        return results

    @staticmethod
    def sync_stock_kline(stock_code: str, days: int = 250) -> dict:
        """
        同步单只股票的K线数据

        Args:
            stock_code: 股票代码
            days: 获取天数

        Returns:
            同步结果
        """
        try:
            with get_db_session() as session:
                # 检查股票是否存在
                stock = StockRepository.get_stock_by_code(session, stock_code)
                if not stock:
                    return {
                        "success": False,
                        "message": f"股票 {stock_code} 不存在于数据库中"
                    }

                # 获取最新K线日期
                latest_date = KLineRepository.get_latest_date(session, stock_code)

                logger.info(f"开始同步股票 {stock_code} K线数据, 最新日期: {latest_date}")

                # 从AKShare获取数据
                df = get_stock_data(stock_code, days=days)

                if df is None or df.empty:
                    return {
                        "success": True,
                        "message": "未能从AKShare获取到数据（可能非交易日或数据源问题）",
                        "count": 0
                    }

                # 计算技术指标
                df = calculate_all_indicators(df)

                # 检查技术指标计算结果
                if df is None or df.empty:
                    return {
                        "success": False,
                        "message": "技术指标计算失败"
                    }

                # 过滤出需要新增的数据
                if latest_date:
                    # 将latest_date转换为pandas Timestamp以便比较
                    latest_date_ts = pd.Timestamp(latest_date)
                    df = df[df['date'] > latest_date_ts]

                if df.empty:
                    return {
                        "success": True,
                        "message": "数据已是最新,无需同步",
                        "count": 0
                    }

                # 准备插入数据库
                records = []
                for _, row in df.iterrows():
                    record = StockKLine(
                        stock_code=stock_code,
                        date=row['date'],
                        open=float(row['open']) if pd.notna(row['open']) else None,
                        high=float(row['high']) if pd.notna(row['high']) else None,
                        low=float(row['low']) if pd.notna(row['low']) else None,
                        close=float(row['close']) if pd.notna(row['close']) else None,
                        volume=float(row['volume']) if pd.notna(row['volume']) else None,
                        ma5=float(row['ma5']) if pd.notna(row.get('ma5')) else None,
                        ma10=float(row['ma10']) if pd.notna(row.get('ma10')) else None,
                        ma20=float(row['ma20']) if pd.notna(row.get('ma20')) else None,
                        ma60=float(row['ma60']) if pd.notna(row.get('ma60')) else None,
                        macd=float(row['macd']) if pd.notna(row.get('macd')) else None,
                        dif=float(row['dif']) if pd.notna(row.get('dif')) else None,
                        dea=float(row['dea']) if pd.notna(row.get('dea')) else None,
                        rsi=float(row['rsi']) if pd.notna(row.get('rsi')) else None,
                        kdj_k=float(row['k']) if pd.notna(row.get('k')) else None,
                        kdj_d=float(row['d']) if pd.notna(row.get('d')) else None,
                        kdj_j=float(row['j']) if pd.notna(row.get('j')) else None,
                        boll_upper=float(row['boll_upper']) if pd.notna(row.get('boll_upper')) else None,
                        boll_mid=float(row['boll_mid']) if pd.notna(row.get('boll_mid')) else None,
                        boll_lower=float(row['boll_lower']) if pd.notna(row.get('boll_lower')) else None
                    )
                    records.append(record)

                # 批量插入
                session.bulk_save_objects(records)
                session.commit()

                logger.success(f"成功同步股票 {stock_code} K线数据: {len(records)} 条")

                return {
                    "success": True,
                    "message": f"成功同步 {len(records)} 条K线数据",
                    "count": len(records),
                    "latest_date": df['date'].max().strftime('%Y-%m-%d') if not df.empty else None
                }

        except Exception as e:
            logger.error(f"同步股票 {stock_code} K线数据失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"同步失败: {str(e)}"
            }

    @staticmethod
    def sync_stock_announcements(stock_code: str, years: int = 3) -> dict:
        """同步股票公告（增量更新）"""
        try:
            with get_db_session() as session:
                # 查询数据库中该股票最新的公告日期
                latest_record = session.query(StockAnnouncement).filter_by(
                    stock_code=stock_code
                ).order_by(StockAnnouncement.announcement_date.desc()).first()

                start_date = None
                if latest_record and latest_record.announcement_date:
                    # 从最新日期的后一天开始拉取
                    next_day = latest_record.announcement_date + timedelta(days=1)
                    start_date = next_day.strftime("%Y%m%d")
                    logger.info(f"股票 {stock_code} 公告增量更新，从 {start_date} 开始")
                else:
                    logger.info(f"股票 {stock_code} 公告首次全量拉取，获取近 {years} 年数据")

                # 调用公告获取函数（支持增量）
                df = get_stock_notices(stock_code, years=years, start_date=start_date)

                if df is None or df.empty:
                    if start_date:
                        return {"success": True, "message": "无新增公告", "count": 0}
                    return {"success": True, "message": "暂无公告数据", "count": 0}

                # 逐条插入新数据（仍需去重以防边界情况）
                success_count = 0
                for _, row in df.iterrows():
                    try:
                        announcement_date = row.get('date')
                        title = row.get('title', '')

                        # 检查是否已存在
                        existing = session.query(StockAnnouncement).filter_by(
                            stock_code=stock_code,
                            announcement_date=announcement_date,
                            title=title
                        ).first()

                        if not existing:
                            record = StockAnnouncement(
                                stock_code=stock_code,
                                announcement_date=announcement_date,
                                announcement_type='其他',
                                title=title,
                                content=''
                            )
                            session.add(record)
                            session.commit()
                            success_count += 1
                    except Exception as e:
                        session.rollback()
                        logger.debug(f"插入公告失败: {str(e)}")
                        continue

                if success_count > 0:
                    return {"success": True, "count": success_count, "message": f"成功插入 {success_count} 条新公告"}
                else:
                    return {"success": True, "count": 0, "message": "数据已是最新,无需同步"}

        except Exception as e:
            logger.error(f"同步公告失败: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e), "count": 0}

    @staticmethod
    def sync_stock_financials(stock_code: str, years: int = 5) -> dict:
        """同步财务数据（增量更新，默认5年）"""
        try:
            with get_db_session() as session:
                # 查询数据库中该股票最新的财务报告日期
                latest_record = session.query(StockFinancial).filter_by(
                    stock_code=stock_code
                ).order_by(StockFinancial.report_date.desc()).first()

                # 计算需要获取多少期数据
                if latest_record and latest_record.report_date:
                    # 计算从最新报告日期到现在的季度数
                    from datetime import datetime
                    latest_date = latest_record.report_date
                    now = datetime.now()
                    # 计算差了多少个季度（每年4个季度）
                    months_diff = (now.year - latest_date.year) * 12 + (now.month - latest_date.month)
                    periods = max(4, (months_diff // 3) + 2)  # 至少获取4期，多获取2期确保完整
                    logger.info(f"股票 {stock_code} 财务数据增量更新，最新报告期 {latest_date}，获取 {periods} 期数据")
                else:
                    # 首次全量拉取
                    periods = (years + 1) * 4
                    logger.info(f"股票 {stock_code} 财务数据首次全量拉取，获取 {periods} 期数据")

                financial_data = get_all_financial_data(stock_code, years=years)

                # 检查返回的数据结构
                if not isinstance(financial_data, dict):
                    return {"success": True, "message": "暂无财务数据", "count": 0}

                # 从利润表DataFrame提取数据
                profit_df = financial_data.get('profit')
                if profit_df is None or (isinstance(profit_df, pd.DataFrame) and profit_df.empty):
                    return {"success": True, "message": "暂无财务数据", "count": 0}

                # 如果有最新记录，过滤出更新的数据
                if latest_record and latest_record.report_date:
                    profit_df = profit_df[profit_df['report_date'] > pd.Timestamp(latest_record.report_date)]
                    if profit_df.empty:
                        return {"success": True, "message": "财务数据已是最新，无需同步", "count": 0}

                records = []
                for _, row in profit_df.iterrows():
                    record = StockFinancial(
                        stock_code=stock_code,
                        report_date=row.get('report_date'),
                        revenue=row.get('revenue'),
                        net_profit=row.get('net_profit'),
                        eps=row.get('eps'),
                        roe=None,  # ROE需要从indicators获取
                        debt_ratio=None  # 资产负债率需要从balance sheet计算
                    )
                    records.append(record)

                if not records:
                    return {"success": True, "message": "无新增财务数据", "count": 0}

                # 批量插入，忽略重复记录
                try:
                    session.bulk_save_objects(records)
                    session.commit()
                    logger.info(f"股票 {stock_code} 成功插入 {len(records)} 条财务数据")
                    return {"success": True, "count": len(records), "message": f"成功插入 {len(records)} 条财务数据"}
                except Exception as insert_error:
                    # 如果批量插入失败（通常是重复键），逐条插入并跳过重复
                    session.rollback()
                    success_count = 0
                    for record in records:
                        try:
                            # 检查记录是否已存在
                            existing = session.query(StockFinancial).filter_by(
                                stock_code=record.stock_code,
                                report_date=record.report_date
                            ).first()

                            if not existing:
                                session.add(record)
                                session.commit()
                                success_count += 1
                            else:
                                # 更新现有记录
                                existing.revenue = record.revenue
                                existing.net_profit = record.net_profit
                                existing.eps = record.eps
                                session.commit()
                        except:
                            session.rollback()
                            continue

                    return {"success": True, "count": success_count, "message": f"成功插入/更新 {success_count} 条记录"}

        except Exception as e:
            logger.error(f"同步财务数据失败: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e), "count": 0}

    @staticmethod
    def sync_stock_news(stock_code: str, limit: int = 50) -> dict:
        """同步新闻数据（增加limit到50以获取更多新闻）"""
        try:
            with get_db_session() as session:
                # 获取股票名称
                stock_name = get_stock_name(stock_code)

                # 获取新闻列表
                news_list = get_stock_news(stock_code, stock_name, limit=limit)

                if not news_list:
                    return {"success": True, "message": "暂无新闻数据", "count": 0}

                # 改为逐条检查并插入（强制去重）
                success_count = 0
                for item in news_list:
                    try:
                        news_date = item.get('date') or item.get('time')
                        title = item.get('title', '')

                        # 检查是否已存在
                        existing = session.query(StockNews).filter_by(
                            stock_code=stock_code,
                            news_date=news_date,
                            title=title
                        ).first()

                        if not existing:
                            # 简单的情感分析
                            sentiment = '中性'
                            title_content = title + item.get('content', '')
                            if any(word in title_content for word in ['利好', '增长', '突破', '创新高', '大涨', '获批', '中标']):
                                sentiment = '正面'
                            elif any(word in title_content for word in ['利空', '下跌', '亏损', '减持', '失败', '暴跌', '处罚']):
                                sentiment = '负面'

                            record = StockNews(
                                stock_code=stock_code,
                                news_date=news_date,
                                news_type=item.get('type', '资讯'),
                                title=title,
                                content=item.get('content', ''),
                                source=item.get('source'),  # 保存来源
                                url=item.get('url'),  # 保存URL
                                sentiment=sentiment
                            )
                            session.add(record)
                            session.commit()
                            success_count += 1
                    except Exception as e:
                        session.rollback()
                        logger.debug(f"插入新闻失败: {str(e)}")
                        continue

                if success_count > 0:
                    return {"success": True, "count": success_count, "message": f"成功插入 {success_count} 条新新闻"}
                else:
                    return {"success": True, "count": 0, "message": "数据已是最新,无需同步"}

        except Exception as e:
            logger.error(f"同步新闻数据失败: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e), "count": 0}

    @staticmethod
    def sync_chip_distribution(stock_code: str, days: int = None) -> dict:
        """同步筹码分布数据（默认获取所有可用数据）"""
        try:
            with get_db_session() as session:
                df = get_chip_distribution(stock_code, days=days)

                if df is None or df.empty:
                    return {"success": True, "message": "暂无筹码分布数据", "count": 0}

                # 逐条检查并插入
                success_count = 0
                for _, row in df.iterrows():
                    try:
                        chip_date = row.get('date')

                        # 检查是否已存在
                        existing = session.query(StockChipDistribution).filter_by(
                            stock_code=stock_code,
                            date=chip_date
                        ).first()

                        if not existing:
                            record = StockChipDistribution(
                                stock_code=stock_code,
                                date=chip_date,
                                profit_ratio=float(row['profit_ratio']) if pd.notna(row.get('profit_ratio')) else None,
                                avg_cost=float(row['avg_cost']) if pd.notna(row.get('avg_cost')) else None,
                                cost_90_low=float(row['cost_90_low']) if pd.notna(row.get('cost_90_low')) else None,
                                cost_90_high=float(row['cost_90_high']) if pd.notna(row.get('cost_90_high')) else None,
                                concentration_90=float(row['concentration_90']) if pd.notna(row.get('concentration_90')) else None,
                                cost_70_low=float(row['cost_70_low']) if pd.notna(row.get('cost_70_low')) else None,
                                cost_70_high=float(row['cost_70_high']) if pd.notna(row.get('cost_70_high')) else None,
                                concentration_70=float(row['concentration_70']) if pd.notna(row.get('concentration_70')) else None
                            )
                            session.add(record)
                            session.commit()
                            success_count += 1
                    except Exception as e:
                        session.rollback()
                        logger.debug(f"插入筹码分布失败: {str(e)}")
                        continue

                if success_count > 0:
                    return {"success": True, "count": success_count, "message": f"成功插入 {success_count} 条筹码分布"}
                else:
                    return {"success": True, "count": 0, "message": "数据已是最新,无需同步"}

        except Exception as e:
            logger.error(f"同步筹码分布失败: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e), "count": 0}

    @staticmethod
    def sync_market_statistics() -> dict:
        """同步市场统计数据（全市场）"""
        try:
            with get_db_session() as session:
                stats = get_market_statistics()

                if not stats:
                    return {"success": False, "message": "获取市场统计失败"}

                stat_date = stats['stat_date']

                # 检查今天是否已存在
                existing = session.query(MarketStatistics).filter_by(
                    stat_date=stat_date
                ).first()

                if existing:
                    # 更新现有记录
                    for key, value in stats.items():
                        if key != 'stat_date':
                            setattr(existing, key, value)
                    session.commit()
                    return {"success": True, "message": "市场统计已更新", "count": 1}
                else:
                    # 插入新记录
                    record = MarketStatistics(**stats)
                    session.add(record)
                    session.commit()
                    return {"success": True, "message": "市场统计已保存", "count": 1}

        except Exception as e:
            logger.error(f"同步市场统计失败: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e), "count": 0}

    @staticmethod
    def sync_stock_valuation(stock_code: str) -> dict:
        """
        同步股票估值指标数据

        Args:
            stock_code: 股票代码

        Returns:
            同步结果
        """
        try:
            with get_db_session() as session:
                # 获取估值数据
                valuation_data = get_full_valuation(stock_code)

                if not valuation_data:
                    return {"success": True, "message": "暂无估值数据", "count": 0}

                valuation_date = valuation_data.get('date')
                if not valuation_date:
                    return {"success": True, "message": "估值数据无日期", "count": 0}

                # 检查是否已存在
                existing = session.query(StockValuation).filter_by(
                    stock_code=stock_code,
                    date=valuation_date
                ).first()

                if existing:
                    # 更新现有记录
                    existing.pe_ttm = valuation_data.get('pe_ttm')
                    existing.pe_static = valuation_data.get('pe_static')
                    existing.pb = valuation_data.get('pb')
                    existing.ps_ttm = valuation_data.get('ps_ttm')
                    existing.total_mv = valuation_data.get('total_mv')
                    existing.circ_mv = valuation_data.get('circ_mv')
                    existing.dividend_yield = valuation_data.get('dividend_yield')
                    existing.industry = valuation_data.get('industry')
                    existing.industry_pe = valuation_data.get('industry_pe')
                    existing.industry_pb = valuation_data.get('industry_pb')
                    session.commit()
                    return {"success": True, "message": "估值数据已更新", "count": 1}
                else:
                    # 插入新记录
                    record = StockValuation(
                        stock_code=stock_code,
                        date=valuation_date,
                        pe_ttm=valuation_data.get('pe_ttm'),
                        pe_static=valuation_data.get('pe_static'),
                        pb=valuation_data.get('pb'),
                        ps_ttm=valuation_data.get('ps_ttm'),
                        total_mv=valuation_data.get('total_mv'),
                        circ_mv=valuation_data.get('circ_mv'),
                        dividend_yield=valuation_data.get('dividend_yield'),
                        industry=valuation_data.get('industry'),
                        industry_pe=valuation_data.get('industry_pe'),
                        industry_pb=valuation_data.get('industry_pb')
                    )
                    session.add(record)
                    session.commit()
                    return {"success": True, "message": "估值数据已保存", "count": 1}

        except Exception as e:
            logger.error(f"同步估值数据失败: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e), "count": 0}

    @staticmethod
    def sync_fund_flow(stock_code: str, days: int = 30) -> dict:
        """
        同步股票资金流向数据

        Args:
            stock_code: 股票代码
            days: 获取天数

        Returns:
            同步结果
        """
        try:
            with get_db_session() as session:
                # 获取资金流向数据
                df = get_stock_fund_flow(stock_code, days=days)

                if df is None or df.empty:
                    return {"success": True, "message": "暂无资金流向数据", "count": 0}

                # 逐条检查并插入
                success_count = 0
                for _, row in df.iterrows():
                    try:
                        flow_date = row.get('date')

                        # 检查是否已存在
                        existing = session.query(StockFundFlow).filter_by(
                            stock_code=stock_code,
                            date=flow_date
                        ).first()

                        if not existing:
                            record = StockFundFlow(
                                stock_code=stock_code,
                                date=flow_date,
                                close_price=float(row['close_price']) if pd.notna(row.get('close_price')) else None,
                                change_pct=float(row['change_pct']) if pd.notna(row.get('change_pct')) else None,
                                main_net_inflow=float(row['main_net_inflow']) if pd.notna(row.get('main_net_inflow')) else None,
                                main_net_inflow_pct=float(row['main_net_inflow_pct']) if pd.notna(row.get('main_net_inflow_pct')) else None,
                                super_large_net_inflow=float(row['super_large_net_inflow']) if pd.notna(row.get('super_large_net_inflow')) else None,
                                super_large_net_inflow_pct=float(row['super_large_net_inflow_pct']) if pd.notna(row.get('super_large_net_inflow_pct')) else None,
                                large_net_inflow=float(row['large_net_inflow']) if pd.notna(row.get('large_net_inflow')) else None,
                                large_net_inflow_pct=float(row['large_net_inflow_pct']) if pd.notna(row.get('large_net_inflow_pct')) else None,
                                medium_net_inflow=float(row['medium_net_inflow']) if pd.notna(row.get('medium_net_inflow')) else None,
                                medium_net_inflow_pct=float(row['medium_net_inflow_pct']) if pd.notna(row.get('medium_net_inflow_pct')) else None,
                                small_net_inflow=float(row['small_net_inflow']) if pd.notna(row.get('small_net_inflow')) else None,
                                small_net_inflow_pct=float(row['small_net_inflow_pct']) if pd.notna(row.get('small_net_inflow_pct')) else None
                            )
                            session.add(record)
                            session.commit()
                            success_count += 1
                    except Exception as e:
                        session.rollback()
                        logger.debug(f"插入资金流向失败: {str(e)}")
                        continue

                if success_count > 0:
                    return {"success": True, "count": success_count, "message": f"成功插入 {success_count} 条资金流向"}
                else:
                    return {"success": True, "count": 0, "message": "数据已是最新,无需同步"}

        except Exception as e:
            logger.error(f"同步资金流向失败: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e), "count": 0}

    @staticmethod
    def sync_stock_holder(stock_code: str) -> dict:
        """
        同步股票股东数据

        Args:
            stock_code: 股票代码

        Returns:
            同步结果
        """
        try:
            with get_db_session() as session:
                # 获取股东人数变化
                holder_change = get_holder_count_change(stock_code)
                # 获取十大股东汇总
                top_holders = get_top_holders_summary(stock_code)

                if not holder_change and not top_holders:
                    return {"success": True, "message": "暂无股东数据", "count": 0}

                # 确定报告期
                report_date = None
                if holder_change and holder_change.get('report_date'):
                    report_date = holder_change.get('report_date')
                elif top_holders and top_holders.get('report_date'):
                    report_date = top_holders.get('report_date')

                if not report_date:
                    return {"success": True, "message": "无法确定报告期", "count": 0}

                # 检查是否已存在
                existing = session.query(StockHolder).filter_by(
                    stock_code=stock_code,
                    report_date=report_date
                ).first()

                if existing:
                    # 更新现有记录
                    if holder_change:
                        existing.total_holders = holder_change.get('total_holders')
                        existing.avg_hold_num = holder_change.get('avg_hold_num')
                        existing.holder_change = holder_change.get('holder_change')
                        existing.holder_change_pct = holder_change.get('holder_change_pct')
                        existing.concentration_trend = holder_change.get('concentration_trend')
                    if top_holders:
                        existing.top10_hold_ratio = top_holders.get('top10_hold_ratio')
                        existing.first_holder_name = top_holders.get('first_holder_name')
                        existing.first_holder_ratio = top_holders.get('first_holder_ratio')
                        existing.control_type = top_holders.get('control_type')
                        existing.top_holders_detail = top_holders.get('holders')
                    session.commit()
                    return {"success": True, "message": "股东数据已更新", "count": 1}
                else:
                    # 插入新记录
                    record = StockHolder(
                        stock_code=stock_code,
                        report_date=report_date,
                        total_holders=holder_change.get('total_holders') if holder_change else None,
                        avg_hold_num=holder_change.get('avg_hold_num') if holder_change else None,
                        holder_change=holder_change.get('holder_change') if holder_change else None,
                        holder_change_pct=holder_change.get('holder_change_pct') if holder_change else None,
                        concentration_trend=holder_change.get('concentration_trend') if holder_change else None,
                        top10_hold_ratio=top_holders.get('top10_hold_ratio') if top_holders else None,
                        first_holder_name=top_holders.get('first_holder_name') if top_holders else None,
                        first_holder_ratio=top_holders.get('first_holder_ratio') if top_holders else None,
                        control_type=top_holders.get('control_type') if top_holders else None,
                        top_holders_detail=top_holders.get('holders') if top_holders else None
                    )
                    session.add(record)
                    session.commit()
                    return {"success": True, "message": "股东数据已保存", "count": 1}

        except Exception as e:
            logger.error(f"同步股东数据失败: {str(e)}", exc_info=True)
            return {"success": False, "message": str(e), "count": 0}


# 全局单例
_data_sync_service = None


def get_data_sync_service() -> DataSyncService:
    """获取数据同步服务实例"""
    global _data_sync_service
    if _data_sync_service is None:
        _data_sync_service = DataSyncService()
    return _data_sync_service
