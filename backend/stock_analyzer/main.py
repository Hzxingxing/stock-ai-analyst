"""A股技术分析工具 - 主入口"""

import argparse
import sys

from .data_fetcher import get_stock_data, get_stock_name
from .indicators import calculate_all_indicators, get_latest_indicators
from .analyzer import run_full_analysis
from .reporter import generate_report, print_report


def analyze_stock(stock_code: str, days: int = 60) -> tuple:
    """
    分析指定股票 (技术面)

    Args:
        stock_code: 股票代码，如 "600519"
        days: 分析周期天数

    Returns:
        (报告文本, 分析结果字典, 指标字典)
    """
    # 获取股票名称
    stock_name = get_stock_name(stock_code)

    # 获取K线数据
    df = get_stock_data(stock_code, days=days)

    if df.empty:
        return f"错误: 无法获取股票 {stock_code} 的数据", {}, {}

    # 计算技术指标
    df = calculate_all_indicators(df)

    # 获取最新指标值
    indicators = get_latest_indicators(df)

    # 运行分析
    analysis = run_full_analysis(indicators, df)

    # 生成报告
    report = generate_report(stock_code, stock_name, indicators, analysis, days)

    return report, analysis, indicators


def analyze_stock_full(stock_code: str, days: int = 60, years: int = 3, with_news: bool = False, export_format: str = None) -> str:
    """
    完整分析股票 (技术面 + 公告 + 财务 + 深度分析)

    Args:
        stock_code: 股票代码
        days: 技术分析周期天数
        years: 财务数据年限
        with_news: 是否获取市场资讯
        export_format: 导出格式 (json/text/None)

    Returns:
        完整分析报告文本或结构化数据
    """
    from .notice_fetcher import get_important_notices, get_all_notices_classified
    from .financial_fetcher import get_all_financial_data
    from .financial_analyzer import run_financial_analysis
    from .deep_analyzer import run_deep_analysis
    from .full_reporter import generate_full_report

    # 获取股票名称
    stock_name = get_stock_name(stock_code)

    # 1. 技术分析
    tech_report, tech_analysis, indicators = analyze_stock(stock_code, days)

    if not tech_analysis:
        return tech_report  # 返回错误信息

    # 2. 获取公告 (分类)
    print("正在获取公告数据...", file=sys.stderr)
    classified_notices = get_all_notices_classified(stock_code, years=years)
    notices = get_important_notices(stock_code, years=years, limit=20)

    # 2.1 增强版公告分析（提取关键信息）
    notice_analysis = None
    try:
        from .notice_content import get_enhanced_notice_analysis
        print("正在分析公告详情...", file=sys.stderr)
        notice_analysis = get_enhanced_notice_analysis(stock_code, years=years)
    except Exception as e:
        print(f"公告详情分析跳过: {e}", file=sys.stderr)

    # 3. 获取财务数据
    print("正在获取财务数据...", file=sys.stderr)
    financial_data = get_all_financial_data(stock_code, years=years)

    # 4. 财务分析
    print("正在分析财务数据...", file=sys.stderr)
    financial_analysis = run_financial_analysis(financial_data)

    # 5. 获取市场资讯（可选）
    market_info = None
    if with_news or export_format:
        try:
            from .market_news import get_comprehensive_market_info
            print("正在获取市场资讯...", file=sys.stderr)
            market_info = get_comprehensive_market_info(stock_code, stock_name)
        except Exception as e:
            print(f"市场资讯获取失败: {e}", file=sys.stderr)

    # 6. 深度分析（整合所有数据源）
    print("正在进行深度分析...", file=sys.stderr)
    deep_analysis = run_deep_analysis(
        classified_notices,
        financial_data,
        market_info=market_info,
        notice_analysis=notice_analysis
    )

    # 如果需要导出结构化数据
    if export_format:
        from .timeline_export import export_timeline_data, export_to_json, export_to_text
        print("正在导出时间线数据...", file=sys.stderr)
        timeline = export_timeline_data(
            stock_code=stock_code,
            stock_name=stock_name,
            notices=notices,
            classified_notices=classified_notices,
            financial_data=financial_data,
            market_info=market_info,
            notice_analysis=notice_analysis
        )
        if export_format == "json":
            return export_to_json(timeline)
        else:
            return export_to_text(timeline)

    # 7. 生成综合报告
    full_report = generate_full_report(
        stock_code=stock_code,
        stock_name=stock_name,
        tech_report=tech_report,
        tech_analysis=tech_analysis,
        notices=notices,
        financial_data=financial_data,
        financial_analysis=financial_analysis,
        years=years,
        classified_notices=classified_notices,
        deep_analysis=deep_analysis,
        market_info=market_info,
        notice_analysis=notice_analysis
    )

    return full_report


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="A股技术分析工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m stock_analyzer --code 600519           # 技术分析贵州茅台
  python -m stock_analyzer --code 000001 --days 30 # 技术分析平安银行最近30天
  python -m stock_analyzer --code 600519 --full    # 完整分析(技术+公告+财务)
  python -m stock_analyzer --code 600519 --full --years 3  # 完整分析,财务数据3年
  python -m stock_analyzer --code 002174 --full --news     # 完整分析+市场资讯
  python -m stock_analyzer --code 002174 --full --export json  # 导出JSON时间线数据
  python -m stock_analyzer --code 002174 --export-data all     # 导出全部数据(增量)
  python -m stock_analyzer --code 002174 --export-data kline   # 仅导出K线数据
  python -m stock_analyzer --code 002174 --export-data news    # 仅导出资讯明细

