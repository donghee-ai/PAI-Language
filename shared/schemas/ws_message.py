"""WebSocket 공통 envelope 모델."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class WSMessage(BaseModel):
    """모든 WS 메시지가 따르는 공통 envelope."""

    type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sender: str
    data: dict[str, Any] = {}
