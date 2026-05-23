# API Reference

本文档提供 DeerFlow 后端 API 的完整参考。

## 概述

DeerFlow 后端暴露两组 API：

1. **LangGraph-compatible API** - Agent 交互、threads 和流式传输 (`/api/langgraph/*`)
2. **Gateway API** - Models、MCP、skills、uploads 和 artifacts (`/api/*`)

所有 API 通过 Nginx 反向代理（端口 2026）访问。

## LangGraph-compatible API

Base URL: `/api/langgraph`

公开的 LangGraph-compatible API 遵循 LangGraph SDK 约定。在统一的 nginx 部署中，Gateway 拥有 `/api/langgraph/*` 并将这些路径翻译为其原生的 `/api/*` run、thread 和 streaming 路由。

### Threads

#### Create Thread

```http
POST /api/langgraph/threads
Content-Type: application/json
```

**Request Body:**
```json
{
  "metadata": {}
}
```

**Response:**
```json
{
  "thread_id": "abc123",
  "created_at": "2024-01-15T10:30:00Z",
  "metadata": {}
}
```

#### Get Thread State

```http
GET /api/langgraph/threads/{thread_id}/state
```

**Response:**
```json
{
  "values": {
    "messages": [...],
    "sandbox": {...},
    "artifacts": [...],
    "thread_data": {...},
    "title": "Conversation Title"
  },
  "next": [],
  "config": {...}
}
```

### Runs

#### Create Run

执行 agent 并传入输入。

```http
POST /api/langgraph/threads/{thread_id}/runs
Content-Type: application/json
```

**Request Body:**
```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Hello, can you help me?"
      }
    ]
  },
  "config": {
    "recursion_limit": 100,
    "configurable": {
      "model_name": "gpt-4",
      "thinking_enabled": false,
      "is_plan_mode": false
    }
  },
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

**Stream Mode Compatibility:**
- 使用：`values`、`messages-tuple`、`custom`、`updates`、`events`、`debug`、`tasks`、`checkpoints`
- 不使用：`tools`（deprecated/invalid in current `langgraph-api`，会触发 schema validation 错误）

**Recursion Limit:**

`config.recursion_limit` 限制 LangGraph 在单次 run 中执行的 graph steps 数量。统一 Gateway 路径在 `build_run_config`（见 `backend/app/gateway/services.py`）中默认为 `100`，这是 plan-mode 或 subagent-heavy runs 的更安全起点。客户端仍可以在请求体中显式设置 `recursion_limit`；如果运行深层嵌套 subagent graphs，可以增加。

**Configurable Options:**
- `model_name` (string): 覆盖默认 model
- `thinking_enabled` (boolean): 为支持的 models 启用 extended thinking
- `is_plan_mode` (boolean): 启用 TodoList middleware 进行任务跟踪

**Response:** Server-Sent Events (SSE) stream

```
event: values
data: {"messages": [...], "title": "..."}

event: messages
data: {"content": "Hello! I'd be happy to help.", "role": "assistant"}

