"""Language 파트 설정 — 환경변수 기반."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from shared.constants import WS_URL

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Config:
    # WebSocket
    ws_url: str = field(default_factory=lambda: os.getenv("WS_URL", WS_URL))

    # OpenAI
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    # 재연결
    ws_reconnect_interval: float = 3.0
    ws_max_retries: int | None = None  # None = 무한 재시도

    def validate(self) -> None:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
