# syntax=docker/dockerfile:1
# 多阶段构建 Dockerfile for Hentai Assistant
# 启用 BuildKit 优化构建性能

# 阶段1: 构建 Vue.js 前端
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制 package.json 和 package-lock.json 以利用缓存
COPY webui/package*.json ./

# 安装依赖（生产环境）
RUN npm ci --only=production && npm cache clean --force

# 复制源码并构建
COPY webui/ ./

# 构建生产版本
RUN npm run build && \
    npm prune --production

# 阶段2: 构建 Python 后端
FROM python:3.13-slim AS backend

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    libzbar0 \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

# 创建非root用户
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# 复制 requirements.txt 并安装依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY src/ ./src/
COPY scripts/ ./scripts/

# 从前端构建阶段复制构建的静态文件
COPY --from=frontend-builder /app/frontend/dist ./webui/dist/

# 创建数据目录并设置权限
RUN mkdir -p ./data/download/ehentai ./data/logs && \
    chown -R appuser:appuser /app

# 切换到非root用户
USER appuser

# 暴露端口
EXPOSE 5001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5001/api/task_stats || exit 1

# 启动命令
CMD ["python", "src/main.py"]