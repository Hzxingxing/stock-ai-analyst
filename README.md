# 研序 · A 股研究工作台

面向持续股票研究的聊天应用。用户通过对话提出问题，LangGraph Harness 根据任务调用可追溯的数据工具，并保留账户隔离的会话、长期研究记忆与工具执行记录。数据库时间统一按 UTC 存储，市场日期按数据源交易日记录。

## 技术架构

- **前端**：React 19、TypeScript、Vite、Tailwind CSS 4。
- **API**：Python 3.12、FastAPI、SQLAlchemy 2、MySQL 8。
- **Harness**：LangGraph 管理有状态研究工作流；从单一协调器和边界明确的研究工具开始。
- **状态与缓存**：MySQL 保存研究事实、用户会话、记忆、工具轨迹和 LangGraph checkpoints；Redis 短期缓存分时、逐笔及股票目录。
- **行情源**：AKShare 适配器在可终止的子进程运行，避免供应商请求阻塞 API。

新系统仅使用 `stock_research` 数据库和 `research_mysql_data` Compose volume。旧项目代码、迁移和配置已移除；现有 `stock_analysis` 数据库及其中的旧表和记录不由本系统访问、迁移或修改。

## 数据范围

- 个股数据仅在用户关注后按需获取；日线和公告、财报、估值、资金流、筹码、股东数据持久保存。
- 上证、深证成指、创业板、科创 50、沪深 300、中证 500、中证 1000 和上证 50 属于系统级指数，独立于用户关注列表持续同步日线。
- 周线和月线从同一复权口径的日线聚合。实时行情、分时线和逐笔成交按数据源返回结果短期缓存；逐笔原始记录不写入 MySQL。
- 财务报告按报告期和披露可用日期保存，避免将尚未披露的数据用于历史时点分析。
- AKShare 筹码接口提供成本区间与集中度摘要，不提供可还原的逐价筹码柱；系统明确标记完整价位分布不可用，不伪造分布。
- 工具轨迹保存实际工具、参数摘要、结果摘要、数据来源与日期、缓存状态、耗时和错误；不保存模型隐式推理过程。

## 本地开发

需要 Python 3.12、uv、Node.js 20、npm、MySQL 8 和 Redis。

```bash
cp backend/.env.example backend/.env
# 设置 RESEARCH_MYSQL_*、LLM_API_KEY、LLM_BASE_URL、LLM_MODEL，
# 并将 AUTH_SECRET_KEY 替换为至少 32 位随机值。
uv sync --all-groups
```

在本地开发 MySQL 中创建空的 `stock_research` 数据库，然后创建有该库 DDL/DML 权限的专用用户。不要将旧 `stock_analysis` 作为 `RESEARCH_MYSQL_DATABASE`。从空库建立新 schema：

```bash
PYTHONPATH=backend uv run alembic -c backend/alembic.ini upgrade head
```

启动 API、指数同步任务和前端：

```bash
PYTHONPATH=backend uv run uvicorn app.main:app --app-dir backend --reload --port 8000
PYTHONPATH=backend uv run python -m app.jobs.market_sync
cd frontend && npm ci && npm run dev
```

打开 `http://localhost:5173`，首次使用需注册账户。密码以 Argon2 哈希保存；会话使用 HttpOnly、SameSite Strict Cookie。生产环境需启用安全 Cookie 并设置高熵 `AUTH_SECRET_KEY`。

## Docker Compose（本地开发）

Compose 启动独立的新 MySQL volume、Redis、API、市场同步进程和 Vite 前端。它不挂载或连接旧 Compose volume；所有端口绑定到本机 loopback。

```bash
cp .env.example .env
cp backend/.env.example backend/.env
# backend/.env 中填写模型配置和 AUTH_SECRET_KEY。
# Compose 从根目录 .env 读取 MySQL root 密码，并将同一密码传给仅供本地开发的 API。

docker compose up --build
```

首次启动后迁移新库：

```bash
docker compose exec api uv run --project /app alembic -c /app/backend/alembic.ini upgrade head
```

访问 `http://localhost:5173`；API 文档位于 `http://localhost:8000/docs`。

## 验证

```bash
PYTHONPATH=backend uv run pytest
PYTHONPATH=backend uv run ruff check backend/app backend/src/migrations backend/tests
cd frontend && npm run typecheck && npm run build
```

## 目录

```text
backend/app/                 # API、数据服务、供应商适配器、LangGraph Harness、同步任务
backend/src/migrations/      # 新系统独立的 Alembic 基线
frontend/src/                # React 聊天、工具轨迹、关注股票与长期记忆界面
AGENTS.md                    # 项目架构与协作规范
```
