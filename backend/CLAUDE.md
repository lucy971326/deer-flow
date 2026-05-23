# CLAUDE.md

本文件为 Claude Code（claude.ai/code）在本代码仓库中工作时提供指导。

## 项目概述

DeerFlow 是一个基于 LangGraph 的 AI super agent 系统，采用全栈架构。后端提供一个"super agent"，具有沙箱执行、持久化 memory、子 agent 委托和可扩展工具集成功能——全部在 per-thread 隔离环境中运行。

**架构**：
- **Gateway API**（端口 8001）：REST API + 嵌入式 LangGraph 兼容 agent 运行时
- **Frontend**（端口 3000）：Next.js Web 界面
- **Nginx**（端口 2026）：统一反向代理入口
- **Provisioner**（端口 8002，仅在 Docker dev 模式下）：仅当 sandbox 配置为 provisioner/Kubernetes 模式时启动

**运行时**：
- `make dev`、Docker dev 和 production 都通过 `RunManager` + `run_agent()` + `StreamBridge`（`packages/harness/deerflow/runtime/`）在 Gateway 中运行 agent 运行时。Nginx 在 `/api/langgraph/*` 暴露该运行时，并重写到 Gateway 的原生 `/api/*` 路由。

**项目结构**：
```
deer-flow/
├── Makefile                    # 根目录命令（check, install, dev, stop）
├── config.yaml                 # 主应用配置
├── extensions_config.json      # MCP servers 和 skills 配置
├── backend/                    # 后端应用（当前目录）
│   ├── Makefile               # 后端专用命令（dev, gateway, lint）
│   ├── langgraph.json         # LangGraph Studio 图配置
│   ├── packages/
│   │   └── harness/           # deerflow-harness 包（导入：deerflow.*）
│   │       ├── pyproject.toml
│   │       └── deerflow/
│   │           ├── agents/            # LangGraph agent 系统
│   │           │   ├── lead_agent/    # 主 agent（工厂 + system prompt）
│   │           │   ├── middlewares/   # 10 个 middleware 组件
│   │           │   ├── memory/        # Memory 提取、队列、prompts
│   │           │   └── thread_state.py # ThreadState schema
│   │           ├── sandbox/           # 沙箱执行系统
│   │           │   ├── local/         # 本地文件系统 provider
│   │           │   ├── sandbox.py     # 抽象 Sandbox 接口
│   │           │   ├── tools.py       # bash, ls, read/write/str_replace
│   │           │   └── middleware.py  # Sandbox 生命周期管理
│   │           ├── subagents/         # 子 agent 委托系统
│   │           │   ├── builtins/      # general-purpose, bash agents
│   │           │   ├── executor.py    # 后台执行引擎
│   │           │   └── registry.py    # Agent 注册表
│   │           ├── tools/builtins/    # 内置工具（present_files, ask_clarification, view_image）
│   │           ├── mcp/               # MCP 集成（tools, cache, client）
│   │           ├── models/            # Model 工厂，支持 thinking/vision
│   │           ├── skills/            # Skills 发现、加载、解析
│   │           ├── config/            # 配置系统（app, model, sandbox, tool 等）
│   │           ├── community/         # Community 工具（tavily, jina_ai, firecrawl, image_search, aio_sandbox）
│   │           ├── reflection/        # 动态模块加载（resolve_variable, resolve_class）
│   │           └── utils/             # 工具函数（network, readability）
│   ├── app/                   # 应用层（导入：app.*）
│   │   ├── gateway/           # FastAPI Gateway API
│   │   │   ├── app.py         # FastAPI 应用
│   │   │   └── routers/       # FastAPI 路由模块（models, mcp, memory, skills, uploads, threads, artifacts, agents, suggestions, channels）
│   │   └── channels/          # IM 平台集成（Feishu, Slack, Telegram, DingTalk）
│   ├── tests/                 # 测试套件
│   └── docs/                  # 文档
├── frontend/                   # Next.js 前端应用
└── skills/                     # Agent skills 目录
    ├── public/                # 公共 skills（提交）
    └── custom/                # 自定义 skills（gitignored）
```

## 重要的开发指南

### 文档更新政策
**关键：每次代码更改后必须更新 README.md 和 CLAUDE.md**

进行代码更改时，必须更新相关文档：
- 更新 `README.md` 用于面向用户的更改（功能、设置、使用说明）
- 更新 `CLAUDE.md` 用于开发更改（架构、命令、工作流程、内部系统）
- 保持文档与代码库同步
- 确保所有文档的准确性和时效性

## 命令

**根目录**（完整应用）：
```bash
make check      # 检查系统需求
make install    # 安装所有依赖（frontend + backend）
make dev        # 启动所有服务（Gateway + Frontend + Nginx），并执行 config.yaml 预检
make start      # 本地启动生产服务
make stop       # 停止所有服务
```

**backend 目录**（仅后端开发）：
```bash
make install    # 安装后端依赖
make dev        # 运行 Gateway API 并启用 reload（端口 8001）
make gateway    # 仅运行 Gateway API（端口 8001）
make test       # 运行所有后端测试
make lint       # 用 ruff 检查
make format     # 用 ruff 格式化代码
```

与 Docker/provisioner 行为相关的回归测试：
- `tests/test_docker_sandbox_mode_detection.py`（从 `config.yaml` 检测模式）
- `tests/test_provisioner_kubeconfig.py`（kubeconfig 文件/目录处理）

边界检查（harness → app 导入防火墙）：
- `tests/test_harness_boundary.py` — 确保 `packages/harness/deerflow/` 永不从 `app.*` 导入

