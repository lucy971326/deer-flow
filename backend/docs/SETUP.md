# 快速上手指南

DeerFlow 快速上手说明。

## 配置

DeerFlow 使用 YAML 配置文件，应放置在**项目根目录**。

### 步骤

1. **进入项目根目录**：
   ```bash
   cd /path/to/deer-flow
   ```

2. **复制示例配置**：
   ```bash
   cp config.example.yaml config.yaml
   ```

3. **编辑配置**：
   ```bash
   # 选项 A：设置环境变量（推荐）
   export OPENAI_API_KEY="your-key-here"

   # 可选：当从其他目录运行时固定项目根目录
   export DEER_FLOW_PROJECT_ROOT="/path/to/deer-flow"

   # 选项 B：直接编辑 config.yaml
   vim config.yaml  # 或你喜欢的编辑器
   ```

4. **验证配置**：
   ```bash
   cd backend
   python -c "from deerflow.config import get_app_config; print('✓ Config loaded:', get_app_config().models[0].name)"
   ```

## 重要说明

- **位置**：`config.yaml` 应在 `deer-flow/`（项目根目录）
- **Git**：`config.yaml` 自动被 git 忽略（包含 secrets）
- **运行时根目录**：如果 DeerFlow 可能从项目根外启动，设置 `DEER_FLOW_PROJECT_ROOT`
- **运行时数据**：状态默认为项目根目录下的 `.deer-flow`；设置 `DEER_FLOW_HOME` 可以移动它
- **Skills**：Skills 默认为项目根目录下的 `skills/`；设置 `DEER_FLOW_SKILLS_PATH` 或 `skills.path` 可以移动它们

## 配置文件位置

后端按此顺序搜索 `config.yaml`：

1. 代码中的显式 `config_path` 参数
2. `DEER_FLOW_CONFIG_PATH` 环境变量（如果设置）
3. `DEER_FLOW_PROJECT_ROOT` 下的 `config.yaml`，或当 `DEER_FLOW_PROJECT_ROOT` 未设置时为当前工作目录
4. Legacy backend/repository-root locations 用于 monorepo 兼容性

**推荐**：将 `config.yaml` 放在项目根目录（`deer-flow/config.yaml`）。

## Sandbox 设置（可选但推荐）

如果你计划使用 Docker/容器化 sandbox（在 `config.yaml` 中配置为 `sandbox.use: deerflow.community.aio_sandbox:AioSandboxProvider`），强烈建议预拉取容器镜像：

```bash
# 从项目根目录
make setup-sandbox
```

**为什么预拉取？**
- sandbox 镜像（~500MB+）在首次使用时拉取，会导致长时间等待
- 预拉取提供清晰的进度指示
- 避免首次使用 agent 时产生困惑

如果你跳过此步骤，镜像将在首次 agent 执行时自动拉取，这可能需要几分钟（取决于网络速度）。

## 故障排查

### 配置文件未找到

```bash
# 检查后端查找的位置
cd deer-flow/backend
python -c "from deerflow.config.app_config import AppConfig; print(AppConfig.resolve_config_path())"
```

如果找不到配置：
1. 确保已将 `config.example.yaml` 复制到 `config.yaml`
2. 验证你在项目根目录，或设置 `DEER_FLOW_PROJECT_ROOT`
3. 检查文件是否存在：`ls -la config.yaml`

### 权限被拒绝

```bash
chmod 600 ../config.yaml  # 保护敏感配置
```

## 另见

- [配置指南](CONFIGURATION.md) - 详细配置选项
- [架构概述](../CLAUDE.md) - 系统架构