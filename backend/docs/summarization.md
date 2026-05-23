# 对话摘要

DeerFlow 包含自动对话摘要功能，用于处理接近模型 token 限制的长对话。启用后，系统会自动压缩旧消息同时保留最近的上下文。

## 概述

摘要功能使用 LangChain 的 `SummarizationMiddleware` 监控对话历史并根据可配置的阈值触发摘要。激活时：

1. 实时监控消息 token 计数
2. 达到阈值时触发摘要
3. 保留最近消息同时压缩旧对话
4. 保持 AI/Tool 消息配对以确保上下文连续性
5. 将摘要注入回对话

## 配置

在 `config.yaml` 的 `summarization` 键下配置：

```yaml
summarization:
  enabled: true
  model_name: null  # 使用默认模型或指定轻量模型

  # 触发条件（OR 逻辑 — 任一条件触发摘要）
  trigger:
    - type: tokens
      value: 4000
    # 额外触发器（可选）
    # - type: messages
    #   value: 50
    # - type: fraction
    #   value: 0.8  # 模型最大输入 tokens 的 80%

  # 上下文保留策略
  keep:
    type: messages
    value: 20

  # 摘要调用的 token 修整
  trim_tokens_to_summarize: 4000

  # 自定义摘要 prompt（可选）
  summary_prompt: null

  # 视为 skill 文件读取的 tool names，用于 skill 救援
  skill_file_read_tool_names:
    - read_file
    - read
    - view
    - cat
```

### 配置选项

#### `enabled`
- **类型**：Boolean
- **默认**：`false`
- **描述**：启用或禁用自动摘要

#### `model_name`
- **类型**：String 或 null
- **默认**：`null`（使用默认模型）
- **描述**：用于生成摘要的模型。建议使用轻量、性价比高的模型如 `gpt-4o-mini` 或同等产品。

#### `trigger`
- **类型**：单个 `ContextSize` 或 `ContextSize` 对象列表
- **必需**：启用时必须指定至少一个触发器
- **描述**：触发摘要的阈值。使用 OR 逻辑——任意阈值满足时运行摘要。

**ContextSize 类型：**

1. **基于 token 的触发器**：token 计数达到指定值时激活
   ```yaml
   trigger:
     type: tokens
     value: 4000
   ```

2. **基于消息的触发器**：消息数量达到指定值时激活
   ```yaml
   trigger:
     type: messages
     value: 50
   ```

3. **基于 fraction 的触发器**：token 使用达到模型最大输入 tokens 的百分比时激活
   ```yaml
   trigger:
     type: fraction
     value: 0.8  # 最大输入 tokens 的 80%
   ```

**多个触发器：**
```yaml
trigger:
  - type: tokens
    value: 4000
  - type: messages
    value: 50
```

#### `keep`
- **类型**：`ContextSize` 对象
- **默认**：`{type: messages, value: 20}`
- **描述**：指定摘要后保留多少最近的对话历史。

**示例：**
```yaml
# 保留最近 20 条消息
keep:
  type: messages
  value: 20

# 保留最近 3000 tokens
keep:
  type: tokens
  value: 3000

# 保留最近 30% 的模型最大输入 tokens
keep:
  type: fraction
  value: 0.3
```

#### `trim_tokens_to_summarize`
- **类型**：Integer 或 null
- **默认**：`4000`
- **描述**：准备摘要调用时包含的最大 tokens。设置为 `null` 跳过修整（不推荐用于非常长的对话）。

#### `summary_prompt`
- **类型**：String 或 null
- **默认**：`null`（使用 LangChain 的默认 prompt）
- **描述**：用于生成摘要的自定义 prompt 模板。Prompt 应引导模型提取最重要的上下文。

#### `preserve_recent_skill_count`
- **类型**：Integer (≥ 0)
- **默认**：`5`
- **描述**：从摘要中救援的最新加载 skill 文件数（tool name 在 `skill_file_read_tool_names` 中且目标路径在 `skills.container_path` 下，例如 `/mnt/skills/...` 的 tool results）。防止 agent 在压缩后丢失 skill 指令。设置为 `0` 完全禁用 skill 救援。