数据导出说明:
  - 默认目录: /Users/asta/stocks/{股票代码}_{股票名称}/
  - 支持增量导出，只获取上次导出后的新数据
  - 导出文件: K线数据.csv, 筹码分布.csv, 资讯明细.csv
        """
    )
    parser.add_argument(
        "--code", "-c",
        required=True,
        help="股票代码，如 600519"
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=60,
        help="技术分析周期天数 (默认: 60)"
    )
    parser.add_argument(
        "--full", "-f",
        action="store_true",
        help="启用完整分析 (技术面+公告+财务)"
    )
    parser.add_argument(
        "--years", "-y",
        type=int,
        default=3,
        help="财务数据年限 (默认: 3年)"
    )
    parser.add_argument(
        "--news", "-n",
        action="store_true",
        help="获取市场资讯 (新闻、研报、龙虎榜、大宗交易)"
    )
    parser.add_argument(
        "--export", "-e",
        choices=["json", "text"],
        help="导出时间线格式数据 (json或text)"
    )
    parser.add_argument(
        "--export-data",
        choices=["kline", "chip", "news", "all"],
        help="导出市场数据为CSV (kline=K线, chip=筹码分布, news=资讯明细, all=全部)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制全量导出（忽略已有数据，重新下载）"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="数据导出根目录 (默认: /Users/asta/stocks)"
    )

    args = parser.parse_args()

    try:
        # 数据导出模式
        if args.export_data:
            from .data_export import (
                export_kline_incremental, export_chip_incremental,
                export_news_incremental, export_all_data
            )
            from .data_fetcher import get_stock_name

            stock_name = get_stock_name(args.code)
            mode_str = "全量" if args.force else "增量"
            print(f"正在{mode_str}导出 {stock_name}({args.code}) 数据...", file=sys.stderr)

            if args.export_data == "kline":
                result = export_kline_incremental(args.code, stock_name, args.output_dir, force=args.force)
                print(f"\nK线数据导出完成:")
                print(f"  文件: {result['path']}")
                print(f"  新增: {result['new_count']} 条, 总计: {result['total_count']} 条")

            elif args.export_data == "chip":
                result = export_chip_incremental(args.code, stock_name, args.output_dir, force=args.force)
                print(f"\n筹码分布导出完成:")
                print(f"  文件: {result['path']}")
                print(f"  新增: {result['new_count']} 条, 总计: {result['total_count']} 条")

            elif args.export_data == "news":
                result = export_news_incremental(args.code, stock_name, args.output_dir, force=args.force)
                print(f"\n资讯明细导出完成:")
                print(f"  文件: {result['path']}")
                print(f"  新增: {result['new_count']} 条, 总计: {result['total_count']} 条")

            elif args.export_data == "all":
                results = export_all_data(args.code, output_dir=args.output_dir, force=args.force)
                print(f"\n数据导出完成:")
                print(f"目录: {results['export_dir']}")
                print(f"股票: {results['stock_name']}({results['stock_code']})")
                print("-" * 40)
                for data_type, info in results["files"].items():
                    type_name = {"kline": "K线数据", "chip": "筹码分布", "news": "资讯明细"}.get(data_type, data_type)
                    print(f"  {type_name}: 新增 {info['new_count']} 条, 总计 {info['total_count']} 条")
            return

        if args.full or args.export:
            report = analyze_stock_full(
                args.code, args.days, args.years,
                with_news=args.news,
                export_format=args.export
            )
        else:
            report, _, _ = analyze_stock(args.code, args.days)
        print_report(report)
    except Exception as e:
        print(f"分析出错: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
