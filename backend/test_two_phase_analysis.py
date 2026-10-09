#!/usr/bin/env python3
"""测试两阶段Gemini分析"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from src.services.gemini_analyzer import get_gemini_analyzer


def main():
    stock_code = "000151"  # 中成股份

    print(f"\n{'='*60}")
    print(f"测试两阶段分析: {stock_code}")
    print(f"{'='*60}\n")

    analyzer = get_gemini_analyzer()

    # 使用两阶段分析
    result = analyzer.analyze_stock_two_phase(stock_code)

    if result["success"]:
        data = result["data"]

        print("\n" + "="*60)
        print("【完整分析报告】")
        print("="*60)
        print(data.get("full_report", "无"))

        print("\n" + "="*60)
        print("【结构化数据】")
        print("="*60)
        print(f"核心逻辑: {data.get('core_logic', 'N/A')}")
        print(f"技术面评分: {data.get('technical_score', 0)}")
        print(f"基本面评分: {data.get('fundamental_score', 0)}")
        print(f"估值评分: {data.get('valuation_score', 0)}")
        print(f"资金面评分: {data.get('fund_flow_score', 0)}")
        print(f"筹码评分: {data.get('holder_score', 0)}")
        print(f"风险等级: {data.get('risk_level', 'N/A')}")
        print(f"投资建议: {data.get('suggestion', 'N/A')}")
        print(f"目标价: {data.get('target_price', 'N/A')}")
        print(f"止损价: {data.get('stop_loss_price', 'N/A')}")

        print("\n【核心要点】")
        for i, point in enumerate(data.get('key_points', []), 1):
            print(f"  {i}. {point}")

        print("\n【机会点】")
        for i, opp in enumerate(data.get('opportunities', []), 1):
            print(f"  {i}. {opp}")

        print("\n【风险点】")
        for i, risk in enumerate(data.get('risks', []), 1):
            print(f"  {i}. {risk}")

        print("\n【操作建议】")
        print(f"  {data.get('operation_suggestion', 'N/A')}")

        print("\n【投资总结】")
        print(f"  {data.get('summary', 'N/A')}")

    else:
        print(f"分析失败: {result['message']}")


if __name__ == "__main__":
    main()
