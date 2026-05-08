"""WS 메시지 어댑터 — 외부 송신 형식과 PAI_LE 표준 envelope 사이의 변환.

분리 의도:
    수신 메시지 정규화 로직을 client.py에서 분리해, 향후 다른 외부 시스템
    (Action Hub 등)이 합류해도 어댑터만 추가/수정할 수 있도록 한다.

현재 어댑터:
    - PAI-Vision raw scene → vision_update envelope (envelope_from_vision_raw)

향후 어댑터(예시, 미구현):
    - 다른 카메라 소스의 raw frame → vision_update envelope
    - 외부 Hub의 비표준 메시지 → 표준 envelope
"""

from __future__ import annotations

from datetime import datetime, timezone

from shared.constants import SENDER_VISION, TOPIC_VISION_UPDATE


def normalize_envelope(msg: dict) -> dict:
    """수신 메시지가 PAI_LE 표준 envelope이 아니면 보정한다.

    - 이미 envelope 형태(`type` 필드 존재) → 손대지 않고 통과.
    - PAI-Vision raw scene 휴리스틱(`objects` list 존재) → vision_update envelope으로 래핑.
    - 그 외 → 손대지 않고 통과 (dispatcher에서 무시됨).

    TODO(envelope-wire-standard):
        PAI-Vision이 envelope으로 감싸 송출하도록 변경되면 이 함수의 raw scene
        분기는 제거 가능. (PAI-Vision app/main.py: `send_json(scene)` →
        `send_json(envelope)` PR 이후)
    """
    if "type" in msg:
        return msg
    if isinstance(msg.get("objects"), list):
        return _wrap_vision_raw(msg)
    return msg


def _wrap_vision_raw(scene: dict) -> dict:
    """PAI-Vision의 raw scene을 vision_update envelope으로 감싼다."""
    return {
        "type": TOPIC_VISION_UPDATE,
        "timestamp": scene.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "sender": SENDER_VISION,
        "data": scene,
    }