event: end
data: {}
```

#### Get Run History

```http
GET /api/langgraph/threads/{thread_id}/runs
```

**Response:**
```json
{
  "runs": [
    {
      "run_id": "run123",
      "status": "success",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Stream Run

实时流式传输响应。

```http
POST /api/langgraph/threads/{thread_id}/runs/stream
Content-Type: application/json
```

请求体与 Create Run 相同。返回 SSE stream。

---

## Gateway API

Base URL: `/api`

### Models

#### List Models

从配置获取所有可用的 LLM models。

```http
GET /api/models
```

**Response:**
```json
{
  "models": [
    {
      "name": "gpt-4",
      "display_name": "GPT-4",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "claude-3-opus",
      "display_name": "Claude 3 Opus",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "deepseek-v3",
      "display_name": "DeepSeek V3",
      "supports_thinking": true,
      "supports_vision": false
    }
  ]
}
```

#### Get Model Details

```http
GET /api/models/{model_name}
```

**Response:**
```json
{
  "name": "gpt-4",
  "display_name": "GPT-4",
  "model": "gpt-4",
  "max_tokens": 4096,
  "supports_thinking": false,
  "supports_vision": true
}
```

### MCP Configuration

#### Get MCP Config

获取当前 MCP server 配置。

```http
GET /api/mcp/config
```

**Response:**
```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "***"
      },
      "description": "GitHub operations"
    }
  }
}
```

#### Update MCP Config

更新 MCP server 配置。

```http
PUT /api/mcp/config
Content-Type: application/json
```

**Request Body:**
```json
{
  "mcpServers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN"
      },
      "description": "GitHub operations"
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "MCP configuration updated"
}
```

### Skills

#### List Skills

获取所有可用的 skills。

```http
GET /api/skills
```

**Response:**
```json
{
  "skills": [
    {
      "name": "pdf-processing",
      "display_name": "PDF Processing",
      "description": "Handle PDF documents efficiently",
      "enabled": true,
      "license": "MIT",
      "path": "public/pdf-processing"
    },
    {
      "name": "frontend-design",
      "display_name": "Frontend Design",
      "description": "Design and build frontend interfaces",
      "enabled": false,
      "license": "MIT",
      "path": "public/frontend-design"
    }
  ]
}
```

#### Get Skill Details

```http
GET /api/skills/{skill_name}
```

**Response:**
```json
{
  "name": "pdf-processing",
  "display_name": "PDF Processing",
  "description": "Handle PDF documents efficiently",
  "enabled": true,
  "license": "MIT",
  "path": "public/pdf-processing",
  "allowed_tools": ["read_file", "write_file", "bash"],
  "content": "# PDF Processing\n\nInstructions for the agent..."
}
```

#### Enable Skill

```http
POST /api/skills/{skill_name}/enable
```

**Response:**
```json
{
  "success": true,
  "message": "Skill 'pdf-processing' enabled"
}
```

#### Disable Skill

```http
POST /api/skills/{skill_name}/disable
```

**Response:**
```json
{
  "success": true,
  "message": "Skill 'pdf-processing' disabled"
}
```

#### Install Skill

从 `.skill` 文件安装 skill。

```http
POST /api/skills/install
Content-Type: multipart/form-data
```

**Request Body:**
- `file`: 要安装的 `.skill` 文件

**Response:**
```json
{
  "success": true,
  "message": "Skill 'my-skill' installed successfully",
  "skill": {
    "name": "my-skill",
    "display_name": "My Skill",
    "path": "custom/my-skill"
  }
}
```

### File Uploads

#### Upload Files

上传一个或多个文件到 thread。

```http
POST /api/threads/{thread_id}/uploads
Content-Type: multipart/form-data
```

**Request Body:**
- `files`: 一个或多个文件

网关在应用层限制上传规模，默认最多 10 个文件、单文件 50 MiB、单次请求总计 100 MiB。可通过 `config.yaml` 的 `uploads.max_files`、`uploads.max_file_size`、`uploads.max_total_size` 调整；前端会读取同一组限制并在选择文件时提示，超过限制时后端返回 `413 Payload Too Large`。

**Response:**
```json
{
  "success": true,
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "markdown_file": "document.md",
      "markdown_path": ".deer-flow/threads/abc123/user-data/uploads/document.md",
      "markdown_virtual_path": "/mnt/user-data/uploads/document.md",
      "markdown_artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.md"
    }
  ],
  "message": "Successfully uploaded 1 file(s)"
}
```

**Supported Document Formats** (auto-converted to Markdown):
- PDF (`.pdf`)
- PowerPoint (`.ppt`, `.pptx`)
- Excel (`.xls`, `.xlsx`)
- Word (`.doc`, `.docx`)

#### List Uploaded Files

```http
GET /api/threads/{thread_id}/uploads/list
```

**Response:**
```json
{
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "extension": ".pdf",
      "modified": 1705997600.0
    }
  ],
  "count": 1
}
```

#### Delete File

```http
DELETE /api/threads/{thread_id}/uploads/{filename}
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted document.pdf"
}
```

### Thread Cleanup

在 LangGraph thread 本身被删除后，删除 DeerFlow 管理的本地 thread 文件（`.deer-flow/threads/{thread_id}`）。

```http
DELETE /api/threads/{thread_id}
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted local thread data for abc123"
}
```

**Error behavior:**
- 对无效 thread ID 返回 `422`
- `500` 返回通用 `{"detail": "Failed to delete local thread data."}` 响应，同时完整异常详情保留在服务器日志

### Artifacts

#### Get Artifact

下载或查看 agent 生成的 artifact。

```http
GET /api/threads/{thread_id}/artifacts/{path}
```

**Path Examples:**
- `/api/threads/abc123/artifacts/mnt/user-data/outputs/result.txt`
- `/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf`

**Query Parameters:**
- `download` (boolean): 如果为 `true`，强制使用 Content-Disposition header 下载

**Response:** File content with appropriate Content-Type

---

## Error Responses

所有 API 以一致格式返回错误：

```json
{
  "detail": "Error message describing what went wrong"
}
```

**HTTP Status Codes:**
- `400` - Bad Request: Invalid input
- `404` - Not Found: Resource not found
- `422` - Validation Error: Request validation failed
- `500` - Internal Server Error: Server-side error

---

## Authentication

DeerFlow 对所有非公开 HTTP 路由强制认证。公开路由限于健康检查、文档和这些公开 auth 端点：

- `POST /api/v1/auth/initialize` 在没有 admin 时创建第一个 admin 账户。
- `POST /api/v1/auth/login/local` 用 email/password 登录并设置 HttpOnly `access_token` cookie。
- `POST /api/v1/auth/register` 创建普通 `user` 账户并设置 session cookie。
- `POST /api/v1/auth/logout` 清除 session cookie。
- `GET /api/v1/auth/setup-status` 报告是否仍需创建第一个 admin。

已认证的 auth 端点：

- `GET /api/v1/auth/me` 返回当前用户。
- `POST /api/v1/auth/change-password` 修改密码，可在 setup 期间选择性地更改 email，增量 `token_version` 并重新签发 cookie。

受保护的状态更改请求还需要 CSRF double-submit token：将 `csrf_token` cookie 值作为 `X-CSRF-Token` header 发送。login/register/initialize/logout 是 bootstrap auth 端点：它们免于 double-submit token，但仍拒绝 hostile browser `Origin` header。

用户隔离从认证用户上下文强制执行：

- Thread metadata 按 `threads_meta.user_id` 作用域隔离；搜索/读取/写入/删除 API 只暴露当前用户的 threads。
- Thread 文件位于 `{base_dir}/users/{user_id}/threads/{thread_id}/user-data/` 并在 sandbox 中作为 `/mnt/user-data/` 暴露。
- Memory 和自定义 agents 存储在 `{base_dir}/users/{user_id}/...` 下。

注意：MCP 出站连接仍可为配置的 HTTP/SSE MCP servers 使用 OAuth；这与 DeerFlow API 认证分离。

---

## Rate Limiting

默认未实现 rate limiting。对于生产部署，在 Nginx 中配置 rate limiting：

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://backend;
}
```

---

## Streaming Support

Gateway 的 LangGraph-compatible API 通过 Server-Sent Events (SSE) 流式传输 run 事件：

```http
POST /api/langgraph/threads/{thread_id}/runs/stream
Accept: text/event-stream
```

---

## SDK Usage

### Python (LangGraph SDK)

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2026/api/langgraph")

# Create thread
thread = await client.threads.create()

# Run agent
async for event in client.runs.stream(
    thread["thread_id"],
    "lead_agent",
    input={"messages": [{"role": "user", "content": "Hello"}]},
    config={"configurable": {"model_name": "gpt-4"}},
    stream_mode=["values", "messages-tuple", "custom"],
):
    print(event)
```

### JavaScript/TypeScript

```typescript
// Using fetch for Gateway API
const response = await fetch('/api/models');
const data = await response.json();
console.log(data.models);

// Create a run and stream SSE events
const streamResponse = await fetch(`/api/langgraph/threads/${threadId}/runs/stream`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  },
  body: JSON.stringify({
    input: { messages: [{ role: "user", content: "Hello" }] },
    stream_mode: ["values", "messages-tuple", "custom"],
  }),
});

const reader = streamResponse.body?.getReader();
// Decode and parse SSE frames from reader in your client code.
```

### cURL Examples

```bash
# List models
curl http://localhost:2026/api/models

# Get MCP config
curl http://localhost:2026/api/mcp/config

# Upload file
curl -X POST http://localhost:2026/api/threads/abc123/uploads \
  -F "files=@document.pdf"

# Enable skill
curl -X POST http://localhost:2026/api/skills/pdf-processing/enable

# Create thread and run agent
curl -X POST http://localhost:2026/api/langgraph/threads \
  -H "Content-Type: application/json" \
  -d '{}'

curl -X POST http://localhost:2026/api/langgraph/threads/abc123/runs \
  -H "Content-Type: application/json" \
  -d '{
    "input": {"messages": [{"role": "user", "content": "Hello"}]},
    "config": {
      "recursion_limit": 100,
      "configurable": {"model_name": "gpt-4"}
    }
  }'
```

> The unified Gateway path defaults `config.recursion_limit` to 100 for
> plan-mode and subagent-heavy runs. Clients may still set
> `config.recursion_limit` explicitly — see the [Create Run](#create-run)
> section for details.