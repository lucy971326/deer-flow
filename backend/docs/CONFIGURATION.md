# 配置指南

本文档说明如何为你的环境配置 DeerFlow。

## Config Versioning

`config.example.yaml` 包含 `config_version` 字段，用于追踪 schema 变更。当示例版本高于本地 `config.yaml` 时，应用会在启动时发出警告：

```
WARNING - Your config.yaml (version 0) is outdated — the latest version is 1.
Run `make config-upgrade` to merge new fields into your config.
```

- 配置中缺少 `config_version` 视为版本 0。
- 运行 `make config-upgrade` 自动合并缺失字段（你现有的值会被保留，会创建 `.bak` 备份）。
- 更改配置 schema 时，在 `config.example.yaml` 中 bump `config_version`。

## 配置 sections

### Models

配置 agent 可用的 LLM models：

```yaml
models:
  - name: gpt-4                    # 内部标识符
    display_name: GPT-4            # 人类可读名称
    use: langchain_openai:ChatOpenAI  # LangChain class path
    model: gpt-4                   # API 模型标识符
    api_key: $OPENAI_API_KEY       # API key（使用 env var）
    max_tokens: 4096               # 每次请求最大 tokens
    temperature: 0.7               # 采样温度
```

**Supported Providers**:
- OpenAI (`langchain_openai:ChatOpenAI`)
- Anthropic (`langchain_anthropic:ChatAnthropic`)
- DeepSeek (`langchain_deepseek:ChatDeepSeek`)
- Claude Code OAuth (`deerflow.models.claude_provider:ClaudeChatModel`)
- Codex CLI (`deerflow.models.openai_codex_provider:CodexChatModel`)
- Any LangChain-compatible provider

CLI-backed provider 示例：

```yaml
models:
  - name: gpt-5.4
    display_name: GPT-5.4 (Codex CLI)
    use: deerflow.models.openai_codex_provider:CodexChatModel
    model: gpt-5.4
    supports_thinking: true
    supports_reasoning_effort: true

  - name: claude-sonnet-4.6
    display_name: Claude Sonnet 4.6 (Claude Code OAuth)
    use: deerflow.models.claude_provider:ClaudeChatModel
    model: claude-sonnet-4-6
    max_tokens: 4096
    supports_thinking: true
```

**Auth behavior for CLI-backed providers**:
- `CodexChatModel` 从 `~/.codex/auth.json` 加载 Codex CLI auth
- Codex Responses endpoint 当前拒绝 `max_tokens` 和 `max_output_tokens`，所以 `CodexChatModel` 不暴露请求级别的 token 上限
- `ClaudeChatModel` 接受 `CLAUDE_CODE_OAUTH_TOKEN`、`ANTHROPIC_AUTH_TOKEN`、`CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`、`CLAUDE_CODE_CREDENTIALS_PATH` 或明文 `~/.claude/.credentials.json`
- 在 macOS 上，DeerFlow 不会自动探测 Keychain。需要时使用 `scripts/export_claude_code_oauth.py` 显式导出 Claude Code auth

要使用 OpenAI 的 `/v1/responses` endpoint 配合 LangChain，继续使用 `langchain_openai:ChatOpenAI` 并设置：

```yaml
models:
  - name: gpt-5-responses
    display_name: GPT-5 (Responses API)
    use: langchain_openai:ChatOpenAI
    model: gpt-5
    api_key: $OPENAI_API_KEY
    use_responses_api: true
    output_version: responses/v1
```

对于 OpenAI-compatible gateways（例如 Novita 或 OpenRouter），继续使用 `langchain_openai:ChatOpenAI` 并设置 `base_url`：

