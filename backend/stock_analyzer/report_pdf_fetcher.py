"""财报PDF获取模块 - 从巨潮资讯获取上市公司财务报告PDF"""

import os
import requests
from typing import List, Dict, Optional
from datetime import datetime


# 报告类型映射
REPORT_CATEGORIES = {
    "年报": "category_ndbg_szsh",      # 年度报告
    "半年报": "category_bndbg_szsh",   # 半年度报告
    "一季报": "category_yjdbg_szsh",   # 第一季度报告
    "三季报": "category_sjdbg_szsh",   # 第三季度报告
    "全部": "",                        # 所有定期报告
}


def get_market_code(stock_code: str) -> str:
    """
    根据股票代码判断市场

    Args:
        stock_code: 股票代码

    Returns:
        市场代码 szse/sse
    """
    if stock_code.startswith(('6', '9')):
        return 'sse'  # 上交所
    else:
        return 'szse'  # 深交所


def get_org_id(stock_code: str) -> str:
    """
    生成巨潮资讯的orgId

    Args:
        stock_code: 股票代码

    Returns:
        orgId格式字符串
    """
    market = get_market_code(stock_code)
    if market == 'sse':
        return f"gssh{stock_code}"
    else:
        return f"gssz{stock_code}"


def get_financial_reports(
    stock_code: str,
    report_type: str = "全部",
    limit: int = 10
) -> List[Dict]:
    """
    获取股票的财务报告列表（包含PDF下载链接）

    Args:
        stock_code: 股票代码，如 "000151"
        report_type: 报告类型 - "年报"、"半年报"、"一季报"、"三季报"、"全部"
        limit: 返回数量限制

    Returns:
        财务报告列表，每条包含: title, report_date, pdf_url, report_type
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
    }

    url = 'http://www.cninfo.com.cn/new/hisAnnouncement/query'
    market = get_market_code(stock_code)
    org_id = get_org_id(stock_code)
    category = REPORT_CATEGORIES.get(report_type, "")

    data = {
        'stock': f'{stock_code},{org_id}',
        'tabName': 'fulltext',
        'pageSize': limit,
        'pageNum': 1,
        'column': market,
        'category': category,
        'plate': '',
        'seDate': '',
        'searchkey': '',
        'secid': '',
        'sortName': '',
        'sortType': '',
        'isHLtitle': 'true',
    }

    try:
        resp = requests.post(url, data=data, headers=headers, timeout=15)
        result = resp.json()

        reports = []
        if result.get('announcements'):
            for ann in result['announcements']:
                title = ann.get('announcementTitle', '')

                # 过滤只保留定期报告（年报、半年报、季报）
                if not any(keyword in title for keyword in ['年度报告', '半年度报告', '季度报告', '年报', '半年报', '季报']):
                    continue

                # 排除摘要、英文版等
                if '摘要' in title or '英文' in title or '更正' in title:
                    continue

                adj_url = ann.get('adjunctUrl', '')
                if adj_url:
                    pdf_url = f'http://static.cninfo.com.cn/{adj_url}'
                else:
                    pdf_url = None

                # 解析报告时间
                ann_time = ann.get('announcementTime', '')
                if ann_time:
                    try:
                        report_date = datetime.fromtimestamp(ann_time / 1000).strftime('%Y-%m-%d')
                    except:
                        report_date = ''
                else:
                    report_date = ''

                # 判断报告类型
                if '年度报告' in title or '年报' in title:
                    r_type = '年报'
                elif '半年度' in title or '半年报' in title:
                    r_type = '半年报'
                elif '第一季度' in title or '一季报' in title:
                    r_type = '一季报'
                elif '第三季度' in title or '三季报' in title:
                    r_type = '三季报'
                else:
                    r_type = '其他'

                reports.append({
                    'title': title,
                    'report_date': report_date,
                    'pdf_url': pdf_url,
                    'report_type': r_type,
                    'announcement_id': ann.get('announcementId', ''),
                    'file_size': ann.get('adjunctSize', 0),  # 文件大小(KB)
                })

        return reports

    except Exception as e:
        print(f"获取财报列表失败: {e}")
        return []


def download_report_pdf(
    pdf_url: str,
    save_path: str,
    timeout: int = 60
) -> bool:
    """
    下载财报PDF文件

    Args:
        pdf_url: PDF下载链接
        save_path: 保存路径
        timeout: 下载超时时间(秒)

    Returns:
        是否下载成功
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }

    try:
        resp = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
        resp.raise_for_status()

        # 确保目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return True

    except Exception as e:
        print(f"下载PDF失败: {e}")
        return False


def get_latest_annual_report(stock_code: str) -> Optional[Dict]:
    """
    获取最新的年度报告

    Args:
        stock_code: 股票代码

    Returns:
        最新年报信息或None
    """
    reports = get_financial_reports(stock_code, report_type="年报", limit=5)

    for report in reports:
        if report.get('pdf_url'):
            return report

    return None


def get_all_periodic_reports(stock_code: str, years: int = 3) -> List[Dict]:
    """
    获取所有定期报告（年报+季报）

    Args:
        stock_code: 股票代码
        years: 获取最近几年的报告

    Returns:
        报告列表
    """
    # 估算需要的报告数量：每年4份定期报告
    limit = years * 5
    return get_financial_reports(stock_code, report_type="全部", limit=limit)


if __name__ == "__main__":
    # 测试
    stock_code = "000151"

    print(f"获取 {stock_code} 的财报列表:")
    reports = get_financial_reports(stock_code, report_type="年报", limit=5)

    for r in reports:
        print(f"\n标题: {r['title']}")
        print(f"日期: {r['report_date']}")
        print(f"类型: {r['report_type']}")
        print(f"PDF: {r['pdf_url']}")
        print(f"大小: {r['file_size']} KB")
