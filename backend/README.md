# DeerFlow Backend

DeerFlow 是一个基于 LangGraph 的 AI super agent，具有沙箱执行、持久化 memory 和可扩展工具集成。后端使 AI agents 能够执行代码、浏览网页、管理文件、将任务委托给 subagents，并在隔离的 per-thread 环境中保留上下文。

---

## 架构

```
                        ┌──────────────────────────────────────┐
                        │          Nginx (端口 2026)            │
                        │      统一反向代理                      │
                        └───────┬──────────────────┬───────────┘
                                │
            /api/langgraph/*    │    /api/* (其他)
            重写为 /api/*       │
                                ▼
               ┌────────────────────────────────────────┐
               │        Gateway API (8001)             │
               │        FastAPI REST + agent 运行时     │
               │                                        │
               │ Models, MCP, Skills, Memory, Uploads,  │
               │ Artifacts, Threads, Runs, Streaming    │
               │                                        │
               │ ┌────────────────────────────────────┐ │
               │ │ Lead Agent                         │ │
               │ │ Middleware Chain, Tools, Subagents │ │
               │ └────────────────────────────────────┘ │
               └────────────────────────────────────────┘
```

**请求路由**（通过 Nginx）：
- `/api/langgraph/*` → Gateway LangGraph 兼容 API - agent 交互、线程、流式
- `/api/*`（其他）→ Gateway API - models, MCP, skills, memory, artifacts, uploads, 线程本地清理
- `/`（非 API）→ Frontend - Next.js Web 界面

### LangGraph Agent Server 兼容

