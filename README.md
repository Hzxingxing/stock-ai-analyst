# A 股研究助手

这是一个面向 A 股研究的应用。目标体验是让用户通过简洁、严谨的聊天界面持续讨论股票；后端以受控的数据工具和有状态 Agent 工作流取数、整理证据、记录研究过程，并给出可追溯的结论。

## 产品与架构方向

- **后端**：Python 3.12、FastAPI、SQLAlchemy、MySQL。保留并逐步整理现有 Python 行情采集和分析能力。
- **Agent Harness**：以 LangGraph 管理有状态研究工作流，按需使用 LangChain 组件。先由协调器编排具备清晰边界的工具和研究节点；多 Agent 按实际协作需要引入。
- **前端**：React、TypeScript、Vite，承载新的对话体验；既有 Jinja 页面按迁移计划逐步处理。
- **缓存**：Redis 用于实时行情、分时和逐笔成交等短期数据；MySQL 保存长期研究数据、会话和审计记录。
- **研究记忆**：当前轮次上下文、会话摘要、长期用户/研究记忆和市场事实分开管理，并按用户隔离。

架构质量优先于短期改动量。若完整方案较大，应拆分为边界清楚、可独立验收的阶段；不应只为缩小首轮改动而采用明显次优方案。

### 数据范围

- 个股长期采集限于用户关注的股票；日线、财务、公告、估值、资金流、筹码和股东等研究数据按来源和时间保存。
- 上证、深证、创业板、科创板及选定的参考指数是系统默认数据，应持续保存指数日线和市场统计，不依赖用户关注列表。
- 周线、月线优先根据统一复权口径的日线计算。
- 个股实时行情、分时和逐笔按需通过数据接口获取并短期缓存。逐笔原始记录默认不长期保存，必要时保存有定义的聚合结果。
- 行情和研究结论应带来源、数据日期、采集时间及单位/口径。财报与公告分析使用实际披露时间，避免历史分析引用当时尚不可得的信息。
- 对话中需区分外部事实、用户观点和模型推断。长期记忆可查看、修订和删除。

## 当前代码基线

仓库目前仍是旧版 FastAPI/Jinja 应用和数据采集项目，目标中的 React 聊天界面、LangGraph Harness、Redis 缓存、会话管理和长期记忆尚未实现。

当前已有的主要能力：

- `backend/src/web/main.py`：FastAPI Web 应用入口；提供仪表板、股票管理、详情及报告页面。
- `backend/src/web/routes/api.py`：股票管理、行情及研究数据 API，包括按需同步和单股 AI 分析接口。
- `backend/src/services/data_sync.py`：将 AKShare 获取的个股行情及部分基本面数据写入数据库。
- `backend/src/services/gemini_analyzer.py`：通过 OpenAI 兼容接口调用配置的模型并保存分析结果。
- `backend/stock_analyzer/`：现有行情、技术指标、财务、公告、新闻和相关分析模块。
- `backend/src/database/models.py`：现有个股行情、筹码摘要、财务、公告、新闻、分析、估值、资金流、股东和市场统计模型。
- `backend/src/web/templates/`：旧版 Jinja 用户界面。

目前市场统计模型有部分每日广度和成交数据；完整的核心指数历史行情、分钟线与逐笔缓存链路尚未建立。现有筹码数据主要是成本区间等摘要，不是完整的逐价位筹码峰分布。

旧版 `/api/reports/generate` 根据已存 AI 评分生成汇总文本；尽管数据库模型沿用 `ClaudeReport` 名称，该接口不调用 Claude。仓库没有可用的 `backend/main.py` 命令行流程或 `src/scheduler` 定时任务实现。

## 本地开发

项目依赖清单目前位于 `backend/requirements.txt`。建议使用 Python 3.12；根目录 `.python-version` 与 `pyproject.toml` 的 Python 版本声明尚未统一，后续开发需一并校准。

```bash
# 在项目根目录
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
cp backend/.env.example backend/.env
```

编辑 `backend/.env` 配置数据库密码和模型服务：

```dotenv
MYSQL_PASSWORD=your_mysql_password
NEWAPI_KEY=your_api_key
NEWAPI_ENDPOINT=https://your-api-endpoint.example/v1
```

MySQL 数据库需先运行，数据库名称、用户和主机等配置见 `backend/config/config.yaml`。然后在项目根目录运行：

```bash
cd backend
../.venv/bin/python src/database/init_db.py
../.venv/bin/uvicorn src.web.main:app --reload --port 8000
```

访问 `http://localhost:8000`。`/health` 提供健康检查，`/docs` 提供 FastAPI API 文档。

初始化脚本通过 SQLAlchemy `create_all` 创建当前模型中的表并插入示例关注股票；生产环境的结构变更应使用 Alembic 迁移。初始化不会自动抓取历史行情或运行 AI 分析。

### 现有独立分析命令

旧版单股分析工具可以从 `backend` 目录运行：

```bash
python -m stock_analyzer --code 600519
python -m stock_analyzer --code 600519 --full --news
```

这与 Web 数据库同步及目标中的 Harness 工作流是不同的入口。

## 目录结构

```text
.
├── AGENTS.md                  # 项目架构、开发流程与协作约定
├── README.md
├── setup.sh                   # 旧版 Python 后端依赖安装辅助脚本
├── docker-compose.yml         # 旧版 Compose 配置，当前需整改后再依赖
└── backend/
    ├── config/                # 应用和数据源配置
    ├── src/
    │   ├── database/          # ORM、连接、Repository 和初始化
    │   ├── migrations/        # Alembic 迁移
    │   ├── services/          # 数据同步、搜索、模型分析
    │   └── web/               # FastAPI 路由、Jinja 模板和静态文件
    ├── stock_analyzer/        # 行情采集和传统分析模块
    └── requirements.txt
```

## 已知待整理项

- 根目录 `main.py` 和 `pyproject.toml` 仍是模板/占位内容，`backend/requirements.txt` 才是现有后端依赖清单。
- `.python-version` 与 `pyproject.toml` 声明 Python 3.8，安装脚本和 Dockerfile 使用 Python 3.12；需统一版本来源。
- `docker-compose.yml` 的 scheduler 服务引用不存在的模块，并包含开发者本机的绝对路径挂载；Compose 部署链路需按目标架构重新设计。
- 现有测试文件是旧版后端测试；运行前需确认数据库、密钥和外部数据服务配置，测试策略遵从 `AGENTS.md`。

## 开发约定

开始功能或重构前先按根目录 `AGENTS.md` 做只读定位并提交方案；方案确认后再实施。对数据源能力、存储期限和接口限制，不以假设替代验证。