CI 通过 [.github/workflows/backend-unit-tests.yml](../.github/workflows/backend-unit-tests.yml) 为每个 PR 运行这些回归测试。

## 架构

### Harness / App 分离

后端分为两层，有严格的依赖方向：

- **Harness**（`packages/harness/deerflow/`）：可发布的 agent 框架包（`deerflow-harness`）。导入前缀：`deerflow.*`。包含构建和运行 agent 所需的一切：agent 编排、tools、sandbox、models、MCP、skills、config。
- **App**（`app/`）：未发布的应用代码。导入前缀：`app.*`。包含 FastAPI Gateway API 和 IM channel 集成（Feishu, Slack, Telegram, DingTalk）。

**依赖规则**：App 导入 deerflow，但 deerflow 永不导入 app。此边界由 `tests/test_harness_boundary.py` 强制执行，CI 会运行。

**导入约定**：
```python
# Harness 内部
from deerflow.agents import make_lead_agent
from deerflow.models import create_chat_model

# App 内部
from app.gateway.app import app
from app.channels.service import start_channel_service

# App → Harness（允许）
from deerflow.config import get_app_config

# Harness → App（禁止 — 由 test_harness_boundary.py 强制执行）
# from app.gateway.routers.uploads import ...  # ← 会导致 CI 失败
```

### Agent 系统

**Lead Agent**（`packages/harness/deerflow/agents/lead_agent/agent.py`）：
- 入口点：通过 `make_lead_agent(config: RunnableConfig)` 创建，在 `langgraph.json` 中注册
- 通过 `create_chat_model()` 动态选择模型，支持 thinking/vision
- 工具通过 `get_available_tools()` 加载——组合 sandbox、内置、MCP、community 和 subagent tools
- 系统 prompt 通过 `apply_prompt_template()` 生成，包含 skills、memory 和 subagent 说明

**ThreadState**（`packages/harness/deerflow/agents/thread_state.py`）：
- 扩展 `AgentState`，包含：`sandbox`、`thread_data`、`title`、`artifacts`、`todos`、`uploaded_files`、`viewed_images`
- 使用自定义 reducer：`merge_artifacts`（去重）、`merge_viewed_images`（合并/清除）

**运行时配置**（通过 `config.configurable`）：
- `thinking_enabled` - 启用模型的扩展思考
- `model_name` - 选择特定 LLM 模型
- `is_plan_mode` - 启用 TodoList middleware
- `subagent_enabled` - 启用任务委托工具

### Middleware 链

Lead agent middlewares 在 `packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py`（`build_lead_runtime_middlewares`）和 `packages/harness/deerflow/agents/lead_agent/agent.py`（`_build_middlewares`）中按严格顺序追加：

1. **ThreadDataMiddleware** - 在用户的隔离范围内创建 per-thread 目录（`backend/.deer-flow/users/{user_id}/threads/{thread_id}/user-data/{workspace,uploads,outputs}`）；通过 `get_effective_user_id()` 解析 `user_id`（无 auth 模式下回退到 `"default"`）；Web UI 线程删除现在跟随 LangGraph 线程删除，Gateway 清理本地线程目录
2. **UploadsMiddleware** - 跟踪并注入新上传的文件到对话中
3. **SandboxMiddleware** - 获取 sandbox，在 state 中存储 `sandbox_id`
4. **DanglingToolCallMiddleware** - 为缺少响应的 AIMessage tool_calls 注入占位符 ToolMessage（例如由于用户中断），包括仅保存在 `additional_kwargs["tool_calls"]` 中的原始 provider tool-call payloads
5. **LLMErrorHandlingMiddleware** - 在后续 middleware/工具阶段之前，将 provider/model 调用失败规范化为可恢复的 assistant-facing 错误
6. **GuardrailMiddleware** - 通过可插拔的 `GuardrailProvider` 协议进行 tool-call 前授权（如果 `guardrails.enabled` 在 config 中）。评估每个 tool call，拒绝时返回错误 ToolMessage。三种 provider 选项：内置 `AllowlistProvider`（零依赖）、OAP policy providers（例如 `aport-agent-guardrails`）或自定义 providers。详见 [docs/GUARDRAILS.md](docs/GUARDRAILS.md) 获取设置、使用和实现 provider 的说明。
7. **SandboxAuditMiddleware** - 在工具执行继续之前审计沙箱化 shell/文件操作以进行安全日志记录
8. **ToolErrorHandlingMiddleware** - 将工具异常转换为错误 `ToolMessage`，使 run 可以继续而不是中止
9. **SummarizationMiddleware** - 接近 token 限制时的上下文缩减（可选，如果启用）
10. **TodoListMiddleware** - 通过 `write_todos` 工具进行任务跟踪（可选，如果 plan_mode）
11. **TokenUsageMiddleware** - 启用 token 跟踪时记录 token 使用指标（可选）；subagent 使用通过 `tool_call_id` 缓存，仅在 token 使用启用时，并通过消息位置（而非消息 ID）合并回派发的 AIMessage
12. **TitleMiddleware** - 在第一次完整交换后自动生成线程标题，并在提示标题模型之前规范化结构化消息内容
13. **MemoryMiddleware** - 将对话排队等待异步 memory 更新（过滤到 user + 最终 AI 响应）
14. **ViewImageMiddleware** - 在 LLM 调用之前注入 base64 图像数据（取决于 vision 支持）
15. **DeferredToolFilterMiddleware** - 在启用工具搜索之前，向绑定模型隐藏 deferred 工具 schemas（可选）
16. **SubagentLimitMiddleware** - 在 `after_model` 中截断多余的 `task` tool calls 以强制执行 `MAX_CONCURRENT_SUBAGENTS` 限制（可选，如果 `subagent_enabled`）
17. **LoopDetectionMiddleware** - 检测重复的 tool-call 循环；硬停止响应在强制最终文本回答之前清除结构化 `tool_calls` 和原始 provider tool-call 元数据
18. **ClarificationMiddleware** - 拦截 `ask_clarification` tool calls，通过 `Command(goto=END)` 中断（必须在最后）

