#!/usr/bin/env python3
"""测试Gemini分析器"""
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

from src.services.gemini_analyzer import get_gemini_analyzer
from src.utils.logger import get_logger

logger = get_logger(__name__)


def test_analyze_stock():
    """测试分析单只股票"""
    stock_code = "600519"  # 贵州茅台

    print("=" * 80)
    print(f"测试Gemini AI分析 - {stock_code}")
    print("=" * 80)

    try:
        # 获取分析器实例
        analyzer = get_gemini_analyzer()

        # 执行分析
        print(f"\n正在分析股票 {stock_code}...")
        result = analyzer.analyze_stock(stock_code)

        if result['success']:
            print("\n✓ 分析成功!")
            print("\n【分析结果】")

            data = result['data']
            print(f"技术面评分: {data.get('technical_score', 'N/A')}/100")
            print(f"基本面评分: {data.get('fundamental_score', 'N/A')}/100")
            print(f"风险等级: {data.get('risk_level', 'N/A')}")
            print(f"投资建议: {data.get('suggestion', 'N/A')}")
            print(f"目标价格: {data.get('target_price', 'N/A')}")

            print("\n【核心要点】")
            for i, point in enumerate(data.get('key_points', []), 1):
                print(f"{i}. {point}")

            print("\n【技术分析】")
            print(data.get('technical_analysis', 'N/A'))

            print("\n【基本面分析】")
            print(data.get('fundamental_analysis', 'N/A'))

            print("\n【风险提示】")
            print(data.get('risk_analysis', 'N/A'))

            print("\n【投资建议】")
            print(data.get('summary', 'N/A'))

        else:
            print(f"\n✗ 分析失败: {result.get('message', '未知错误')}")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n✗ 测试失败: {e}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    test_analyze_stock()
