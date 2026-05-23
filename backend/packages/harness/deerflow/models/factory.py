import logging

from langchain.chat_models import BaseChatModel

from deerflow.config import get_app_config
from deerflow.config.app_config import AppConfig
from deerflow.reflection import resolve_class
from deerflow.tracing import build_tracing_callbacks

logger = logging.getLogger(__name__)


def _deep_merge_dicts(base: dict | None, override: dict) -> dict:
    """递归合并两个字典，不修改输入。"""
    merged = dict(base or {})
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _enable_stream_usage_by_default(model_use_path: str, model_settings_from_config: dict) -> None:
    """为 OpenAI 兼容模型默认启用 stream usage，除非显式配置。

    LangChain 仅在未配置自定义 base URL 或 client 时为 OpenAI 模型自动启用
    ``stream_usage``。DeerFlow 频繁使用 OpenAI 兼容网关，否则 token 使用量
    跟踪将保持为空，TokenUsageMiddleware 将没有内容可记录。
    """
    if model_use_path != "langchain_openai:ChatOpenAI":
        return
    if "stream_usage" in model_settings_from_config:
        return
    if "base_url" in model_settings_from_config or "openai_api_base" in model_settings_from_config:
        model_settings_from_config["stream_usage"] = True


def create_chat_model(name: str | None = None, thinking_enabled: bool = False, *, app_config: AppConfig | None = None, attach_tracing: bool = True, **kwargs) -> BaseChatModel:
    """从配置创建 chat model 实例。

    Args:
        name: 要创建的模型名称。若为 None，则使用配置中的第一个模型。
        thinking_enabled: 支持时启用模型的扩展思考模式。
        app_config: 显式传入的 app config；省略时回退到缓存的全局配置。
        attach_tracing: 是否在 model 上附加 tracing callbacks（Langfuse、LangSmith）。

            - 默认 True：独立调用（不在 LangGraph run 内的代码，如 MemoryUpdater）使用。
              此时 model 自己会产生 trace，与 LangGraph trace 分开。

            - 必须传 False：graph root 已附加 tracing 后，graph 内部的调用
              （如 make_lead_agent 内部、TitleMiddleware）必须传 False，
              否则同一 LLM 调用会产生两个重复 span，且 session_id/user_id
              无法正确传播到 root trace。

    Returns:
        chat model 实例。
    """
    config = app_config or get_app_config()
    if name is None:
        name = config.models[0].name

    model_config = config.get_model_config(name)
    if model_config is None:
        raise ValueError(f"Model {name} not found in config") from None

    model_class = resolve_class(model_config.use, BaseChatModel)

    model_settings_from_config = model_config.model_dump(
        exclude_none=True,
        exclude={
            "use",
            "name",
            "display_name",
            "description",
            "supports_thinking",
            "supports_reasoning_effort",
            "when_thinking_enabled",
            "when_thinking_disabled",
            "thinking",
            "supports_vision",
        },
    )

    # 计算 effective when_thinking_enabled，合并 `thinking` 快捷字段。
    # `thinking` 快捷方式等价于设置 when_thinking_enabled["thinking"]。
    has_thinking_settings = (model_config.when_thinking_enabled is not None) or (model_config.thinking is not None)
    effective_wte: dict = dict(model_config.when_thinking_enabled) if model_config.when_thinking_enabled else {}
    if model_config.thinking is not None:
        merged_thinking = {**(effective_wte.get("thinking") or {}), **model_config.thinking}
        effective_wte = {**effective_wte, "thinking": merged_thinking}
    if thinking_enabled and has_thinking_settings:
        if not model_config.supports_thinking:
            raise ValueError(f"Model {name} does not support thinking. Set `supports_thinking` to true in the `config.yaml` to enable thinking.") from None
        if effective_wte:
            model_settings_from_config.update(effective_wte)
    if not thinking_enabled:
        if model_config.when_thinking_disabled is not None:
            # 用户提供的禁用设置优先
            model_settings_from_config.update(model_config.when_thinking_disabled)
        elif has_thinking_settings and effective_wte.get("extra_body", {}).get("thinking", {}).get("type"):
            # OpenAI 兼容网关：thinking 嵌套在 extra_body 下
            model_settings_from_config["extra_body"] = _deep_merge_dicts(
                model_settings_from_config.get("extra_body"),
                {"thinking": {"type": "disabled"}},
            )
            model_settings_from_config["reasoning_effort"] = "minimal"
        elif has_thinking_settings and effective_wte.get("thinking", {}).get("type"):
            # Native langchain_anthropic: thinking 是直接构造函数参数
            model_settings_from_config["thinking"] = {"type": "disabled"}
    if not model_config.supports_reasoning_effort:
        kwargs.pop("reasoning_effort", None)
        model_settings_from_config.pop("reasoning_effort", None)

    _enable_stream_usage_by_default(model_config.use, model_settings_from_config)

    # 对于 Codex Responses API 模型：将 thinking 模式映射到 reasoning_effort
    from deerflow.models.openai_codex_provider import CodexChatModel

    if issubclass(model_class, CodexChatModel):
        # ChatGPT Codex 端点当前拒绝 max_tokens/max_output_tokens。
        model_settings_from_config.pop("max_tokens", None)

        # 若前端提供了显式的 reasoning_effort 则使用（low/medium/high）
        explicit_effort = kwargs.pop("reasoning_effort", None)
        if not thinking_enabled:
            model_settings_from_config["reasoning_effort"] = "none"
        elif explicit_effort and explicit_effort in ("low", "medium", "high", "xhigh"):
            model_settings_from_config["reasoning_effort"] = explicit_effort
        elif "reasoning_effort" not in model_settings_from_config:
            model_settings_from_config["reasoning_effort"] = "medium"

    # 确保 stream_usage 已启用，以便在流式响应中获取 token 使用量元数据。
    # LangChain 的 BaseChatOpenAI 仅在未设置自定义 base_url/api_base 时才默认
    # stream_usage=True，因此访问第三方端点（如 doubao、deepseek）的模型会静默
    # 丢失 usage 数据。除非显式配置，否则我们默认将其设为 True。
    if "stream_usage" not in model_settings_from_config and "stream_usage" not in kwargs:
        if "stream_usage" in getattr(model_class, "model_fields", {}):
            model_settings_from_config["stream_usage"] = True

    model_instance = model_class(**kwargs, **model_settings_from_config)

    if attach_tracing:
        callbacks = build_tracing_callbacks()
        if callbacks:
            existing_callbacks = model_instance.callbacks or []
            model_instance.callbacks = [*existing_callbacks, *callbacks]
            logger.debug(f"Tracing attached to model '{name}' with providers={len(callbacks)}")
    return model_instance
