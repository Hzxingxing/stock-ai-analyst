"""数据导出模块 - 导出K线、筹码分布、资讯明细为CSV格式，支持增量导出"""

import os
import sys
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import pandas as pd
import akshare as ak

# 默认导出根目录
DEFAULT_EXPORT_ROOT = "/Users/asta/Documents/stocks"


def get_stock_export_dir(stock_code: str, stock_name: str, root_dir: str = None) -> str:
    """
    获取股票导出目录路径

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        root_dir: 根目录，默认为 /Users/asta/Documents/stocks

    Returns:
        目录路径: {root_dir}/{股票代码}_{股票名称}/
    """
    if root_dir is None:
        root_dir = DEFAULT_EXPORT_ROOT

    dir_name = f"{stock_code}_{stock_name}"
    dir_path = os.path.join(root_dir, dir_name)

    # 确保目录存在
    os.makedirs(dir_path, exist_ok=True)

    return dir_path


def get_last_export_date(file_path: str, date_column: str = "date") -> Optional[str]:
    """
    从已有CSV文件获取最后一条数据的日期

    Args:
        file_path: CSV文件路径
        date_column: 日期列名

    Returns:
        最后日期字符串 (YYYYMMDD)，如果文件不存在返回None
    """
    if not os.path.exists(file_path):
        return None

    try:
        df = pd.read_csv(file_path, encoding="utf-8-sig")
        if df.empty or date_column not in df.columns:
            return None

        # 获取最后一行的日期
        last_date = df[date_column].iloc[-1]
        # 转换为YYYYMMDD格式
        if isinstance(last_date, str):
            last_date = last_date.replace("-", "")[:8]
        return last_date
    except Exception:
        return None


def merge_and_save_csv(new_df: pd.DataFrame, file_path: str, date_column: str = "date") -> int:
    """
    合并新数据到已有CSV文件（去重）

    Args:
        new_df: 新数据DataFrame
        file_path: CSV文件路径
        date_column: 日期列名

    Returns:
        新增记录数
    """
    if new_df.empty:
        return 0

    if os.path.exists(file_path):
        try:
            existing_df = pd.read_csv(file_path, encoding="utf-8-sig")
            # 合并数据
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            # 按日期去重，保留最新的
            combined_df = combined_df.drop_duplicates(subset=[date_column], keep="last")
            # 按日期排序
            combined_df = combined_df.sort_values(by=date_column).reset_index(drop=True)
            new_count = len(combined_df) - len(existing_df)
        except Exception:
            combined_df = new_df
            new_count = len(new_df)
    else:
        combined_df = new_df
        new_count = len(new_df)

    combined_df.to_csv(file_path, index=False, encoding="utf-8-sig")
    return new_count


