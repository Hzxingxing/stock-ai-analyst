"""Gemini AI分析服务 - 使用NewAPI调用Gemini进行股票分析"""
import os
import json
from datetime import datetime, date
from typing import Dict, List, Optional
from openai import OpenAI

from src.database.connection import get_db_session
from src.database.repository import KLineRepository, AnalysisRepository
from src.database.models import Stock, StockFinancial, StockAnnouncement, StockNews, GeminiAnalysis, StockChipDistribution, StockValuation, StockFundFlow, StockHolder
from src.utils.logger import get_logger
from src.utils.config_manager import get_config_manager

logger = get_logger(__name__)


class GeminiAnalyzer:
    """Gemini分析器 - 通过NewAPI调用Gemini模型分析股票"""

    def __init__(self):
        """初始化Gemini分析器"""
        # 从环境变量获取NewAPI配置
        self.api_key = os.getenv('NEWAPI_KEY')
        base_url = os.getenv('NEWAPI_ENDPOINT')

        if not self.api_key or not base_url:
            raise ValueError("NEWAPI_KEY 和 NEWAPI_ENDPOINT 环境变量必须设置")

        # 确保base_url以/v1结尾（OpenAI兼容接口路径）
        if not base_url.endswith('/v1'):
            base_url = base_url.rstrip('/') + '/v1'

        self.base_url = base_url

        # 从配置文件获取模型配置
        config_manager = get_config_manager()
        self.model = config_manager.get('gemini.model', 'gemini-2.0-flash-exp')
        self.temperature = config_manager.get('gemini.temperature', 0.7)
        self.timeout = config_manager.get('gemini.timeout', 60)

        # 初始化OpenAI客户端（NewAPI兼容OpenAI接口）
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        logger.info(f"Gemini分析器初始化完成 - Model: {self.model}, Endpoint: {self.base_url}")

    def analyze_stock(self, stock_code: str) -> Dict:
        """
        分析单只股票

        Args:
            stock_code: 股票代码

        Returns:
            分析结果字典
        """
        try:
            logger.info(f"开始分析股票: {stock_code}")

            # 1. 收集分析数据
            analysis_data = self._collect_analysis_data(stock_code)

            if not analysis_data:
                return {
                    "success": False,
                    "message": "无法收集到足够的分析数据"
                }

            # 2. 构建分析prompt
            prompt = self._build_analysis_prompt(analysis_data)

            # 3. 调用Gemini API
            analysis_result = self._call_gemini_api(prompt)

            if not analysis_result:
                return {
                    "success": False,
                    "message": "AI分析失败"
                }

            # 4. 保存分析结果到数据库
            self._save_analysis_result(stock_code, analysis_result)

            logger.success(f"股票 {stock_code} 分析完成")

            return {
                "success": True,
                "message": "分析完成",
                "data": analysis_result
            }

        except Exception as e:
            logger.error(f"分析股票 {stock_code} 失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"分析失败: {str(e)}"
            }

    def _collect_analysis_data(self, stock_code: str) -> Optional[Dict]:
        """收集股票分析所需数据"""
        try:
            with get_db_session() as session:
                # 获取股票基本信息
                stock = session.query(Stock).filter_by(stock_code=stock_code).first()
                if not stock:
                    logger.warning(f"股票 {stock_code} 不存在")
                    return None

                # 获取最近60日K线数据
                klines = KLineRepository.get_recent_klines(session, stock_code, 60)
                if not klines:
                    logger.warning(f"股票 {stock_code} 无K线数据")
                    return None

                # 获取最近财务数据
                financials = session.query(StockFinancial).filter_by(
                    stock_code=stock_code
                ).order_by(StockFinancial.report_date.desc()).limit(4).all()

                # 获取最近公告
                announcements = session.query(StockAnnouncement).filter_by(
                    stock_code=stock_code
                ).order_by(StockAnnouncement.announcement_date.desc()).limit(10).all()

                # 获取最近新闻
                news = session.query(StockNews).filter_by(
                    stock_code=stock_code
                ).order_by(StockNews.news_date.desc()).limit(10).all()

                # 获取最近筹码分布数据
                chip_distributions = session.query(StockChipDistribution).filter_by(
                    stock_code=stock_code
                ).order_by(StockChipDistribution.date.desc()).limit(5).all()

                # 获取最近估值指标数据
                valuations = session.query(StockValuation).filter_by(
                    stock_code=stock_code
                ).order_by(StockValuation.date.desc()).limit(5).all()

                # 获取最近资金流向数据
                fund_flows = session.query(StockFundFlow).filter_by(
                    stock_code=stock_code
                ).order_by(StockFundFlow.date.desc()).limit(10).all()

                # 获取最近股东数据
                holders = session.query(StockHolder).filter_by(
                    stock_code=stock_code
                ).order_by(StockHolder.report_date.desc()).limit(2).all()

                # 将ORM对象转换为字典，以便在session外使用
                return {
                    "stock": {
                        "stock_code": stock.stock_code,
                        "stock_name": stock.stock_name,
                        "market": stock.market
                    },
                    "klines": [
                        {
                            "date": k.date,
                            "open": k.open,
                            "close": k.close,
                            "high": k.high,
                            "low": k.low,
                            "volume": k.volume,
                            "ma5": k.ma5,
                            "ma10": k.ma10,
                            "ma20": k.ma20,
                            "ma60": k.ma60,
                            "macd": k.macd,
                            "rsi": k.rsi,
                            "kdj_k": k.kdj_k,
                            "kdj_d": k.kdj_d,
                            "kdj_j": k.kdj_j
                        }
                        for k in klines
                    ],
                    "financials": [
                        {
                            "report_date": f.report_date,
                            "revenue": f.revenue,
                            "net_profit": f.net_profit,
                            "eps": f.eps,
                            "roe": f.roe,
                            "debt_ratio": f.debt_ratio
                        }
                        for f in financials
                    ],
                    "announcements": [
                        {
                            "announcement_date": a.announcement_date,
                            "announcement_type": a.announcement_type,
                            "title": a.title
                        }
                        for a in announcements
                    ],
                    "news": [
                        {
                            "news_date": n.news_date,
                            "title": n.title,
                            "sentiment": n.sentiment
                        }
                        for n in news
                    ],
                    "chip_distributions": [
                        {
                            "date": c.date,
                            "profit_ratio": c.profit_ratio,
                            "avg_cost": c.avg_cost,
                            "cost_90_low": c.cost_90_low,
                            "cost_90_high": c.cost_90_high,
                            "concentration_90": c.concentration_90,
                            "cost_70_low": c.cost_70_low,
                            "cost_70_high": c.cost_70_high,
                            "concentration_70": c.concentration_70
                        }
                        for c in chip_distributions
                    ],
                    "valuations": [
                        {
                            "date": v.date,
                            "pe_ttm": v.pe_ttm,
                            "pe_static": v.pe_static,
                            "pb": v.pb,
                            "ps_ttm": v.ps_ttm,
                            "total_mv": v.total_mv,
                            "circ_mv": v.circ_mv,
                            "dividend_yield": v.dividend_yield,
                            "industry": v.industry,
                            "industry_pe": v.industry_pe,
                            "industry_pb": v.industry_pb
                        }
                        for v in valuations
                    ],
                    "fund_flows": [
                        {
                            "date": f.date,
                            "close_price": f.close_price,
                            "change_pct": f.change_pct,
                            "main_net_inflow": f.main_net_inflow,
                            "main_net_inflow_pct": f.main_net_inflow_pct,
                            "super_large_net_inflow": f.super_large_net_inflow,
                            "large_net_inflow": f.large_net_inflow,
                            "small_net_inflow": f.small_net_inflow
                        }
                        for f in fund_flows
                    ],
                    "holders": [
                        {
                            "report_date": h.report_date,
                            "total_holders": h.total_holders,
                            "holder_change": h.holder_change,
                            "holder_change_pct": h.holder_change_pct,
                            "top10_hold_ratio": h.top10_hold_ratio,
                            "first_holder_name": h.first_holder_name,
                            "first_holder_ratio": h.first_holder_ratio,
                            "concentration_trend": h.concentration_trend,
                            "control_type": h.control_type
                        }
                        for h in holders
                    ]
                }

        except Exception as e:
            logger.error(f"收集分析数据失败: {e}", exc_info=True)
            return None

    def _build_data_context(self, data: Dict) -> str:
        """构建数据上下文（供两阶段分析使用）"""
        stock = data['stock']
        klines = data['klines']
        financials = data['financials']
        announcements = data['announcements']
        news = data['news']
        chip_distributions = data.get('chip_distributions', [])
        valuations = data.get('valuations', [])
        fund_flows = data.get('fund_flows', [])
        holders = data.get('holders', [])

        # 最新K线数据
        latest_kline = klines[0] if klines else None

        context = f"""【基本信息】
股票代码：{stock['stock_code']}
股票名称：{stock['stock_name']}
市场：{stock['market']}

【最新行情】（{latest_kline['date'] if latest_kline else 'N/A'}）
"""

        if latest_kline:
            open_price = latest_kline['open']
            close_price = latest_kline['close']
            change_pct = ((close_price - open_price) / open_price * 100) if open_price else 0

            context += f"""开盘价：{open_price}
收盘价：{close_price}
最高价：{latest_kline['high']}
最低价：{latest_kline['low']}
成交量：{latest_kline['volume']}
涨跌幅：{change_pct:.2f}%

【技术指标】
MA5：{latest_kline['ma5']}
MA10：{latest_kline['ma10']}
MA20：{latest_kline['ma20']}
MA60：{latest_kline['ma60']}
MACD：{latest_kline['macd']}
RSI：{latest_kline['rsi']}
KDJ_K：{latest_kline['kdj_k']}
KDJ_D：{latest_kline['kdj_d']}
KDJ_J：{latest_kline['kdj_j']}

"""

        # 估值指标
        if valuations:
            latest_val = valuations[0]
            context += f"【估值指标】（{latest_val['date']}）\n"
            if latest_val.get('pe_ttm'):
                context += f"市盈率(TTM): {latest_val['pe_ttm']:.2f}\n"
            if latest_val.get('pe_static'):
                context += f"市盈率(静态): {latest_val['pe_static']:.2f}\n"
            if latest_val.get('pb'):
                context += f"市净率: {latest_val['pb']:.2f}\n"
            if latest_val.get('ps_ttm'):
                context += f"市销率(TTM): {latest_val['ps_ttm']:.2f}\n"
            if latest_val.get('dividend_yield'):
                context += f"股息率: {latest_val['dividend_yield']:.2f}%\n"
            if latest_val.get('total_mv'):
                context += f"总市值: {latest_val['total_mv']/100000000:.2f}亿元\n"
            if latest_val.get('circ_mv'):
                context += f"流通市值: {latest_val['circ_mv']/100000000:.2f}亿元\n"

            # 行业对比
            if latest_val.get('industry'):
                context += f"\n【行业对比】（{latest_val['industry']}）\n"
                if latest_val.get('industry_pe'):
                    pe_diff = ((latest_val.get('pe_ttm', 0) or 0) - latest_val['industry_pe']) / latest_val['industry_pe'] * 100 if latest_val['industry_pe'] else 0
                    context += f"行业平均PE: {latest_val['industry_pe']:.2f} (个股{'高于' if pe_diff > 0 else '低于'}行业{abs(pe_diff):.1f}%)\n"
                if latest_val.get('industry_pb'):
                    pb_diff = ((latest_val.get('pb', 0) or 0) - latest_val['industry_pb']) / latest_val['industry_pb'] * 100 if latest_val['industry_pb'] else 0
                    context += f"行业平均PB: {latest_val['industry_pb']:.2f} (个股{'高于' if pb_diff > 0 else '低于'}行业{abs(pb_diff):.1f}%)\n"
            context += "\n"

        # 近期走势（含筹码变化）
        context += "【近期走势】（最近10天）\n"
        for i, kline in enumerate(klines[:10]):
            open_price = kline['open']
            close_price = kline['close']
            change_pct = ((close_price - open_price) / open_price * 100) if open_price else 0
            # 找对应日期的筹码数据
            chip_info = ""
            if chip_distributions:
                for chip in chip_distributions:
                    if chip['date'] == kline['date']:
                        chip_info = f" | 获利比例:{chip['profit_ratio']}%, 集中度90:{chip['concentration_90']}"
                        break
            context += f"{kline['date']}: 收盘{close_price}, 涨跌{change_pct:+.2f}%, 成交量{kline['volume']}{chip_info}\n"

        # 筹码分布详情
        if chip_distributions:
            latest_chip = chip_distributions[0]
            context += f"\n【筹码分布详情】（{latest_chip['date']}）\n"
            context += f"获利比例: {latest_chip['profit_ratio']}%\n"
            context += f"平均成本: {latest_chip['avg_cost']}元\n"
            context += f"90%成本区间: {latest_chip['cost_90_low']} - {latest_chip['cost_90_high']}元\n"
            context += f"90%集中度: {latest_chip['concentration_90']}\n"
            context += f"70%成本区间: {latest_chip['cost_70_low']} - {latest_chip['cost_70_high']}元\n"
            context += f"70%集中度: {latest_chip['concentration_70']}\n"
            # 筹码变化趋势
            if len(chip_distributions) > 1:
                prev_chip = chip_distributions[1]
                profit_change = (latest_chip['profit_ratio'] or 0) - (prev_chip['profit_ratio'] or 0)
                context += f"获利比例变化: {profit_change:+.2f}%（相比{prev_chip['date']}）\n"

        # 资金流向
        if fund_flows:
            context += "\n【资金流向】（最近10日）\n"
            total_main_inflow = 0
            total_small_inflow = 0
            for f in fund_flows:
                main_inflow = f['main_net_inflow'] or 0
                small_inflow = f['small_net_inflow'] or 0
                total_main_inflow += main_inflow
                total_small_inflow += small_inflow
                context += f"{f['date']}: 主力{'流入' if main_inflow >= 0 else '流出'}{abs(main_inflow)/10000:.2f}万, 散户{'流入' if small_inflow >= 0 else '流出'}{abs(small_inflow)/10000:.2f}万\n"

            context += f"\n近期资金汇总:\n"
            context += f"- 主力累计: {'流入' if total_main_inflow >= 0 else '流出'}{abs(total_main_inflow)/10000:.2f}万元\n"
            context += f"- 散户累计: {'流入' if total_small_inflow >= 0 else '流出'}{abs(total_small_inflow)/10000:.2f}万元\n"

            # 判断背离
            if total_main_inflow > 0 and total_small_inflow < 0:
                context += "- 背离判断: 主力吸筹、散户出货（看涨背离）\n"
            elif total_main_inflow < 0 and total_small_inflow > 0:
                context += "- 背离判断: 主力出货、散户接盘（看跌背离）\n"
            else:
                context += "- 背离判断: 无明显背离\n"

        # 股东数据
        if holders:
            latest_holder = holders[0]
            context += f"\n【股东数据】（{latest_holder['report_date']}）\n"
            if latest_holder['total_holders']:
                context += f"股东人数: {latest_holder['total_holders']}\n"
            if latest_holder['holder_change']:
                context += f"人数变化: {latest_holder['holder_change']:+d} ({latest_holder['holder_change_pct']:+.2f}%)\n"
            if latest_holder['top10_hold_ratio']:
                context += f"十大股东合计持股: {latest_holder['top10_hold_ratio']:.2f}%\n"
            if latest_holder['first_holder_name']:
                context += f"第一大股东: {latest_holder['first_holder_name']} ({latest_holder['first_holder_ratio']:.2f}%)\n"
            if latest_holder['concentration_trend']:
                context += f"筹码集中度趋势: {latest_holder['concentration_trend']}\n"
            if latest_holder['control_type']:
                context += f"控股类型: {latest_holder['control_type']}\n"

        # 财务数据
        if financials:
            context += "\n【财务数据】（最近4期）\n"
            for f in financials:
                context += f"{f['report_date']}: 营收{f['revenue']}亿, 净利润{f['net_profit']}亿, EPS{f['eps']}\n"

        # 重要公告
        if announcements:
            context += "\n【重要公告】（最近10条）\n"
            for a in announcements:
                context += f"{a['announcement_date']} [{a['announcement_type']}] {a['title']}\n"

        # 相关新闻
        if news:
            context += "\n【相关新闻】（最近10条）\n"
            for n in news:
                sentiment_tag = f"[{n['sentiment']}]" if n['sentiment'] else ""
                context += f"{n['news_date']} {sentiment_tag} {n['title']}\n"

        return context

    def _build_phase1_prompt(self, data: Dict) -> str:
        """构建第一阶段prompt - 自由深度分析"""
        stock = data['stock']
        context = self._build_data_context(data)

        prompt = f"""你是一位资深的A股分析师，擅长从多维度数据中洞察投资机会和风险。

请基于以下{stock['stock_code']} {stock['stock_name']}的数据进行深度分析：

{context}

请按以下结构进行专业分析，要求结合具体数据，给出有深度的见解：

## 一、核心结论
用一句话概括当前股票的核心投资逻辑（例如：业绩驱动的主升浪、估值修复行情、题材炒作等）

## 二、数据深度拆解

### 1. 筹码与资金分析
- 分析获利比例变化的含义（是否存在主力锁仓、获利盘抛压等）
- 筹码集中度解读（集中度数值越小代表筹码越密集）
- 平均成本与当前价位的关系（支撑位、压力位判断）
- 主力与散户资金的博弈关系

### 2. 技术面分析
- K线形态特征（放量突破、缩量洗盘、滞涨出货等）
- 均线系统状态（多头排列、空头排列、粘合突破等）
- 关键技术指标信号（MACD金叉/死叉、RSI超买超卖、KDJ信号）
- 量价配合情况

### 3. 消息面与基本面
- 近期重要公告/新闻解读（业绩预告、重大合同、政策利好等）
- 业绩变化趋势及原因分析
- 所属板块/概念的市场热度

## 三、投资风险与机会评估

### 机会点
列举2-3个核心投资机会，结合数据说明

### 风险点
列举2-3个需要警惕的风险，结合数据说明

## 四、后市研判

### 支撑位与压力位
基于筹码分布和技术面给出具体价位

### 操作策略建议
给出明确的操作建议（买入条件、止损位、止盈目标等）

请确保分析有理有据，引用具体数据支撑观点。"""

        return prompt

    def _build_phase2_prompt(self, analysis_text: str, data: Dict) -> str:
        """构建第二阶段prompt - 提取结构化数据"""
        stock = data['stock']

        prompt = f"""基于以下对{stock['stock_code']} {stock['stock_name']}的分析报告，提取结构化的评分和关键信息。

分析报告：
{analysis_text}

请严格按以下JSON格式输出，不要包含其他文字：
{{
  "technical_score": 0-100的技术面评分,
  "fundamental_score": 0-100的基本面评分,
  "valuation_score": 0-100的估值评分,
  "fund_flow_score": 0-100的资金面评分,
  "holder_score": 0-100的筹码评分,
  "risk_level": "低/中/高",
  "suggestion": "买入/持有/观望/卖出",
  "target_price": 预期目标价格（数字，基于分析中的压力位）,
  "stop_loss_price": 止损价格（数字，基于分析中的支撑位）,
  "key_points": ["从分析中提取3-5个核心要点"],
  "core_logic": "从分析中提取的核心投资逻辑（一句话）",
  "opportunities": ["从分析中提取的机会点"],
  "risks": ["从分析中提取的风险点"],
  "technical_analysis": "技术面分析摘要（100-150字）",
  "fundamental_analysis": "基本面分析摘要（100-150字）",
  "chip_analysis": "筹码资金分析摘要（100-150字）",
  "risk_analysis": "风险提示摘要（50-100字）",
  "operation_suggestion": "操作策略建议（50-100字）",
  "summary": "投资建议总结（50-100字）",
  "full_report": "完整分析报告原文"
}}"""

        return prompt

    def analyze_stock_two_phase(self, stock_code: str) -> Dict:
        """
        两阶段分析股票
        第一阶段：自由深度分析
        第二阶段：提取结构化数据

        Args:
            stock_code: 股票代码

        Returns:
            分析结果字典
        """
        try:
            logger.info(f"开始两阶段分析股票: {stock_code}")

            # 1. 收集分析数据
            analysis_data = self._collect_analysis_data(stock_code)

            if not analysis_data:
                return {
                    "success": False,
                    "message": "无法收集到足够的分析数据"
                }

            # 2. 第一阶段：深度自由分析
            logger.info(f"第一阶段：深度分析 {stock_code}")
            phase1_prompt = self._build_phase1_prompt(analysis_data)
            phase1_result = self._call_gemini_api_raw(phase1_prompt)

            if not phase1_result:
                return {
                    "success": False,
                    "message": "第一阶段分析失败"
                }

            logger.info(f"第一阶段分析完成，报告长度: {len(phase1_result)} 字符")

            # 3. 第二阶段：提取结构化数据
            logger.info(f"第二阶段：提取结构化数据 {stock_code}")
            phase2_prompt = self._build_phase2_prompt(phase1_result, analysis_data)
            analysis_result = self._call_gemini_api(phase2_prompt)

            if not analysis_result:
                # 如果第二阶段失败，至少保存第一阶段的结果
                analysis_result = {
                    "technical_score": 0,
                    "fundamental_score": 0,
                    "valuation_score": 0,
                    "fund_flow_score": 0,
                    "holder_score": 0,
                    "risk_level": "未知",
                    "suggestion": "观望",
                    "key_points": [],
                    "full_report": phase1_result,
                    "summary": "详细分析请查看完整报告"
                }

            # 确保full_report字段包含完整的第一阶段分析
            analysis_result["full_report"] = phase1_result

            # 4. 保存分析结果到数据库
            self._save_analysis_result(stock_code, analysis_result)

            logger.success(f"股票 {stock_code} 两阶段分析完成")

            return {
                "success": True,
                "message": "分析完成",
                "data": analysis_result
            }

        except Exception as e:
            logger.error(f"两阶段分析股票 {stock_code} 失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"分析失败: {str(e)}"
            }

    def _call_gemini_api_raw(self, prompt: str) -> Optional[str]:
        """调用Gemini API并返回原始文本（不解析JSON）"""
        try:
            logger.info(f"调用Gemini API (raw) - Model: {self.model}")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                timeout=self.timeout
            )

            if isinstance(response, str):
                logger.error(f"API返回错误字符串: {response}")
                return None

            if hasattr(response, 'error'):
                logger.error(f"API返回错误: {response.error}")
                return None

            content = response.choices[0].message.content
            logger.success("Gemini API调用成功 (raw)")
            return content

        except Exception as e:
            logger.error(f"调用Gemini API失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return None

    def _build_analysis_prompt(self, data: Dict) -> str:
        """构建分析prompt"""
        stock = data['stock']
        klines = data['klines']
        financials = data['financials']
        announcements = data['announcements']
        news = data['news']
        chip_distributions = data.get('chip_distributions', [])
        valuations = data.get('valuations', [])
        fund_flows = data.get('fund_flows', [])
        holders = data.get('holders', [])

        # 最新K线数据
        latest_kline = klines[0] if klines else None

        prompt = f"""你是一位专业的A股分析师。请基于以下数据对股票 {stock['stock_code']} {stock['stock_name']} 进行全面分析。

【基本信息】
股票代码：{stock['stock_code']}
股票名称：{stock['stock_name']}
市场：{stock['market']}

【最新行情】（{latest_kline['date'] if latest_kline else 'N/A'}）
"""

        if latest_kline:
            open_price = latest_kline['open']
            close_price = latest_kline['close']
            change_pct = ((close_price - open_price) / open_price * 100) if open_price else 0

            prompt += f"""开盘价：{open_price}
收盘价：{close_price}
最高价：{latest_kline['high']}
最低价：{latest_kline['low']}
成交量：{latest_kline['volume']}
涨跌幅：{change_pct:.2f}%

【技术指标】
MA5：{latest_kline['ma5']}
MA10：{latest_kline['ma10']}
MA20：{latest_kline['ma20']}
MA60：{latest_kline['ma60']}
MACD：{latest_kline['macd']}
RSI：{latest_kline['rsi']}
KDJ_K：{latest_kline['kdj_k']}
KDJ_D：{latest_kline['kdj_d']}
KDJ_J：{latest_kline['kdj_j']}

"""

        # 估值指标
        if valuations:
            latest_val = valuations[0]
            prompt += f"【估值指标】（{latest_val['date']}）\n"
            if latest_val.get('pe_ttm'):
                prompt += f"市盈率(TTM): {latest_val['pe_ttm']:.2f}\n"
            if latest_val.get('pe_static'):
                prompt += f"市盈率(静态): {latest_val['pe_static']:.2f}\n"
            if latest_val.get('pb'):
                prompt += f"市净率: {latest_val['pb']:.2f}\n"
            if latest_val.get('ps_ttm'):
                prompt += f"市销率(TTM): {latest_val['ps_ttm']:.2f}\n"
            if latest_val.get('dividend_yield'):
                prompt += f"股息率: {latest_val['dividend_yield']:.2f}%\n"
            if latest_val.get('total_mv'):
                prompt += f"总市值: {latest_val['total_mv']/100000000:.2f}亿元\n"
            if latest_val.get('circ_mv'):
                prompt += f"流通市值: {latest_val['circ_mv']/100000000:.2f}亿元\n"

            # 行业对比
            if latest_val.get('industry'):
                prompt += f"\n【行业对比】（{latest_val['industry']}）\n"
                if latest_val.get('industry_pe'):
                    pe_diff = ((latest_val.get('pe_ttm', 0) or 0) - latest_val['industry_pe']) / latest_val['industry_pe'] * 100 if latest_val['industry_pe'] else 0
                    prompt += f"行业平均PE: {latest_val['industry_pe']:.2f} (个股{'高于' if pe_diff > 0 else '低于'}行业{abs(pe_diff):.1f}%)\n"
                if latest_val.get('industry_pb'):
                    pb_diff = ((latest_val.get('pb', 0) or 0) - latest_val['industry_pb']) / latest_val['industry_pb'] * 100 if latest_val['industry_pb'] else 0
                    prompt += f"行业平均PB: {latest_val['industry_pb']:.2f} (个股{'高于' if pb_diff > 0 else '低于'}行业{abs(pb_diff):.1f}%)\n"

            prompt += "\n【估值分析要点】\n"
            prompt += "- PE低于行业平均可能被低估，但需结合成长性判断\n"
            prompt += "- PB低于1可能意味着股价低于账面价值\n"
            prompt += "- 高股息率适合价值投资，但需关注分红可持续性\n\n"

        # 最近K线走势
        prompt += "【近期走势】（最近10天）\n"
        for kline in klines[:10]:
            open_price = kline['open']
            close_price = kline['close']
            change_pct = ((close_price - open_price) / open_price * 100) if open_price else 0
            prompt += f"{kline['date']}: 收盘{close_price}, 涨跌{change_pct:+.2f}%\n"

        # 财务数据
        if financials:
            prompt += "\n【财务数据】（最近4期）\n"
            for f in financials:
                prompt += f"{f['report_date']}: 营收{f['revenue']}亿, 净利润{f['net_profit']}亿, EPS{f['eps']}, ROE{f['roe']}%, 资产负债率{f['debt_ratio']}%\n"

        # 重要公告
        if announcements:
            prompt += "\n【重要公告】（最近10条）\n"
            for a in announcements:
                prompt += f"{a['announcement_date']} [{a['announcement_type']}] {a['title']}\n"

        # 相关新闻
        if news:
            prompt += "\n【相关新闻】（最近10条）\n"
            for n in news:
                sentiment_tag = f"[{n['sentiment']}]" if n['sentiment'] else ""
                prompt += f"{n['news_date']} {sentiment_tag} {n['title']}\n"

        # 筹码分布
        if chip_distributions:
            latest_chip = chip_distributions[0]
            prompt += f"\n【筹码分布】（{latest_chip['date']}）\n"
            prompt += f"获利比例: {latest_chip['profit_ratio']}%\n"
            prompt += f"平均成本: {latest_chip['avg_cost']}元\n"
            prompt += f"90%成本区间: {latest_chip['cost_90_low']} - {latest_chip['cost_90_high']}元\n"
            prompt += f"90%集中度: {latest_chip['concentration_90']}%\n"
            prompt += f"70%成本区间: {latest_chip['cost_70_low']} - {latest_chip['cost_70_high']}元\n"
            prompt += f"70%集中度: {latest_chip['concentration_70']}%\n"
            prompt += "\n【筹码分析要点】\n"
            prompt += "- 获利比例高说明大部分持仓者盈利，卖压可能增加\n"
            prompt += "- 集中度高说明筹码集中，主力控盘强\n"
            prompt += "- 平均成本接近当前价说明套牢盘少\n"

        # 资金流向
        if fund_flows:
            prompt += "\n【资金流向】（最近10日）\n"
            total_main_inflow = 0
            total_small_inflow = 0
            for f in fund_flows:
                main_inflow = f['main_net_inflow'] or 0
                small_inflow = f['small_net_inflow'] or 0
                total_main_inflow += main_inflow
                total_small_inflow += small_inflow
                prompt += f"{f['date']}: 主力{'流入' if main_inflow >= 0 else '流出'}{abs(main_inflow)/10000:.2f}万, 散户{'流入' if small_inflow >= 0 else '流出'}{abs(small_inflow)/10000:.2f}万\n"

            prompt += f"\n近期资金汇总:\n"
            prompt += f"- 主力累计: {'流入' if total_main_inflow >= 0 else '流出'}{abs(total_main_inflow)/10000:.2f}万元\n"
            prompt += f"- 散户累计: {'流入' if total_small_inflow >= 0 else '流出'}{abs(total_small_inflow)/10000:.2f}万元\n"

            # 判断背离
            if total_main_inflow > 0 and total_small_inflow < 0:
                prompt += "- 背离判断: 主力吸筹、散户出货（看涨背离）\n"
            elif total_main_inflow < 0 and total_small_inflow > 0:
                prompt += "- 背离判断: 主力出货、散户接盘（看跌背离）\n"
            else:
                prompt += "- 背离判断: 无明显背离\n"

            prompt += "\n【资金分析要点】\n"
            prompt += "- 主力持续流入通常是上涨信号\n"
            prompt += "- 主力出货散户接盘是危险信号\n"
            prompt += "- 背离往往预示着趋势反转\n"

        # 股东数据
        if holders:
            latest_holder = holders[0]
            prompt += f"\n【股东数据】（{latest_holder['report_date']}）\n"
            prompt += f"股东人数: {latest_holder['total_holders']}\n"
            if latest_holder['holder_change']:
                prompt += f"人数变化: {latest_holder['holder_change']:+d} ({latest_holder['holder_change_pct']:+.2f}%)\n"
            if latest_holder['top10_hold_ratio']:
                prompt += f"十大股东合计持股: {latest_holder['top10_hold_ratio']:.2f}%\n"
            if latest_holder['first_holder_name']:
                prompt += f"第一大股东: {latest_holder['first_holder_name']} ({latest_holder['first_holder_ratio']:.2f}%)\n"
            if latest_holder['concentration_trend']:
                prompt += f"筹码集中度趋势: {latest_holder['concentration_trend']}\n"
            if latest_holder['control_type']:
                prompt += f"控股类型: {latest_holder['control_type']}\n"

            prompt += "\n【股东分析要点】\n"
            prompt += "- 股东人数减少通常意味着筹码集中，主力控盘\n"
            prompt += "- 股东人数增加可能意味着筹码分散，散户入场\n"
            prompt += "- 十大股东持股比例高意味着流通盘小，容易被控盘\n"

        prompt += """

请基于以上数据，提供JSON格式的分析报告，包含以下字段：
{
  "technical_score": 0-100的技术面评分,
  "fundamental_score": 0-100的基本面评分,
  "valuation_score": 0-100的估值评分（基于PE/PB与行业对比、股息率等判断股价合理性）,
  "fund_flow_score": 0-100的资金面评分（基于主力资金流向、散户资金流向判断）,
  "holder_score": 0-100的筹码评分（基于股东变化、集中度趋势判断）,
  "risk_level": "低/中/高",
  "suggestion": "买入/持有/观望/卖出",
  "target_price": 预期目标价格（数字）,
  "key_points": ["核心要点1", "核心要点2", "核心要点3"],
  "technical_analysis": "技术面详细分析（100-200字）",
  "fundamental_analysis": "基本面详细分析（100-200字）",
  "valuation_analysis": "估值分析（50-100字，分析PE/PB是否合理、与行业对比情况）",
  "fund_flow_analysis": "资金流向分析（50-100字，分析主力和散户资金动向）",
  "holder_analysis": "股东筹码分析（50-100字，分析股东变化和筹码集中度）",
  "risk_analysis": "风险提示（50-100字）",
  "summary": "投资建议总结（50-100字）"
}

请确保返回的是有效的JSON格式，不要包含其他文字。"""

        return prompt

    def _call_gemini_api(self, prompt: str) -> Optional[Dict]:
        """调用Gemini API"""
        try:
            logger.info(f"调用Gemini API - Model: {self.model}")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                timeout=self.timeout
            )

            # 检查响应类型
            logger.debug(f"Response type: {type(response)}, Response: {response}")

            # 如果response是字符串，说明API返回了错误
            if isinstance(response, str):
                logger.error(f"API返回错误字符串: {response}")
                return None

            # 检查是否有错误
            if hasattr(response, 'error'):
                logger.error(f"API返回错误: {response.error}")
                return None

            # 提取响应内容
            content = response.choices[0].message.content
            logger.debug(f"API返回内容: {content[:200]}...")

            # 尝试解析JSON
            try:
                # 移除可能的markdown代码块标记
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                result = json.loads(content)
                logger.success("Gemini API调用成功")
                return result

            except json.JSONDecodeError as e:
                logger.error(f"解析JSON失败: {e}, 原始内容: {content[:200]}")
                # 如果JSON解析失败，返回原始文本
                return {
                    "technical_score": 0,
                    "fundamental_score": 0,
                    "valuation_score": 0,
                    "fund_flow_score": 0,
                    "holder_score": 0,
                    "risk_level": "未知",
                    "suggestion": "观望",
                    "target_price": 0,
                    "key_points": [],
                    "technical_analysis": content[:500],
                    "fundamental_analysis": "",
                    "valuation_analysis": "",
                    "fund_flow_analysis": "",
                    "holder_analysis": "",
                    "risk_analysis": "AI分析格式异常",
                    "summary": "请查看技术分析部分获取详细信息"
                }

        except Exception as e:
            logger.error(f"调用Gemini API失败: {type(e).__name__}: {str(e)}", exc_info=True)
            return None

    def _save_analysis_result(self, stock_code: str, analysis_result: Dict):
        """保存分析结果到数据库"""
        try:
            with get_db_session() as session:
                # 检查今天是否已有分析
                today = date.today()
                existing = session.query(GeminiAnalysis).filter_by(
                    stock_code=stock_code,
                    analysis_date=today
                ).first()

                if existing:
                    # 更新现有分析
                    existing.model_name = self.model
                    existing.analysis_result = json.dumps(analysis_result, ensure_ascii=False)
                    existing.updated_at = datetime.now()
                    logger.info(f"更新股票 {stock_code} 的分析结果")
                else:
                    # 创建新分析
                    new_analysis = GeminiAnalysis(
                        stock_code=stock_code,
                        analysis_date=today,
                        model_name=self.model,
                        analysis_result=json.dumps(analysis_result, ensure_ascii=False)
                    )
                    session.add(new_analysis)
                    logger.info(f"保存股票 {stock_code} 的分析结果")

                session.commit()

        except Exception as e:
            logger.error(f"保存分析结果失败: {e}", exc_info=True)
            raise


# 单例模式
_analyzer_instance = None


def get_gemini_analyzer() -> GeminiAnalyzer:
    """获取Gemini分析器实例（单例）"""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = GeminiAnalyzer()
    return _analyzer_instance
