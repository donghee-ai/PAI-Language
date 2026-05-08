"""Language 파트 설정 — 환경변수 기반."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from shared.constants import VISION_WS_URL

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class Config:
    # WebSocket — 현재 단계는 Vision 서버에 직접 붙는다.
    ws_url: str = field(default_factory=lambda: os.getenv("VISION_WS_URL", VISION_WS_URL))

    # OpenAI
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    # 재연결
    ws_reconnect_interval: float = 3.0
    ws_max_retries: int | None = None  # None = 무한 재시도

    # Action Hub 연동 토글. 현재(직결합 단계)는 False — robot_command를 송신하지 않고
    # stdout으로만 출력한다. Action Hub 도입 시 ACTION_HUB_ENABLED=1 로 설정.
    action_hub_enabled: bool = field(
        default_factory=lambda: os.getenv("ACTION_HUB_ENABLED", "0") == "1"
    )

    def validate(self) -> None:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
        if self.action_hub_enabled:
            # 현 단계에서는 단일 HubClient가 VISION_WS_URL에 연결된다. ACTION_HUB_ENABLED=1
            # 인데 그 URL이 Vision 서버를 가리키면 robot_command가 Vision 서버로 잘못 송신된다.
            # 명시적으로 막아 사용자가 ACTION_WS_URL을 분리하기 전까지 활성화되지 않도록 한다.
            raise RuntimeError(
                "ACTION_HUB_ENABLED=1 이지만 별도 Action Hub URL이 분리되어 있지 않습니다. "
                "현재 단일 클라이언트가 VISION_WS_URL에 연결되어 robot_command가 Vision "
                "서버로 잘못 송신됩니다. Action Hub 도입 시 듀얼 클라이언트 구조로 전환한 "
                "후에만 활성화하세요."
            )
