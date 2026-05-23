# Memory Settings 评审指南

本文档帮助你在本地用最少的步骤评审 Memory Settings 的新增/编辑流程。

## 快速评审

1. 用你熟悉的开发方式启动 DeerFlow。

   示例：

   ```bash
   make dev
   ```

   或：

   ```bash
   make docker-start
   ```

   如果已经跑着 DeerFlow，直接复用现有环境。

2. 加载示例 memory fixture：

   ```bash
   python scripts/load_memory_sample.py
   ```

3. 打开 `Settings > Memory`。

   本地默认 URL：
   - App：`http://localhost:2026`
   - 纯前端 fallback：`http://localhost:3000`

## 最小化手动测试

1. 点击 `Add fact`。
2. 创建新 fact，字段：
   - Content：`Reviewer-added memory fact`
   - Category：`testing`
   - Confidence：`0.88`
3. 确认新 fact 立即出现，且 source 显示为 `Manual`。
4. 编辑示例 fact `This sample fact is intended for edit testing.`，改为：
   - Content：`This sample fact was edited during manual review.`
   - Category：`testing`
   - Confidence：`0.91`
5. 确认编辑后的 fact 立即更新。
6. 刷新页面，确认新增 fact 和编辑的 fact 仍持续存在。

## 可选检查项

- 搜索 `Reviewer-added`，确认新 fact 被匹配到。
- 搜索 `workflow`，确认 category 文本可搜索。
- 切换 `All`、`Facts`、`Summaries` 视图。
- 删除Disposable 示例 fact `Delete fact testing can target this disposable sample entry.`，确认列表立即更新。
- 清空所有 memory，确认页面进入空状态。

## Fixture 文件

- 示例 fixture：`backend/docs/memory-settings-sample.json`
- 本地默认运行时目标：`backend/.deer-flow/memory.json`

Loader 脚本在覆盖现有运行时 memory 文件前会自动创建带时间戳的备份。