### 配置系统

**主配置**（`config.yaml`）：

设置：从 **项目根目录** 复制 `config.example.yaml` 到 `config.yaml`。

**配置版本控制**：`config.example.yaml` 有 `config_version` 字段。启动时，`AppConfig.from_file()` 比较用户版本与示例版本，如果过时则发出警告。缺少 `config_version` = 版本 0。运行 `make config-upgrade` 自动合并缺失字段。更改配置 schema 时，在 `config.example.yaml` 中 bump `config_version`。

**配置缓存**：`get_app_config()` 缓存解析后的配置，但当解析的配置路径更改或文件 mtime 增加时会自动重新加载。这使 Gateway 和 LangGraph 读取与 `config.yaml` 编辑保持一致，无需手动重启进程。

**配置热重载边界**：Gateway 依赖通过 `get_app_config()` 在每个请求上路由，因此 per-run 字段如 `models[*].max_tokens`、`summarization.*`、`title.*`、`memory.*`、`subagents.*`、`tools[*]` 和 agent system prompt 在下次消息时获取 `config.yaml` 编辑。`AppConfig` 故意 **不** 缓存在 `app.state` 上——`lifespan()` 保留一个本地 `startup_config` 变量用于一次性引导工作（日志级别、channels、`langgraph_runtime` engines），并明确传递给 `langgraph_runtime(app, startup_config)`。基础设施字段需要 **重启**：

| 字段 | 为什么需要重启 |
|---|---|
| `database.*` | `init_engine_from_config()` 在 `langgraph_runtime()` 启动时运行一次；SQLAlchemy engine 持有连接池。 |
| `checkpointer.*`（包括 SQLite WAL/journal 设置） | `make_checkpointer()` 在启动时绑定持久化 checkpointer。 |
| `run_events.*` | `make_run_event_store()` 在启动时选择 memory- vs. SQL-backed 实现。 |
| `stream_bridge.*` | `make_stream_bridge()` 在启动时构造 bridge 对象一次。 |
| `sandbox.use` | `get_sandbox_provider()` 缓存 provider 单例（`_default_sandbox_provider`）；新的类路径仅在下次进程启动时生效。 |
| `log_level` | `apply_logging_level()` 仅在 `app.py` 启动时调用；它改变 root logger 的 level，而 `get_app_config()` 返回新的 `AppConfig` 不会重新触发它。 |
| `channels.*` IM 平台凭证 | `start_channel_service()` 在启动时调用一次；live channels 在配置更改时不会重建。 |

配置优先级：
1. 显式 `config_path` 参数
2. `DEER_FLOW_CONFIG_PATH` 环境变量
3. 当前目录（backend/）中的 `config.yaml`
4. 父目录中的 `config.yaml`（项目根目录 — **推荐位置**）

以 `$` 开头的配置值解析为环境变量（例如 `$OPENAI_API_KEY`）。
`ModelConfig` 还声明 `use_responses_api` 和 `output_version`，因此可以明确启用 OpenAI `/v1/responses`，同时仍使用 `langchain_openai:ChatOpenAI`。

**扩展配置**（`extensions_config.json`）：

MCP servers 和 skills 在 `extensions_config.json` 中一起配置，位于项目根目录：

配置优先级：
1. 显式 `config_path` 参数
2. `DEER_FLOW_EXTENSIONS_CONFIG_PATH` 环境变量
3. 当前目录（backend/）中的 `extensions_config.json`
4. 父目录中的 `extensions_config.json`（项目根目录 — **推荐位置**）

### Gateway API（`app/gateway/`）

FastAPI 应用，端口 8001，健康检查在 `GET /health`。设置 `GATEWAY_ENABLE_DOCS=false` 在生产中禁用 `/docs`、`/redoc` 和 `/openapi.json`（默认：启用）。

当请求通过 nginx 进入端口 2026 时，CORS 是同源的。分源或端口转发的浏览器客户端必须通过 `GATEWAY_CORS_ORIGINS`（逗号分隔的精确源）选择加入；Gateway 的 `CORSMiddleware` 和 `CSRFMiddleware` 都读取该变量，因此浏览器 CORS 和 auth-origin 检查保持一致。

**路由**：

