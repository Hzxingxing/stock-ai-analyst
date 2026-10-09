"""
SQLAlchemy ORM模型定义
包含股票AI分析系统的所有数据库表模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, Date, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Stock(Base):
    """股票基础信息表"""
    __tablename__ = 'stocks'
    __table_args__ = (
        {'mysql_charset': 'utf8mb4', 'mysql_collate': 'utf8mb4_unicode_ci', 'comment': '股票基础信息表'}
    )

    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), primary_key=True, comment='股票代码')
    stock_name = Column(String(50), nullable=False, comment='股票名称')
    market = Column(String(2), comment='市场(SH/SZ)')
    is_active = Column(Integer, default=1, comment='是否启用(1=是,0=否)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关系
    klines = relationship("StockKLine", back_populates="stock", cascade="all, delete-orphan")
    chip_distributions = relationship("StockChipDistribution", back_populates="stock", cascade="all, delete-orphan")
    financials = relationship("StockFinancial", back_populates="stock", cascade="all, delete-orphan")
    announcements = relationship("StockAnnouncement", back_populates="stock", cascade="all, delete-orphan")
    news = relationship("StockNews", back_populates="stock", cascade="all, delete-orphan")
    analyses = relationship("GeminiAnalysis", back_populates="stock", cascade="all, delete-orphan")
    valuations = relationship("StockValuation", back_populates="stock", cascade="all, delete-orphan")
    fund_flows = relationship("StockFundFlow", back_populates="stock", cascade="all, delete-orphan")
    holders = relationship("StockHolder", back_populates="stock", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Stock(code={self.stock_code}, name={self.stock_name})>"


class StockKLine(Base):
    """K线数据表"""
    __tablename__ = 'stock_kline'
    __table_args__ = (
        Index('idx_stock_date', 'stock_code', 'date', unique=True),
        {'mysql_charset': 'utf8mb4', 'comment': 'K线数据表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    date = Column(Date, nullable=False, index=True, comment='日期')
    open = Column(Float, comment='开盘价')
    high = Column(Float, comment='最高价')
    low = Column(Float, comment='最低价')
    close = Column(Float, comment='收盘价')
    volume = Column(Float, comment='成交量')
    amount = Column(Float, comment='成交额')

    # 技术指标
    ma5 = Column(Float, comment='5日均线')
    ma10 = Column(Float, comment='10日均线')
    ma20 = Column(Float, comment='20日均线')
    ma60 = Column(Float, comment='60日均线')
    macd = Column(Float, comment='MACD')
    dif = Column(Float, comment='DIF')
    dea = Column(Float, comment='DEA')
    rsi = Column(Float, comment='RSI')
    kdj_k = Column(Float, comment='KDJ_K')
    kdj_d = Column(Float, comment='KDJ_D')
    kdj_j = Column(Float, comment='KDJ_J')
    boll_upper = Column(Float, comment='布林带上轨')
    boll_mid = Column(Float, comment='布林带中轨')
    boll_lower = Column(Float, comment='布林带下轨')

    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="klines")

    def __repr__(self):
        return f"<StockKLine(code={self.stock_code}, date={self.date}, close={self.close})>"


class StockChipDistribution(Base):
    """筹码分布表"""
    __tablename__ = 'stock_chip_distribution'
    __table_args__ = (
        Index('idx_chip_stock_date', 'stock_code', 'date', unique=True),
        {'mysql_charset': 'utf8mb4', 'comment': '筹码分布表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    date = Column(Date, nullable=False, index=True, comment='日期')
    profit_ratio = Column(Float, comment='获利比例(%)')
    avg_cost = Column(Float, comment='平均成本(元)')
    cost_90_low = Column(Float, comment='90%成本区间下限(元)')
    cost_90_high = Column(Float, comment='90%成本区间上限(元)')
    concentration_90 = Column(Float, comment='90%集中度(%)')
    cost_70_low = Column(Float, comment='70%成本区间下限(元)')
    cost_70_high = Column(Float, comment='70%成本区间上限(元)')
    concentration_70 = Column(Float, comment='70%集中度(%)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="chip_distributions")

    def __repr__(self):
        return f"<StockChipDistribution(code={self.stock_code}, date={self.date}, profit_ratio={self.profit_ratio})>"


class StockFinancial(Base):
    """财务数据表"""
    __tablename__ = 'stock_financials'
    __table_args__ = (
        Index('idx_stock_report', 'stock_code', 'report_date', unique=True),
        {'mysql_charset': 'utf8mb4', 'comment': '财务数据表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    report_date = Column(Date, nullable=False, comment='报告期')
    report_type = Column(String(10), comment='报告类型(Q1/Q2/Q3/年报)')

    # 利润表
    revenue = Column(Float, comment='营业收入')
    net_profit = Column(Float, comment='净利润')
    gross_profit = Column(Float, comment='毛利润')
    operating_profit = Column(Float, comment='营业利润')

    # 资产负债表
    total_assets = Column(Float, comment='总资产')
    total_liabilities = Column(Float, comment='总负债')
    net_assets = Column(Float, comment='净资产')
    current_assets = Column(Float, comment='流动资产')
    current_liabilities = Column(Float, comment='流动负债')

    # 现金流量表
    operating_cash_flow = Column(Float, comment='经营活动现金流')
    investing_cash_flow = Column(Float, comment='投资活动现金流')
    financing_cash_flow = Column(Float, comment='筹资活动现金流')

    # 财务指标
    eps = Column(Float, comment='每股收益')
    roe = Column(Float, comment='净资产收益率')
    roa = Column(Float, comment='总资产收益率')
    debt_ratio = Column(Float, comment='资产负债率')
    current_ratio = Column(Float, comment='流动比率')
    quick_ratio = Column(Float, comment='速动比率')
    gross_margin = Column(Float, comment='毛利率')
    net_margin = Column(Float, comment='净利率')

    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="financials")

    def __repr__(self):
        return f"<StockFinancial(code={self.stock_code}, date={self.report_date})>"


class StockAnnouncement(Base):
    """公告数据表"""
    __tablename__ = 'stock_announcements'
    __table_args__ = (
        Index('idx_stock_announcement_date', 'stock_code', 'announcement_date'),
        Index('idx_unique_announcement', 'stock_code', 'announcement_date', 'title', unique=True),
        {'mysql_charset': 'utf8mb4', 'comment': '公告数据表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    announcement_date = Column(Date, nullable=False, comment='公告日期')
    announcement_type = Column(String(50), comment='公告类型')
    title = Column(String(500), comment='公告标题')
    content = Column(Text, comment='公告内容')
    url = Column(String(500), comment='公告链接')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="announcements")

    def __repr__(self):
        return f"<StockAnnouncement(code={self.stock_code}, date={self.announcement_date}, type={self.announcement_type})>"


class StockNews(Base):
    """新闻资讯表"""
    __tablename__ = 'stock_news'
    __table_args__ = (
        Index('idx_stock_news_date', 'stock_code', 'news_date'),
        Index('idx_unique_news', 'stock_code', 'news_date', 'title', unique=True),
        {'mysql_charset': 'utf8mb4', 'comment': '新闻资讯表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    news_date = Column(Date, nullable=False, comment='新闻日期')
    news_type = Column(String(50), comment='新闻类型')
    title = Column(String(500), comment='新闻标题')
    content = Column(Text, comment='新闻内容')
    source = Column(String(200), comment='新闻来源')
    url = Column(String(500), comment='新闻链接')
    sentiment = Column(String(20), comment='情绪倾向(正面/中性/负面)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="news")

    def __repr__(self):
        return f"<StockNews(code={self.stock_code}, date={self.news_date}, title={self.title[:30]})>"


class GeminiAnalysis(Base):
    """Gemini AI分析结果表"""
    __tablename__ = 'gemini_analysis'
    __table_args__ = (
        Index('idx_stock_analysis_date', 'stock_code', 'analysis_date', unique=True),
        {'mysql_charset': 'utf8mb4', 'comment': 'Gemini AI分析结果表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    analysis_date = Column(Date, nullable=False, index=True, comment='分析日期')
    model_name = Column(String(50), comment='使用的模型名称')
    prompt_tokens = Column(Integer, comment='Prompt消耗的Token数')
    completion_tokens = Column(Integer, comment='Completion消耗的Token数')
    analysis_result = Column(JSON, comment='分析结果(JSON格式)')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="analyses")

    def __repr__(self):
        return f"<GeminiAnalysis(code={self.stock_code}, date={self.analysis_date}, model={self.model_name})>"


class ClaudeReport(Base):
    """Claude汇总报告表"""
    __tablename__ = 'claude_reports'
    __table_args__ = (
        {'mysql_charset': 'utf8mb4', 'comment': 'Claude汇总报告表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(Date, nullable=False, unique=True, index=True, comment='报告日期')
    report_type = Column(String(20), default='daily', comment='报告类型(daily/weekly/monthly)')
    top_opportunities = Column(JSON, comment='Top投资机会(JSON格式)')
    market_overview = Column(Text, comment='市场概况')
    full_report = Column(Text, comment='完整报告')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    def __repr__(self):
        return f"<ClaudeReport(date={self.report_date}, type={self.report_type})>"


class MarketStatistics(Base):
    """市场统计数据表"""
    __tablename__ = 'market_statistics'
    __table_args__ = (
        {'mysql_charset': 'utf8mb4', 'comment': '市场整体统计数据表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stat_date = Column(Date, nullable=False, unique=True, index=True, comment='统计日期')
    total_stocks = Column(Integer, comment='总股票数')
    up_count = Column(Integer, comment='上涨家数')
    down_count = Column(Integer, comment='下跌家数')
    flat_count = Column(Integer, comment='平盘家数')
    limit_up_count = Column(Integer, comment='涨停家数')
    limit_down_count = Column(Integer, comment='跌停家数')
    total_volume = Column(Float, comment='总成交量(手)')
    total_amount = Column(Float, comment='总成交额(元)')
    up_over_7_count = Column(Integer, comment='涨幅>7%家数')
    up_5_to_7_count = Column(Integer, comment='涨幅5-7%家数')
    up_3_to_5_count = Column(Integer, comment='涨幅3-5%家数')
    up_0_to_3_count = Column(Integer, comment='涨幅0-3%家数')
    down_0_to_3_count = Column(Integer, comment='跌幅0-3%家数')
    down_3_to_5_count = Column(Integer, comment='跌幅3-5%家数')
    down_5_to_7_count = Column(Integer, comment='跌幅5-7%家数')
    down_over_7_count = Column(Integer, comment='跌幅>7%家数')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    def __repr__(self):
        return f"<MarketStatistics(date={self.stat_date}, total_stocks={self.total_stocks})>"


class StockValuation(Base):
    """股票估值指标表"""
    __tablename__ = 'stock_valuation'
    __table_args__ = (
        Index('idx_valuation_stock_date', 'stock_code', 'date', unique=True),
        {'mysql_charset': 'utf8mb4', 'comment': '股票估值指标表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    date = Column(Date, nullable=False, index=True, comment='日期')

    # 估值指标
    pe_ttm = Column(Float, comment='市盈率(TTM)')
    pe_static = Column(Float, comment='市盈率(静态)')
    pb = Column(Float, comment='市净率')
    ps_ttm = Column(Float, comment='市销率(TTM)')
    pcf = Column(Float, comment='市现率')
    peg = Column(Float, comment='PEG')

    # 市值数据
    total_mv = Column(Float, comment='总市值(元)')
    circ_mv = Column(Float, comment='流通市值(元)')

    # 分红数据
    dividend_yield = Column(Float, comment='股息率(%)')

    # 行业对比
    industry = Column(String(50), comment='所属行业')
    industry_pe = Column(Float, comment='行业平均PE')
    industry_pb = Column(Float, comment='行业平均PB')

    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="valuations")

    def __repr__(self):
        return f"<StockValuation(code={self.stock_code}, date={self.date}, pe={self.pe_ttm}, pb={self.pb})>"


class StockFundFlow(Base):
    """资金流向表"""
    __tablename__ = 'stock_fund_flow'
    __table_args__ = (
        Index('idx_fund_flow_stock_date', 'stock_code', 'date', unique=True),
        {'mysql_charset': 'utf8mb4', 'comment': '资金流向表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    date = Column(Date, nullable=False, index=True, comment='日期')

    # 价格信息
    close_price = Column(Float, comment='收盘价')
    change_pct = Column(Float, comment='涨跌幅(%)')

    # 主力资金
    main_net_inflow = Column(Float, comment='主力净流入(元)')
    main_net_inflow_pct = Column(Float, comment='主力净流入占比(%)')

    # 超大单（机构）
    super_large_net_inflow = Column(Float, comment='超大单净流入(元)')
    super_large_net_inflow_pct = Column(Float, comment='超大单净流入占比(%)')

    # 大单
    large_net_inflow = Column(Float, comment='大单净流入(元)')
    large_net_inflow_pct = Column(Float, comment='大单净流入占比(%)')

    # 中单
    medium_net_inflow = Column(Float, comment='中单净流入(元)')
    medium_net_inflow_pct = Column(Float, comment='中单净流入占比(%)')

    # 小单（散户）
    small_net_inflow = Column(Float, comment='小单净流入(元)')
    small_net_inflow_pct = Column(Float, comment='小单净流入占比(%)')

    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="fund_flows")

    def __repr__(self):
        return f"<StockFundFlow(code={self.stock_code}, date={self.date}, main_inflow={self.main_net_inflow})>"


class StockHolder(Base):
    """股东数据表"""
    __tablename__ = 'stock_holder'
    __table_args__ = (
        Index('idx_holder_stock_date', 'stock_code', 'report_date'),
        {'mysql_charset': 'utf8mb4', 'comment': '股东数据表'}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10, collation='utf8mb4_unicode_ci'), ForeignKey('stocks.stock_code'), nullable=False, index=True, comment='股票代码')
    report_date = Column(Date, nullable=False, index=True, comment='报告期')

    # 股东人数
    total_holders = Column(Integer, comment='股东总数')
    avg_hold_num = Column(Float, comment='平均持股数')
    holder_change = Column(Integer, comment='股东人数变化')
    holder_change_pct = Column(Float, comment='股东人数变化率(%)')

    # 十大股东汇总
    top10_hold_ratio = Column(Float, comment='十大股东合计持股比例(%)')
    first_holder_name = Column(String(200), comment='第一大股东名称')
    first_holder_ratio = Column(Float, comment='第一大股东持股比例(%)')
    control_type = Column(String(20), comment='控股类型')

    # 集中度分析
    concentration_trend = Column(String(50), comment='集中度趋势')

    # 十大股东详情（JSON）
    top_holders_detail = Column(JSON, comment='十大股东详情')

    created_at = Column(DateTime, default=datetime.now, comment='创建时间')

    stock = relationship("Stock", back_populates="holders")

    def __repr__(self):
        return f"<StockHolder(code={self.stock_code}, date={self.report_date}, holders={self.total_holders})>"