#### `preserve_recent_skill_tokens`
- **类型**：Integer (≥ 0)
- **默认**：`25000`
- **描述**：为救援的 skill reads 保留的总 token 预算。一旦这个预算耗尽，较旧的 skill bundles 可以被摘要。

#### `preserve_recent_skill_tokens_per_skill`
- **类型**：Integer (≥ 0)
- **默认**：`5000`
- **描述**：每个 skill 的 token 上限。任何单个 skill read 的 tool result 超过此大小则不救援（它像普通内容一样落入摘要器）。

#### `skill_file_read_tool_names`
- **类型**：字符串列表
- **默认**：`["read_file", "read", "view", "cat"]`
- **描述**：在摘要救援期间被视为 skill 文件读取的 tool names。只有当 tool name 在此列表中且目标路径在 `skills.container_path` 下时，tool call 才有资格进行 skill 救援。

**默认 Prompt 行为：**
默认 LangChain prompt 指示模型：
- 提取最高质量/最相关上下文
- 聚焦对整体目标至关重要的信息
- 避免重复已完成操作
- 仅返回提取的上下文

## 工作原理

### 摘要流程

1. **监控**：每次模型调用前，middleware 计算消息历史中的 tokens
2. **触发检查**：如果满足任何配置的阈值，触发摘要
3. **消息分区**：消息分为：
   - 要摘要的消息（超过 `keep` 阈值的旧消息）
   - 要保留的消息（`keep` 阈值内的最近消息）
4. **摘要生成**：模型生成旧消息的简洁摘要
5. **上下文替换**：更新消息历史：
   - 删除所有旧消息
   - 添加单个摘要消息
   - 保留最近消息
6. **AI/Tool 配对保护**：系统确保 AI 消息及其对应的 Tool 消息保持在一起
7. **Skill 救援**：在生成摘要之前，最近加载的 skill 文件（tool name 在 `skill_file_read_tool_names` 中且目标路径在 `skills.container_path` 下的 tool results）从摘要集中取出并前置到保留尾部。选区以三种预算从新到旧遍历：`preserve_recent_skill_count`、`preserve_recent_skill_tokens` 和 `preserve_recent_skill_tokens_per_skill`。触发的 AIMessage 及其所有配对的 ToolMessages 一起移动，以保持 tool_call ↔ tool_result 配对完整。

### Token 计数

- 使用基于字符计数的近似 token 计数
- 对于 Anthropic 模型：约每 token 3.3 个字符
- 对于其他模型：使用 LangChain 的默认估计
- 可以用自定义 `token_counter` 函数自定义

### 消息保留

middleware 智能保留消息上下文：

- **最近消息**：始终根据 `keep` 配置保持完整
- **AI/Tool 配对**：永不拆分——如果截止点落在 tool 消息中，系统调整以保持整个 AI + Tool 消息序列在一起
- **摘要格式**：摘要作为 HumanMessage 注入，格式为：
  ```
  Here is a summary of the conversation to date:

  [Generated summary text]
  ```

## 最佳实践

### 选择触发阈值

1. **基于 token 的触发器**：推荐用于大多数用例
   - 设置为模型上下文窗口的 60-80%
   - 示例：对于 8K 上下文，使用 4000-6000 tokens

2. **基于消息的触发器**：用于控制对话长度
   - 适用于消息较多的应用
   - 示例：50-100 条消息，取决于平均消息长度

3. **基于 fraction 的触发器**：理想用于使用多个模型
   - 自动适应每个模型的容量
   - 示例：0.8（最大输入 tokens 的 80%）

### 选择保留策略（`keep`）

1. **基于消息的保留**：适用于大多数场景
   - 保留自然对话流程
   - 推荐：15-25 条消息

2. **基于 token 的保留**：需要精确控制时使用
   - 适合管理精确 token 预算
   - 推荐：2000-4000 tokens

3. **基于 fraction 的保留**：用于多模型设置
   - 自动随模型容量扩展
   - 推荐：0.2-0.4（最大输入的 20-40%）