| 路由 | 端点 |
|--------|-----------|
| **Models**（`/api/models`） | `GET /` - 列出模型；`GET /{name}` - 模型详情 |
| **MCP**（`/api/mcp`） | `GET /config` - 获取配置；`PUT /config` - 更新配置（保存到 extensions_config.json） |
| **Skills**（`/api/skills`） | `GET /` - 列出 skills；`GET /{name}` - 详情；`PUT /{name}` - 更新启用状态；`POST /install` - 从 .skill 归档安装（接受标准可选 frontmatter 如 `version`、`author`、`compatibility`） |
| **Memory**（`/api/memory`） | `GET /` - memory 数据；`POST /reload` - 强制重新加载；`GET /config` - 配置；`GET /status` - 配置 + 数据 |
| **Uploads**（`/api/threads/{id}/uploads`） | `POST /` - 上传文件（自动转换 PDF/PPT/Excel/Word）；`GET /list` - 列出；`DELETE /{filename}` - 删除 |
| **Threads**（`/api/threads/{id}`） | `DELETE /` - 在 LangGraph 线程删除后删除 DeerFlow 管理的本地线程数据；意外失败在服务器端记录并返回通用 500 详情 |
| **Artifacts**（`/api/threads/{id}/artifacts`） | `GET /{path}` - 提供 artifacts；活动内容类型（`text/html`、`application/xhtml+xml`、`image/svg+xml`）始终强制作为下载附件以降低 XSS 风险；`?download=true` 仍强制下载其他文件类型 |
| **Suggestions**（`/api/threads/{id}/suggestions`） | `POST /` - 生成后续问题；富列表/块模型内容在 JSON 解析前规范化 |
| **Thread Runs**（`/api/threads/{id}/runs`） | `POST /` - 创建后台 run；`POST /stream` - 创建 + SSE 流；`POST /wait` - 创建 + 阻塞；`GET /` - 列出 runs；`GET /{rid}` - run 详情；`POST /{rid}/cancel` - 取消；`GET /{rid}/join` - 加入 SSE；`GET /{rid}/messages` - 分页消息 `{data, has_more}`；`GET /{rid}/events` - 完整事件流；`GET /../messages` - 带反馈的线程消息；`GET /../token-usage` - 聚合 tokens |
| **Feedback**（`/api/threads/{id}/runs/{rid}/feedback`） | `PUT /` - upsert 反馈；`DELETE /` - 删除用户反馈；`POST /` - 创建反馈；`GET /` - 列出反馈；`GET /stats` - 聚合统计；`DELETE /{fid}` - 删除特定反馈 |
| **Runs**（`/api/runs`） | `POST /stream` - 无状态 run + SSE；`POST /wait` - 无状态 run + 阻塞；`GET /{rid}/messages` - 按 run_id 分页消息 `{data, has_more}`（游标：`after_seq`/`before_seq`）；`GET /{rid}/feedback` - 按 run_id 列出反馈 |

**RunManager / RunStore 契约**：
- `RunManager.get()` 是 async；直接调用者必须 `await` 它。
- 当配置了持久化 `RunStore` 时，`get()` 和 `list_by_thread()` 从 store 中补充历史 runs。相同 `run_id` 的内存记录优先，因此 task、abort 和 stream-control 状态保持在活跃的本地 runs 上。
- `cancel()` 和 `create_or_reject(..., multitask_strategy="interrupt"|"rollback")` 通过 `RunStore.update_status()` 持久化中断状态，匹配正常的 `set_status()` 转换。
- 仅从 store 补充的 runs 是可读历史。如果当前 worker 没有该 run 的内存 task/control 状态，取消 API 可能返回 409，因为该 worker 无法停止 task。

通过 nginx 代理：`/api/langgraph/*` → Gateway LangGraph 兼容运行时，其他 `/api/*` → Gateway REST API。

### Sandbox 系统（`packages/harness/deerflow/sandbox/`）

**接口**：抽象 `Sandbox`，包含 `execute_command`、`read_file`、`write_file`、`list_dir`
**Provider 模式**：`SandboxProvider`，包含 `acquire`、`acquire_async`、`get`、`release` 生命周期。Async agent/工具路径调用 async sandbox 生命周期钩子，因此 Docker sandbox 创建、发现、跨进程锁定、就绪轮询和释放不会阻塞事件循环。
**实现**：
- `LocalSandboxProvider` - 本地文件系统执行。`acquire(thread_id)` 返回 per-thread `LocalSandbox`（id `local:{thread_id}`），其 `path_mappings` 将 `/mnt/user-data/{workspace,uploads,outputs}` 和 `/mnt/acp-workspace` 解析为该线程的主机目录，使公开的 `Sandbox` API 与 AIO 统一接受 `/mnt/user-data` 约定。`acquire()` / `acquire(None)` 保留legacy通用单例（id `local`），用于没有线程上下文 的调用者。Per-thread sandboxes 保存在 LRU 缓存中（默认 256 项），由 `threading.Lock` 保护。
- `AioSandboxProvider`（`packages/harness/deerflow/community/`） - 基于 Docker 的隔离

**虚拟路径系统**：
- Agent 看到：`/mnt/user-data/{workspace,uploads,outputs}`、`/mnt/skills`
- 物理路径：`backend/.deer-flow/users/{user_id}/threads/{thread_id}/user-data/...`、`deer-flow/skills/`
- 翻译：`LocalSandboxProvider` 在 acquire 时构建 per-thread `PathMapping`，用于 user-data 前缀；`tools.py` 保持 `replace_virtual_path()` / `replace_virtual_paths_in_command()` 作为深度防御（并用于路径验证）。AIO 在容器内以相同的虚拟路径挂载目录，因此两个实现都原生接受 `/mnt/user-data/...`。
- 检测：`is_local_sandbox()` 接受 `sandbox_id == "local"`（legacy/无线程）和 `sandbox_id.startswith("local:")`（per-thread）两种情况。

**Sandbox 工具**（在 `packages/harness/deerflow/sandbox/tools.py` 中）：
- `bash` - 执行命令，带路径翻译和错误处理
- `ls` - 目录列表（树格式，最多 2 层）
- `read_file` - 读取文件内容，可选行范围
- `write_file` - 写/追加到文件，创建目录；默认覆盖，并在模型面向 schema 中暴露 `append` 参数用于文件末尾写
- `str_replace` - 子字符串替换（单次或全部）；相同路径序列化作用域为 `(sandbox.id, path)`，因此隔离 sandboxes 在虚拟路径相同时不会竞争

