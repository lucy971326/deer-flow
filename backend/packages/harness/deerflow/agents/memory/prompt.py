"""Prompt templates for memory update and injection."""

import math
import re
from typing import Any

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

# Prompt template for updating memory based on conversation
MEMORY_UPDATE_PROMPT = """你是一个 Memory 管理系统的角色任务是对对话进行分析并更新用户 Memory Profile。

当前 Memory 状态:
<current_memory>
{current_memory}
</current_memory>

新对话内容:
<conversation>
{conversation}
</conversation>

操作指南:
1. 分析对话中关于用户的重要信息
2. 提取相关的事实、偏好和上下文，包含具体细节（数字、名称、技术）
3. 按照以下详细的长度指南更新 Memory sections

在提取事实之前，先对对话进行结构化反思：
1. Error/Retry 检测: Agent 是否遇到了错误、需要重试或产生了错误结果？
   如果是，请将根本原因和正确方法记录为高置信度事实，类别为 "correction"。
2. User Correction 检测: 用户是否纠正了 Agent 的方向、理解或输出？
   如果是，请将正确的理解或方法记录为高置信度事实，类别为 "correction"。
   仅当类别为 "correction" 且错误在对话中明确时，才在 "sourceError" 中包含错误内容。
3. Project Constraint 发现: 对话中是否发现了项目特定的约束？
   如果是，请以最合适的类别和置信度将它们记录为事实。

{correction_hint}

Memory Section 指南:

**User Context**（当前状态 - 简洁摘要）:
- workContext: 专业角色、公司、关键项目、主要技术（2-3 句话）
  示例: 核心贡献者、项目名称及指标（16k+ stars）、技术栈
- personalContext: 语言、沟通偏好、关键兴趣（1-2 句话）
  示例: 双语能力、特定兴趣领域、专业领域
- topOfMind: 多个进行中的关注领域和优先级（3-5 句话，详细段落）
  示例: 主要项目工作、并行技术调查、持续学习/追踪
  包含: 活跃的实施工作、问题排查、市场/研究兴趣
  注意: 这捕捉的是多个并发关注领域，而非单一任务

**History**（时序上下文 - 详细段落）:
- recentMonths: 近期活动的详细摘要（4-6 句话或 1-2 段）
  时间线: 最近 1-3 个月的交互
  包含: 探索的技术、从事的项目、解决的问题、展示的兴趣
- earlierContext: 重要的历史模式（3-5 句话或 1 段）
  时间线: 3-12 个月前
  包含: 过去的项目、学习历程、已建立的模式
- longTermBackground: 持久背景和基础上下文（2-4 句话）
  时间线: 整体/基础信息
  包含: 核心专业知识、长期兴趣、基本工作风格

**Facts 提取**:
- 提取具体的、可量化的细节（例如："16k+ GitHub stars"、"200+ datasets"）
- 包含专有名词（公司名称、项目名称、技术名称）
- 保留技术术语和版本号
- 类别:
  * preference: 用户偏好/厌恶的工具、风格、方法
  * knowledge: 特定专业知识、掌握的技术、领域知识
  * context: 背景事实（职位、项目、地点、语言）
  * behavior: 工作模式、沟通习惯、问题解决方法
  * goal: 陈述的目标、学习目标、项目愿景
  * correction: 明确的 Agent 错误或用户纠正，包括正确方法
- 置信度级别:
  * 0.9-1.0: 明确陈述的事实（"我从事 X"、"我的角色是 Y"）
  * 0.7-0.8: 从行动/讨论中强烈暗示
  * 0.5-0.6: 推断的模式（谨慎使用，仅用于明确的模式）

**分配到哪个 Section**:
- workContext: 当前工作、活跃项目、主要技术栈
- personalContext: 语言、个性、直接工作任务外的兴趣
- topOfMind: 用户最近关心的多个进行中的优先级和关注领域（更新最频繁）
  应捕捉 3-5 个并发主题: 主要工作、边栏探索、学习/追踪兴趣
- recentMonths: 近期技术探索和工作的详细描述
- earlierContext: 稍早的仍相关的交互模式
- longTermBackground: 用户不变的基础事实

**多语言内容**:
- 保留专有名词和公司名称的原始语言
- 保持技术术语的原始形式（DeepSeek, LangGraph 等）
- 在 personalContext 中注明语言能力

输出格式 (JSON):
{{
  "user": {{
    "workContext": {{ "summary": "...", "shouldUpdate": true/false }},
    "personalContext": {{ "summary": "...", "shouldUpdate": true/false }},
    "topOfMind": {{ "summary": "...", "shouldUpdate": true/false }}
  }},
  "history": {{
    "recentMonths": {{ "summary": "...", "shouldUpdate": true/false }},
    "earlierContext": {{ "summary": "...", "shouldUpdate": true/false }},
    "longTermBackground": {{ "summary": "...", "shouldUpdate": true/false }}
  }},
  "newFacts": [
    {{ "content": "...", "category": "preference|knowledge|context|behavior|goal|correction", "confidence": 0.0-1.0 }}
  ],
  "factsToRemove": ["fact_id_1", "fact_id_2"]
}}

重要规则:
- 仅当有有意义的新信息时才设置 shouldUpdate=true
- 遵循长度指南: workContext/personalContext 应简洁（1-3 句话），topOfMind 和 history sections 应详细（段落）
- 在 facts 中包含具体指标、版本号和专有名词
- 仅添加明确陈述（0.9+）或强烈暗示（0.7+）的事实
- 对明确的 Agent 错误或用户纠正使用类别 "correction"；当纠正明确时分配置信度 >= 0.95
- 仅当先前的错误或错误方法在对话中明确时才包含 "sourceError"；否则省略
- 删除被新信息矛盾的事实
- 更新 topOfMind 时，集成新的关注领域同时删除已完成/放弃的
  保持 3-5 个仍活跃且相关的并发关注主题
- 对于 history sections，将新信息按时间顺序集成到适当的时间段
- 保持技术准确性 - 保留技术、公司、项目的准确名称
- 专注于对未来交互和个人化有用的信息
- 重要: 不要在 memory 中记录文件上传事件。上传的文件是会话特定的和临时的 — 它们在未来的会话中不可访问。
  记录上传事件会导致后续对话中的混淆。

只返回有效的 JSON，不需要解释或 markdown。"""


