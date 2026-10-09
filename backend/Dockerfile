FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 安装uv（快速的Python包管理器）
RUN pip install --no-cache-dir uv

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN uv pip install --system --no-cache -r requirements.txt

# 复制应用代码
COPY . .

# 设置时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 暴露端口
EXPOSE 8000

# 默认命令（可被docker-compose覆盖）
CMD ["uvicorn", "src.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