### Subagent 系统（`packages/harness/deerflow/subagents/`）

**内置 Agents**：`general-purpose`（除 `task` 外的所有工具）和 `bash`（命令专家）
**执行**：双线程池 - `_scheduler_pool`（3 个 workers）+ `_execution_pool`（3 个 workers）
**并发**：`MAX_CONCURRENT_SUBAGENTS = 3` 由 `SubagentLimitMiddleware` 强制执行（在 `after_model` 中截断多余的 tool calls），15 分钟超时
**流程**：`task()` 工具 → `SubagentExecutor` → 后台线程 → 轮询 5s → SSE 事件 → 结果
**事件**：`task_started`、`task_running`、`task_completed`/`task_failed`/`task_timed_out`

### 工具系统（`packages/harness/deerflow/tools/`）

`get_available_tools(groups, include_mcp, model_name, subagent_enabled)` 组装：
1. **Config 定义的工具** - 通过 `resolve_variable()` 从 `config.yaml` 解析
2. **MCP 工具** - 从启用的 MCP servers（延迟初始化，带 mtime 无效化的缓存）
3. **内置工具**：
   - `present_files` - 使输出文件对用户可见（仅 `/mnt/user-data/outputs`）
   - `ask_clarification` - 请求澄清（被 ClarificationMiddleware 拦截 → 中断）
   - `view_image` - 将图像读取为 base64（仅在模型支持 vision 时添加）
   - `setup_agent` - 仅引导时：持久化全新自定义 agent 的 `SOUL.md` 和 `config.yaml`。仅在 `is_bootstrap=True` 时绑定。
   - `update_agent` - 仅自定义 agent：在普通聊天中持久化当前 agent 的 `SOUL.md` / `config.yaml` 的自身更新（部分更新 + 原子写）。在 `agent_name` 设置且 `is_bootstrap=False` 时绑定。
4. **Subagent 工具**（如果启用）：
   - `task` - 委托给 subagent（description, prompt, subagent_type）

**Community 工具**（`packages/harness/deerflow/community/`）：
- `tavily/` - 网络搜索（默认 5 条结果）和网络获取（4KB 限制）
- `jina_ai/` - 通过 Jina reader API 进行网络获取，带可读性提取
- `firecrawl/` - 通过 Firecrawl API 进行网络抓取

**ACP agent 工具**：
- `invoke_acp_agent` - 从 `config.yaml` 调用外部 ACP 兼容 agents
- ACP launcher 必须是真正的 ACP adapters。标准 `codex` CLI 本身不是 ACP 兼容的；配置一个 wrapper 如 `npx -y @zed-industries/codex-acp` 或已安装的 `codex-acp` 二进制文件
- 缺少 ACP 可执行文件现在返回可操作的错误消息，而不是原始的 `[Errno 2]`
- 每个 ACP agent 在 `{base_dir}/users/{user_id}/threads/{thread_id}/acp-workspace/` 使用 per-thread 工作区。该工作区可通过虚拟路径 `/mnt/acp-workspace/` 由 lead agent 访问（只读）。在 docker sandbox 模式下，目录被卷挂载到容器内的 `/mnt/acp-workspace`（只读）；在本地 sandbox 模式下，路径翻译由 `tools.py` 处理
- `image_search/` - 通过 DuckDuckGo 进行图像搜索

### MCP 系统（`packages/harness/deerflow/mcp/`）

- 使用 `langchain-mcp-adapters` `MultiServerMCPClient` 进行多服务器管理
- **延迟初始化**：工具在首次使用时通过 `get_cached_mcp_tools()` 加载
- **缓存失效**：通过 mtime 比较检测配置文件更改
- **传输**：stdio（基于命令）、SSE、HTTP
- **OAuth（HTTP/SSE）**：支持 token 端点流程（`client_credentials`、`refresh_token`），带自动 token 刷新 + Authorization 头注入
- **运行时更新**：Gateway API 保存到 extensions_config.json；LangGraph 通过 mtime 检测

### Skills 系统（`packages/harness/deerflow/skills/`）

- **位置**：`deer-flow/skills/{public,custom}/`
- **格式**：带有 `SKILL.md` 的目录（YAML frontmatter：name, description, license, allowed-tools）
- **加载**：`load_skills()` 递归扫描 `skills/{public,custom}` 查找 `SKILL.md`，解析元数据，并从 extensions_config.json 读取启用状态
- **注入**：启用的 skills 在 agent system prompt 中列出，带容器路径
- **安装**：`POST /api/skills/install` 将 .skill ZIP 归档提取到 custom/ 目录

### Model 工厂（`packages/harness/deerflow/models/factory.py`）

- `create_chat_model(name, thinking_enabled)` 通过反射从配置实例化 LLM
- 支持 `thinking_enabled` 标志，带 per-model `when_thinking_enabled` 覆盖
- 支持通过 `when_thinking_enabled.extra_body.chat_template_kwargs.enable_thinking` 为 Qwen 推理模型启用 vLLM 风格的思考切换，同时规范化 legacy `thinking` 配置以保持向后兼容
- 支持 `supports_vision` 标志用于图像理解模型
- 以 `$` 开头的配置值解析为环境变量
- 缺少 provider 模块从反射解析器显示可操作的安装提示（例如 `uv add langchain-google-genai`）

### vLLM Provider（`packages/harness/deerflow/models/vllm_provider.py`）

