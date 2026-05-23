# DeerFlow 心智模型

> 一针见血，点破迷雾

## 这个文件是干嘛的？

AI 会遗忘，但这个文件不会。  
每次压缩对话前，把今天研究出的"关键洞察"存进来，下次 AI 读一遍就能快速上手。

---

## 存什么？

**本质类**
- 这个项目"是什么"和"为什么这样设计"
- 例：Gateway 兼容 LangGraph Agent Server、配置驱动架构

**洞察类**
- 知道了就一下通透的内容
- 例：RunnableConfig vs AppConfig 的分界、工厂函数不是为了"必须这样写"

**模式类**
- 项目的心智模型理解
- 例：配置驱动 vs 中间件驱动的两种架构

## 怎么用？

每次压缩前更新，**累加不覆盖**，用户提出更新时才允许更新。

---


--- 

## 核心心智模型

### 1. 配置驱动 vs 中间件驱动

DeerFlow 和 deepagents 是 LangChain 上层框架的两种架构：

**DeerFlow（配置驱动）：**
```
AppConfig (零件配置单) → make_lead_agent (工厂函数) → create_agent
```
- 创建时决定零件（model, tools, middleware）
- config.yaml 配置文件驱动
- 改配置"下次 run"生效

**deepagents（中间件驱动）：**
```
create_deep_agent(middleware=[...]) → 运行时拦截
```
- 运行时通过中间件拦截修改
- 每次调用可动态决定

**DeerFlow 用配置驱动的原因？**
- 更直观：看 config.yaml 就知道用了什么
- 兼容 LangGraph Studio：需要 `def xxx(config: RunnableConfig)` 签名
- 热重载：改文件自动生效

---

### 2. RunnableConfig vs AppConfig

```
AppConfig (DeerFlow 的)    → 用什么零件（model, tools, middleware）
RunnableConfig (LangGraph) → 怎么跑（thread_id, callbacks, recursion_limit）
```

**各管各的，在 make_lead_agent 里汇合。**

---

### 3. 工厂函数的核心目的

`make_lead_agent(config)` 存在的原因：

**不是"必须这样写"，而是"支持动态配置"**

```
请求1: thinking=True,  model="deepseek-v4"
请求2: thinking=False, model="gpt-4o"
请求3: thinking=True,  model="qwen"
```

每次请求不同配置，不需要重启 Studio。

---

### 4. attach_tracing=False 不变量

**位置：** `agent.py` 模块 docstring

**含义：** tracing callbacks 只在 graph root 加一次，不要在 model 级别再加

**后果：** 不传会产生重复 span，Langfuse 无法传递 session_id/user_id

---

### 5. resolve_class / resolve_variable 动态加载

**本质：** 字符串路径 → 运行时 Python 对象

```
"langchain_openai:ChatOpenAI" → resolve_class() → <class ChatOpenAI>
```

**为什么需要？**
- config.yaml 只能用字符串
- 运行时根据字符串动态加载真正的 class
- 换模型不改代码，只改配置

**类似设计：** LangChain 的 `_import_module` + `getattr`

---

### 6. create_chat_model 的输入输出

**输入：** name + thinking_enabled + app_config
**输出：** 配置好的 ChatOpenAI/Claude 实例

**核心流程：**
```
config.yaml 的 ModelConfig
    ↓ model_dump() 去掉元数据
剩余真正的参数（api_key, base_url...）
    ↓ thinking 模式处理
    ↓ provider 特化处理
    ↓ stream_usage 强制开启
    ↓ new ChatOpenAI(**参数)
```

---

### 7. attach_tracing 的两种场景

| 调用者 | attach_tracing | 原因 |
|--------|---------------|------|
| MemoryUpdater（后台独立） | 默认 True | 不在 LangGraph run 内，需要自己 trace |
| make_lead_agent（graph 内部） | 必须传 False | graph root 已加 tracing，避免重复 |

---

### 8. factory.py 的脏代码

**问题：** 10 个字段 exclude + 4 种 thinking 关闭分支 + issubclass 判断 class

**本质：** provider 差异被堆在 factory 里，没用多态抽象

**干净设计应该是：** 各 provider class 自己实现 `disable_thinking()` 方法

---

### 9. LangGraph Studio 的角色

- 不是 DeerFlow 的一部分，是 LangGraph 的可视化工具
- DeerFlow 通过 `langgraph.json` 指向 `make_lead_agent` factory
- Studio 能显示 18 个 middleware 作为节点