# Prompt template for extracting facts from a single message
FACT_EXTRACTION_PROMPT = """从这条消息中提取关于用户的事实信息。

消息:
{message}

按以下 JSON 格式提取事实:
{{
  "facts": [
    {{ "content": "...", "category": "preference|knowledge|context|behavior|goal|correction", "confidence": 0.0-1.0 }}
  ]
}}

类别:
- preference: 用户偏好（喜欢/厌恶、风格、工具）
- knowledge: 用户的专业知识或知识领域
- context: 背景上下文（地点、工作、项目）
- behavior: 行为模式
- goal: 用户的目標或目的
- correction: 明确的纠正或需要避免的错误

规则:
- 只提取明确、具体的事实
- 置信度应反映确定性（明确陈述 = 0.9+，暗示 = 0.6-0.8）
- 跳过模糊或临时信息

只返回有效的 JSON。"""


def _count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens in text using tiktoken.

    Args:
        text: The text to count tokens for.
        encoding_name: The encoding to use (default: cl100k_base for GPT-4/3.5).

    Returns:
        The number of tokens in the text.
    """
    if not TIKTOKEN_AVAILABLE:
        # Fallback to character-based estimation if tiktoken is not available
        return len(text) // 4

    try:
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text))
    except Exception:
        # Fallback to character-based estimation on error
        return len(text) // 4


def _coerce_confidence(value: Any, default: float = 0.0) -> float:
    """Coerce a confidence-like value to a bounded float in [0, 1].

    Non-finite values (NaN, inf, -inf) are treated as invalid and fall back
    to the default before clamping, preventing them from dominating ranking.
    The ``default`` parameter is assumed to be a finite value.
    """
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return max(0.0, min(1.0, default))
    if not math.isfinite(confidence):
        return max(0.0, min(1.0, default))
    return max(0.0, min(1.0, confidence))


def format_memory_for_injection(memory_data: dict[str, Any], max_tokens: int = 2000) -> str:
    """Format memory data for injection into system prompt.

    Args:
        memory_data: The memory data dictionary.
        max_tokens: Maximum tokens to use (counted via tiktoken for accuracy).

    Returns:
        Formatted memory string for system prompt injection.
    """
    if not memory_data:
        return ""

    sections = []

    # Format user context
    user_data = memory_data.get("user", {})
    if user_data:
        user_sections = []

        work_ctx = user_data.get("workContext", {})
        if work_ctx.get("summary"):
            user_sections.append(f"Work: {work_ctx['summary']}")

        personal_ctx = user_data.get("personalContext", {})
        if personal_ctx.get("summary"):
            user_sections.append(f"Personal: {personal_ctx['summary']}")

        top_of_mind = user_data.get("topOfMind", {})
        if top_of_mind.get("summary"):
            user_sections.append(f"Current Focus: {top_of_mind['summary']}")

        if user_sections:
            sections.append("User Context:\n" + "\n".join(f"- {s}" for s in user_sections))

    # Format history
    history_data = memory_data.get("history", {})
    if history_data:
        history_sections = []

        recent = history_data.get("recentMonths", {})
        if recent.get("summary"):
            history_sections.append(f"Recent: {recent['summary']}")

        earlier = history_data.get("earlierContext", {})
        if earlier.get("summary"):
            history_sections.append(f"Earlier: {earlier['summary']}")

        background = history_data.get("longTermBackground", {})
        if background.get("summary"):
            history_sections.append(f"Background: {background['summary']}")

        if history_sections:
            sections.append("History:\n" + "\n".join(f"- {s}" for s in history_sections))

    # Format facts (sorted by confidence; include as many as token budget allows)
    facts_data = memory_data.get("facts", [])
    if isinstance(facts_data, list) and facts_data:
        ranked_facts = sorted(
            (f for f in facts_data if isinstance(f, dict) and isinstance(f.get("content"), str) and f.get("content").strip()),
            key=lambda fact: _coerce_confidence(fact.get("confidence"), default=0.0),
            reverse=True,
        )

        # Compute token count for existing sections once, then account
        # incrementally for each fact line to avoid full-string re-tokenization.
        base_text = "\n\n".join(sections)
        base_tokens = _count_tokens(base_text) if base_text else 0
        # Account for the separator between existing sections and the facts section.
        facts_header = "Facts:\n"
        separator_tokens = _count_tokens("\n\n" + facts_header) if base_text else _count_tokens(facts_header)
        running_tokens = base_tokens + separator_tokens

        fact_lines: list[str] = []
        for fact in ranked_facts:
            content_value = fact.get("content")
            if not isinstance(content_value, str):
                continue
            content = content_value.strip()
            if not content:
                continue
            category = str(fact.get("category", "context")).strip() or "context"
            confidence = _coerce_confidence(fact.get("confidence"), default=0.0)
            source_error = fact.get("sourceError")
            if category == "correction" and isinstance(source_error, str) and source_error.strip():
                line = f"- [{category} | {confidence:.2f}] {content} (avoid: {source_error.strip()})"
            else:
                line = f"- [{category} | {confidence:.2f}] {content}"

            # Each additional line is preceded by a newline (except the first).
            line_text = ("\n" + line) if fact_lines else line
            line_tokens = _count_tokens(line_text)

            if running_tokens + line_tokens <= max_tokens:
                fact_lines.append(line)
                running_tokens += line_tokens
            else:
                break

        if fact_lines:
            sections.append("Facts:\n" + "\n".join(fact_lines))

    if not sections:
        return ""

    result = "\n\n".join(sections)

    # Use accurate token counting with tiktoken
    token_count = _count_tokens(result)
    if token_count > max_tokens:
        # Truncate to fit within token limit
        # Estimate characters to remove based on token ratio
        char_per_token = len(result) / token_count
        target_chars = int(max_tokens * char_per_token * 0.95)  # 95% to leave margin
        result = result[:target_chars] + "\n..."

    return result


def format_conversation_for_update(messages: list[Any]) -> str:
    """Format conversation messages for memory update prompt.

    Args:
        messages: List of conversation messages.

    Returns:
        Formatted conversation string.
    """
    lines = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", str(msg))

        # Handle content that might be a list (multimodal)
        if isinstance(content, list):
            text_parts = []
            for p in content:
                if isinstance(p, str):
                    text_parts.append(p)
                elif isinstance(p, dict):
                    text_val = p.get("text")
                    if isinstance(text_val, str):
                        text_parts.append(text_val)
            content = " ".join(text_parts) if text_parts else str(content)

        # Strip uploaded_files tags from human messages to avoid persisting
        # ephemeral file path info into long-term memory.  Skip the turn entirely
        # when nothing remains after stripping (upload-only message).
        if role == "human":
            content = re.sub(r"<uploaded_files>[\s\S]*?</uploaded_files>\n*", "", str(content)).strip()
            if not content:
                continue

        # Truncate very long messages
        if len(str(content)) > 1000:
            content = str(content)[:1000] + "..."

        if role == "human":
            lines.append(f"User: {content}")
        elif role == "ai":
            lines.append(f"Assistant: {content}")

    return "\n\n".join(lines)