- `VllmChatModel` 是 `langchain_openai:ChatOpenAI` 的子类，用于 vLLM 0.19.0 OpenAI 兼容端点
- 在完整响应、流式 deltas 和后续 tool-call 轮次中保留 vLLM 非标准的 assistant `reasoning` 字段
- 专为通过 `extra_body.chat_template_kwargs.enable_thinking` 为 vLLM 0.19.0 Qwen 推理模型启用思考的配置而设计，同时接受 older `thinking` 别名

### IM Channels 系统（`app/channels/`）

将外部消息平台（Feishu, Slack, Telegram, DingTalk）桥接到 DeerFlow agent，通过 LangGraph Server。

**架构**：Channels 通过 `langgraph-sdk` HTTP client（与 frontend 相同）与 Gateway 通信，确保线程在服务器端创建和管理。内部 SDK client 注入进程本地的内部 auth 以及匹配的 CSRF cookie/header 对，使 Gateway 接受来自 channel workers 的状态更改线程/run 请求，而不依赖浏览器会话 cookies。

**组件**：
- `message_bus.py` - 异步 pub/sub hub（`InboundMessage` → 队列 → 调度器；`OutboundMessage` → 回调 → channels）
- `store.py` - JSON 文件持久化，映射 `channel_name:chat_id[:topic_id]` → `thread_id`（键是根对话的 `channel:chat` 和线程对话的 `channel:chat:topic`）
- `manager.py` - 核心调度器：通过 `client.threads.create()` 创建线程，路由命令，在 Slack/Telegram 上保持 `client.runs.wait()`，并使用 `client.runs.stream(["messages-tuple", "values"])` 进行 Feishu 增量出站更新
- `base.py` - 抽象 `Channel` 基类（start/stop/send 生命周期）
- `service.py` - 从 `config.yaml` 管理所有配置的 channels 的生命周期
- `slack.py` / `feishu.py` / `telegram.py` / `dingtalk.py` - 平台特定实现（`feishu.py` 在内存中跟踪运行中的 card `message_id`，并就地修补同一 card；`dingtalk.py` 在配置了 `card_template_id` 时可选使用 AI Card 流式更新）

**消息流**：
1. 外部平台 -> Channel 实现 -> `MessageBus.publish_inbound()`
2. `ChannelManager._dispatch_loop()` 从队列消费
3. 对于聊天：通过 Gateway 的 LangGraph 兼容 API 查找/创建线程
4. Feishu 聊天：`runs.stream()` → 累积 AI 文本 → 发布多个出站更新（`is_final=False`）→ 发布最终出站（`is_final=True`）
5. Slack/Telegram 聊天：`runs.wait()` → 提取最终响应 → 发布出站
6. Feishu channel 首先发送一个运行中的回复 card，然后对每个出站更新修补同一 card（card JSON 设置 `config.update_multi=true` 以满足 Feishu 的 patch API 要求）
7. DingTalk AI Card 模式（配置了 `card_template_id` 时）：`runs.stream()` → 用初始文本创建 card → 通过 `PUT /v1.0/card/streaming` 流式更新 → 在 `is_final=True` 时完成。如果 card 创建或流式失败则回退到 `sampleMarkdown`
8. 对于命令（`/new`、`/status`、`/models`、`/memory`、`/help`）：本地处理或查询 Gateway API
9. 出站 → channel 回调 → 平台回复

**配置**（`config.yaml` -> `channels`）：
- `langgraph_url` - LangGraph 兼容 Gateway API 基础 URL（默认：`http://localhost:8001/api`）
- `gateway_url` - 用于辅助命令的 Gateway API URL（默认：`http://localhost:8001`）
- 在 Docker Compose 中，IM channels 在 `gateway` 容器内运行，因此 `localhost` 指回该容器。使用 `http://gateway:8001/api` 作为 `langgraph_url`，使用 `http://gateway:8001` 作为 `gateway_url`，或设置 `DEER_FLOW_CHANNELS_LANGGRAPH_URL` / `DEER_FLOW_CHANNELS_GATEWAY_URL`。
- Per-channel 配置：`feishu`（app_id, app_secret）、`slack`（bot_token, app_token）、`telegram`（bot_token）、`dingtalk`（client_id, client_secret，可选 `card_template_id` 用于 AI Card 流式）

### Memory 系统（`packages/harness/deerflow/agents/memory/`）

**组件**：
- `updater.py` - 基于 LLM 的 memory 更新，带事实提取、去重（trim 首尾空白后再比较）和原子文件 I/O
- `queue.py` - 去重更新的队列（per-thread 去重，可配置等待时间）；在入队时捕获 `user_id`，因此它在线程 Timer 边界外仍然有效
- `prompt.py` - memory 更新的 prompt 模板
- `storage.py` - 基于文件的存储，带 per-user 隔离；缓存按 `(user_id, agent_name)` 键

**Per-User 隔离**：
- Memory 存储在 `{base_dir}/users/{user_id}/memory.json`（per-user）
- Per-agent per-user memory 存储在 `{base_dir}/users/{user_id}/agents/{agent_name}/memory.json`
- 自定义 agent 定义（`SOUL.md` + `config.yaml`）也在 `{base_dir}/users/{user_id}/agents/{agent_name}/`。Legacy 共享布局 `{base_dir}/agents/{agent_name}/` 保持为未迁移安装的回退只读
- `user_id` 通过 `deerflow.runtime.user_context` 中的 `get_effective_user_id()` 解析
- 无 auth 模式下，`user_id` 默认为 `"default"`（常量 `DEFAULT_USER_ID`）
- 配置中的绝对 `storage_path` 选择退出 per-user 隔离
- **迁移**：运行 `PYTHONPATH=. python scripts/migrate_user_isolation.py` 将 legacy `memory.json`、`threads/` 和 `agents/` 迁移到 per-user 布局。支持 `--dry-run`（预览更改）和 `--user-id USER_ID`（为未拥有的 legacy 数据分配 user，默认为 `default`）。

