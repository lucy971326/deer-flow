# DeerFlow Install

本文档面向 coding agents。如果 DeerFlow 仓库尚未克隆并打开，请先克隆 `https://github.com/bytedance/deer-flow.git`，然后从仓库根目录继续。

## 目标

在用户本地机器上以最低风险的方式引导（bootstrap）一个 DeerFlow local development workspace。

默认优先级：

1. Docker development environment
2. Local development environment

不要假设 API keys 或 model credentials 已存在。安全地准备好一切前置条件后停止，并向用户简洁总结仍需提供的内容。

## 操作规则

- Be idempotent. 重复执行本文档不应破坏已有配置。
- 优先使用仓库现有命令，而非临时 shell 命令。
- 未经用户明确授权，不得使用 `sudo` 或安装系统包。
- 除非用户要求，否则不要覆盖已有用户配置值。
- 如果某步骤失败，停止，解释阻塞点，并提供最小化的下一步操作。
- 如果存在多条设置路径，在 Docker 可用时优先选择 Docker。

## 成功标准

满足以下全部条件时视为设置成功：

- DeerFlow 仓库已克隆，且当前工作目录为仓库根目录。
- `config.yaml` 存在。
- Docker setup：`make docker-init` 执行成功，Docker prerequisites 已准备就绪，但不假设服务已在运行。
- Local setup：`make check` 通过或报告无缺失 prerequisites，`make install` 执行成功。
- 用户收到启动 DeerFlow 的精确下一条命令。
- 用户同时收到 `config.yaml` 中缺失的 model 配置项或引用的环境变量名，但不检查包含 secret 的文件中的实际值。

## 步骤

- 如果当前目录不是 DeerFlow 仓库根目录，按需克隆 `https://github.com/bytedance/deer-flow.git`，然后切换到仓库根目录。
- 通过检查 `Makefile`、`backend/`、`frontend/` 和 `config.example.yaml` 是否存在来确认当前目录是 DeerFlow 仓库根目录。
- 检测 `config.yaml` 是否已存在。
- 如果 `config.yaml` 不存在，运行 `make config`。
- 检测 Docker 是否可用且 daemon 可通过 `docker info` 访问。
- 如果 Docker 可用：
  - 运行 `make docker-init`。
  - 将此视为 Docker prerequisite preparation。仅此而已，不要声称 app services、compose validation 或 image builds 已成功。
  - 除非用户明确要求或此设置请求明确包含 launch verification，否则不要启动 long-running services。
  - 告知用户推荐的下一条命令是 `make docker-start`。
- 如果 Docker 不可用：
  - 运行 `make check`。
  - 如果 `make check` 报告缺失系统依赖（如 `node`、`pnpm`、`uv` 或 `nginx`），停止并报告缺失的工具，不尝试 privileged installs。
  - 如果 prerequisites 满足，运行 `make install`。
  - 告知用户推荐的下一条命令是 `make dev`。
- 仅检查 `config.yaml` 中缺失的 model 条目或引用的环境变量占位符。不要读取 `.env`、`frontend/.env` 或其他包含 secret 的文件。
- 如果未配置任何 model，告知用户必须在 `config.yaml` 的 `models` 下至少添加一个条目。
- 如果 `config.yaml` 引用了类似 `$OPENAI_API_KEY` 的变量，告知用户哪些变量名仍需真实值，但不通过打开包含 secret 的文件来验证。
- 如果仓库看起来已经配置好，除非必要验证环境，否则不要重复耗时工作。

## 验证

使用与所选设置路径相匹配的最轻量级验证方式。

Docker setup：

- 确认 `make docker-init` 执行成功。
- 确认 `config.yaml` 存在。
- 明确说明 Docker services 未启动，`make docker-start` 仍是第一个真正的启动步骤。
- 除非用户要求，否则不要让 background services 保持运行。

Local setup：

- 确认 `make install` 执行成功。
- 确认 `config.yaml` 存在。
- 除非用户要求，否则不要让 background services 保持运行。

## 最终响应格式

返回简短状态报告，包含：

1. 使用的设置路径：Docker 或 local
2. 达到的设置级别：Docker prerequisites prepared 或 local dependencies installed
3. 创建或检测到的文件：例如 `config.yaml`
4. 剩余用户操作：model config、env var values、auth files 或 nothing
5. 启动 DeerFlow 的精确下一条命令

## 立即执行

完成上述步骤。完成后在设置边界处停止并报告状态，不要继续进入无关的项目工作。