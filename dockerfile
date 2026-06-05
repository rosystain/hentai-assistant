# syntax=docker/dockerfile:1
# 多阶段构建 Dockerfile for Hentai Assistant
# 启用 BuildKit 优化构建性能

# 阶段1: 构建 Vue.js 前端
# 固定为 amd64 平台，前端构建产物是纯静态文件，与 CPU 架构无关
# 避免 QEMU 模拟 ARM 时 npm ci 触发 SIGILL (exit code 132)
FROM --platform=linux/amd64 node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制 package.json 和 package-lock.json 以利用缓存
COPY webui/package*.json ./

# 安装依赖（生产环境）
RUN npm ci && npm cache clean --force

# 复制源码并构建
COPY webui/ ./

# 构建生产版本
# 优化：移除多余的 npm prune 命令
RUN npm run build

# 阶段2: 构建 Python 后端
FROM python:3.11-slim-bookworm AS python-builder

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libc6-dev \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 预编译依赖
COPY requirements.txt .
# 优化：移除多余的 pip upgrade 命令，直接使用预装的 pip
RUN pip wheel --no-cache-dir --wheel-dir=/app/wheels -r requirements.txt

# 阶段3: 最终镜像
FROM python:3.11-slim-bookworm AS backend

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libzbar0 \
    curl \
    gosu \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 创建非root用户
RUN groupadd -g 1000 appuser && useradd -u 1000 -g appuser -r appuser

# 安装Python依赖
COPY --from=python-builder /app/wheels /wheels
COPY requirements.txt .
# 优化：移除多余的 pip upgrade 命令，直接从 wheels 安装
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
    rm -rf /wheels

# 复制应用代码
COPY src/ ./src/
COPY scripts/ ./scripts/

COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
COPY --from=frontend-builder /app/frontend/dist ./webui/dist/

# 创建数据目录并设置权限
RUN mkdir -p ./data/download/ehentai ./data/logs && \
    chown -R appuser:appuser /app

# 切换到非root用户

# 暴露端口
EXPOSE 5001

ENTRYPOINT ["docker-entrypoint.sh"]

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5001/api/task_stats || exit 1

# 启动命令
CMD ["python", "src/main.py"]