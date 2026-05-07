"""수신 메시지 type별 핸들러 라우팅."""

from __future__ import annotations

import logging
from typing import Callable, Coroutine

from shared.constants import TOPIC_ACTION_STATUS, TOPIC_VISION_UPDATE

log = logging.getLogger(__name__)

Handler = Callable[[dict], Coroutine]


class Dispatcher:
    """WS 메시지를 type 필드에 따라 적절한 핸들러로 분배."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, msg_type: str, handler: Handler) -> None:
        self._handlers[msg_type] = handler

    async def dispatch(self, msg: dict) -> None:
        msg_type = msg.get("type")
        if not msg_type:
            log.warning("type 필드 없는 메시지 무시: %s", msg)
            return

        handler = self._handlers.get(msg_type)
        if handler:
            await handler(msg)
        else:
            log.debug("등록되지 않은 메시지 타입 무시: %s", msg_type)