```yaml
models:
  - name: novita-deepseek-v3.2
    display_name: Novita DeepSeek V3.2
    use: langchain_openai:ChatOpenAI
    model: deepseek/deepseek-v3.2
    api_key: $NOVITA_API_KEY
    base_url: https://api.novita.ai/openai
    supports_thinking: true
    when_thinking_enabled:
      extra_body:
        thinking:
          type: enabled

  - name: minimax-m2.5
    display_name: MiniMax M2.5
    use: langchain_openai:ChatOpenAI
    model: MiniMax-M2.5
    api_key: $MINIMAX_API_KEY
    base_url: https://api.minimax.io/v1
    max_tokens: 4096
    temperature: 1.0  # MiniMax requires temperature in (0.0, 1.0]
    supports_vision: true

  - name: minimax-m2.5-highspeed
    display_name: MiniMax M2.5 Highspeed
    use: langchain_openai:ChatOpenAI
    model: MiniMax-M2.5-highspeed
    api_key: $MINIMAX_API_KEY
    base_url: https://api.minimax.io/v1
    max_tokens: 4096
    temperature: 1.0  # MiniMax requires temperature in (0.0, 1.0]
    supports_vision: true
  - name: openrouter-gemini-2.5-flash
    display_name: Gemini 2.5 Flash (OpenRouter)
    use: langchain_openai:ChatOpenAI
    model: google/gemini-2.5-flash-preview
    api_key: $OPENAI_API_KEY
    base_url: https://openrouter.ai/api/v1
```

如果你的 OpenRouter key 位于不同名称的环境变量中，显式地将 `api_key` 指向该变量（例如 `api_key: $OPENROUTER_API_KEY`）。

**Thinking Models**:
有些 models 支持 "thinking" 模式用于复杂推理：

```yaml
models:
  - name: deepseek-v3
    supports_thinking: true
    when_thinking_enabled:
      extra_body:
        thinking:
          type: enabled
```

**Gemini with thinking via OpenAI-compatible gateway**:

当通过 OpenAI-compatible proxy（Vertex AI OpenAI compat endpoint、AI Studio 或第三方 gateways）路由 Gemini 并启用 thinking 时，API 在响应中返回的每个 tool-call 对象上附加一个 `thought_signature`。 后续重放这些 assistant 消息的每个请求**必须**将那些 signature echo 回 tool-call 条目，否则 API 返回：

```
HTTP 400 INVALID_ARGUMENT: function call `<tool>` in the N. content block is
missing a `thought_signature`.
```

标准 `langchain_openai:ChatOpenAI` 在序列化消息时静默删除 `thought_signature`。 使用 `deerflow.models.patched_openai:PatchedChatOpenAI` 替代——它在每个传出 payload 中重新注入 tool-call signatures（从 `AIMessage.additional_kwargs["tool_calls"]` 获取）：

```yaml
models:
  - name: gemini-2.5-pro-thinking
    display_name: Gemini 2.5 Pro (Thinking)
    use: deerflow.models.patched_openai:PatchedChatOpenAI
    model: google/gemini-2.5-pro-preview   # model name as expected by your gateway
    api_key: $GEMINI_API_KEY
    base_url: https://<your-openai-compat-gateway>/v1
    max_tokens: 16384
    supports_thinking: true
    supports_vision: true
    when_thinking_enabled:
      extra_body:
        thinking:
          type: enabled
```

对于**不启用** thinking 访问的 Gemini（例如通过 OpenRouter，thinking 未激活），使用普通的 `langchain_openai:ChatOpenAI` 且 `supports_thinking: false` 即可，不需要 patch。

### Tool Groups

将 tools 组织成逻辑组：

```yaml
tool_groups:
  - name: web          # Web browsing and search
  - name: file:read    # Read-only file operations
  - name: file:write   # Write file operations
  - name: bash         # Shell command execution
```

### Tools

配置 agent 可用的特定 tools：

```yaml
tools:
  - name: web_search
    group: web
    use: deerflow.community.tavily.tools:web_search_tool
    max_results: 5
    # api_key: $TAVILY_API_KEY  # Optional
```

