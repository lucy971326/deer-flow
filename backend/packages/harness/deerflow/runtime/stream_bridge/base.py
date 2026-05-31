"""StreamBridge 抽象协议。

StreamBridge 将 Agent Worker（生产者）与 SSE 端点（消费者）解耦，
对齐 LangGraph Platform 的 Queue + StreamManager 架构。
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    """单个流事件。

    Attributes:
        id: 递增的事件 ID（用于 SSE 的 ``id:`` 字段，支持 ``Last-Event-ID`` 断线重连）。
        event: SSE 事件名称，如 ``"metadata"``、``"updates"``、``"events"``、``"error"``、``"end"``。
        data: JSON 可序列化的负载。
    """

    id: str
    event: str
    data: Any


HEARTBEAT_SENTINEL = StreamEvent(id="", event="__heartbeat__", data=None)
END_SENTINEL = StreamEvent(id="", event="__end__", data=None)


class StreamBridge(abc.ABC):
    """StreamBridge 抽象基类。"""

    @abc.abstractmethod
    async def publish(self, run_id: str, event: str, data: Any) -> None:
        """将单个事件加入 *run_id* 的队列（生产者端）。"""

    @abc.abstractmethod
    async def publish_end(self, run_id: str) -> None:
        """通知不再会有更多事件发往 *run_id*。"""

    @abc.abstractmethod
    def subscribe(
        self,
        run_id: str,
        *,
        last_event_id: str | None = None,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[StreamEvent]:
        """异步迭代器，逐个产出 *run_id* 的事件（消费者端）。

        若超过 *heartbeat_interval* 秒无新事件，产出 :data:`HEARTBEAT_SENTINEL`。
        当生产者调用 :meth:`publish_end` 时，产出 :data:`END_SENTINEL`。
        """

    @abc.abstractmethod
    async def cleanup(self, run_id: str, *, delay: float = 0) -> None:
        """释放与 *run_id* 关联的资源。

        若 *delay* > 0，实现应等待一段时间后再释放，
        以便迟到的订阅者有机会获取剩余事件。
        """

    async def close(self) -> None:
        """释放后端资源。默认是空操作。"""
