# Contributing to DeerFlow

感谢您对 DeerFlow 贡献感兴趣！本指南将帮助您设置开发环境并了解我们的开发工作流程。

## Development Environment Setup

我们提供两种开发环境。**推荐使用 Docker**，以获得最一致、最顺畅的体验。

### Option 1: Docker Development（推荐）

Docker 提供了一个一致的、隔离的环境，所有依赖都已预配置。无需在本地安装 Node.js、Python 或 nginx。

#### Prerequisites

- Docker Desktop 或 Docker Engine
- pnpm（用于缓存优化）

#### Setup Steps

1. **Configure the application**:
   ```bash
   # Copy example configuration
   cp config.example.yaml config.yaml

   # Set your API keys
   export OPENAI_API_KEY="your-key-here"
   # or edit config.yaml directly
   ```

2. **Initialize Docker environment**（仅首次需要）:
   ```bash
   make docker-init
   ```
   这将：
   - Build Docker images
   - Install frontend dependencies（pnpm）
   - Install backend dependencies（uv）
   - 将 pnpm cache 与 host 共享以加快构建速度

3. **Start development services**:
   ```bash
   make docker-start
   ```
   `make docker-start` 读取 `config.yaml`，仅为 provisioner/Kubernetes sandbox mode 启动 `provisioner`。

   所有 services 将启用 hot-reload：
   - Frontend 更改会自动 reload
   - Backend 更改会触发自动 restart
   - Gateway-hosted LangGraph-compatible runtime 支持 hot-reload

4. **Access the application**:
   - Web Interface: http://localhost:2026
   - API Gateway: http://localhost:2026/api/*
   - LangGraph-compatible API: http://localhost:2026/api/langgraph/*

#### Docker Commands

```bash
# Build the custom k3s image (with pre-cached sandbox image)
make docker-init
# Start Docker services (mode-aware, localhost:2026)
make docker-start
# Stop Docker development services
make docker-stop
# View Docker development logs
make docker-logs
# View Docker frontend logs
make docker-logs-frontend
# View Docker gateway logs
make docker-logs-gateway
```

如果 Docker build 在您的网络中较慢，您可以在运行 `make docker-init` 或 `make docker-start` 之前覆盖默认的 package registries：

```bash
export UV_INDEX_URL=https://pypi.org/simple
export NPM_REGISTRY=https://registry.npmjs.org
```

#### Recommended host resources

将这些作为开发和 review 环境的实际起点：

| Scenario | Starting point | Recommended | Notes |
|---------|-----------|------------|-------|
| `make dev` on one machine | 4 vCPU, 8 GB RAM | 8 vCPU, 16 GB RAM | DeerFlow 使用 hosted model APIs 时效果最佳。 |
| `make docker-start` review environment | 4 vCPU, 8 GB RAM | 8 vCPU, 16 GB RAM | Docker image builds 和 sandbox containers 需要额外的 headroom。 |
| Shared Linux test server | 8 vCPU, 16 GB RAM | 16 vCPU, 32 GB RAM | 对于更重的 multi-agent runs 或多个 reviewers，更适合选择这个配置。 |

`2 vCPU / 4 GB` 环境通常无法可靠启动，或在正常 DeerFlow workloads 下变得无响应。

#### Linux: Docker daemon permission denied

如果在 Linux 上 `make docker-init`、`make docker-start` 或 `make docker-stop` 失败并显示类似以下错误，您当前的用户可能没有访问 Docker daemon socket 的权限：

```text
unable to get image 'deer-flow-gateway': permission denied while trying to connect to the Docker daemon socket at unix:///var/run/docker.sock
```

推荐的修复方法：将您当前的用户添加到 `docker` 组，使 Docker 命令无需 `sudo` 即可工作。

1. 确认 `docker` 组存在：
   ```bash
   getent group docker
   ```
2. 将当前用户添加到 `docker` 组：
   ```bash
   sudo usermod -aG docker $USER
   ```
3. 应用新的组成员身份。最可靠的方式是完全注销然后重新登录。如果希望刷新当前 shell session，请运行：
   ```bash
   newgrp docker
   ```
4. 验证 Docker 访问：
   ```bash
   docker ps
   ```
5. 重试 DeerFlow 命令：
   ```bash
   make docker-stop
   make docker-start
   ```

如果 `docker ps` 在 `usermod` 后仍然报告权限错误，请在重试前完全注销并重新登录。

#### Docker Architecture

```
Host Machine
  ↓
Docker Compose (deer-flow-dev)
  ├→ nginx (port 2026) ← Reverse proxy
  ├→ web (port 3000) ← Frontend with hot-reload
  ├→ gateway (port 8001) ← Gateway API + LangGraph-compatible runtime with hot-reload
  └→ provisioner (optional, port 8002) ← Started only in provisioner/K8s sandbox mode
```

**Benefits of Docker Development**:
- ✅ Consistent environment across different machines
- ✅ 无需在本地安装 Node.js、Python 或 nginx
- ✅ Isolated dependencies and services
- ✅ Easy cleanup and reset
- ✅ Hot-reload for all services
- ✅ Production-like environment

### Option 2: Local Development

如果您偏好直接在机器上运行 services：

#### Prerequisites

检查是否已安装所有必需的工具：

