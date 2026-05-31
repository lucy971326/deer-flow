# Backend Dockerfile — 多阶段构建
# Stage 1 (builder): 使用 build-essential 编译原生 Python 扩展
# Stage 2 (dev):     保留工具链用于开发容器（启动时运行 uv sync）
# Stage 3 (runtime): 精简镜像，不含编译器工具链，用于生产环境

# UV 源镜像（可通过 UV_IMAGE 覆盖，适用于无法访问 ghcr.io 的受限网络）
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.7.20
FROM ${UV_IMAGE} AS uv-source

# ── Stage 1: Builder（构建阶段）────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

ARG NODE_MAJOR=22
ARG APT_MIRROR
ARG UV_INDEX_URL
# 可选安装的额外依赖（例如 "postgres" 支持 PostgreSQL）
# 用法：docker build --build-arg UV_EXTRAS=postgres ...
ARG UV_EXTRAS

# 可选覆盖 apt 镜像源（适用于受限网络，例如 APT_MIRROR=mirrors.aliyun.com）
RUN if [ -n "${APT_MIRROR}" ]; then \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || true; \
      sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list 2>/dev/null || true; \
    fi

# 安装构建工具 + Node.js（build-essential 用于编译原生 Python 扩展）
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    gnupg \
    ca-certificates \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv（源镜像可通过 UV_IMAGE 构建参数覆盖）
COPY --from=uv-source /uv /uvx /usr/local/bin/

# 设置工作目录
WORKDIR /app

# 复制 backend 源码
COPY backend ./backend

# 安装依赖（使用缓存挂载）
# 当设置了 UV_EXTRAS 时（例如 "postgres"），安装可选依赖。
RUN --mount=type=cache,target=/root/.cache/uv \
    sh -c "cd backend && UV_INDEX_URL=${UV_INDEX_URL:-https://pypi.org/simple} uv sync ${UV_EXTRAS:+--extra $UV_EXTRAS}"

# 设置 UTF-8 locale 防止中文/emoji 内容在最小容器中出现 UnicodeEncodeError，
# 因为精简容器可能缺少 locale 配置，默认编码不是 UTF-8。
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8

# ── Stage 2: Dev（开发阶段）─────────────────────────────────────────────────
# 从 builder 保留编译器工具链，使开发容器启动时能运行 `uv sync` 构建源码分发包。
FROM builder AS dev

# 安装 Docker CLI（用于 DooD：允许通过宿主机 Docker socket 启动沙箱容器）
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

EXPOSE 8001 2024

CMD ["sh", "-c", "cd backend && PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001"]

# ── Stage 3: Runtime（生产阶段）──────────────────────────────────────────────
# 精简镜像，不含 build-essential — 减少体积（约 200MB）和攻击面。
FROM python:3.12-slim-bookworm

ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=utf-8

# 从 builder 复制 Node.js 运行时（提供 npx 用于 MCP servers）
COPY --from=builder /usr/bin/node /usr/bin/node
COPY --from=builder /usr/lib/node_modules /usr/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/bin/npx

# 安装 Docker CLI（用于 DooD：允许通过宿主机 Docker socket 启动沙箱容器）
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

# 安装 uv（源镜像可通过 UV_IMAGE 构建参数覆盖）
COPY --from=uv-source /uv /uvx /usr/local/bin/

# 设置工作目录
WORKDIR /app

# 从 builder 复制带有预构建虚拟环境的 backend
COPY --from=builder /app/backend ./backend

# 暴露端口（gateway: 8001, langgraph: 2024）
EXPOSE 8001 2024

# 默认启动命令（可在 docker-compose 中覆盖）
CMD ["sh", "-c", "cd backend && PYTHONPATH=. uv run --no-sync uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001"]