**数据结构**（存储在 `{base_dir}/users/{user_id}/memory.json`）：
- **用户上下文**：`workContext`、`personalContext`、`topOfMind`（1-3 句摘要）
- **历史**：`recentMonths`、`earlierContext`、`longTermBackground`
- **事实**：离散事实，带 `id`、`content`、`category`（preference/knowledge/context/behavior/goal）、`confidence`（0-1）、`createdAt`、`source`

**工作流**：
1. `MemoryMiddleware` 过滤消息（用户输入 + 最终 AI 响应），通过 `get_effective_user_id()` 捕获 `user_id`，并将对话排队
2. 队列去重（30s 默认），批处理更新，per-thread 去重
3. 后台线程调用 LLM 提取上下文更新和事实，使用存储的 `user_id`（不是 contextvar，因为它在 timer 线程上不可用）
4. 原子应用更新（临时文件 + 重命名）并使缓存失效，在追加前跳过重复事实内容
5. 下次交互将 top 15 事实 + 上下文注入到 system prompt 的 `<memory>` 标签中

Updater 的集中回归覆盖在 `backend/tests/test_memory_updater.py`。

**配置**（`config.yaml` → `memory`）：
- `enabled` / `injection_enabled` - 主开关
- `storage_path` - memory.json 路径（绝对路径选择退出 per-user 隔离）
- `debounce_seconds` - 处理前等待时间（默认：30）
- `model_name` - 更新的 LLM（null = 默认模型）
- `max_facts` / `fact_confidence_threshold` - 事实存储限制（100 / 0.7）
- `max_injection_tokens` - prompt 注入的 token 限制（2000）

### Reflection 系统（`packages/harness/deerflow/reflection/`）

- `resolve_variable(path)` - 导入模块并返回变量（例如 `module.path:variable_name`）
- `resolve_class(path, base_class)` - 导入并根据基类验证类

### Tracing 系统（`packages/harness/deerflow/tracing/`）

支持 LangSmith 和 Langfuse。连接位于两层：

- `factory.py::build_tracing_callbacks()` — 返回当前通过 env vars（`LANGSMITH_TRACING`、`LANGFUSE_TRACING` 等）启用的 providers 的 LangChain `CallbackHandler` 列表。处理程序附加在 **图调用根** 处，用于 in-graph runs（`make_lead_agent` 和 `DeerFlowClient.stream` 在调用图之前都向 `config["callbacks"]` 追加它们），因此单个 run 产生一个 trace，所有节点/LLM/工具调用作为子 spans。独立调用者——任何在图外调用模型的东西（例如 `MemoryUpdater`）——保持 `create_chat_model` 的默认 `attach_tracing=True`，回退到模型级回调附加。
- `metadata.py::build_langfuse_trace_metadata()` — 为 `RunnableConfig.metadata` 构建 Langfuse 保留的 trace 属性。Langfuse v4 `langchain.CallbackHandler` 将这些属性提升到根 trace（见其 `_parse_langfuse_trace_attributes`），但仅在看到 `on_chain_start(parent_run_id=None)` 时——这就是为什么 callbacks 必须位于图根，而不是模型。

**Trace 属性注入点**：`runtime/runs/worker.py::run_agent`（gateway 路径）和 `client.py::DeerFlowClient.stream`（嵌入路径）都在构造图之前将元数据合并到 `config["metadata"]` 中。调用者提供的键通过 `setdefault` 优先保留，因此外部 `session_id` 覆盖被保留。字段映射：

| Langfuse 字段 | 来源 |
|-----------------------|----------------------------------------------|
| `langfuse_session_id` | LangGraph `thread_id` |
| `langfuse_user_id` | `get_effective_user_id()`（无 auth 时为 `default`） |
| `langfuse_trace_name` | `RunRecord.assistant_id` / client `agent_name`（默认为 `lead-agent`） |
| `langfuse_tags` | `env:<DEER_FLOW_ENV>` + `model:<model_name>` |

当 Langfuse 不在启用的 providers 中时返回 `{}` — 仅 LangSmith 的部署不受影响。设置 `DEER_FLOW_ENV`（或 `ENVIRONMENT`）以按部署环境标记 traces。测试位于 `tests/test_tracing_factory.py`、`tests/test_tracing_metadata.py`、`tests/test_worker_langfuse_metadata.py` 和 `tests/test_client_langfuse_metadata.py`。

### 配置 Schema

**`config.yaml`** 关键部分：
- `models[]` - LLM 配置，带 `use` 类路径、`supports_thinking`、`supports_vision`、provider 特定字段
- vLLM 推理模型应使用 `deerflow.models.vllm_provider:VllmChatModel`；对于 Qwen 风格解析器，优先使用 `when_thinking_enabled.extra_body.chat_template_kwargs.enable_thinking`，DeerFlow 也会规范化 legacy `thinking` 别名
- `tools[]` - 工具配置，带 `use` 变量路径和 `group`
- `tool_groups[]` - 逻辑工具分组
- `sandbox.use` - Sandbox provider 类路径
- `skills.path` / `skills.container_path` - 主机和容器中 skills 目录的路径
- `title` - 自动标题生成（enabled, max_words, max_chars, prompt_template）
- `summarization` - 上下文摘要（enabled, trigger conditions, keep policy）
- `subagents.enabled` - 子 agent 委托主开关
- `memory` - Memory 系统（enabled, storage_path, debounce_seconds, model_name, max_facts, fact_confidence_threshold, injection_enabled, max_injection_tokens）