def get_kline_data(stock_code: str, start_date: str = None, end_date: str = None, days: int = 1825) -> pd.DataFrame:
    """
    获取K线数据

    Args:
        stock_code: 股票代码
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
        days: 如果未指定日期，默认获取最近天数

    Returns:
        K线数据DataFrame
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y%m%d")
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq"  # 前复权
        )

        # 重命名列为英文
        df = df.rename(columns={
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "涨跌幅": "change_pct",
            "涨跌额": "change_amt",
            "换手率": "turnover"
        })

        return df
    except Exception as e:
        print(f"获取K线数据失败: {e}", file=sys.stderr)
        return pd.DataFrame()


def get_chip_distribution(stock_code: str) -> pd.DataFrame:
    """
    获取筹码分布数据

    Args:
        stock_code: 股票代码

    Returns:
        筹码分布DataFrame
    """
    try:
        df = ak.stock_cyq_em(symbol=stock_code)

        # 重命名列为英文
        df = df.rename(columns={
            "日期": "date",
            "获利比例": "profit_ratio",
            "平均成本": "avg_cost",
            "90成本-低": "cost_90_low",
            "90成本-高": "cost_90_high",
            "90集中度": "concentration_90",
            "70成本-低": "cost_70_low",
            "70成本-高": "cost_70_high",
            "70集中度": "concentration_70"
        })

        return df
    except Exception as e:
        print(f"获取筹码分布失败: {e}", file=sys.stderr)
        return pd.DataFrame()


def get_news_details(stock_code: str, stock_name: str, days: int = 365) -> pd.DataFrame:
    """
    获取资讯明细数据

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        days: 获取天数 (默认365天)

    Returns:
        资讯明细DataFrame
    """
    news_list = []

    # 1. 东方财富个股新闻 (直接调用akshare，获取全部)
    try:
        df = ak.stock_news_em(symbol=stock_code)
        if not df.empty:
            for _, row in df.iterrows():
                news_list.append({
                    "date": str(row.get("发布时间", ""))[:10],
                    "type": "新闻",
                    "source": "东方财富",
                    "title": row.get("新闻标题", ""),
                    "content": str(row.get("新闻内容", ""))[:500] if row.get("新闻内容") else "",
                    "url": row.get("新闻链接", ""),
                })
        print(f"  获取新闻: {len(df) if not df.empty else 0} 条", file=sys.stderr)
    except Exception as e:
        print(f"  获取新闻失败: {e}", file=sys.stderr)

    # 2. 研究报告 (获取全部，不限制数量)
    try:
        df = ak.stock_research_report_em(symbol=stock_code)
        if not df.empty:
            # 列名可能是 "日期" 或 "发布日期"
            date_col = "日期" if "日期" in df.columns else "发布日期"
            institution_col = "机构" if "机构" in df.columns else "研报机构"
            title_col = "报告名称" if "报告名称" in df.columns else "标题"
            rating_col = "东财评级" if "东财评级" in df.columns else "最新评级"

            for _, row in df.iterrows():
                date_str = str(row.get(date_col, ""))[:10] if row.get(date_col) else ""
                # 跳过没有日期的研报
                if not date_str or date_str == "None" or date_str == "nan" or len(date_str) < 8:
                    continue
                news_list.append({
                    "date": date_str,
                    "type": "研报",
                    "source": str(row.get(institution_col, "")),
                    "title": str(row.get(title_col, "")),
                    "content": f"评级: {row.get(rating_col, '')}, 行业: {row.get('行业', '')}",
                    "url": str(row.get("报告PDF链接", "")),
                })
        print(f"  获取研报: {len(df) if not df.empty else 0} 条", file=sys.stderr)
    except Exception as e:
        print(f"  获取研报失败: {e}", file=sys.stderr)

    # 3. 龙虎榜 (尝试多种API调用方式)
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        # 尝试获取龙虎榜数据
        try:
            # 方式1: 使用股票代码直接查询
            df = ak.stock_lhb_stock_statistic_em(symbol=stock_code)
            if not df.empty:
                for _, row in df.iterrows():
                    date_str = str(row.get("上榜日", ""))[:10]
                    if date_str:
                        news_list.append({
                            "date": date_str,
                            "type": "龙虎榜",
                            "source": "东方财富",
                            "title": f"上榜原因: {row.get('上榜原因', '')}",
                            "content": f"涨跌幅: {row.get('涨跌幅', '')}%, 买入额: {row.get('龙虎榜买入额', '')}, 卖出额: {row.get('龙虎榜卖出额', '')}",
                            "url": "",
                        })
                print(f"  获取龙虎榜: {len(df)} 条", file=sys.stderr)
        except Exception:
            # 方式2: 查询个股龙虎榜明细
            try:
                df = ak.stock_lhb_jgmmtj_em(start_date=start_date, end_date=end_date)
                if not df.empty:
                    # 过滤当前股票
                    df_filtered = df[df["代码"] == stock_code]
                    for _, row in df_filtered.iterrows():
                        date_str = str(row.get("上榜日", ""))[:10]
                        if date_str:
                            news_list.append({
                                "date": date_str,
                                "type": "龙虎榜",
                                "source": "东方财富",
                                "title": f"机构买卖",
                                "content": f"买入额: {row.get('买入额', '')}, 卖出额: {row.get('卖出额', '')}",
                                "url": "",
                            })
                    print(f"  获取龙虎榜: {len(df_filtered)} 条", file=sys.stderr)
            except Exception:
                print(f"  龙虎榜API不可用", file=sys.stderr)
    except Exception as e:
        print(f"  获取龙虎榜失败: {e}", file=sys.stderr)

    # 4. 大宗交易
    try:
        df = ak.stock_dzjy_mrmx(symbol=stock_code)
        if not df.empty:
            for _, row in df.iterrows():
                date_str = str(row.get("交易日期", ""))[:10]
                if date_str:
                    news_list.append({
                        "date": date_str,
                        "type": "大宗交易",
                        "source": "东方财富",
                        "title": f"成交额: {row.get('成交额', '')}",
                        "content": f"成交价: {row.get('成交价', '')}, 折溢率: {row.get('折溢率', '')}, 买方: {str(row.get('买方营业部', ''))[:20]}, 卖方: {str(row.get('卖方营业部', ''))[:20]}",
                        "url": "",
                    })
            print(f"  获取大宗交易: {len(df)} 条", file=sys.stderr)
    except Exception as e:
        # 大宗交易可能不存在，静默处理
        pass

    # 5. 增加：股东增减持数据
    try:
        df = ak.stock_ggcg_em(symbol=stock_code)
        if not df.empty:
            for _, row in df.iterrows():
                date_str = str(row.get("公告日期", ""))[:10]
                if date_str:
                    change_type = "增持" if row.get("变动方向") == "增持" else "减持"
                    news_list.append({
                        "date": date_str,
                        "type": f"股东{change_type}",
                        "source": "东方财富",
                        "title": f"{row.get('股东名称', '')}{change_type}",
                        "content": f"变动股数: {row.get('变动股数', '')}, 变动比例: {row.get('变动比例', '')}%, 变动后持股: {row.get('变动后持股数', '')}",
                        "url": "",
                    })
            print(f"  获取股东增减持: {len(df)} 条", file=sys.stderr)
    except Exception:
        pass

    if not news_list:
        return pd.DataFrame()

    df = pd.DataFrame(news_list)
    # 按日期排序
    df = df.sort_values(by="date", ascending=True).reset_index(drop=True)

    return df


def export_kline_incremental(stock_code: str, stock_name: str, output_dir: str = None, force: bool = False) -> Dict:
    """
    增量导出K线数据

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        output_dir: 输出目录
        force: 强制全量导出（删除已有文件重新下载）

    Returns:
        导出结果 {path, new_count, total_count}
    """
    export_dir = get_stock_export_dir(stock_code, stock_name, output_dir)
    file_path = os.path.join(export_dir, "K线数据.csv")

    # 强制全量导出：删除已有文件
    if force and os.path.exists(file_path):
        os.remove(file_path)
        print(f"  已删除旧文件，重新全量获取", file=sys.stderr)

    # 检查已有数据的最后日期
    last_date = get_last_export_date(file_path, "date")

    if last_date:
        # 增量获取：从最后日期的下一天开始
        start_date = (datetime.strptime(last_date, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
        print(f"  K线增量更新: 从 {start_date} 开始", file=sys.stderr)
    else:
        # 全量获取：5年数据
        start_date = (datetime.now() - timedelta(days=1825)).strftime("%Y%m%d")
        print(f"  K线全量获取: 从 {start_date} 开始 (5年)", file=sys.stderr)

    end_date = datetime.now().strftime("%Y%m%d")

    # 如果开始日期已经是今天或未来，无需获取
    if start_date >= end_date:
        print(f"  K线数据已是最新", file=sys.stderr)
        if os.path.exists(file_path):
            existing = pd.read_csv(file_path, encoding="utf-8-sig")
            return {"path": file_path, "new_count": 0, "total_count": len(existing)}
        return {"path": file_path, "new_count": 0, "total_count": 0}

    df = get_kline_data(stock_code, start_date=start_date, end_date=end_date)

    if df.empty and last_date:
        print(f"  无新增K线数据", file=sys.stderr)
        existing = pd.read_csv(file_path, encoding="utf-8-sig")
        return {"path": file_path, "new_count": 0, "total_count": len(existing)}

    new_count = merge_and_save_csv(df, file_path, "date")

    # 获取总记录数
    total_df = pd.read_csv(file_path, encoding="utf-8-sig")

    return {"path": file_path, "new_count": new_count, "total_count": len(total_df)}


def export_chip_incremental(stock_code: str, stock_name: str, output_dir: str = None, force: bool = False) -> Dict:
    """
    增量导出筹码分布数据

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        output_dir: 输出目录
        force: 强制全量导出

    Returns:
        导出结果 {path, new_count, total_count}
    """
    export_dir = get_stock_export_dir(stock_code, stock_name, output_dir)
    file_path = os.path.join(export_dir, "筹码分布.csv")

    # 强制全量导出：删除已有文件
    if force and os.path.exists(file_path):
        os.remove(file_path)
        print(f"  已删除旧文件，重新全量获取", file=sys.stderr)

    # 检查已有数据的最后日期
    last_date = get_last_export_date(file_path, "date")

    if last_date:
        print(f"  筹码增量更新: 最后记录 {last_date}", file=sys.stderr)
    else:
        print(f"  筹码全量获取", file=sys.stderr)

    # 筹码分布API只能获取最近数据，无法指定日期
    df = get_chip_distribution(stock_code)

    if df.empty:
        if os.path.exists(file_path):
            existing = pd.read_csv(file_path, encoding="utf-8-sig")
            return {"path": file_path, "new_count": 0, "total_count": len(existing)}
        return {"path": file_path, "new_count": 0, "total_count": 0}

    new_count = merge_and_save_csv(df, file_path, "date")

    # 获取总记录数
    total_df = pd.read_csv(file_path, encoding="utf-8-sig")

    return {"path": file_path, "new_count": new_count, "total_count": len(total_df)}


def export_news_incremental(stock_code: str, stock_name: str, output_dir: str = None, force: bool = False) -> Dict:
    """
    增量导出资讯明细

    Args:
        stock_code: 股票代码
        stock_name: 股票名称
        output_dir: 输出目录
        force: 强制全量导出

    Returns:
        导出结果 {path, new_count, total_count}
    """
    export_dir = get_stock_export_dir(stock_code, stock_name, output_dir)
    file_path = os.path.join(export_dir, "资讯明细.csv")

    # 强制全量导出：删除已有文件
    if force and os.path.exists(file_path):
        os.remove(file_path)
        print(f"  已删除旧文件，重新全量获取", file=sys.stderr)

    # 检查已有数据的最后日期
    last_date = get_last_export_date(file_path, "date")

    if last_date:
        print(f"  资讯增量更新: 最后记录 {last_date}", file=sys.stderr)
    else:
        print(f"  资讯全量获取", file=sys.stderr)

    df = get_news_details(stock_code, stock_name, days=90)

    if df.empty:
        if os.path.exists(file_path):
            existing = pd.read_csv(file_path, encoding="utf-8-sig")
            return {"path": file_path, "new_count": 0, "total_count": len(existing)}
        return {"path": file_path, "new_count": 0, "total_count": 0}

    # 资讯需要按日期+标题去重
    if os.path.exists(file_path):
        try:
            existing_df = pd.read_csv(file_path, encoding="utf-8-sig")
            combined_df = pd.concat([existing_df, df], ignore_index=True)
            # 按日期和标题去重
            combined_df = combined_df.drop_duplicates(subset=["date", "title"], keep="last")
            combined_df = combined_df.sort_values(by="date").reset_index(drop=True)
            new_count = len(combined_df) - len(existing_df)
        except Exception:
            combined_df = df
            new_count = len(df)
    else:
        combined_df = df
        new_count = len(df)

    combined_df.to_csv(file_path, index=False, encoding="utf-8-sig")

    return {"path": file_path, "new_count": new_count, "total_count": len(combined_df)}


def export_all_data(stock_code: str, output_dir: str = None, force: bool = False) -> Dict:
    """
    导出所有数据（K线、筹码分布、资讯明细）

    Args:
        stock_code: 股票代码
        output_dir: 输出根目录，默认为 /Users/asta/stocks
        force: 强制全量导出

    Returns:
        导出结果字典
    """
    from .data_fetcher import get_stock_name

    stock_name = get_stock_name(stock_code)
    export_dir = get_stock_export_dir(stock_code, stock_name, output_dir)

    print(f"导出目录: {export_dir}", file=sys.stderr)

    results = {
        "export_dir": export_dir,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "files": {}
    }

    # 1. K线数据
    print("正在导出K线数据...", file=sys.stderr)
    kline_result = export_kline_incremental(stock_code, stock_name, output_dir, force=force)
    results["files"]["kline"] = kline_result

    # 2. 筹码分布
    print("正在导出筹码分布...", file=sys.stderr)
    chip_result = export_chip_incremental(stock_code, stock_name, output_dir, force=force)
    results["files"]["chip"] = chip_result

    # 3. 资讯明细
    print("正在导出资讯明细...", file=sys.stderr)
    news_result = export_news_incremental(stock_code, stock_name, output_dir, force=force)
    results["files"]["news"] = news_result

    return results


# 兼容旧接口
def export_kline_csv(stock_code: str, output_path: str = None, days: int = 730) -> str:
    """兼容旧接口：导出K线数据"""
    from .data_fetcher import get_stock_name
    stock_name = get_stock_name(stock_code)
    result = export_kline_incremental(stock_code, stock_name)
    return result.get("path", "")


def export_chip_csv(stock_code: str, output_path: str = None) -> str:
    """兼容旧接口：导出筹码分布"""
    from .data_fetcher import get_stock_name
    stock_name = get_stock_name(stock_code)
    result = export_chip_incremental(stock_code, stock_name)
    return result.get("path", "")
