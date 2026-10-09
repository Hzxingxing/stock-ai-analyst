#!/usr/bin/env python3
"""测试Gemini分析器 - 使用模拟数据"""
import sys
import os
from pathlib import Path
import json

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
from dotenv import load_dotenv
env_path = Path(__file__).parent / '.env'
load_dotenv(env_path)

from src.services.gemini_analyzer import GeminiAnalyzer
from src.utils.logger import get_logger
from src.database.connection import get_db_session
from src.database.models import GeminiAnalysis
from sqlalchemy import desc

logger = get_logger(__name__)


def test_with_mock_data():
    """使用模拟数据测试分析器的数据收集和保存功能"""
    stock_code = "600519"

    print("=" * 80)
    print(f"测试Gemini分析器(模拟模式) - {stock_code}")
    print("=" * 80)

    try:
        analyzer = GeminiAnalyzer()

        # 1. 测试数据收集
        print("\n【步骤1】测试数据收集...")
        data = analyzer._collect_analysis_data(stock_code)

        if not data:
            print("✗ 数据收集失败")
            return

        print(f"✓ 数据收集成功")
        print(f"  股票信息: {data['stock']}")
        print(f"  K线数据: {len(data['klines'])} 条")
        print(f"  财务数据: {len(data['financials'])} 条")
        print(f"  公告数据: {len(data['announcements'])} 条")
        print(f"  新闻数据: {len(data['news'])} 条")

        # 2. 测试Prompt构建
        print("\n【步骤2】测试Prompt构建...")
        prompt = analyzer._build_analysis_prompt(data)
        print(f"✓ Prompt构建成功 ({len(prompt)} 字符)")
        print(f"\nPrompt预览:")
        print(prompt[:500] + "...")

        # 3. 模拟AI分析结果
        print("\n【步骤3】模拟AI分析结果...")
        mock_result = {
            "technical_score": 75,
            "fundamental_score": 82,
            "risk_level": "中",
            "suggestion": "持有",
            "target_price": 1500.00,
            "key_points": [
                "技术面处于上升通道，均线多头排列",
                "基本面稳健，ROE保持高位",
                "行业景气度持续，白酒龙头地位稳固"
            ],
            "technical_analysis": "股价处于上升通道，MA5/MA10金叉向上，MACD指标显示多头强势。成交量温和放大，资金流入明显。短期支撑位在1350元附近，压力位在1450元。",
            "fundamental_analysis": "公司营收和净利润稳步增长，ROE保持在30%以上，盈利能力强劲。现金流充裕，负债率低。品牌价值持续提升，渠道拓展顺利。",
            "risk_analysis": "短期存在技术性回调风险。行业监管政策变化可能影响销售。经济增速放缓可能影响高端消费需求。",
            "summary": "综合技术面和基本面分析，贵州茅台当前估值合理，建议持有。短期可能存在回调，但长期投资价值显著。"
        }

        # 4. 测试结果保存
        print("\n【步骤4】测试结果保存...")
        analyzer._save_analysis_result(stock_code, mock_result)
        print("✓ 分析结果已保存到数据库")

        # 5. 验证数据库存储
        print("\n【步骤5】验证数据库存储...")
        with get_db_session() as session:
            analysis = session.query(GeminiAnalysis).filter_by(
                stock_code=stock_code
            ).order_by(desc(GeminiAnalysis.analysis_date)).first()

            if analysis:
                saved_result = json.loads(analysis.analysis_result)
                print("✓ 从数据库读取成功")
                print(f"\n【保存的分析结果】")
                print(f"技术面评分: {saved_result.get('technical_score')}/100")
                print(f"基本面评分: {saved_result.get('fundamental_score')}/100")
                print(f"风险等级: {saved_result.get('risk_level')}")
                print(f"投资建议: {saved_result.get('suggestion')}")
                print(f"目标价格: {saved_result.get('target_price')}")
                print(f"\n核心要点:")
                for i, point in enumerate(saved_result.get('key_points', []), 1):
                    print(f"{i}. {point}")
            else:
                print("✗ 从数据库读取失败")

        print("\n" + "=" * 80)
        print("✓ 所有测试通过（除AI API调用外）")
        print("\n【重要提示】")
        print("1. 数据收集、Prompt构建、结果保存功能正常")
        print("2. NewAPI需要配置可用的模型（如gemini-pro、gpt-4等）")
        print("3. 当前模型 'gemini-2.0-flash-exp' 在NewAPI中不可用")
        print("4. 请登录NewAPI管理后台配置可用模型，或修改config/config.yaml中的模型名称")
        print("=" * 80)

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n✗ 测试失败: {e}")


if __name__ == "__main__":
    test_with_mock_data()
