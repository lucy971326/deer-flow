# Guardrails：Tool-Call 预授权

> **背景：** [Issue #1213](https://github.com/bytedance/deer-flow/issues/1213) — DeerFlow 有 Docker sandboxing 和通过 `ask_clarification` 的人类批准，但没有用于 tool calls 的确定性、策略驱动的授权层。一个运行自主多步任务的 agent 可以用任意参数执行任意已加载的工具。Guardrails 增加了一个 middleware，在执行**前**根据策略评估每个 tool call。

## 为什么需要 Guardrails

```
Without guardrails:                      With guardrails:

  Agent                                    Agent
    │                                        │
    ▼                                        ▼
  ┌──────────┐                             ┌──────────┐
  │ bash     │──▶ executes immediately     │ bash     │──▶ GuardrailMiddleware
  │ rm -rf / │                             │ rm -rf / │        │
  └──────────┘                             └──────────┘        ▼
                                                         ┌──────────────┐
                                                         │  Provider    │
                                                         │  evaluates   │
                                                         │  against     │
                                                         │  policy      │
                                                         └──────┬───────┘
                                                                │
                                                          ┌─────┴─────┐
                                                          │           │
                                                        ALLOW       DENY
                                                          │           │
                                                          ▼           ▼
                                                      Tool runs   Agent sees:
                                                      normally    "Guardrail denied:
                                                                   rm -rf blocked"
```

- **Sandboxing** 提供进程隔离但不提供语义授权。sandbox 内的 `bash` 仍可以 `curl` 数据出去。
- **Human approval**（`ask_clarification`）需要人类参与每个操作。对于自主工作流不可行。
- **Guardrails** 提供确定性、策略驱动的授权，无需人工干预即可工作。

## 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Middleware Chain                               │
│                                                                      │
│  1. ThreadDataMiddleware     ─── per-thread dirs                     │
│  2. UploadsMiddleware        ─── file upload tracking                 │
│  3. SandboxMiddleware        ─── sandbox acquisition                 │
│  4. DanglingToolCallMiddleware ── fix incomplete tool calls          │
│  5. GuardrailMiddleware ◄──── EVALUATES EVERY TOOL CALL             │
│  6. ToolErrorHandlingMiddleware ── convert exceptions to messages     │
│  7-12. (Summarization, Title, Memory, Vision, Subagent, Clarify)    │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
           ┌──────────────────────────┐
           │    GuardrailProvider     │  ◄── pluggable: any class
           │    (configured in YAML)  │      with evaluate/aevaluate
           └────────────┬─────────────┘
                        │
              ┌─────────┼──────────────┐
              │         │              │
              ▼         ▼              ▼
         Built-in   OAP Passport    Custom
         Allowlist  Provider        Provider
         (zero dep) (open standard) (your code)
                        │
                  Any implementation
                  (e.g. APort, or
                   your own evaluator)
```

`GuardrailMiddleware` 实现 `wrap_tool_call` / `awrap_tool_call`（与 `ToolErrorHandlingMiddleware` 相同的 `AgentMiddleware` 模式）。它：

1. 构建包含 tool name、arguments 和 passport reference 的 `GuardrailRequest`
2. 调用配置的 provider 的 `provider.evaluate(request)`
3. 如果是 **deny**：返回带原因的 `ToolMessage(status="error")` — agent 看到拒绝并适应
4. 如果是 **allow**：传递给实际的 tool handler
5. 如果是 **provider error** 且 `fail_closed=true`（默认）：阻止调用
6. `GraphBubbleUp` 异常（LangGraph 控制信号）总是被传播，从不捕获

## 三种 Provider 选项

### 选项 1：内置 AllowlistProvider（零依赖）

最简单的选项。随 DeerFlow 一起提供。按名称阻止或允许 tools。不需要外部包，不需要 passport，不需要网络。

**config.yaml：**
```yaml
guardrails:
  enabled: true
  provider:
    use: deerflow.guardrails.builtin:AllowlistProvider
    config:
      denied_tools: ["bash", "write_file"]
```

这阻止 `bash` 和 `write_file` 对所有请求。其他所有 tools 放行。

你也可以使用 allowlist（只有这些工具被允许）：
```yaml
guardrails:
  enabled: true
  provider:
    use: deerflow.guardrails.builtin:AllowlistProvider
    config:
      allowed_tools: ["web_search", "read_file", "ls"]
```

**尝试它：**
1. 将上述配置添加到 `config.yaml`
2. 启动 DeerFlow：`make dev`
3. 问 agent："Use bash to run echo hello"
4. agent 看到：`Guardrail denied: tool 'bash' was blocked (oap.tool_not_allowed)`

### 选项 2：OAP Passport Provider（基于策略）

用于基于 [Open Agent Passport (OAP)](https://github.com/aporthq/aport-spec) 开放标准的策略执行。一个 OAP passport 是一个 JSON 文档，声明 agent 的身份、能力和操作限制。任何读取 OAP passport 并返回 OAP 兼容决策的 provider 都可以与 DeerFlow 配合工作。

```
┌─────────────────────────────────────────────────────────────┐
│                    OAP Passport (JSON)                        │
│                   (open standard, any provider)              │
│  {                                                           │
│    "spec_version": "oap/1.0",                                │
│    "status": "active",                                       │
│    "capabilities": [                                         │
│      {"id": "system.command.execute"},                       │
│      {"id": "data.file.read"},                               │
│      {"id": "data.file.write"},                              │
│      {"id": "web.fetch"},                                    │
│      {"id": "mcp.tool.execute"}                              │
│    ],                                                        │
│    "limits": {                                               │
│      "system.command.execute": {                             │
│        "allowed_commands": ["git", "npm", "node", "ls"],      │
│        "blocked_patterns": ["rm -rf", "sudo", "chmod 777"]   │
│      }                                                       │
│    }                                                         │
│  }                                                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
               Any OAP-compliant provider
          ┌────────────────┼────────────────┐
          │                │                │
     Your own         APort (ref.      Other future
     evaluator        implementation)  implementations
```

**手动创建 passport：**

一个 OAP passport 就是一个 JSON 文件。你可以按照 [OAP 规范](https://github.com/aporthq/aport-spec/blob/main/oap/oap-spec.md) 手动创建一个，并针对 [JSON schema](https://github.com/aporthq/aport-spec/blob/main/oap/passport-schema.json) 进行验证。见 [examples](https://github.com/aporthq/aport-spec/tree/main/oap/examples) 目录中的模板。

**使用 APort 作为参考实现：**

[APort Agent Guardrails](https://github.com/aporthq/aport-agent-guardrails) 是一个 OAP provider 的开源（Apache 2.0）实现。它处理 passport 创建、本地评估和可选的托管 API 评估。

```bash
pip install aport-agent-guardrails
aport setup --framework deerflow
```

这会创建：
- `~/.aport/deerflow/config.yaml` — evaluator 配置（本地或 API 模式）
- `~/.aport/deerflow/aport/passport.json` — 带有能力和限制的 OAP passport

**config.yaml（使用 APort 作为 provider）：**
```yaml
guardrails:
  enabled: true
  provider:
    use: aport_guardrails.providers.generic:OAPGuardrailProvider
```

**config.yaml（使用你自己的 OAP provider）：**
```yaml
guardrails:
  enabled: true
  provider:
    use: my_oap_provider:MyOAPProvider
    config:
      passport_path: ./my-passport.json
```

任何接受 `framework` 作为 kwarg 并实现 `evaluate`/`aevaluate` 的 provider 都可以工作。OAP 标准定义 passport 格式和决策码；DeerFlow 不关心哪个 provider 读取它们。

**Passport 控制什么：**

| Passport 字段 | 作用 | 示例 |
|---|---|---|
| `capabilities[].id` | agent 可以使用哪些工具类别 | `system.command.execute`, `data.file.write` |
| `limits.*.allowed_commands` | 允许哪些命令 | `["git", "npm", "node"]` 或 `["*"]` 表示全部 |
| `limits.*.blocked_patterns` | 始终拒绝的模式 | `["rm -rf", "sudo", "chmod 777"]` |
| `status` | 终止开关 | `active`, `suspended`, `revoked` |

**评估模式（provider 依赖）：**

OAP provider 可能支持不同的评估模式。例如，APort 参考实现支持：

| 模式 | 如何工作 | 网络 | 延迟 |
|---|---|---|---|
| **Local** | 本地评估 passport（bash script）。 | 无 | ~300ms |
| **API** | 发送 passport + context 到托管 evaluator。签名决策。 | 是 | ~65ms |

自定义 OAP provider 可以实现任何评估策略——DeerFlow middleware 不关心 provider 如何达到其决策。

**尝试它：**
1. 按上述方式安装和设置
2. 启动 DeerFlow 并问："Create a file called test.txt with content hello"
3. 然后问："Now delete it using bash rm -rf"
4. Guardrail 阻止它：`oap.blocked_pattern: Command contains blocked pattern: rm -rf`

### 选项 3：自定义 Provider（自备代码）

任何带有 `evaluate(request)` 和 `aevaluate(request)` 方法的 Python 类都可以工作。不需要基类或继承——这是一个结构化协议。

```python
# my_guardrail.py

class MyGuardrailProvider:
    name = "my-company"

    def evaluate(self, request):
        from deerflow.guardrails.provider import GuardrailDecision, GuardrailReason

        # 示例：阻止任何包含 "delete" 的 bash 命令
        if request.tool_name == "bash" and "delete" in str(request.tool_input):
            return GuardrailDecision(
                allow=False,
                reasons=[GuardrailReason(code="custom.blocked", message="delete not allowed")],
                policy_id="custom.v1",
            )
        return GuardrailDecision(allow=True, reasons=[GuardrailReason(code="oap.allowed")])

    async def aevaluate(self, request):
        return self.evaluate(request)
```

**config.yaml：**
```yaml
guardrails:
  enabled: true
  provider:
    use: my_guardrail:MyGuardrailProvider
```

确保 `my_guardrail.py` 在 Python 路径上（例如在 backend 目录中或作为包安装）。

**尝试它：**
1. 在 backend 目录创建 `my_guardrail.py`
2. 添加配置
3. 启动 DeerFlow 并问："Use bash to delete test.txt"
4. 你的 provider 阻止它

## 实现 Provider

### 必需接口

```
┌──────────────────────────────────────────────────┐
│              GuardrailProvider Protocol            │
│                                                   │
│  name: str                                        │
│                                                   │
│  evaluate(request: GuardrailRequest)              │
│      -> GuardrailDecision                         │
│                                                   │
│  aevaluate(request: GuardrailRequest)   (async)   │
│      -> GuardrailDecision                         │
└──────────────────────────────────────────────────┘

┌──────────────────────────┐    ┌──────────────────────────┐
│     GuardrailRequest      │    │    GuardrailDecision      │
│                           │    │                           │
│  tool_name: str           │    │  allow: bool              │
│  tool_input: dict         │    │  reasons: [GuardrailReason]│
│  agent_id: str | None     │    │  policy_id: str | None    │
│  thread_id: str | None    │    │  metadata: dict           │
│  is_subagent: bool        │    │                           │
│  timestamp: str           │    │  GuardrailReason:         │
│                           │    │    code: str              │
└──────────────────────────┘    │    message: str           │
                                └──────────────────────────┘
```

### DeerFlow Tool Names

这些是 provider 在 `request.tool_name` 中看到的 tool names：

| Tool | 作用 |
|---|---|
| `bash` | Shell 命令执行 |
| `write_file` | 创建/覆盖文件 |
| `str_replace` | 编辑文件（查找和替换） |
| `read_file` | 读取文件内容 |
| `ls` | 列目录 |
| `web_search` | 网络搜索查询 |
| `web_fetch` | 获取 URL 内容 |
| `image_search` | 图片搜索 |
| `present_files` | 向用户呈现文件 |
| `view_image` | 显示图像 |
| `ask_clarification` | 向用户提问 |
| `task` | 委托给 subagent |
| `mcp__*` | MCP tools（动态） |

### OAP Reason Codes

[OAP 规范](https://github.com/aporthq/aport-spec) 使用的标准码：

| Code | 含义 |
|---|---|
| `oap.allowed` | Tool call 已授权 |
| `oap.tool_not_allowed` | Tool 不在 allowlist 中 |
| `oap.command_not_allowed` | 命令不在 allowed_commands 中 |
| `oap.blocked_pattern` | 命令匹配 blocked pattern |
| `oap.limit_exceeded` | 操作超出限制 |
| `oap.passport_suspended` | Passport 状态为 suspended/revoked |
| `oap.evaluator_error` | Provider 崩溃（fail-closed） |

### Provider 加载

DeerFlow 通过 `resolve_variable()` 加载 providers——与 models、tools 和 sandbox providers 相同的机制。`use:` 字段是一个 Python 类路径：`package.module:ClassName`。

provider 用 `**config` kwargs 实例化（如果设置了 `config:`），加上 `framework="deerflow"` 始终被注入。接受 `**kwargs` 以保持向前兼容：

```python
class YourProvider:
    def __init__(self, framework: str = "generic", **kwargs):
        # framework="deerflow" 告诉你使用哪个配置目录
        ...
```

## 配置参考

```yaml
guardrails:
  # 启用/禁用 guardrail middleware（默认：false）
  enabled: true

  # provider 抛出异常时阻止 tool calls（默认：true）
  fail_closed: true

  # Passport 引用 — 作为 request.agent_id 传递给 provider。
  # 文件路径、托管 agent ID 或 null（provider 从其配置解析）。
  passport: null

  # Provider：通过 class path 加载 via resolve_variable
  provider:
    use: deerflow.guardrails.builtin:AllowlistProvider
    config:  # optional kwargs passed to provider.__init__
      denied_tools: ["bash"]
```

## 测试

```bash
cd backend
uv run python -m pytest tests/test_guardrail_middleware.py -v
```

25 个测试覆盖：
- AllowlistProvider: allow、deny、allowlist+denylist 两者、async
- GuardrailMiddleware: allow passthrough、deny with OAP codes、fail-closed、fail-open、passport 转发、empty reasons 回退、empty tool name、protocol isinstance 检查
- Async 路径：awrap_tool_call 用于 allow、deny、fail-closed、fail-open
- GraphBubbleUp：LangGraph 控制信号传播（不被捕获）
- Config: defaults、from_dict、singleton load/reset

## 文件

```
packages/harness/deerflow/guardrails/
    __init__.py              # Public exports
    provider.py              # GuardrailProvider protocol, GuardrailRequest, GuardrailDecision
    middleware.py             # GuardrailMiddleware (AgentMiddleware subclass)
    builtin.py               # AllowlistProvider (zero deps)

packages/harness/deerflow/config/
    guardrails_config.py     # GuardrailsConfig Pydantic model + singleton

packages/harness/deerflow/agents/middlewares/
    tool_error_handling_middleware.py  # Registers GuardrailMiddleware in chain

config.example.yaml          # Three provider options documented
tests/test_guardrail_middleware.py  # 25 tests
docs/GUARDRAILS.md           # This file
```