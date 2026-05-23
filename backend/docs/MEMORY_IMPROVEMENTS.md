# Memory System Improvements

本文档跟踪 memory 注入行为和路线图状态。

## 状态（截至 2026-03-10）

已在 `main` 中实现：
- 通过 `tiktoken` 在 `format_memory_for_injection` 中进行精确 token 计数。
- Facts 被注入到 prompt memory context。
- Facts 按 confidence 排序（降序）。
- 注入尊重 `max_injection_tokens` 预算。

已计划/尚未合并：
- 基于 TF-IDF 相似性的 fact 检索。
- 用于上下文感知评分的 `current_context` 输入。
- 可配置的相似度/ confidence 权重（`similarity_weight`、`confidence_weight`）。
- 每次模型调用前用于上下文感知检索的 middleware/runtime 连接。

## 当前行为

今天的函数：

```python
def format_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
```

当前注入格式：
- 来自 `user.*.summary` 的 `User Context` 部分
- 来自 `history.*.summary` 的 `History` 部分
- 来自 `facts[]` 的 `Facts` 部分，按 confidence 排序，在达到 token 预算前追加

Token 计数：
- 可用时使用 `tiktoken`（`cl100k_base`）
- 如果 tokenizer 导入失败则回退到 `len(text) // 4`

## 已知差距

之前版本的本文档将 TF-IDF/上下文感知检索描述为已发货。
这对于 `main` 不准确并造成了混淆。

Issue 引用：`#1059`

## 路线图（已计划）

计划的评分策略：

```text
final_score = (similarity * 0.6) + (confidence * 0.4)
```

计划的集成形式：
1. 从过滤后的 user/final-assistant turns 中提取最近对话上下文。
2. 计算每个 fact 与当前上下文的 TF-IDF cosine 相似度。
3. 按加权分数排名并在 token 预算下注入。
4. 如果上下文不可用则回退到仅 confidence 排名。

## 验证

当前回归覆盖包括：
- facts 包含在 memory 注入输出中
- confidence 排序
- token-budget-limited fact 包含

测试：
- `backend/tests/test_memory_prompt_injection.py`