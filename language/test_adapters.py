"""language.ws.adapters 단위 테스트.

실행:
    cd PAI_LE
    python -m language.test_adapters

pytest 없이 plain python으로 실행 가능 (외부 의존 없음).
실패 시 AssertionError로 즉시 종료, 모두 통과하면 "[OK] N개 통과" 출력.
"""

from __future__ import annotations

from language.ws.adapters import normalize_envelope
from shared.constants import SENDER_VISION, TOPIC_VISION_UPDATE


def test_passthrough_when_envelope_present() -> None:
    """이미 envelope 형태(`type` 필드 존재)면 그대로 통과."""
    msg = {"type": "vision_update", "timestamp": "x", "sender": "vision", "data": {}}
    out = normalize_envelope(msg)
    assert out is msg, "envelope이 있으면 같은 객체를 그대로 반환해야 함"


def test_wrap_pai_vision_raw_scene() -> None:
    """PAI-Vision raw scene → vision_update envelope으로 래핑."""
    scene = {
        "frame_id": 42,
        "timestamp": "2026-05-08T00:00:00Z",
        "camera_id": "front_rgb",
        "objects": [
            {"label": "ball", "center_pixel": [100, 200], "confidence": 0.91}
        ],
    }
    out = normalize_envelope(scene)
    assert out["type"] == TOPIC_VISION_UPDATE
    assert out["sender"] == SENDER_VISION
    assert out["timestamp"] == "2026-05-08T00:00:00Z", "scene의 timestamp를 envelope에 승격해야 함"
    assert out["data"] is scene, "원본 scene이 data에 그대로 들어가야 함"


def test_passthrough_when_neither_type_nor_objects() -> None:
    """type도 objects도 없는 알 수 없는 메시지는 손대지 않고 통과."""
    weird = {"foo": "bar", "baz": 1}
    out = normalize_envelope(weird)
    assert out is weird, "알 수 없는 메시지는 같은 객체로 반환"
    assert "type" not in out, "type 필드를 함부로 추가하면 안 됨"


def test_wrap_empty_objects_list() -> None:
    """objects가 빈 list여도 vision_update로 래핑된다 (객체가 화면에 없을 뿐)."""
    scene = {"frame_id": 1, "objects": []}
    out = normalize_envelope(scene)
    assert out["type"] == TOPIC_VISION_UPDATE
    assert out["data"]["objects"] == []


def test_objects_not_list_passthrough() -> None:
    """objects가 list가 아닌 경우(스펙 위반) 휴리스틱 미적용 → 통과."""
    bad = {"objects": "not a list"}
    out = normalize_envelope(bad)
    assert "type" not in out, "objects가 list가 아니면 envelope을 만들지 않아야 함"


def test_timestamp_fallback_when_missing() -> None:
    """raw scene에 timestamp가 없으면 envelope timestamp는 자동 생성된 ISO 문자열."""
    scene = {"objects": []}
    out = normalize_envelope(scene)
    assert isinstance(out["timestamp"], str)
    assert "T" in out["timestamp"], "ISO 8601 형식이어야 함"


def main() -> None:
    tests = [
        test_passthrough_when_envelope_present,
        test_wrap_pai_vision_raw_scene,
        test_passthrough_when_neither_type_nor_objects,
        test_wrap_empty_objects_list,
        test_objects_not_list_passthrough,
        test_timestamp_fallback_when_missing,
    ]
    for t in tests:
        t()
        print(f"  [OK] {t.__name__}")
    print(f"\n[OK] {len(tests)}개 통과")


if __name__ == "__main__":
    main()
