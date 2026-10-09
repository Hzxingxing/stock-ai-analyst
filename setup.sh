#!/bin/bash
# 股票AI分析系统 - 快速设置脚本（使用uv）

set -e

echo "=================================="
echo "  股票AI分析系统 - 环境设置"
echo "=================================="
echo ""

# 检查Python 3.12
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
    echo "✓ Python版本: $(python3.12 --version)"
elif command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    if [[ $(echo "$PYTHON_VERSION >= 3.12" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
        PYTHON_CMD="python3"
        echo "✓ Python版本: $(python3 --version)"
    else
        echo "❌ 错误: 需要Python 3.12+，当前版本: $(python3 --version)"
        echo "请安装Python 3.12: https://www.python.org/downloads/"
        exit 1
    fi
else
    echo "❌ 错误: 未找到python3"
    exit 1
fi

# 检查uv
if ! command -v uv &> /dev/null; then
    echo "⚠️  未找到uv，正在安装..."
    pip3 install uv
    echo "✓ uv安装完成"
else
    echo "✓ uv版本: $(uv --version)"
fi

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "⚠️  虚拟环境不存在，正在创建..."
    $PYTHON_CMD -m venv .venv
    echo "✓ 虚拟环境创建完成（使用 $PYTHON_CMD）"
else
    echo "✓ 虚拟环境已存在"
fi

# 激活虚拟环境
echo ""
echo "激活虚拟环境..."
source .venv/bin/activate

# 进入backend目录
cd backend

# 安装依赖
echo ""
echo "正在使用uv安装依赖..."
echo "（这可能需要1-2分钟，uv比pip快很多）"
uv pip install -r requirements.txt

echo ""
echo "✓ 依赖安装完成！"

# 检查.env文件
if [ ! -f .env ]; then
    echo ""
    echo "⚠️  未找到.env文件，从模板创建..."
    cp .env.example .env
    echo "✓ 已创建 backend/.env"
    echo ""
    echo "⚠️  请编辑 backend/.env 文件，填入以下配置："
    echo "   - MYSQL_PASSWORD (MySQL数据库密码)"
    echo "   - NEWAPI_KEY (NewAPI密钥)"
    echo "   - NEWAPI_ENDPOINT (NewAPI端点URL)"
else
    echo "✓ .env文件已存在"
fi

echo ""
echo "=================================="
echo "  ✓ 环境设置完成！"
echo "=================================="
echo ""
echo "接下来的步骤："
echo ""
echo "1. 配置环境变量："
echo "   vim backend/.env"
echo ""
echo "2. 初始化数据库："
echo "   python src/database/init_db.py"
echo ""
echo "3. 启动Web服务："
echo "   uvicorn src.web.main:app --reload --port 8000"
echo ""
echo "4. 访问系统："
echo "   http://localhost:8000"
echo ""
echo "提示: 如果虚拟环境未激活，运行："
echo "   source .venv/bin/activate"
echo ""