**Built-in Tools**:
- `web_search` - Web search (DuckDuckGo, Tavily, Exa, InfoQuest, Firecrawl)
- `web_fetch` - Fetch web pages (Jina AI, Exa, InfoQuest, Firecrawl)
- `ls` - List directory contents
- `read_file` - Read file contents
- `write_file` - Write file contents
- `str_replace` - String replacement in files
- `bash` - Execute bash commands

### Sandbox

DeerFlow 支持多种 sandbox 执行模式。在 `config.yaml` 中配置你偏好的模式：

**Local Execution**（在宿主机上直接执行 sandbox 代码）：
```yaml
sandbox:
   use: deerflow.sandbox.local:LocalSandboxProvider # Local execution
   allow_host_bash: false # default; host bash is disabled unless explicitly re-enabled
```

**Docker Execution**（在隔离的 Docker 容器中执行 sandbox 代码）：
```yaml
sandbox:
   use: deerflow.community.aio_sandbox:AioSandboxProvider # Docker-based sandbox
```

**Docker Execution with Kubernetes**（通过 provisioner service 在 Kubernetes Pod 中执行 sandbox 代码）：

此模式在宿主机的集群上为每个 sandbox 在隔离的 Kubernetes Pod 中运行。需要 Docker Desktop K8s、OrbStack 或类似的本地 K8s 设置。

```yaml
sandbox:
   use: deerflow.community.aio_sandbox:AioSandboxProvider
   provisioner_url: http://provisioner:8002
```

当使用 Docker 开发（`make docker-start`）时，DeerFlow 仅在此 provisioner 模式配置时启动 `provisioner` 服务。在本地或普通 Docker sandbox 模式下，`provisioner` 被跳过。

详见 [Provisioner Setup Guide](../../docker/provisioner/README.md) 获取详细配置、前置条件和故障排查。

选择本地执行或 Docker-based 隔离：

**Option 1: Local Sandbox**（默认，配置更简单）：
```yaml
sandbox:
  use: deerflow.sandbox.local:LocalSandboxProvider
  allow_host_bash: false
```

`allow_host_bash` 默认是 `false`。DeerFlow 的 local sandbox 是宿主机端的便利模式，不是安全的 shell 隔离边界。如果你需要 `bash`，优先使用 `AioSandboxProvider`。只有对于完全受信任的单用户本地工作流才设置 `allow_host_bash: true`。

**Option 2: Docker Sandbox**（隔离，更安全）：
```yaml
sandbox:
  use: deerflow.community.aio_sandbox:AioSandboxProvider
  port: 8080
  auto_start: true
  container_prefix: deer-flow-sandbox

  # Optional: Additional mounts
  mounts:
    - host_path: /path/on/host
      container_path: /path/in/container
      read_only: false
```

当你配置 `sandbox.mounts` 时，DeerFlow 在 agent prompt 中暴露那些 `container_path` 值，以便 agent 可以直接发现和操作挂载的目录，而不是假设所有内容都必须位于 `/mnt/user-data` 下。

对于使用 localhost 的裸机 Docker sandbox runs，DeerFlow 默认将 sandbox HTTP 端口绑定到 `127.0.0.1`，因此不会暴露在每个宿主接口上。通过 `host.docker.internal` 连接的 Docker-outside-of-Docker 部署为兼容性保留宽泛的 legacy 绑定。如果你的部署需要不同的绑定地址，显式设置 `DEER_FLOW_SANDBOX_BIND_HOST`。

### Skills

配置 specialized workflows 的 skills 目录：

```yaml
skills:
  # Host path (optional, default: ../skills)
  path: /custom/path/to/skills

  # Container mount path (default: /mnt/skills)
  container_path: /mnt/skills
```

**How Skills Work**:
- Skills stored in `deer-flow/skills/{public,custom}/`
- Each skill has a `SKILL.md` file with metadata
- Skills are automatically discovered and loaded
- Available in both local and Docker sandbox via path mapping

