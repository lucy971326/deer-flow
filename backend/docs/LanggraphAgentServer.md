# LangGraph Agent Server 架构解析

> 一针见血，点破迷雾

---

## Agent Server 是什么？

**LangSmith Deployment 的核心组件**：一个用于创建和管理 Agent 应用的 API 平台。

```
传统 Web 框架                    Agent Server
─────────────────                ───────────────────────
处理请求 → 返回响应        处理请求 → 创建 Run → 异步执行 → SSE 推送
无状态                          有状态（Thread + Checkpoint）
短时运行                        长时运行（Agent 可能思考很久）
```

**核心特性：**
- 内置持久化（PostgreSQL）
- 内置任务队列（Task Queue）
- 支持 Assistants / Threads / Runs / Cron Jobs

---

## 核心概念

### Assistants

配置好的 Agent 实例（一个 Graph），用于特定任务。

```
Assistant = Graph 代码 + 配置（模型、工具、系统提示）
```

### Threads

一次完整对话的容器，类似于 DeerFlow 的 Thread。

```
Thread = 对话历史 + 状态
       = 多个 Runs 的上下文
```

### Runs

一次执行单元，类似于 DeerFlow 的 Run。

```
Thread 1
├── Run 1  → "帮我写代码"
├── Run 2  → "改一下"
└── Run 3  → "再优化"
```

### Cron Jobs

定时任务，定期触发 Agent 执行。

---

## 架构全景

```
┌──────────────────────────────────────────────────────────────────────┐
│                         LangGraph Agent Server                            │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│    ┌────────────┐         ┌─────────────┐         ┌─────────────┐  │
│    │   User    │         │ API Server  │         │   Redis     │  │
│    │  Client   │         │   (HTTP)    │         │ (Task Queue)│  │
│    └─────┬─────┘         └──────┬──────┘         └──────┬──────┘  │
│          │                       │                        │           │
│          │ POST /runs           │ enqueue               │           │
│          │─────────────────────►│──────────────────────►│           │
│          │                       │                        │           │
│          │◄──────────────────────│                        │           │
│          │ SSE Stream            │                        │           │
│          │                       │                        │           │
│    ┌─────┴─────┐         ┌──────┴──────┐         ┌──────┴──────┐  │
│    │   User    │         │Queue Worker  │◄────────│   Redis     │  │
│    │  (SSE)   │         │ (执行 Graph) │  dequeue │ (Pub/Sub)  │  │
│    └───────────┘         └──────┬──────┘         └─────────────┘  │
│                                 │                                    │
│                                 │ 读写                               │
│                                 ▼                                    │
│                          ┌─────────────┐                            │
│                          │ PostgreSQL  │                            │
│                          │ (持久化)    │                            │
│                          └─────────────┘                            │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. API Server

**职责：**
- 接收 HTTP 请求（创建 Run、读取状态、流式传输）
- **不执行 Agent 代码**
- 创建任务到 Queue
- 订阅 Redis Pub/Sub，转发 SSE 给用户

**类比：**
```
API Server = 餐厅前台
            接收订单、记录订单、不做饭
            把订单发到后厨（Queue）
            菜做好了端出来（SSE）
```

### 2. Queue Worker

**职责：**
- 从 Task Queue 消费任务
- 执行 Graph 代码
- 写 Checkpoints 到 PostgreSQL
- 通过 Redis Pub/Sub 发布执行事件

**类比：**
```
Queue Worker = 餐厅后厨
               真正炒菜的
               炒完一道出一道
```

### 3. Task Queue (Redis)

**职责：**
- 持久化任务（Run）
- 分发任务给 Worker
- 支持 Cancel / Priority

**注意：**
> Redis 只存**临时数据**（任务状态），不存用户数据
> 用户数据和 Run 数据都在 PostgreSQL

### 4. PostgreSQL

**持久化三件套：**

| 数据类型 | 说明 |
|---------|------|
| **Core 资源** | Assistants、Threads、Runs、Cron Jobs |
| **Checkpoints** | Graph 执行状态的快照（短时记忆） |
| **Store** | 跨线程的长期记忆（长时记忆） |

---

## 执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│                      Run 执行生命周期                              │
└─────────────────────────────────────────────────────────────────┘

1. 创建 Run
   User ──► API Server: POST /runs
            │
            ▼
2. 入队
   API Server ──► Redis: enqueue(task)
   API Server ──► PostgreSQL: 创建 pending run
            │
            ▼
3. 消费任务
   Queue Worker ──► Redis: dequeue
   Queue Worker ──► PostgreSQL: 拿 checkpoint（如有）
            │
            ▼
4. 执行 Graph
   Queue Worker ──► 执行 Graph 代码
   Queue Worker ──► 写 checkpoint 到 PostgreSQL
   Queue Worker ──► 发布事件到 Redis Pub/Sub
            │
            ▼
5. SSE 推送
   API Server ──► 订阅 Redis Pub/Sub
   API Server ──► SSE ──► User
            │
            ▼
6. 完成
   Queue Worker ──► PostgreSQL: 更新 run status
   Queue Worker ──► 释放 slot，处理下一个任务
```

