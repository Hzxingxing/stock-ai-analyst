# Web模板文件说明

## 已创建的模板

所有模板文件位于: `backend/src/web/templates/`

### 1. base.html
基础模板，包含：
- 导航栏
- Bootstrap 5样式
- 通用布局结构
- 所有其他模板继承此模板

### 2. dashboard.html
仪表板页面（首页）
- 显示统计信息卡片
- 分析股票数、今日分析等
- 快速操作按钮

路由: `/dashboard` 或 `/`

### 3. stocks.html
股票管理页面
- 搜索市场股票（通过AKShare）
- 显示搜索结果
- 我的股票分析列表
- 添加/删除/启用/禁用股票

路由: `/stocks`

相关JS: `static/js/stocks.js`

### 4. stock_detail.html
股票详情页面
- 股票基本信息
- K线图表（需要后端API）
- AI分析结果
- 财务数据
- 技术指标
- 最新公告
- 相关新闻

路由: `/stocks/{stock_code}`

### 5. reports.html
分析报告页面
- 报告列表
- 生成新报告按钮
- 报告详情查看
- Claude汇总分析

路由: `/reports`

### 6. error.html
错误页面
- 显示错误信息
- 返回导航按钮

## 模板使用的静态资源

### CSS
- `static/css/style.css` - 自定义样式
- Bootstrap 5 (CDN)

### JavaScript
- `static/js/stocks.js` - 股票管理页面逻辑
- Bootstrap 5 (CDN)

## 页面导航结构

```
/ (重定向到 /dashboard)
├── /dashboard - 仪表板
├── /stocks - 股票管理
│   └── /stocks/{code} - 股票详情
└── /reports - 分析报告
```

## API接口

前端页面调用的API接口（在 `src/web/routes/api.py`）：

### 股票搜索
- `POST /api/stocks/search` - 搜索市场股票
- `GET /api/stocks/info/{code}` - 获取股票信息

### 股票管理
- `GET /api/stocks` - 获取股票列表
- `POST /api/stocks` - 添加股票
- `PUT /api/stocks/{code}` - 更新股票
- `DELETE /api/stocks/{code}` - 删除股票
- `GET /api/stocks/{code}` - 获取股票详情

## 后续开发建议

### 需要添加的API接口

1. **K线数据API**
   - `GET /api/stocks/{code}/kline?days=60`
   - 返回最近N天的K线数据

2. **AI分析结果API**
   - `GET /api/stocks/{code}/analysis?date=2026-01-19`
   - 返回指定日期的Gemini分析结果

3. **财务数据API**
   - `GET /api/stocks/{code}/financials?limit=5`
   - 返回最近N期财报

4. **公告/新闻API**
   - `GET /api/stocks/{code}/announcements?days=30`
   - `GET /api/stocks/{code}/news?days=30`

5. **报告生成API**
   - `POST /api/reports/generate`
   - 生成Claude汇总报告
   - `GET /api/reports` - 获取报告列表
   - `GET /api/reports/{date}` - 获取指定日期报告

### 需要完善的功能

1. **图表展示**
   - 集成ECharts显示K线图
   - 技术指标图表
   - 财务趋势图

2. **实时更新**
   - WebSocket推送数据更新
   - 自动刷新分析状态

3. **搜索优化**
   - 搜索结果分页
   - 搜索历史记录
   - 热门股票推荐

4. **用户体验**
   - 加载动画
   - Toast通知（替代alert）
   - 表格排序和筛选

## 快速测试

启动Web服务后访问：

```bash
# 启动服务
cd backend
uvicorn src.web.main:app --reload --port 8000

# 访问页面
http://localhost:8000                    # 首页
http://localhost:8000/stocks             # 股票管理
http://localhost:8000/stocks/600519      # 股票详情（需要先添加）
http://localhost:8000/reports            # 分析报告
```

## 注意事项

1. 所有模板都继承自 `base.html`
2. 使用Jinja2模板引擎
3. 样式使用Bootstrap 5
4. JavaScript使用原生ES6（无需构建）
5. 部分功能需要后端API支持才能完全工作
