"""최신 YOLO 감지 결과 보관 및 필터링.

전체 vision_update JSON을 수신하되, Language에 필요한 최소 필드만 보관한다:
  - label, center_pixel, confidence, status
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class DetectedObject:
    label: str
    center_pixel: list[int]
    confidence: float
    status: str = "tracked"


class VisionState:
    """가장 최근 vision_update의 객체 목록을 보관."""

    def __init__(self) -> None:
        self._objects: list[DetectedObject] = []

    def update(self, data: dict) -> None:
        """vision_update 메시지의 data 페이로드를 받아 필터링 후 저장."""
        raw_objects = data.get("objects", [])
        self._objects = [
            DetectedObject(
                label=obj["label"],
                center_pixel=obj["center_pixel"],
                confidence=obj["confidence"],
                status=obj.get("status", "tracked"),
            )
            for obj in raw_objects
            if "label" in obj and "center_pixel" in obj
        ]
        log.debug("vision 업데이트: %d개 객체", len(self._objects))

    def get_objects(self) -> list[DetectedObject]:
        return list(self._objects)

    def find_by_label(self, label: str) -> DetectedObject | None:
        """라벨로 가장 높은 confidence 객체를 검색."""
        matches = [o for o in self._objects if o.label == label]
        if not matches:
            return None
        return max(matches, key=lambda o: o.confidence)

    def has_label(self, label: str) -> bool:
        return any(o.label == label for o in self._objects)

    def to_context_string(self) -> str:
        """OpenAI 프롬프트에 삽입할 한 줄 요약 문자열 생성."""
        if not self._objects:
            return "현재 카메라: 감지된 객체 없음"

        parts = []
        for obj in self._objects:
            cx, cy = obj.center_pixel
            parts.append(f"{obj.label}(위치=[{cx},{cy}], 신뢰도 {obj.confidence:.2f})")
        return "현재 카메라: " + ", ".join(parts)