**关键点：**
- 每个 Worker 可以同时执行 N 个 Run（`N_JOBS_PER_WORKER`，默认 10）
- 同一 Thread 同时只能有一个 Run 在执行（Queue 强制）
- Worker 崩溃可从最近 Checkpoint 恢复

---

## 部署模式

### 1. Single Host（开发用）

```
┌─────────────────────────────┐
│      单进程运行              │
│                             │
│  ┌─────────┐  ┌─────────┐  │
│  │API Server│ + │Queue    │  │
│  │         │  │ Worker  │  │
│  └─────────┘  └─────────┘  │
│         共享进程              │
└─────────────────────────────┘
```

### 2. Split API and Queue（生产用）

```
┌──────────────┐      ┌──────────────┐
│  API Server  │      │Queue Workers│
│   (多实例)    │      │  (多实例)    │
└──────┬───────┘      └──────┬───────┘
       │                     │
       │              ┌──────┴───────┐
       │              │   Redis      │
       │              │  Task Queue  │
       │              └──────┬───────┘
       │                     │
       │              ┌──────┴───────┐
       └──────────────►│  PostgreSQL  │
                       └──────────────┘
```

**扩展思路：**
- API Server 根据请求量扩展
- Queue Worker 根据 pending run 数量扩展
- 两者独立扩展，互不影响

### 3. Distributed Runtime（大规模）

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│   ┌──────────┐        ┌──────────┐                 │
│   │Orchestra │        │ Execution │                 │
│   │tion Pool │        │   Pool   │                 │
│   └────┬─────┘        └────┬─────┘                 │
│        │                    │                       │
│        └────────┬───────────┘                       │
│                 │                                    │
│          ┌──────┴──────┐                          │
│          │    Redis     │                          │
│          └─────────────┘                          │
│                                                     │
└─────────────────────────────────────────────────────┘
```

- **Orchestration Pool**：负责任务调度
- **Execution Pool**：负责真正执行

---

## SSE 流式传输

```
User ──► API Server: GET /runs/stream
         │
         ▼
API Server ──► Redis Pub/Sub: 订阅 channel
         │
         ▼
Queue Worker ──► Redis Pub/Sub: 发布事件
         │
         ▼
API Server ◄── Redis Pub/Sub: 收到事件
         │
         ▼
API Server ──► User: SSE
```

**支持的功能：**
- 实时推送每个 token
- 支持断线重连（`Last-Event-ID`）
- Human-in-the-loop（中断 + 恢复）

---

## 持久化设计

### Checkpoint（短时记忆）

```
Graph 执行每步 ──► 写 checkpoint ──► PostgreSQL
                │
                └── 崩溃恢复时从最近 checkpoint 恢复
```

**Durability Mode：**
- `async`（默认）：每步都写
- `exit`：只写最终状态

### Store（长时记忆）

跨线程共享的数据，例如：
- 用户偏好
- 知识库
- 长期上下文

---

## 组件交互总结

```
                    ┌─────────────────────────────────────┐
                    │              User                  │
                    └───────────────┬───────────────────┘
                                    │
                                    │ HTTP / SSE
                                    ▼
                    ┌─────────────────────────────────────┐
                    │           API Server                │
                    │                                     │
                    │  • 接收请求                          │
                    │  • 创建 Run                         │
                    │  • SSE 转发                         │
                    │  • 不执行 Agent                     │
                    └───────────────┬─────────────────────┘
                                    │
                    ┌────────────────┼────────────────────┐
                    │                │                     │
                    ▼                ▼                     ▼
         ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
         │    Redis     │   │  PostgreSQL  │   │Queue Workers │
         │              │   │              │   │              │
         │ • Task Queue │   │ • Runs       │   │ • 执行 Graph │
         │ • Pub/Sub   │   │ • Checkpoints│   │ • 写 Checkpoint
         │              │   │ • Store     │   │ • 发事件    │
         └──────────────┘   └──────────────┘   └──────────────┘
```

---

## 一句话总结

> **Agent Server = API Server（接请求）+ Queue Worker（执行）+ Task Queue（Redis 任务分发）+ PostgreSQL（持久化）**
>
> 核心思路：**解耦** —— API 只管接收和返回，真正执行由独立 Worker 完成，任务通过 Queue 分发，状态通过 PostgreSQL 持久化。

---

## 核心心智模型

### 1. API 和执行分离

```
API Server = 前台（接单、记录、端菜）
Queue Worker = 后厨（炒菜）
```

### 2. Task Queue 是核心

```
没有 Task Queue = 无法横向扩展
Task Queue = 任务缓冲 + 负载均衡 + 故障恢复
```

### 3. Redis 不存数据，只做事

```
Redis = 任务队列 + Pub/Sub 信道
PostgreSQL = 真实数据（Runs、Checkpoints、Store）
```

### 4. Checkpoint = 断点续传

```
每次执行 ──► 写 checkpoint
崩溃恢复 ──► 从最近 checkpoint 继续
不用从头开始
```

### 5. 多 Worker 并行，单 Thread 串行

```
N 个 Worker ──► 并行处理 N 个 Run
同一 Thread ──► 同时只能有 1 个 Run 在跑
```
