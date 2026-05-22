# 为 DeerFlow Backend 贡献

感谢您对 DeerFlow 的兴趣！本文档提供贡献后端代码库的指南和说明。

## 目录

- [入门](#入门)
- [开发环境设置](#开发环境设置)
- [项目结构](#项目结构)
- [代码风格](#代码风格)
- [进行更改](#进行更改)
- [测试](#测试)
- [Pull Request 流程](#pull-request-流程)
- [架构指南](#架构指南)

## 入门

### 前置条件

- Python 3.12 或更高
- [uv](https://docs.astral.sh/uv/) 包管理器
- Git
- Docker（可选，用于 Docker sandbox 测试）

### Fork 和 Clone

1. 在 GitHub 上 Fork 仓库
2. 本地克隆你的 fork：
   ```bash
   git clone https://github.com/YOUR_USERNAME/deer-flow.git
   cd deer-flow
   ```

## 开发环境设置

### 安装依赖

```bash
# 从项目根目录
cp config.example.yaml config.yaml

# 安装后端依赖
cd backend
make install
```

### 配置环境

设置您的 API keys 用于测试：

```bash
export OPENAI_API_KEY="your-api-key"
# 根据需要添加其他 keys
```

### 运行开发服务器

```bash
# Gateway API + 嵌入式 agent 运行时
make dev
```

## 项目结构

```
backend/src/
├── agents/                  # Agent 系统
│   ├── lead_agent/         # 主 agent 实现
│   │   └── agent.py        # Agent 工厂和创建
│   ├── middlewares/        # Agent middlewares
│   │   ├── thread_data_middleware.py
│   │   ├── sandbox_middleware.py
│   │   ├── title_middleware.py
│   │   ├── uploads_middleware.py
│   │   ├── view_image_middleware.py
│   │   └── clarification_middleware.py
│   └── thread_state.py     # Thread state 定义
│
├── gateway/                 # FastAPI Gateway
│   ├── app.py              # FastAPI 应用
│   └── routers/            # 路由处理器
│       ├── models.py       # /api/models 端点
│       ├── mcp.py          # /api/mcp 端点
│       ├── skills.py       # /api/skills 端点
│       ├── artifacts.py    # /api/threads/.../artifacts
│       └── uploads.py      # /api/threads/.../uploads
│
├── sandbox/                 # Sandbox 执行
│   ├── __init__.py         # Sandbox 接口
│   ├── local.py            # 本地 sandbox provider
│   └── tools.py            # Sandbox tools（bash, 文件操作）
│
├── tools/                   # Agent tools
│   └── builtins/           # 内置 tools
│       ├── present_file_tool.py
│       ├── ask_clarification_tool.py
│       └── view_image_tool.py
│
├── mcp/                     # MCP 集成
│   └── manager.py          # MCP server 管理
│
├── models/                  # Model 系统
│   └── factory.py          # Model 工厂
│
├── skills/                  # Skills 系统
│   └── loader.py           # Skills 加载器
│
├── config/                  # 配置
│   ├── app_config.py       # 主应用配置
│   ├── extensions_config.py # 扩展配置
│   └── summarization_config.py
│
├── community/               # Community tools
│   ├── tavily/             # Tavily 网络搜索
│   ├── jina/               # Jina 网络获取
│   ├── firecrawl/          # Firecrawl 抓取
│   └── aio_sandbox/        # Docker sandbox
│
├── reflection/              # 动态加载
│   └── __init__.py         # 模块解析
│
└── utils/                   # 工具函数
    └── __init__.py
```

## 代码风格

### Linting 和格式化

我们使用 `ruff` 进行 linting 和格式化：

```bash
# 检查问题
make lint

# 自动修复和格式化
make format
```

### 风格指南

- **行长度**：最多 240 个字符
- **Python 版本**：允许 3.12+ 特性
- **类型提示**：为函数签名使用类型提示
- **引号**：字符串使用双引号
- **缩进**：4 个空格（无 tabs）
- **导入**：按标准库、第三方、本地分组

### Docstrings

为公共函数和类使用 docstrings：

```python
def create_chat_model(name: str, thinking_enabled: bool = False) -> BaseChatModel:
    """Create a chat model instance from configuration.

    Args:
        name: The model name as defined in config.yaml
        thinking_enabled: Whether to enable extended thinking

    Returns:
        A configured LangChain chat model instance

    Raises:
        ValueError: If the model name is not found in configuration
    """
    ...
```

## 进行更改

### 分支命名

使用描述性的分支名称：

- `feature/add-new-tool` - 新功能
- `fix/sandbox-timeout` - Bug 修复
- `docs/update-readme` - 文档
- `refactor/config-system` - 代码重构

### Commit 消息

写清楚、简洁的 commit 消息：

```
feat: add support for Claude 3.5 model

- Add model configuration in config.yaml
- Update model factory to handle Claude-specific settings
- Add tests for new model
```

前缀类型：
- `feat:` - 新功能
- `fix:` - Bug 修复
- `docs:` - 文档
- `refactor:` - 代码重构
- `test:` - 测试
- `chore:` - 构建/配置更改

## 测试

### 运行测试

```bash
uv run pytest
```

### 编写测试

将测试放在 `tests/` 目录中，镜像源结构：

```
tests/
├── test_models/
│   └── test_factory.py
├── test_sandbox/
│   └── test_local.py
└── test_gateway/
    └── test_models_router.py
```

示例测试：

```python
import pytest
from deerflow.models.factory import create_chat_model

def test_create_chat_model_with_valid_name():
    """Test that a valid model name creates a model instance."""
    model = create_chat_model("gpt-4")
    assert model is not None

def test_create_chat_model_with_invalid_name():
    """Test that an invalid model name raises ValueError."""
    with pytest.raises(ValueError):
        create_chat_model("nonexistent-model")
```

## Pull Request 流程

### 提交前

1. **确保测试通过**：`uv run pytest`
2. **运行 linter**：`make lint`
3. **格式化代码**：`make format`
4. **如需要更新文档**

### PR 描述

在您的 PR 描述中包含：

- **What**：更改的简要描述
- **Why**：更改的动机
- **How**：实现方法
- **Testing**：如何测试更改

### 审查流程

1. 提交带有清晰描述的 PR
2. 解决审查反馈
3. 确保 CI 通过
4. 维护者在批准后合并

## 架构指南

### 添加新 Tools

1. 在 `packages/harness/deerflow/tools/builtins/` 或 `packages/harness/deerflow/community/` 创建 tool：

```python
# packages/harness/deerflow/tools/builtins/my_tool.py
from langchain_core.tools import tool

@tool
def my_tool(param: str) -> str:
    """Tool description for the agent.

    Args:
        param: Description of the parameter

    Returns:
        Description of return value
    """
    return f"Result: {param}"
```

2. 在 `config.yaml` 中注册：

```yaml
tools:
  - name: my_tool
    group: my_group
    use: deerflow.tools.builtins.my_tool:my_tool
```

### 添加新 Middleware

1. 在 `packages/harness/deerflow/agents/middlewares/` 创建 middleware：

```python
# packages/harness/deerflow/agents/middlewares/my_middleware.py
from langchain.agents.middleware import BaseMiddleware
from langchain_core.runnables import RunnableConfig

class MyMiddleware(BaseMiddleware):
    """Middleware description."""

    def transform_state(self, state: dict, config: RunnableConfig) -> dict:
        """Transform the state before agent execution."""
        # Modify state as needed
        return state
```

2. 在 `packages/harness/deerflow/agents/lead_agent/agent.py` 中注册：

```python
middlewares = [
    ThreadDataMiddleware(),
    SandboxMiddleware(),
    MyMiddleware(),  # Add your middleware
    TitleMiddleware(),
    ClarificationMiddleware(),
]
```

### 添加新 API 端点

1. 在 `app/gateway/routers/` 创建 router：

```python
# app/gateway/routers/my_router.py
from fastapi import APIRouter

router = APIRouter(prefix="/my-endpoint", tags=["my-endpoint"])

@router.get("/")
async def get_items():
    """Get all items."""
    return {"items": []}

@router.post("/")
async def create_item(data: dict):
    """Create a new item."""
    return {"created": data}
```

2. 在 `app/gateway/app.py` 中注册：

```python
from app.gateway.routers import my_router

app.include_router(my_router.router)
```

### 配置更改

添加新配置选项时：

1. 在 `packages/harness/deerflow/config/app_config.py` 添加新字段
2. 在 `config.example.yaml` 添加默认值
3. 在 `docs/CONFIGURATION.md` 中记录

### MCP Server 集成

添加对新 MCP server 的支持：

1. 在 `extensions_config.json` 中添加配置：

```json
{
  "mcpServers": {
    "my-server": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@my-org/mcp-server"],
      "description": "My MCP Server"
    }
  }
}
```

2. 在 `extensions_config.example.json` 中添加新 server

### Skills 开发

创建新 skill：

1. 在 `skills/public/` 或 `skills/custom/` 创建目录：

```
skills/public/my-skill/
└── SKILL.md
```

2. 编写带有 YAML front matter 的 `SKILL.md`：

```markdown
---
name: My Skill
description: What this skill does
license: MIT
allowed-tools:
  - read_file
  - write_file
  - bash
---

# My Skill

Instructions for the agent when this skill is enabled...
```

## 问题？

如果您有关于贡献的问题：

1. 查看 `docs/` 中的现有文档
2. 在 GitHub 上寻找类似的问题或 PRs
3. 在 GitHub 上开启讨论或 issue

感谢您为 DeerFlow 贡献！