### 模型选择

- **推荐**：使用轻量、性价比高的模型进行摘要
  - 示例：`gpt-4o-mini`、`claude-haiku` 或同等产品
  - 摘要不需要最强大的模型
  - 高容量应用显著节省成本

- **默认**：如果 `model_name` 为 `null`，使用默认模型
  - 可能更昂贵但确保一致性
  - 适合简单设置

### 优化提示

1. **平衡触发器**：结合 token 和消息触发器以获得稳健处理
   ```yaml
   trigger:
     - type: tokens
       value: 4000
     - type: messages
       value: 50
   ```

2. **保守保留**：最初保留更多消息，根据性能调整
   ```yaml
   keep:
     type: messages
     value: 25  # 开始更高，需要时减少
   ```

3. **策略性修整**：限制发送给摘要模型的内容
   ```yaml
   trim_tokens_to_summarize: 4000  # 防止昂贵的摘要调用
   ```

4. **监控和迭代**：跟踪摘要质量并调整配置

## 故障排查

### 摘要质量问题

**问题**：摘要丢失重要上下文

**解决方案**：
1. 增加 `keep` 值以保留更多消息
2. 降低触发阈值以更早摘要
3. 自定义 `summary_prompt` 以强调关键信息
4. 使用更有能力的模型进行摘要

### 性能问题

**问题**：摘要调用花费时间太长

**解决方案**：
1. 使用更快的模型进行摘要（例如 `gpt-4o-mini`）
2. 减少 `trim_tokens_to_summarize` 以发送更少上下文
3. 增加触发阈值以减少摘要频率

### Token 限制错误

**问题**：尽管有摘要仍达到 token 限制

**解决方案**：
1. 降低触发阈值以更早摘要
2. 减少 `keep` 值以保留更少消息
3. 检查个别消息是否非常大
4. 考虑使用基于 fraction 的触发器

## 实现细节

### 代码结构

- **配置**：`packages/harness/deerflow/config/summarization_config.py`
- **集成**：`packages/harness/deerflow/agents/lead_agent/agent.py`
- **Middleware**：使用 `langchain.agents.middleware.SummarizationMiddleware`

### Middleware 顺序

摘要在线程数据初始化后、Sandbox 之后、Title 和 Clarification 之前运行：

1. ThreadDataMiddleware
2. SandboxMiddleware
3. **SummarizationMiddleware** ← 在此运行
4. TitleMiddleware
5. ClarificationMiddleware

### 状态管理

- 摘要是无状态的——配置在启动时加载一次
- 摘要作为常规消息添加到对话历史中
- checkpointer 自动持久化摘要后的历史

## 示例配置

### 最小配置
```yaml
summarization:
  enabled: true
  trigger:
    type: tokens
    value: 4000
  keep:
    type: messages
    value: 20
```

### 生产配置
```yaml
summarization:
  enabled: true
  model_name: gpt-4o-mini  # 轻量模型，成本效率
  trigger:
    - type: tokens
      value: 6000
    - type: messages
      value: 75
  keep:
    type: messages
    value: 25
  trim_tokens_to_summarize: 5000
```

### 多模型配置
```yaml
summarization:
  enabled: true
  model_name: gpt-4o-mini
  trigger:
    type: fraction
    value: 0.7  # 模型最大输入的 70%
  keep:
    type: fraction
    value: 0.3  # 保留最大输入的 30%
  trim_tokens_to_summarize: 4000
```

### 保守配置（高质量）
```yaml
summarization:
  enabled: true
  model_name: gpt-4  # 使用完整模型以获得高质量摘要
  trigger:
    type: tokens
    value: 8000
  keep:
    type: messages
    value: 40  # 保留更多上下文
  trim_tokens_to_summarize: null  # 不修整
```

## 参考

- [LangChain Summarization Middleware 文档](https://docs.langchain.com/oss/python/langchain/middleware/built-in#summarization)
- [LangChain 源码](https://github.com/langchain-ai/langchain)