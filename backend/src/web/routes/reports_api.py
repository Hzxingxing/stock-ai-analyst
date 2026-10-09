"""
Claude报告API路由
"""
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import desc
from datetime import date, datetime
import json

from src.database.connection import get_db_session
from src.database.models import ClaudeReport, Stock, GeminiAnalysis, MarketStatistics
from src.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/reports")
async def list_reports(limit: int = Query(default=10, ge=1, le=50)):
    """
    获取Claude分析报告列表

    Args:
        limit: 获取条数

    Returns:
        报告列表
    """
    try:
        with get_db_session() as session:
            reports = session.query(ClaudeReport).order_by(
                desc(ClaudeReport.report_date)
            ).limit(limit).all()

            if not reports:
                return {
                    "success": True,
                    "data": [],
                    "count": 0,
                    "message": "暂无报告"
                }

            data = []
            for r in reports:
                data.append({
                    "id": r.id,
                    "report_date": r.report_date.strftime('%Y-%m-%d'),
                    "market_overview": r.market_overview,
                    "created_at": r.created_at.isoformat()
                })

            return {
                "success": True,
                "data": data,
                "count": len(data)
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _remove_top10_from_report(full_report: str) -> str:
    """
    从完整报告中移除Top 10投资机会章节
    因为前端已经用表格单独展示了top_opportunities数据
    """
    if not full_report:
        return full_report

    import re
    # 匹配从"## 二、Top 10投资机会"到下一个"## "二级标题或文件结束
    # 使用 (?=\n## [^#]) 确保只匹配二级标题，不匹配三级标题 ###
    pattern = r'##\s*[一二三四五六七八九十]*[、.]?\s*Top\s*10.*?投资机会[\s\S]*?(?=\n## [^#]|\n---|\Z)'
    cleaned = re.sub(pattern, '', full_report, flags=re.IGNORECASE)

    # 清理多余空行
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

    return cleaned.strip()


@router.get("/reports/{report_id}")
async def get_report_detail(report_id: int):
    """
    获取报告详情

    Args:
        report_id: 报告ID

    Returns:
        报告详情
    """
    try:
        with get_db_session() as session:
            report = session.query(ClaudeReport).filter_by(id=report_id).first()

            if not report:
                raise HTTPException(status_code=404, detail="报告不存在")

            # 解析top_opportunities JSON
            top_opportunities = json.loads(report.top_opportunities) if isinstance(report.top_opportunities, str) else report.top_opportunities

            # 从full_report中移除Top 10章节（前端已用表格展示）
            cleaned_full_report = _remove_top10_from_report(report.full_report)

            return {
                "success": True,
                "data": {
                    "id": report.id,
                    "report_date": report.report_date.strftime('%Y-%m-%d'),
                    "top_opportunities": top_opportunities,
                    "market_overview": report.market_overview,
                    "full_report": cleaned_full_report,
                    "created_at": report.created_at.isoformat()
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reports/generate")
async def generate_report(report_date: str = None):
    """
    生成新的Claude分析报告

    基于指定日期的Gemini分析结果生成汇总报告
    如果不指定日期，则使用今天的日期

    Args:
        report_date: 报告日期(YYYY-MM-DD格式)，可选，默认今天

    Returns:
        生成的报告
    """
    try:
        # 确定报告日期
        if report_date:
            try:
                target_date = datetime.strptime(report_date, '%Y-%m-%d').date()
            except ValueError:
                return {
                    "success": False,
                    "message": "日期格式错误，请使用YYYY-MM-DD格式"
                }
        else:
            target_date = date.today()

        with get_db_session() as session:
            # 获取指定日期的所有分析结果
            stocks_with_analysis = session.query(
                Stock.stock_code,
                Stock.stock_name,
                Stock.market,
                GeminiAnalysis.analysis_result,
                GeminiAnalysis.analysis_date
            ).join(
                GeminiAnalysis,
                Stock.stock_code == GeminiAnalysis.stock_code
            ).filter(
                GeminiAnalysis.analysis_date == target_date
            ).all()

            if not stocks_with_analysis:
                return {
                    "success": False,
                    "message": f"{target_date.strftime('%Y-%m-%d')}暂无股票分析数据。请先对股票进行AI分析，或选择其他日期。"
                }

            # 构建股票分析数据
            stock_analysis_map = {}
            for stock_code, stock_name, market, analysis_result, analysis_date in stocks_with_analysis:
                stock_analysis_map[stock_code] = {
                    "stock_code": stock_code,
                    "stock_name": stock_name,
                    "market": market,
                    "analysis_result": json.loads(analysis_result) if isinstance(analysis_result, str) else analysis_result,
                    "analysis_date": analysis_date
                }

            # 计算综合评分并排序
            scored_stocks = []
            for stock_code, data in stock_analysis_map.items():
                analysis = data["analysis_result"]
                tech_score = analysis.get("technical_score", 0) or 0
                fund_score = analysis.get("fundamental_score", 0) or 0
                total_score = tech_score + fund_score

                scored_stocks.append({
                    "stock_code": stock_code,
                    "stock_name": data["stock_name"],
                    "market": data["market"],
                    "technical_score": tech_score,
                    "fundamental_score": fund_score,
                    "total_score": total_score,
                    "suggestion": analysis.get("suggestion", "-"),
                    "risk_level": analysis.get("risk_level", "-"),
                    "key_points": analysis.get("key_points", [])
                })

            # 按总分排序
            scored_stocks.sort(key=lambda x: x["total_score"], reverse=True)

            # Top 10投资机会
            top_opportunities = scored_stocks[:10]

            # 高风险股票
            high_risk_stocks = [s for s in scored_stocks if s["risk_level"] == "高"]

            # 获取市场统计数据
            market_stats = session.query(MarketStatistics).filter_by(
                stat_date=target_date
            ).first()

            market_stats_text = ""
            if market_stats:
                market_stats_text = f"""
## 市场概况（{target_date.strftime('%Y-%m-%d')}）

- 总股票数: {market_stats.total_stocks}只
- 上涨: {market_stats.up_count}只 ({market_stats.up_count/market_stats.total_stocks*100:.1f}%)
- 下跌: {market_stats.down_count}只 ({market_stats.down_count/market_stats.total_stocks*100:.1f}%)
- 平盘: {market_stats.flat_count}只
- 涨停: {market_stats.limit_up_count}只，跌停: {market_stats.limit_down_count}只
- 总成交额: {market_stats.total_amount/100000000:.2f}亿元

涨跌幅分布:
- 涨幅>7%: {market_stats.up_over_7_count}只
- 涨幅5-7%: {market_stats.up_5_to_7_count}只
- 涨幅3-5%: {market_stats.up_3_to_5_count}只
- 涨幅0-3%: {market_stats.up_0_to_3_count}只
- 跌幅0-3%: {market_stats.down_0_to_3_count}只
- 跌幅3-5%: {market_stats.down_3_to_5_count}只
- 跌幅5-7%: {market_stats.down_5_to_7_count}只
- 跌幅>7%: {market_stats.down_over_7_count}只

"""

            # 生成市场概况
            avg_tech_score = sum(s["technical_score"] for s in scored_stocks) / len(scored_stocks)
            avg_fund_score = sum(s["fundamental_score"] for s in scored_stocks) / len(scored_stocks)

            market_overview = f"""市场分析概况（{target_date.strftime('%Y-%m-%d')}）

分析日期：{target_date.strftime('%Y年%m月%d日')}
分析股票总数：{len(scored_stocks)}
平均技术面评分：{avg_tech_score:.1f}/100
平均基本面评分：{avg_fund_score:.1f}/100
高风险股票数量：{len(high_risk_stocks)}

建议买入：{len([s for s in scored_stocks if s['suggestion'] == '买入'])}只
建议持有：{len([s for s in scored_stocks if s['suggestion'] == '持有'])}只
建议观望：{len([s for s in scored_stocks if s['suggestion'] == '观望'])}只
建议卖出：{len([s for s in scored_stocks if s['suggestion'] == '卖出'])}只
"""

            # 生成完整报告
            full_report = f"""# 股票AI分析汇总报告

报告日期：{target_date.strftime('%Y年%m月%d日')}
生成时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}
分析股票：{len(scored_stocks)}只

{market_stats_text}

## 一、市场概况

{market_overview}

## 二、Top 10投资机会

"""
            for i, stock in enumerate(top_opportunities, 1):
                full_report += f"""### {i}. {stock['stock_name']}（{stock['stock_code']}）

- **综合评分**：{stock['total_score']}/200（技术面{stock['technical_score']}，基本面{stock['fundamental_score']}）
- **投资建议**：{stock['suggestion']}
- **风险等级**：{stock['risk_level']}
- **核心要点**：
"""
                for point in stock['key_points'][:3]:
                    full_report += f"  - {point}\n"
                full_report += "\n"

            # 风险警示
            if high_risk_stocks:
                full_report += "## 三、风险警示\n\n以下股票风险等级为\"高\"，建议谨慎对待：\n\n"
                for stock in high_risk_stocks[:5]:
                    full_report += f"- {stock['stock_name']}（{stock['stock_code']}）- {stock['suggestion']}\n"

            # 保存到数据库
            # 检查指定日期是否已有报告
            existing_report = session.query(ClaudeReport).filter_by(
                report_date=target_date
            ).first()

            if existing_report:
                # 更新现有报告
                existing_report.top_opportunities = json.dumps(top_opportunities, ensure_ascii=False)
                existing_report.market_overview = market_overview
                existing_report.full_report = full_report
                existing_report.updated_at = datetime.now()
                report = existing_report
                message = f"已更新{target_date.strftime('%Y-%m-%d')}的报告"
            else:
                # 创建新报告
                report = ClaudeReport(
                    report_date=target_date,
                    top_opportunities=json.dumps(top_opportunities, ensure_ascii=False),
                    market_overview=market_overview,
                    full_report=full_report
                )
                session.add(report)
                message = f"已生成{target_date.strftime('%Y-%m-%d')}的报告"

            session.commit()
            session.refresh(report)

            return {
                "success": True,
                "message": message,
                "data": {
                    "id": report.id,
                    "report_date": report.report_date.strftime('%Y-%m-%d'),
                    "analysis_count": len(scored_stocks),
                    "top_opportunities": top_opportunities,
                    "market_overview": market_overview,
                    "full_report": full_report
                }
            }

    except Exception as e:
        logger.error(f"生成报告失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
