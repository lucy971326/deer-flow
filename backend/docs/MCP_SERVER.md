# MCP (Model Context Protocol) 配置

DeerFlow 支持可配置的 MCP servers 和 skills 以扩展其能力，这些从项目根目录的专用 `extensions_config.json` 文件加载。

## 设置

1. 将 `extensions_config.example.json` 复制到项目根目录的 `extensions_config.json`。
   ```bash
   # 复制示例配置
   cp extensions_config.example.json extensions_config.json
   ```

2. 通过设置 `"enabled": true` 启用所需的 MCP servers 或 skills。
3. 根据需要配置每个 server 的命令、参数和环境变量。
4. 重启应用以加载和注册 MCP tools。

## 文件系统 MCP Servers

DeerFlow 已经为 thread-scoped workspace 访问提供了内置文件工具。
不要为同一个 DeerFlow workspace 添加 MCP filesystem server。
重叠的文件工具使用不同的路径语义，这会使 LLM tool 选择和文件访问行为不稳定。

DeerFlow 目前没有为 filesystem servers 适配 MCP Roots 模式。
特别是，它不发布 per-thread MCP roots 或将 DeerFlow sandbox 路径（如 `/mnt/user-data/...`）映射到 `@modelcontextprotocol/server-filesystem` 接受的路径。
对于 DeerFlow workspace 文件，使用 DeerFlow 的内置文件工具。

## OAuth 支持（HTTP/SSE MCP Servers）

对于 `http` 和 `sse` MCP servers，DeerFlow 支持 OAuth token 获取和自动 token 刷新。

- 支持的 grants：`client_credentials`、`refresh_token`
- 在 `extensions_config.json` 中配置 per-server `oauth` 块
- 密钥应通过环境变量提供（例如：`$MCP_OAUTH_CLIENT_SECRET`）

示例：

```json
{
   "mcpServers": {
      "secure-http-server": {
         "enabled": true,
         "type": "http",
         "url": "https://api.example.com/mcp",
         "oauth": {
            "enabled": true,
            "token_url": "https://auth.example.com/oauth/token",
            "grant_type": "client_credentials",
            "client_id": "$MCP_OAUTH_CLIENT_ID",
            "client_secret": "$MCP_OAUTH_CLIENT_SECRET",
            "scope": "mcp.read",
            "refresh_skew_seconds": 60
         }
      }
   }
}
```

## 自定义 Tool 拦截器

你可以注册自定义拦截器，在每次 MCP tool call 之前运行。这对于注入 per-request headers（例如来自 LangGraph 执行上下文的用户 auth tokens）、日志或指标很有用。

在 `extensions_config.json` 中使用 `mcpInterceptors` 字段声明拦截器：

```json
{
  "mcpInterceptors": [
    "my_package.mcp.auth:build_auth_interceptor"
  ],
  "mcpServers": { ... }
}
```

每个条目是 Python 导入路径，格式为 `module:variable`（通过 `resolve_variable` 解析）。该变量必须是一个**无参数 builder 函数**，返回与 `MultiServerMCPClient` 的 `tool_interceptors` 接口兼容的 async 拦截器，或 `None` 以跳过。

示例拦截器，从 LangGraph metadata 注入 auth headers：

```python
def build_auth_interceptor():
    async def interceptor(request, handler):
        from langgraph.config import get_config
        metadata = get_config().get("metadata", {})
        headers = dict(request.headers or {})
        if token := metadata.get("auth_token"):
            headers["X-Auth-Token"] = token
        return await handler(request.override(headers=headers))
    return interceptor
```

- 接受单个字符串值并规范化为单元素列表。
- 无效路径或 builder 失败记录为警告而不阻塞其他拦截器。
- Builder 返回值必须是 `callable`；非 callable 值会被跳过并发出警告。

## 工作原理

MCP servers 暴露的工具在运行时自动被发现并集成到 DeerFlow 的 agent 系统中。启用后，这些工具对 agents 可用，无需额外代码更改。

## 示例能力

MCP servers 可以提供对以下内容的访问：

- **数据库**（例如 PostgreSQL）
- **外部 APIs**（例如 GitHub、Brave Search）
- **浏览器自动化**（例如 Puppeteer）
- **自定义 MCP server 实现**

## 了解更多

有关 Model Context Protocol 的详细文档，请访问：
https://modelcontextprotocol.io