**Per-Agent Skill Filtering**:
Custom agents can restrict which skills they load by defining a `skills` field in their `config.yaml` (located at `workspace/agents/<agent_name>/config.yaml`):
- **Omitted or `null`**: Loads all globally enabled skills (default fallback).
- **`[]` (empty list)**: Disables all skills for this specific agent.
- **`["skill-name"]`**: Loads only the explicitly specified skills.

### Title Generation

自动对话 title 生成：

```yaml
title:
  enabled: true
  max_words: 6
  max_chars: 60
  model_name: null  # Use first model in list
```

### GitHub API Token (Optional for GitHub Deep Research Skill)

默认 GitHub API rate limits 相当严格。对于频繁的项目研究，我们建议配置具有只读权限的个人访问 token (PAT)。

**Configuration Steps**:
1. 在 `.env` 文件中取消注释 `GITHUB_TOKEN` 行并添加你的个人访问 token
2. 重启 DeerFlow 服务以应用更改

## 环境变量

DeerFlow 支持使用 `$` 前缀的环境变量替换：

```yaml
models:
  - api_key: $OPENAI_API_KEY  # Reads from environment
```

**Common Environment Variables**:
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key
- `DEEPSEEK_API_KEY` - DeepSeek API key
- `NOVITA_API_KEY` - Novita API key (OpenAI-compatible endpoint)
- `TAVILY_API_KEY` - Tavily search API key
- `DEER_FLOW_PROJECT_ROOT` - Project root for relative runtime paths
- `DEER_FLOW_CONFIG_PATH` - Custom config file path
- `DEER_FLOW_EXTENSIONS_CONFIG_PATH` - Custom extensions config file path
- `DEER_FLOW_HOME` - Runtime state directory (defaults to `.deer-flow` under the project root)
- `DEER_FLOW_SKILLS_PATH` - Skills directory when `skills.path` is omitted
- `GATEWAY_ENABLE_DOCS` - Set to `false` to disable Swagger UI (`/docs`), ReDoc (`/redoc`), and OpenAPI schema (`/openapi.json`) endpoints (default: `true`)

## 配置位置

配置文件应放置在**项目根目录**（`deer-flow/config.yaml`）。当进程可能从其他工作目录启动时设置 `DEER_FLOW_PROJECT_ROOT`，或设置 `DEER_FLOW_CONFIG_PATH` 指向特定文件。

## 配置优先级

DeerFlow 按以下顺序搜索配置：

1. 代码中通过 `config_path` 参数指定的路径
2. `DEER_FLOW_CONFIG_PATH` 环境变量指定的路径
3. `DEER_FLOW_PROJECT_ROOT` 下的 `config.yaml`，或当 `DEER_FLOW_PROJECT_ROOT` 未设置时为当前工作目录
4. Legacy backend/repository-root locations for monorepo compatibility

## Best Practices

1. **Place `config.yaml` in project root** - Set `DEER_FLOW_PROJECT_ROOT` if the runtime starts elsewhere
2. **Never commit `config.yaml`** - It's already in `.gitignore`
3. **Use environment variables for secrets** - Don't hardcode API keys
4. **Keep `config.example.yaml` updated** - Document all new options
5. **Test configuration changes locally** - Before deploying
6. **Use Docker sandbox for production** - Better isolation and security

## 故障排查

### "Config file not found"
- Ensure `config.yaml` exists in the **project root** directory (`deer-flow/config.yaml`)
- If the runtime starts outside the project root, set `DEER_FLOW_PROJECT_ROOT`
- Alternatively, set `DEER_FLOW_CONFIG_PATH` environment variable to custom location

### "Invalid API key"
- Verify environment variables are set correctly
- Check that `$` prefix is used for env var references

### "Skills not loading"
- Check that `deer-flow/skills/` directory exists
- Verify skills have valid `SKILL.md` files
- Check `skills.path` or `DEER_FLOW_SKILLS_PATH` if using a custom path

### "Docker sandbox fails to start"
- Ensure Docker is running
- Check port 8080 (or configured port) is available
- Verify Docker image is accessible

## 示例

See `config.example.yaml` for complete examples of all configuration options.