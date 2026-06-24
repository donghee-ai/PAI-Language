"""Language 파트 설정 — 환경변수 기반."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from shared.constants import BOX_LABELS_DEFAULT, INSTRUCTION_PUB_BIND_DEFAULT, VISION_WS_URL

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _parse_box_labels() -> tuple[str, ...]:
    """환경변수 BOX_LABELS(쉼표 구분)를 파싱. 미설정/빈 값이면 기본값 사용."""
    raw = os.getenv("BOX_LABELS", "")
    labels = tuple(s.strip() for s in raw.split(",") if s.strip())
    return labels or BOX_LABELS_DEFAULT


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

    # Coordinator 연동 토글. 현재(Vision 직결합 단계)는 False — robot_command를 송신하지
    # 않고 stdout으로만 출력한다. Phase 2(Coordinator 도입) 시 COORDINATOR_ENABLED=1 로 설정.
    coordinator_enabled: bool = field(
        default_factory=lambda: os.getenv("COORDINATOR_ENABLED", "0") == "1"
    )

    # LeRobot Action 직결합용 ZMQ instruction publisher. 기본 활성. LeRobot 측은
    # ZMQ SUB 소켓으로 INSTRUCTION_PUB_BIND 에 connect 한다 (bind는 Language가 한다).
    # Coordinator 도입 후 라우팅을 그쪽으로 옮기면 INSTRUCTION_PUB_ENABLED=0 으로 끄면 된다.
    instruction_pub_enabled: bool = field(
        default_factory=lambda: os.getenv("INSTRUCTION_PUB_ENABLED", "1") == "1"
    )
    instruction_pub_bind: str = field(
        default_factory=lambda: os.getenv("INSTRUCTION_PUB_BIND", INSTRUCTION_PUB_BIND_DEFAULT)
    )

    # move(박스 옮기기) 명령의 "박스 감지" 게이팅에 쓰는 YOLO 라벨 집합.
    # COCO 에 'box' 가 없어 실제 박스가 잡히는 라벨로 매핑한다 (BOX_LABELS env 로 덮어쓰기).
    box_labels: tuple[str, ...] = field(default_factory=_parse_box_labels)

    def validate(self) -> None:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
        if self.coordinator_enabled:
            # 현 단계에서는 단일 HubClient가 VISION_WS_URL에 연결된다. COORDINATOR_ENABLED=1
            # 인데 그 URL이 Vision 서버를 가리키면 robot_command가 Vision 서버로 잘못 송신된다.
            # 명시적으로 막아 사용자가 COORDINATOR_WS_URL을 분리하기 전까지 활성화되지 않도록 한다.
            raise RuntimeError(
                "COORDINATOR_ENABLED=1 이지만 별도 Coordinator URL이 분리되어 있지 않습니다. "
                "현재 단일 클라이언트가 VISION_WS_URL에 연결되어 robot_command가 Vision "
                "서버로 잘못 송신됩니다. Coordinator 도입 시 클라이언트 연결 대상을 분리한 "
                "후에만 활성화하세요."
            )
