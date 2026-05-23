# Plan Mode 与 TodoList Middleware

本文档描述如何在 DeerFlow 2.0 中启用和使用带 TodoList middleware 的 Plan Mode 功能。

## 概述

Plan Mode 向 agent 添加 TodoList middleware，提供 `write_todos` 工具，帮助 agent：
- 将复杂任务分解为更小、可管理的步骤
- 跟踪工作进度
- 为用户提供正在做什么的可见性

TodoList middleware 构建在 LangChain 的 `TodoListMiddleware` 之上。

## 配置

### 启用 Plan Mode

Plan mode 通过 `RunnableConfig` 的 `configurable` 部分中的 `is_plan_mode` 参数控制。这允许你动态地基于每个请求启用或禁用 plan mode。

```python
from langchain_core.runnables import RunnableConfig
from deerflow.agents.lead_agent.agent import make_lead_agent

# 通过运行时配置启用 plan mode
config = RunnableConfig(
    configurable={
        "thread_id": "example-thread",
        "thinking_enabled": True,
        "is_plan_mode": True,  # Enable plan mode
    }
)

# 创建启用 plan mode 的 agent
agent = make_lead_agent(config)
```

### 配置选项

- **is_plan_mode** (bool)：是否启用带 TodoList middleware 的 plan mode。默认：`False`
  - 通过 `config.get("configurable", {}).get("is_plan_mode", False)` 传递
  - 可以为每次 agent 调用动态设置
  - 无需全局配置

## 默认行为

启用默认设置的 plan mode 后，agent 可以访问具有以下行为的 `write_todos` 工具：

### 何时使用 TodoList

agent 将使用 todo list 用于：
1. 复杂多步任务（3+ 个不同步骤）
2. 需要仔细计划的非平凡任务
3. 用户明确请求 todo list 时
4. 用户提供多个任务时

### 何时不使用 TodoList

agent 将跳过使用 todo list 用于：
1. 单一的、直接的任务
2. 平凡任务（< 3 个步骤）
3. 纯对话或信息请求

### 任务状态

- **pending**：任务尚未开始
- **in_progress**：当前正在处理（可以有多个并行任务）
- **completed**：任务成功完成

## 使用示例

### 基本用法

```python
from langchain_core.runnables import RunnableConfig
from deerflow.agents.lead_agent.agent import make_lead_agent

# 创建启用 plan mode 的 agent
config_with_plan_mode = RunnableConfig(
    configurable={
        "thread_id": "example-thread",
        "thinking_enabled": True,
        "is_plan_mode": True,  # TodoList middleware 将被添加
    }
)
agent_with_todos = make_lead_agent(config_with_plan_mode)

# 创建禁用 plan mode 的 agent（默认）
config_without_plan_mode = RunnableConfig(
    configurable={
        "thread_id": "another-thread",
        "thinking_enabled": True,
        "is_plan_mode": False,  # 无 TodoList middleware
    }
)
agent_without_todos = make_lead_agent(config_without_plan_mode)
```

### 动态 Plan Mode 每个请求

你可以为不同对话或任务动态启用/禁用 plan mode：

```python
from langchain_core.runnables import RunnableConfig
from deerflow.agents.lead_agent.agent import make_lead_agent

def create_agent_for_task(task_complexity: str):
    """根据任务复杂度创建带 plan mode 的 agent。"""
    is_complex = task_complexity in ["high", "very_high"]

    config = RunnableConfig(
        configurable={
            "thread_id": f"task-{task_complexity}",
            "thinking_enabled": True,
            "is_plan_mode": is_complex,  # 仅对复杂任务启用
        }
    )

    return make_lead_agent(config)

# 简单任务 - 不需要 TodoList
simple_agent = create_agent_for_task("low")

# 复杂任务 - 启用 TodoList 以便更好地跟踪
complex_agent = create_agent_for_task("high")
```

## 工作原理

1. 调用 `make_lead_agent(config)` 时，从 `config.configurable` 提取 `is_plan_mode`
2. 配置传递给 `_build_middlewares(config)`
3. `_build_middleware()` 读取 `is_plan_mode` 并调用 `_create_todo_list_middleware(is_plan_mode)`
4. 如果 `is_plan_mode=True`，创建 `TodoListMiddleware` 实例并添加到 middleware 链
5. middleware 自动将 `write_todos` 工具添加到 agent 的 toolset
6. agent 可以在执行期间使用此工具管理任务
7. middleware 处理 todo list 状态并向 agent 提供

## 架构

```
make_lead_agent(config)
  │
├─> Extracts: is_plan_mode = config.configurable.get("is_plan_mode", False)
  │
└─> _build_middlewares(config)
      │
      ├─> ThreadDataMiddleware
      ├─> SandboxMiddleware
      ├─> SummarizationMiddleware (如果通过全局配置启用)
      ├─> TodoListMiddleware (如果 is_plan_mode=True) ← 新增
      ├─> TitleMiddleware
      └─> ClarificationMiddleware
```

## 实现细节

### Agent 模块
- **位置**：`packages/harness/deerflow/agents/lead_agent/agent.py`
- **函数**：`_create_todo_list_middleware(is_plan_mode: bool)` - 如果 plan mode 启用则创建 TodoListMiddleware
- **函数**：`_build_middlewares(config: RunnableConfig)` - 基于运行时配置构建 middleware 链
- **函数**：`make_lead_agent(config: RunnableConfig)` - 创建带适当 middlewares 的 agent

### 运行时配置
Plan mode 通过 `RunnableConfig.configurable` 中的 `is_plan_mode` 参数控制：
```python
config = RunnableConfig(
    configurable={
        "is_plan_mode": True,  # 启用 plan mode
        # ... 其他可配置选项
    }
)
```

## 关键优势

1. **动态控制**：无需全局状态即可每个请求启用/禁用 plan mode
2. **灵活性**：不同对话可以有不同的 plan mode 设置
3. **简单性**：无需全局配置管理
4. **上下文感知**：Plan mode 决策可以基于任务复杂度、用户偏好等

## 自定义 Prompts

DeerFlow 使用自定义 `system_prompt` 和 `tool_description` 用于 TodoListMiddleware，与 DeerFlow 整体 prompt 风格匹配：

### System Prompt 特性
- 使用 XML 标签（`<todo_list_system>`）与 DeerFlow 主 prompt 的结构一致性
- 强调 CRITICAL 规则和最佳实践
- 清晰的"何时使用"与"何时不使用"指南
- 专注于实时更新和即时任务完成

### Tool Description 特性
- 详细的用法场景和示例
- 强烈强调不用于简单任务
- 清晰的任务状态定义（pending、in_progress、completed）
- 综合最佳实践部分
- 任务完成要求以防止过早标记

自定义 prompts 定义在 `/Users/hetao/workspace/deer-flow/backend/packages/harness/deerflow/agents/lead_agent/agent.py:57` 的 `_create_todo_list_middleware()` 中。

## 注意事项

- TodoList middleware 使用 LangChain 内置的 `TodoListMiddleware`，但带有**自定义 DeerFlow 风格 prompts**
- Plan mode 默认**禁用**（`is_plan_mode=False`）以保持向后兼容性
- middleware 位于 `ClarificationMiddleware` 之前，允许在澄清流程期间进行 todo 管理
- 自定义 prompts 强调与 DeerFlow 主 system prompt 相同的原则（清晰、面向行动、关键规则）