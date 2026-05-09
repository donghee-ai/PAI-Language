"""language.context.vision_state.VisionState 단위 테스트.

핵심 동작: Pydantic 1순위 검증 → 실패 시 dict fallback, 라벨 조회, context 문자열.
"""

from __future__ import annotations

from language.context.vision_state import VisionState


# 완전한 VisionUpdate(typed) 페이로드 — frame_id, timestamp 포함
TYPED_PAYLOAD = {
    "frame_id": 1,
    "timestamp": "2026-05-09T00:00:00Z",
    "objects": [
        {
            "id": "o1",
            "label": "ball",
            "confidence": 0.91,
            "bbox_xyxy": [10.0, 20.0, 30.0, 40.0],
            "center_pixel": [640, 360],
            "status": "tracked",
        },
        {
            "id": "o2",
            "label": "basket",
            "confidence": 0.87,
            "bbox_xyxy": [100.0, 200.0, 300.0, 400.0],
            "center_pixel": [900, 400],
            "status": "tracked",
        },
    ],
}


# --- typed 경로 (Pydantic 검증 성공) ----------------------------------------


def test_typed_update_stores_filtered_objects() -> None:
    vs = VisionState()
    vs.update(TYPED_PAYLOAD)

    objs = vs.get_objects()
    assert len(objs) == 2
    labels = {o.label for o in objs}
    assert labels == {"ball", "basket"}


def test_has_label() -> None:
    vs = VisionState()
    vs.update(TYPED_PAYLOAD)

    assert vs.has_label("ball") is True
    assert vs.has_label("basket") is True
    assert vs.has_label("banana") is False


def test_find_by_label_returns_highest_confidence() -> None:
    payload = {
        "frame_id": 1,
        "timestamp": "x",
        "objects": [
            {
                "id": "a",
                "label": "ball",
                "confidence": 0.5,
                "bbox_xyxy": [0, 0, 1, 1],
                "center_pixel": [10, 10],
            },
            {
                "id": "b",
                "label": "ball",
                "confidence": 0.95,
                "bbox_xyxy": [0, 0, 1, 1],
                "center_pixel": [20, 20],
            },
            {
                "id": "c",
                "label": "ball",
                "confidence": 0.7,
                "bbox_xyxy": [0, 0, 1, 1],
                "center_pixel": [30, 30],
            },
        ],
    }
    vs = VisionState()
    vs.update(payload)

    best = vs.find_by_label("ball")
    assert best is not None
    assert best.confidence == 0.95
    assert best.center_pixel == [20, 20]


def test_find_by_label_returns_none_when_absent() -> None:
    vs = VisionState()
    vs.update(TYPED_PAYLOAD)
    assert vs.find_by_label("banana") is None


# --- to_context_string ------------------------------------------------------


def test_context_string_with_objects() -> None:
    vs = VisionState()
    vs.update(TYPED_PAYLOAD)
    s = vs.to_context_string()
    assert "현재 카메라" in s
    assert "ball" in s
    assert "basket" in s
    assert "0.91" in s
    assert "[640,360]" in s


def test_context_string_when_empty() -> None:
    vs = VisionState()
    assert vs.to_context_string() == "현재 카메라: 감지된 객체 없음"


# --- fallback 경로 (Pydantic 검증 실패 → dict best-effort) ------------------


def test_fallback_when_required_fields_missing() -> None:
    """frame_id, timestamp 같은 VisionUpdate 필수 필드가 없으면 fallback 경로."""
    payload = {
        "objects": [
            {"label": "ball", "center_pixel": [640, 360], "confidence": 0.91, "status": "tracked"},
        ]
    }
    vs = VisionState()
    vs.update(payload)

    objs = vs.get_objects()
    assert len(objs) == 1
    assert objs[0].label == "ball"
    assert objs[0].center_pixel == [640, 360]


def test_fallback_skips_invalid_center_pixel() -> None:
    payload = {
        "objects": [
            {"label": "ok", "center_pixel": [1, 2], "confidence": 0.9},
            {"label": "wrong_len", "center_pixel": [1, 2, 3], "confidence": 0.9},
            {"label": "not_list", "center_pixel": "nope", "confidence": 0.9},
        ]
    }
    vs = VisionState()
    vs.update(payload)

    labels = {o.label for o in vs.get_objects()}
    assert labels == {"ok"}


def test_fallback_skips_objects_missing_required_fields() -> None:
    payload = {
        "objects": [
            {"label": "ok", "center_pixel": [1, 2], "confidence": 0.9},
            {"label": "no_confidence", "center_pixel": [3, 4]},
            {"center_pixel": [5, 6], "confidence": 0.9},  # label 없음
        ]
    }
    vs = VisionState()
    vs.update(payload)

    labels = {o.label for o in vs.get_objects()}
    assert labels == {"ok"}


def test_fallback_when_objects_field_is_not_list() -> None:
    payload = {"objects": "not a list"}
    vs = VisionState()
    vs.update(payload)
    assert vs.get_objects() == []


def test_fallback_when_objects_field_missing_entirely() -> None:
    vs = VisionState()
    vs.update({})  # objects 키 자체가 없음
    assert vs.get_objects() == []


# --- get_objects는 복사본 반환 ----------------------------------------------


def test_get_objects_returns_copy() -> None:
    vs = VisionState()
    vs.update(TYPED_PAYLOAD)

    snapshot = vs.get_objects()
    snapshot.clear()  # 외부 수정이 내부 상태에 영향 X
    assert len(vs.get_objects()) == 2