**`extensions_config.json`**：
- `mcpServers` - server 名称 → 配置的映射（enabled, type, command, args, env, url, headers, oauth, description）
- `skills` - skill 名称 → 状态的映射（enabled）

两者都可以通过 Gateway API 端点修改。

## 开发工作流

### 测试驱动开发（TDD）— 强制

**每个新功能或 bug 修复必须伴随单元测试。没有例外。**

- 在 `backend/tests/` 中编写测试，遵循现有命名约定 `test_<feature>.py`
- 在更改前后运行完整套件：`make test`
- 测试通过后才能认为功能完成
- 对于轻量级配置/工具模块，优先使用无外部依赖的纯单元测试
- 如果模块在测试中导致循环导入问题，在 `tests/conftest.py` 中添加 `sys.modules` mock（参见 `deerflow.subagents.executor` 的现有示例）

```bash
# 运行所有测试
make test

# 运行特定测试文件
PYTHONPATH=. uv run pytest tests/test_<feature>.py -v
```

### 运行完整应用

从 **项目根目录**：
```bash
make dev
```

这启动所有服务，使应用在 `http://localhost:2026` 可用。

**所有启动模式：**

| | **本地前台** | **本地守护进程** | **Docker Dev** | **Docker Prod** |
|---|---|---|---|---|
| **Dev** | `./scripts/serve.sh --dev`<br/>`make dev` | `./scripts/serve.sh --dev --daemon`<br/>`make dev-daemon` | `./scripts/docker.sh start`<br/>`make docker-start` | — |
| **Prod** | `./scripts/serve.sh --prod`<br/>`make start` | `./scripts/serve.sh --prod --daemon`<br/>`make start-daemon` | — | `./scripts/deploy.sh`<br/>`make up` |

| 操作 | 本地 | Docker Dev | Docker Prod |
|---|---|---|---|
| **停止** | `./scripts/serve.sh --stop`<br/>`make stop` | `./scripts/docker.sh stop`<br/>`make docker-stop` | `./scripts/deploy.sh down`<br/>`make down` |
| **重启** | `./scripts/serve.sh --restart [flags]` | `./scripts/docker.sh restart` | — |

**Nginx 路由**：
- `/api/langgraph/*` → Gateway 嵌入式运行时（8001），重写为 `/api/*`
- `/api/*`（其他）→ Gateway API（8001）
- `/`（非 API）→ Frontend（3000）

### 分别运行后端服务

从 **backend 目录**：

```bash
# Gateway API
make gateway
```

直接访问（无 nginx）：
- Gateway：`http://localhost:8001`

### 前端配置

前端使用环境变量连接后端服务：
- `NEXT_PUBLIC_LANGGRAPH_BASE_URL` - 默认为 `/api/langgraph`（通过 nginx）
- `NEXT_PUBLIC_BACKEND_BASE_URL` - 默认为空字符串（通过 nginx）

使用 `make dev` 从根目录时，前端自动通过 nginx 连接。

## 关键功能

### 文件上传

多文件上传，带自动文档转换：
- 端点：`POST /api/threads/{thread_id}/uploads`
- 支持：PDF、PPT、Excel、Word 文档（通过 `markitdown` 转换）
- 在复制前拒绝目录输入，因此上传保持全有或全无
- 从活跃事件循环调用时重用单个转换 worker
- 文件存储在线程隔离目录中
- 单个上传请求中的重复文件名自动重命名为 `_N` 后缀，因此后来的文件不会截断早期的文件
- Agent 通过 `UploadsMiddleware` 接收上传文件列表

详见 [docs/FILE_UPLOAD.md](docs/FILE_UPLOAD.md)。

### Plan Mode

用于复杂多步任务的 TodoList middleware：
- 通过运行时配置控制：`config.configurable.is_plan_mode = True`
- 提供 `write_todos` 工具进行任务跟踪
- 一次只能有一个任务 in_progress，实时更新

详见 [docs/plan_mode_usage.md](docs/plan_mode_usage.md)。

### 上下文摘要

接近 token 限制时的自动对话摘要：
- 在 `config.yaml` 的 `summarization` 键下配置
- 触发类型：tokens、messages 或 max input 的 fraction
- 在总结旧消息时保留 recent messages

详见 [docs/summarization.md](docs/summarization.md)。

### Vision 支持

对于带 `supports_vision: true` 的模型：
- `ViewImageMiddleware` 处理对话中的图像
- `view_image_tool` 添加到 agent 的工具集
- 图像自动转换为 base64 并注入到 state

## 代码风格

- 使用 `ruff` 进行 linting 和格式化
- 行长度：240 个字符
- Python 3.12+，带类型提示
- 双引号，空格缩进

## 文档

详见 `docs/` 目录：
- [CONFIGURATION.md](docs/CONFIGURATION.md) - 配置选项
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - 架构详情
- [API.md](docs/API.md) - API 参考
- [SETUP.md](docs/SETUP.md) - 设置指南
- [FILE_UPLOAD.md](docs/FILE_UPLOAD.md) - 文件上传功能
- [PATH_EXAMPLES.md](docs/PATH_EXAMPLES.md) - 路径类型和用法
- [summarization.md](docs/summarization.md) - 上下文摘要
- [plan_mode_usage.md](docs/plan_mode_usage.md) - Plan Mode 与 TodoList