```bash
make check
```

Required tools:
- Node.js 22+
- pnpm
- uv（Python package manager）
- nginx

#### Setup Steps

1. **Configure the application**（与 Docker setup 相同）

2. **Install dependencies**（这也会设置 pre-commit hooks）：
   ```bash
   make install
   ```

3. **Run development server**（启动所有 services 并使用 nginx）：
   ```bash
   make dev
   ```

4. **Access the application**:
   - Web Interface: http://localhost:2026
   - All API requests are automatically proxied through nginx

#### Manual Service Control

如果需要单独启动 services：

1. **Start backend service**:
   ```bash
   # Terminal 1: Start Gateway API + embedded agent runtime (port 8001)
   cd backend
   make dev

   # Terminal 2: Start Frontend (port 3000)
   cd frontend
   pnpm dev
   ```

2. **Start nginx**:
   ```bash
   make nginx
   # or directly: nginx -c $(pwd)/docker/nginx/nginx.local.conf -g 'daemon off;'
   ```

3. **Access the application**:
   - Web Interface: http://localhost:2026

#### Nginx Configuration

nginx configuration 提供：
- Unified entry point on port 2026
- Rewrites `/api/langgraph/*` to Gateway's LangGraph-compatible API (8001)
- Routes other `/api/*` endpoints to Gateway API (8001)
- Routes non-API requests to Frontend (3000)
- Same-origin API routing; split-origin or port-forwarded browser clients should use the Gateway `GATEWAY_CORS_ORIGINS` allowlist
- SSE/streaming support for real-time agent responses
- Optimized timeouts for long-running operations

## Project Structure

```
deer-flow/
├── config.example.yaml      # Configuration template
├── extensions_config.example.json  # MCP and Skills configuration template
├── Makefile                 # Build and development commands
├── scripts/
│   └── docker.sh           # Docker management script
├── docker/
│   ├── docker-compose-dev.yaml  # Docker Compose configuration
│   └── nginx/
│       ├── nginx.conf      # Nginx config for Docker
│       └── nginx.local.conf # Nginx config for local dev
├── backend/                 # Backend application
│   ├── src/
│   │   ├── gateway/        # Gateway API and LangGraph-compatible runtime (port 8001)
│   │   ├── agents/         # LangGraph agent runtime used by Gateway
│   │   ├── mcp/            # Model Context Protocol integration
│   │   ├── skills/         # Skills system
│   │   └── sandbox/        # Sandbox execution
│   ├── docs/               # Backend documentation
│   └── Makefile            # Backend commands
├── frontend/               # Frontend application
│   └── Makefile            # Frontend commands
└── skills/                 # Agent skills
    ├── public/             # Public skills
    └── custom/             # Custom skills
```

## Architecture

```
Browser
  ↓
Nginx (port 2026) ← Unified entry point
  ├→ Frontend (port 3000) ← / (non-API requests)
  └→ Gateway API (port 8001) ← /api/* and /api/langgraph/* (LangGraph-compatible agent interactions)
```

## Development Workflow

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** with hot-reload enabled

3. **Format and lint your code**（CI will reject unformatted code）：
   ```bash
   # Backend
   cd backend
   make format   # ruff check --fix + ruff format

   # Frontend
   cd frontend
   pnpm format:write   # Prettier
   ```

4. **Test your changes** thoroughly

5. **Commit your changes**:
   ```bash
   git add .
   git commit -m "feat: description of your changes"
   ```

6. **Push and create a Pull Request**:
   ```bash
   git push origin feature/your-feature-name
   ```

## Testing

```bash
# Backend tests
cd backend
make test

# Frontend unit tests
cd frontend
make test

# Frontend E2E tests (requires Chromium; builds and auto-starts the Next.js production server)
cd frontend
make test-e2e
```

### PR Regression Checks

每个 pull request 都会触发以下 CI workflows：

- **Backend unit tests** — [.github/workflows/backend-unit-tests.yml](.github/workflows/backend-unit-tests.yml)
- **Frontend unit tests** — [.github/workflows/frontend-unit-tests.yml](.github/workflows/frontend-unit-tests.yml)
- **Frontend E2E tests** — [.github/workflows/e2e-tests.yml](.github/workflows/e2e-tests.yml)（仅在 `frontend/` 文件更改时触发）

## Code Style

- **Backend (Python)**: 我们使用 `ruff` 进行 linting 和 formatting。在 commit 前运行 `make format`。
- **Frontend (TypeScript)**: 我们使用 ESLint 和 Prettier。在 commit 前运行 `pnpm format:write`。
- CI 强制执行 formatting — 带有未格式化代码的 PR 将失败 lint check。

## Documentation

- [Configuration Guide](backend/docs/CONFIGURATION.md) - Setup and configuration
- [Architecture Overview](backend/CLAUDE.md) - Technical architecture
- [MCP Setup Guide](backend/docs/MCP_SERVER.md) - Model Context Protocol configuration

## Need Help?

- Check existing [Issues](https://github.com/bytedance/deer-flow/issues)
- Read the [Documentation](backend/docs/)
- Ask questions in [Discussions](https://github.com/bytedance/deer-flow/discussions)

## License

By contributing to DeerFlow, you agree that your contributions will be licensed under the [MIT License](./LICENSE).