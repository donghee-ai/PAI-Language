"""language.context.vision_state.VisionState 단위 테스트.

핵심 동작: Pydantic 1순위 검증 → 실패 시 dict fallback, 라벨 조회, context 문자열,
KNOWN_LABELS(현재 COCO 80개)에 없는 라벨 수신 시 1회 경고.
"""

from __future__ import annotations

import logging

from language.context.vision_state import VisionState


# 완전한 VisionUpdate(typed) 페이로드 — frame_id, timestamp 포함.
# 데모 시나리오 객체(sports ball / bowl)를 사용 — 둘 다 COCO 라벨.
TYPED_PAYLOAD = {
    "frame_id": 1,
    "timestamp": "2026-05-09T00:00:00Z",
    "objects": [
        {
            "id": "o1",
            "label": "sports ball",
            "confidence": 0.91,
            "bbox_xyxy": [10.0, 20.0, 30.0, 40.0],
            "center_pixel": [640, 360],
            "status": "tracked",
        },
        {
            "id": "o2",
            "label": "bowl",
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
    assert labels == {"sports ball", "bowl"}


def test_has_label() -> None:
    vs = VisionState()
    vs.update(TYPED_PAYLOAD)

    assert vs.has_label("sports ball") is True
    assert vs.has_label("bowl") is True
    assert vs.has_label("banana") is False


def test_find_by_label_returns_highest_confidence() -> None:
    payload = {
        "frame_id": 1,
        "timestamp": "x",
        "objects": [
            {
                "id": "a",
                "label": "sports ball",
                "confidence": 0.5,
                "bbox_xyxy": [0, 0, 1, 1],
                "center_pixel": [10, 10],
            },
            {
                "id": "b",
                "label": "sports ball",
                "confidence": 0.95,
                "bbox_xyxy": [0, 0, 1, 1],
                "center_pixel": [20, 20],
            },
            {
                "id": "c",
                "label": "sports ball",
                "confidence": 0.7,
                "bbox_xyxy": [0, 0, 1, 1],
                "center_pixel": [30, 30],
            },
        ],
    }
    vs = VisionState()
    vs.update(payload)

    best = vs.find_by_label("sports ball")
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
    assert "sports ball" in s
    assert "bowl" in s
    assert "0.91" in s
    assert "[640,360]" in s


def test_context_string_when_empty() -> None:
    vs = VisionState()
    assert vs.to_context_string() == "현재 카메라: 감지된 객체 없음"


# --- 알 수 없는 라벨 경고 (KNOWN_LABELS 미포함) -----------------------------


def test_unknown_label_warns_once(caplog) -> None:
    """COCO_LABELS에 없는 라벨이 들어오면 최초 1회만 WARNING. 객체는 그대로 보관."""
    payload = {
        "frame_id": 1,
        "timestamp": "x",
        "objects": [
            {
                "id": "o1",
                "label": "wicker basket",  # COCO에 없음
                "confidence": 0.8,
                "bbox_xyxy": [0, 0, 1, 1],
                "center_pixel": [5, 5],
            },
        ],
    }
    vs = VisionState()
    with caplog.at_level(logging.WARNING, logger="language.context.vision_state"):
        vs.update(payload)
        vs.update(payload)  # 두 번째 호출은 다시 경고하지 않아야 함

    warnings = [r for r in caplog.records if "wicker basket" in r.getMessage()]
    assert len(warnings) == 1
    # 경고했어도 객체 자체는 보관
    assert vs.has_label("wicker basket") is True


def test_known_label_does_not_warn(caplog) -> None:
    vs = VisionState()
    with caplog.at_level(logging.WARNING, logger="language.context.vision_state"):
        vs.update(TYPED_PAYLOAD)
    assert not [r for r in caplog.records if "알 수 없는" in r.getMessage()]


# --- fallback 경로 (Pydantic 검증 실패 → dict best-effort) ------------------


def test_fallback_when_required_fields_missing() -> None:
    """frame_id, timestamp 같은 VisionUpdate 필수 필드가 없으면 fallback 경로."""
    payload = {
        "objects": [
            {"label": "sports ball", "center_pixel": [640, 360], "confidence": 0.91, "status": "tracked"},
        ]
    }
    vs = VisionState()
    vs.update(payload)

    objs = vs.get_objects()
    assert len(objs) == 1
    assert objs[0].label == "sports ball"
    assert objs[0].center_pixel == [640, 360]


def test_fallback_skips_invalid_center_pixel() -> None:
    payload = {
        "objects": [
            {"label": "cup", "center_pixel": [1, 2], "confidence": 0.9},
            {"label": "bottle", "center_pixel": [1, 2, 3], "confidence": 0.9},
            {"label": "bowl", "center_pixel": "nope", "confidence": 0.9},
        ]
    }
    vs = VisionState()
    vs.update(payload)

    labels = {o.label for o in vs.get_objects()}
    assert labels == {"cup"}


def test_fallback_skips_objects_missing_required_fields() -> None:
    payload = {
        "objects": [
            {"label": "cup", "center_pixel": [1, 2], "confidence": 0.9},
            {"label": "bottle", "center_pixel": [3, 4]},  # confidence 없음
            {"center_pixel": [5, 6], "confidence": 0.9},  # label 없음
        ]
    }
    vs = VisionState()
    vs.update(payload)

    labels = {o.label for o in vs.get_objects()}
    assert labels == {"cup"}


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
