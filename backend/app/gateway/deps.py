"""app.state 单例对象的集中访问器。

【单例创建】langgraph_runtime() 在启动时创建 9 个 app.state 单例

【单例访问】通过 get_xxx() 函数访问，缺失则 503

【配置热重载】
- AppConfig：不缓存，每次请求读文件（mtime 检测）
- 其他单例：绑定 startup_config，修改 config.yaml 需要重启才生效

初始化在 app.py 的 lifespan() 里调用。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, TypeVar, cast

from fastapi import FastAPI, HTTPException, Request
from langgraph.types import Checkpointer

from deerflow.config.app_config import AppConfig, get_app_config
from deerflow.persistence.feedback import FeedbackRepository
from deerflow.runtime import RunContext, RunManager, StreamBridge
from deerflow.runtime.events.store.base import RunEventStore
from deerflow.runtime.runs.store.base import RunStore

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.gateway.auth.local_provider import LocalAuthProvider
    from app.gateway.auth.repositories.sqlite import SQLiteUserRepository
    from deerflow.persistence.thread_meta.base import ThreadMetaStore


T = TypeVar("T")


def get_config() -> AppConfig:
    """返回当前请求最新的 AppConfig（热重载）。

    每次请求都重新读取 config.yaml，返回最新配置。
    失败返回 503。
    """
    try:
        return get_app_config()
    except Exception as exc:  # noqa: BLE001 - request boundary: log and degrade gracefully
        logger.exception("Failed to load AppConfig at request time")
        raise HTTPException(status_code=503, detail="Configuration not available") from exc


@asynccontextmanager
async def langgraph_runtime(app: FastAPI, startup_config: AppConfig) -> AsyncGenerator[None, None]:
    """启动和关闭所有 LangGraph 运行时单例。

    这个函数是「初始化 → yield → 清理」的上下文管理器。

    【启动阶段】创建 8 个 app.state 单例：
    - stream_bridge：SSE 流式传输
    - checkpointer：状态快照持久化
    - store：跨线程共享存储
    - run_store：Run 记录存储
    - feedback_repo：反馈存储
    - thread_store：Thread 元数据
    - run_event_store：Run 事件
    - run_manager：Run 管理器

    【运行阶段】yield，请求处理中

    【关闭阶段】统一清理所有连接

    设计原则：
    - 这些单例持有数据库连接，绑定到 startup_config 快照
    - 修改 config.yaml 后，单例不重建（需要重启）
    - 但 get_config() 每次请求读文件，获取最新配置

    ``app.py`` 用法::

        async with langgraph_runtime(app, startup_config):
            yield
    """
    from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
    from deerflow.runtime import make_store, make_stream_bridge
    from deerflow.runtime.checkpointer.async_provider import make_checkpointer
    from deerflow.runtime.events.store import make_run_event_store
    from deerflow.runtime.runs.store.memory import MemoryRunStore

    async with AsyncExitStack() as stack:
        config = startup_config

        # 1. StreamBridge — SSE 流式传输
        app.state.stream_bridge = await stack.enter_async_context(make_stream_bridge(config))

        # 2. Persistence engine — 数据库连接
        #    必须先于 checkpointer 初始化，让 postgres auto-create-database 先跑
        await init_engine_from_config(config.database)

        # 3. Checkpointer — 状态快照（对话历史持久化）
        app.state.checkpointer = await stack.enter_async_context(make_checkpointer(config))

        # 4. Store — 跨线程共享存储
        app.state.store = await stack.enter_async_context(make_store(config))

        # 5-6. Run Store & Feedback Repo — Run 记录和反馈
        from deerflow.persistence.feedback import FeedbackRepository
        from deerflow.persistence.run import RunRepository

        sf = get_session_factory()
        if sf is not None:
            app.state.run_store = RunRepository(sf)
            app.state.feedback_repo = FeedbackRepository(sf)
        else:
            # 无 SQL 时用内存（开发/测试模式）
            app.state.run_store = MemoryRunStore()
            app.state.feedback_repo = None

        # 7. Thread Store — Thread 元数据
        from deerflow.persistence.thread_meta import make_thread_store

        app.state.thread_store = make_thread_store(sf, app.state.store)

        # 8. Run Event Store & Config — 冻结配置，防止不一致
        run_events_config = getattr(config, "run_events", None)
        app.state.run_events_config = run_events_config  # ← 冻结快照
        app.state.run_event_store = make_run_event_store(run_events_config)

        # 9. Run Manager — Run 生命周期管理
        app.state.run_manager = RunManager(store=app.state.run_store)

        try:
            yield  # ← 请求处理中
        finally:
            await close_engine()  # ← 关闭所有连接


# ---------------------------------------------------------------------------
# Getters – called by routers per-request
# ---------------------------------------------------------------------------


def _require(attr: str, label: str) -> Callable[[Request], T]:
    """创建一个 FastAPI 依赖，返回 ``app.state.<attr>`` 或抛出 503。"""

    def dep(request: Request) -> T:
        val = getattr(request.app.state, attr, None)
        if val is None:
            raise HTTPException(status_code=503, detail=f"{label} not available")
        return cast(T, val)

    dep.__name__ = dep.__qualname__ = f"get_{attr}"
    return dep


get_stream_bridge: Callable[[Request], StreamBridge] = _require("stream_bridge", "Stream bridge")
get_run_manager: Callable[[Request], RunManager] = _require("run_manager", "Run manager")
get_checkpointer: Callable[[Request], Checkpointer] = _require("checkpointer", "Checkpointer")
get_run_event_store: Callable[[Request], RunEventStore] = _require("run_event_store", "Run event store")
get_feedback_repo: Callable[[Request], FeedbackRepository] = _require("feedback_repo", "Feedback")
get_run_store: Callable[[Request], RunStore] = _require("run_store", "Run store")


def get_store(request: Request):
    """Return the global store (may be ``None`` if not configured)."""
    return getattr(request.app.state, "store", None)


def get_thread_store(request: Request) -> ThreadMetaStore:
    """Return the thread metadata store (SQL or memory-backed)."""
    val = getattr(request.app.state, "thread_store", None)
    if val is None:
        raise HTTPException(status_code=503, detail="Thread metadata store not available")
    return val


def get_run_context(request: Request) -> RunContext:
    """从 app.state 单例构建 RunContext。

    app_config 是热重载的，其他是启动时冻结的。
    """
    return RunContext(
        checkpointer=get_checkpointer(request),
        store=get_store(request),
        event_store=get_run_event_store(request),
        run_events_config=getattr(request.app.state, "run_events_config", None),
        thread_store=get_thread_store(request),
        app_config=get_config(),
    )


# ---------------------------------------------------------------------------
# Auth helpers (used by authz.py and auth middleware)
# ---------------------------------------------------------------------------

# 缓存单例，避免每个请求都重新实例化
_cached_local_provider: LocalAuthProvider | None = None
_cached_repo: SQLiteUserRepository | None = None


def get_local_provider() -> LocalAuthProvider:
    """获取或创建缓存的 LocalAuthProvider 单例。

    必须在 ``init_engine_from_config()`` 之后调用——
    因为构造 user repository 需要共享的 session factory。
    """
    global _cached_local_provider, _cached_repo
    if _cached_repo is None:
        from app.gateway.auth.repositories.sqlite import SQLiteUserRepository
        from deerflow.persistence.engine import get_session_factory

        sf = get_session_factory()
        if sf is None:
            raise RuntimeError("get_local_provider() called before init_engine_from_config(); cannot access users table")
        _cached_repo = SQLiteUserRepository(sf)
    if _cached_local_provider is None:
        from app.gateway.auth.local_provider import LocalAuthProvider

        _cached_local_provider = LocalAuthProvider(repository=_cached_repo)
    return _cached_local_provider


async def get_current_user_from_request(request: Request):
    """从请求 cookie 获取当前已认证的用户。

    未认证则抛出 HTTPException 401。
    """
    from app.gateway.auth import decode_token
    from app.gateway.auth.errors import AuthErrorCode, AuthErrorResponse, TokenError, token_error_to_code

    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail=AuthErrorResponse(code=AuthErrorCode.NOT_AUTHENTICATED, message="Not authenticated").model_dump(),
        )

    payload = decode_token(access_token)
    if isinstance(payload, TokenError):
        raise HTTPException(
            status_code=401,
            detail=AuthErrorResponse(code=token_error_to_code(payload), message=f"Token error: {payload.value}").model_dump(),
        )

    provider = get_local_provider()
    user = await provider.get_user(payload.sub)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail=AuthErrorResponse(code=AuthErrorCode.USER_NOT_FOUND, message="User not found").model_dump(),
        )

    # Token 版本不匹配 → 密码已改，token 过期
    if user.token_version != payload.ver:
        raise HTTPException(
            status_code=401,
            detail=AuthErrorResponse(code=AuthErrorCode.TOKEN_INVALID, message="Token revoked (password changed)").model_dump(),
        )

    return user


async def get_optional_user_from_request(request: Request):
    """从请求获取可选的已认证用户。

    未认证返回 None。
    """
    try:
        return await get_current_user_from_request(request)
    except HTTPException:
        return None


async def get_current_user(request: Request) -> str | None:
    """从请求 cookie 提取 user_id，未认证返回 None。

    薄适配器，只返回字符串 id，供只需要用户标识的调用方使用
    （如 ``feedback.py``）。需要完整用户的调用方应使用
    ``get_current_user_from_request`` 或 ``get_optional_user_from_request``。
    """
    user = await get_optional_user_from_request(request)
    return str(user.id) if user else None