DeerFlow 的 `/api/langgraph/*` 路径刻意兼容 [LangGraph Agent Server](https://docs.langchain.com/langsmith/agent-server) 的 API 契约。

**什么是 LangGraph Agent Server？** LangSmith Deployment 的组件，提供标准化的 Assistants / Threads / Runs / Stateless Runs / Crons 等 API。LangGraph CLI 的 `langgraph dev` 命令可以本地运行这样一个 server。

**DeerFlow 如何兼容？** Gateway 在 `/api/langgraph/*` 下实现了与 LangGraph Agent Server 相同的 API 模式（`client.threads.create()`、`client.runs.wait()`、`client.runs.stream()` 等）。这意味着：如果你用 LangGraph SDK（`langgraph-sdk`）写过客户端代码，换成 DeerFlow 的地址（`http://localhost:8001/api/langgraph`）也能直接跑，不需要修改任何调用代码。

**这让 DeerFlow 可以：** 用 LangGraph Studio 连接进行可视化调试、用标准 LangGraph SDK 客户端进行集成开发、以及与任何兼容 LangGraph Agent Server 契约的工具链配合使用。

---

## 核心组件

### Lead Agent

单个 LangGraph agent（`lead_agent`）是运行时入口点，通过 `make_lead_agent(config)` 创建。它组合了：

- **动态模型选择**，支持 thinking 和 vision
- **Middleware 链**，用于横切关注点（9 个 middlewares）
- **工具系统**，包含 sandbox、MCP、community 和内置 tools
- **Subagent 委托**，用于并行任务执行
- **系统 prompt**，包含 skills 注入、memory 上下文和工作目录指导

### Middleware 链

Middlewares 按严格顺序执行，每个处理特定关注点：

| # | Middleware | 用途 |
|---|-----------|---|
| 1 | **ThreadDataMiddleware** | 创建 per-thread 隔离目录（workspace, uploads, outputs） |
| 2 | **UploadsMiddleware** | 将新上传的文件注入到对话上下文中 |
| 3 | **SandboxMiddleware** | 获取代码执行的沙箱环境 |
| 4 | **SummarizationMiddleware** | 接近 token 限制时减少上下文（可选） |
| 5 | **TodoListMiddleware** | 在 plan 模式中跟踪多步任务（可选） |
| 6 | **TitleMiddleware** | 在首次交换后自动生成对话标题 |
| 7 | **MemoryMiddleware** | 将对话排队等待异步 memory 提取 |
| 8 | **ViewImageMiddleware** | 为 vision 兼容模型注入图像数据（条件性） |
| 9 | **ClarificationMiddleware** | 拦截澄清请求并中断执行（必须在最后） |

### Sandbox 系统

Per-thread 隔离执行，带虚拟路径翻译：

- **抽象接口**：`execute_command`、`read_file`、`write_file`、`list_dir`
- **Providers**：`LocalSandboxProvider`（文件系统）和 `AioSandboxProvider`（Docker，在 community/ 中）。Async 运行时路径使用 async sandbox 生命周期钩子，因此启动、就绪轮询和释放不会阻塞事件循环。
- **虚拟路径**：`/mnt/user-data/{workspace,uploads,outputs}` → 线程特定的物理目录
- **Skills 路径**：`/mnt/skills` → `deer-flow/skills/` 目录
- **Skills 加载**：递归发现 `skills/{public,custom}` 下嵌套的 `SKILL.md` 文件，并保留嵌套的容器路径
- **文件写入安全**：`str_replace` 对每个 `(sandbox.id, path)` 进行序列化读-修改-写，因此隔离的 sandboxes 在虚拟路径匹配时仍保持并发
- **工具**：`bash`、`ls`、`read_file`、`write_file`、`str_replace`（`write_file` 默认覆盖，并在模型面向 schema 中暴露 `append` 用于文件末尾写；使用 `LocalSandboxProvider` 时 `bash` 默认禁用；使用 `AioSandboxProvider` 进行隔离的 shell 访问）

### Subagent 系统

带并发执行的异步任务委托：

- **内置 agents**：`general-purpose`（完整工具集）和 `bash`（命令专家，仅在 shell 可用时暴露）
- **并发**：每轮最多 3 个 subagents，15 分钟超时
- **执行**：后台线程池，带状态跟踪和 SSE 事件
- **流程**：Agent 调用 `task()` 工具 → executor 在后台运行 subagent → 轮询完成 → 返回结果

### Memory 系统

基于 LLM 的持久化上下文保留，跨对话：

- **自动提取**：分析对话以获取用户上下文、事实和偏好
- **结构化存储**：用户上下文（工作、个人、top-of-mind）、历史和置信度评分的事实
- **去重更新**：批处理更新以最小化 LLM 调用（可配置等待时间）
- **系统 prompt 注入**：Top facts + 上下文注入到 agent prompts 中
- **存储**：带 mtime 的 JSON 文件缓存失效

### 工具生态系统

| 类别 | 工具 |
|----------|-------|
| **Sandbox** | `bash`、`ls`、`read_file`、`write_file`、`str_replace` |
| **内置** | `present_files`、`ask_clarification`、`view_image`、`task`（subagent） |
| **Community** | Tavily（网络搜索）、Jina AI（网络获取）、Firecrawl（抓取）、DuckDuckGo（图像搜索） |
| **MCP** | 任何 Model Context Protocol server（stdio、SSE、HTTP 传输） |
| **Skills** | 通过系统 prompt 注入的领域特定工作流 |

### Gateway API

FastAPI 应用，为 frontend 集成提供 REST 端点：

| 路由 | 用途 |
|-------|--------|
| `GET /api/models` | 列出可用的 LLM 模型 |
| `GET/PUT /api/mcp/config` | 管理 MCP server 配置 |
| `GET/PUT /api/skills` | 列出和管理 skills |
| `POST /api/skills/install` | 从 `.skill` 归档安装 skill |
| `GET /api/memory` | 检索 memory 数据 |
| `POST /api/memory/reload` | 强制重新加载 memory |
| `GET /api/memory/config` | Memory 配置 |
| `GET /api/memory/status` | 组合配置 + 数据 |
| `POST /api/threads/{id}/uploads` | 上传文件（自动转换 PDF/PPT/Excel/Word 为 Markdown，拒绝目录路径，在一次请求中自动重命名重复文件名） |
| `GET /api/threads/{id}/uploads/list` | 列出上传的文件 |
| `DELETE /api/threads/{id}` | 在 LangGraph 线程删除后删除 DeerFlow 管理的本地线程数据；意外失败在服务器端记录并返回通用 500 详情 |
| `GET /api/threads/{id}/artifacts/{path}` | 提供生成的 artifacts |

### IM Channels

IM 桥支持 Feishu、Slack 和 Telegram。Slack 和 Telegram 仍使用最终的 `runs.wait()` 响应路径，而 Feishu 现在通过 `runs.stream(["messages-tuple", "values"])` 流式传输，并在同一线程内 card 中就地更新。

对于 Feishu card 更新，DeerFlow 在每次入站消息时存储运行中 card 的 `message_id`，并修补同一个 card，直到 run 完成，保持现有的 `OK` / `DONE` 反应流程。

---

## 快速入门

### 前置条件

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 包管理器
- 您所选 LLM provider 的 API keys

### 安装

```bash
cd deer-flow

# 复制配置文件
cp config.example.yaml config.yaml

# 安装后端依赖
cd backend
make install
```

### 配置

在项目根目录编辑 `config.yaml`：

```yaml
models:
  - name: gpt-4o
    display_name: GPT-4o
    use: langchain_openai:ChatOpenAI
    model: gpt-4o
    api_key: $OPENAI_API_KEY
    supports_thinking: false
    supports_vision: true

  - name: gpt-5-responses
    display_name: GPT-5 (Responses API)
    use: langchain_openai:ChatOpenAI
    model: gpt-5
    api_key: $OPENAI_API_KEY
    use_responses_api: true
    output_version: responses/v1
    supports_vision: true
```

设置您的 API keys：

```bash
export OPENAI_API_KEY="your-api-key-here"
```

### 运行

**完整应用**（从项目根目录）：

```bash
make dev  # 启动 Gateway + Frontend + Nginx
```

访问：`http://localhost:2026`

**仅后端**（从 backend 目录）：

```bash
# Gateway API + 嵌入式 agent 运行时
make dev
```

直接访问：Gateway 在 `http://localhost:8001`

---

## 项目结构

```
backend/
├── src/
│   ├── agents/                  # Agent 系统
│   │   ├── lead_agent/         # 主 agent（工厂、prompts）
│   │   ├── middlewares/        # 9 个 middleware 组件
│   │   ├── memory/             # Memory 提取 & 存储
│   │   └── thread_state.py    # ThreadState schema
│   ├── gateway/                # FastAPI Gateway API
│   │   ├── app.py             # 应用设置
│   │   └── routers/           # 6 个路由模块
│   ├── sandbox/                # Sandbox 执行
│   │   ├── local/             # 本地文件系统 provider
│   │   ├── sandbox.py         # 抽象接口
│   │   ├── tools.py           # bash, ls, read/write/str_replace
│   │   └── middleware.py      # Sandbox 生命周期
│   ├── subagents/              # Subagent 委托
│   │   ├── builtins/          # general-purpose, bash agents
│   │   ├── executor.py        # 后台执行引擎
│   │   └── registry.py        # Agent 注册表
│   ├── tools/builtins/         # 内置 tools
│   ├── mcp/                    # MCP 协议集成
│   ├── models/                 # Model 工厂
│   ├── skills/                 # Skill 发现 & 加载
│   ├── config/                 # 配置系统
│   ├── community/              # Community tools & providers
│   ├── reflection/             # 动态模块加载
│   └── utils/                  # 工具函数
├── docs/                       # 文档
├── tests/                      # 测试套件
├── langgraph.json              # LangGraph 图注册表，用于工具/LangGraph Studio 兼容性
├── pyproject.toml              # Python 依赖
├── Makefile                    # 开发命令
└── Dockerfile                  # 容器构建
```

`langgraph.json` 主要用于 [LangGraph Studio](https://studio.langchain.com/) 可视化调试 agent 图结构。DeerFlow 运行时通过 Gateway 直接构建 agent，不依赖此文件。

---

## 配置

### 主配置（`config.yaml`）

放在项目根目录。以 `$` 开头的配置值解析为环境变量。

关键部分：
- `models` - LLM 配置，带类路径、API keys、thinking/vision 标志
- `tools` - 工具定义，带模块路径和分组
- `tool_groups` - 逻辑工具分组
- `sandbox` - 执行环境 provider
- `skills` - Skills 目录路径
- `title` - 自动标题生成设置
- `summarization` - 上下文摘要设置
- `subagents` - Subagent 系统（启用/禁用）
- `memory` - Memory 系统设置（enabled, storage, debounce, facts 限制）

Provider 说明：
- `models[*].use` 通过模块路径引用 provider 类（例如 `langchain_openai:ChatOpenAI`）。
- 如果缺少 provider 模块，DeerFlow 现在返回可操作的错误，带安装指导（例如 `uv add langchain-google-genai`）。

### 扩展配置（`extensions_config.json`）

MCP servers 和 skill 状态在单个文件中：

```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "$GITHUB_TOKEN"}
    },
    "secure-http": {
      "enabled": true,
      "type": "http",
      "url": "https://api.example.com/mcp",
      "oauth": {
        "enabled": true,
        "token_url": "https://auth.example.com/oauth/token",
        "grant_type": "client_credentials",
        "client_id": "$MCP_OAUTH_CLIENT_ID",
        "client_secret": "$MCP_OAUTH_CLIENT_SECRET"
      }
    }
  },
  "skills": {
    "pdf-processing": {"enabled": true}
  }
}
```

### 环境变量

- `DEER_FLOW_CONFIG_PATH` - 覆盖 config.yaml 位置
- `DEER_FLOW_EXTENSIONS_CONFIG_PATH` - 覆盖 extensions_config.json 位置
- Model API keys：`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`DEEPSEEK_API_KEY` 等
- Tool API keys：`TAVILY_API_KEY`、`GITHUB_TOKEN` 等

### LangSmith Tracing

DeerFlow 内置 [LangSmith](https://smith.langchain.com) 集成用于可观测性。启用后，所有 LLM 调用、agent runs、工具执行和 middleware 处理都被追踪并在 LangSmith dashboard 中可见。

**设置：**

1. 在 [smith.langchain.com](https://smith.langchain.com) 注册并创建一个项目。
2. 将以下内容添加到项目根目录的 `.env` 文件中：

```bash
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=lsv2_pt_xxxxxxxxxxxxxxxx
LANGSMITH_PROJECT=xxx
```

**Legacy 变量：** `LANGCHAIN_TRACING_V2`、`LANGCHAIN_API_KEY`、`LANGCHAIN_PROJECT` 和 `LANGCHAIN_ENDPOINT` 变量也支持以保持向后兼容。当两者都设置时，`LANGSMITH_*` 变量优先。

### Langfuse Tracing

DeerFlow 还支持 [Langfuse](https://langfuse.com) 用于 LangChain 兼容 runs 的可观测性。

将以下内容添加到您的 `.env` 文件中：

```bash
LANGFUSE_TRACING=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

如果您使用自托管 Langfuse 部署，将 `LANGFUSE_BASE_URL` 设置为您的 Langfuse 主机。

### 双 Provider 行为

如果同时启用了 LangSmith 和 Langfuse，DeerFlow 初始化并附加两个 callbacks，因此相同的 run 数据被报告到两个系统。

如果 provider 被明确启用但缺少必需的凭据，或者 provider callback 无法初始化，DeerFlow 在模型创建期间初始化 tracing 时抛出错误，而不是静默禁用 tracing。

**Docker：** 在 `docker-compose.yaml` 中，tracing 默认禁用（`LANGSMITH_TRACING=false`）。在您的 `.env` 中设置 `LANGSMITH_TRACING=true` 和/或 `LANGFUSE_TRACING=true`，以及必需的凭据，以在容器化部署中启用 tracing。

---

## 开发

### 命令

```bash
make install    # 安装依赖
make dev        # 运行 Gateway API + 嵌入式 agent 运行时（端口 8001）
make gateway    # 运行 Gateway API，不启用 reload（端口 8001）
make lint       # 运行 linter（ruff）
make format     # 格式化代码（ruff）
```

### 代码风格

- **Linter/Formatter**：`ruff`
- **行长度**：240 个字符
- **Python**：3.12+，带类型提示
- **引号**：双引号
- **缩进**：4 个空格

### 测试

```bash
uv run pytest
```

---

## 技术栈

- **LangGraph**（1.0.6+）- Agent 框架和多 agent 编排
- **LangChain**（1.2.3+）- LLM 抽象和工具系统
- **FastAPI**（0.115.0+）- Gateway REST API
- **langchain-mcp-adapters** - Model Context Protocol 支持
- **agent-sandbox** - 沙箱代码执行
- **markitdown** - 多格式文档转换
- **tavily-python** / **firecrawl-py** - 网络搜索和抓取

---

## 文档

- [Configuration Guide](docs/CONFIGURATION.md) - 配置指南
- [Architecture Details](docs/ARCHITECTURE.md) - 架构详情
- [API Reference](docs/API.md) - API 参考
- [File Upload](docs/FILE_UPLOAD.md) - 文件上传
- [Path Examples](docs/PATH_EXAMPLES.md) - 路径类型和用法
- [Context Summarization](docs/summarization.md) - 上下文摘要
- [Plan Mode](docs/plan_mode_usage.md) - Plan Mode
- [Setup Guide](docs/SETUP.md) - 设置指南

---

## 许可证

参见项目根目录的 [LICENSE](../LICENSE) 文件。

## 贡献

参见 [CONTRIBUTING.md](CONTRIBUTING.md) 获取贡献指南。



## 临时存储完整的langgraph.json


```json
{
  "$schema": "https://langgra.ph/schema.json",
  "python_version": "3.12",
  "dependencies": [
    "."
  ],
  "env": ".env",
  "graphs": {
    "lead_agent": "deerflow.agents:make_lead_agent"
  },
  "auth": {
    "path": "./app/gateway/langgraph_auth.py:auth"
  },
  "checkpointer": {
    "path": "./packages/harness/deerflow/runtime/checkpointer/async_provider.py:make_checkpointer"
  }
}

```