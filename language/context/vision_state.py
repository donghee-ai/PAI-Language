"""최신 YOLO 감지 결과 보관 및 필터링.

전체 vision_update JSON을 수신하되, Language에 필요한 최소 필드만 보관한다:
  - label, center_pixel, confidence, status

검증 전략: 우선 shared/schemas/vision.py의 Pydantic VisionUpdate로 검증을 시도해
schema drift를 빠르게 감지한다. 검증 실패 시(스펙 불일치/외부 변경)에도 서비스가
죽지 않도록 dict 기반 best-effort 파싱으로 graceful fallback한다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pydantic import ValidationError

from shared.constants import KNOWN_LABELS
from shared.schemas.vision import VisionUpdate

log = logging.getLogger(__name__)


@dataclass
class DetectedObject:
    label: str
    center_pixel: list[int]
    confidence: float
    status: str = "detected"


class VisionState:
    """가장 최근 vision_update의 객체 목록을 보관."""

    def __init__(self) -> None:
        self._objects: list[DetectedObject] = []
        # 알 수 없는 label은 최초 1회만 경고한다 (vision_update가 ~10Hz로 들어와서
        # 매 프레임 찍으면 로그가 폭주함).
        self._warned_labels: set[str] = set()

    def _warn_if_unknown_label(self, label: str) -> None:
        """KNOWN_LABELS(현재 COCO 80개)에 없는 label이면 최초 1회만 경고."""
        if label in KNOWN_LABELS or label in self._warned_labels:
            return
        self._warned_labels.add(label)
        log.warning(
            "알 수 없는 vision label %r — shared/constants.py 의 COCO_LABELS 에 없음. "
            "Vision 모델이 바뀌었거나 라벨 합의가 어긋났을 수 있음.",
            label,
        )

    def update(self, data: dict) -> None:
        """vision_update 메시지의 data 페이로드를 받아 필터링 후 저장.

        1순위: VisionUpdate Pydantic 모델로 typed 검증.
        2순위(실패 시): dict 기반 best-effort 파싱.

        어느 쪽이든 개별 객체 파싱 실패가 다른 객체나 _recv_loop을 죽이지 않도록
        방어한다.
        """
        try:
            update = VisionUpdate.model_validate(data)
        except ValidationError as exc:
            log.warning(
                "VisionUpdate schema 검증 실패, dict 기반 fallback (%s)", exc.error_count()
            )
            self._update_from_dict(data)
            return

        objects: list[DetectedObject] = []
        for obj in update.objects:
            if len(obj.center_pixel) != 2:
                continue
            self._warn_if_unknown_label(obj.label)
            objects.append(
                DetectedObject(
                    label=obj.label,
                    center_pixel=list(obj.center_pixel),
                    confidence=obj.confidence,
                    status=obj.status,
                )
            )
        self._objects = objects
        log.debug("vision 업데이트(typed): %d개 객체", len(self._objects))

    def _update_from_dict(self, data: dict) -> None:
        """Pydantic 검증 실패 시 best-effort dict 파싱."""
        raw_objects = data.get("objects", [])
        if not isinstance(raw_objects, list):
            log.warning("vision_update.objects 필드가 list가 아님: %r", raw_objects)
            self._objects = []
            return

        parsed: list[DetectedObject] = []
        for obj in raw_objects:
            if not isinstance(obj, dict):
                log.warning("vision 객체 항목이 dict가 아님: %r", obj)
                continue
            try:
                label = obj["label"]
                cp = obj["center_pixel"]
                confidence = obj["confidence"]
            except KeyError as exc:
                log.warning("vision 객체 필수 필드 누락(%s): %r", exc, obj)
                continue
            if not isinstance(cp, (list, tuple)) or len(cp) != 2:
                log.warning("center_pixel 형식 오류 무시: %r", obj)
                continue
            try:
                label_str = str(label)
                self._warn_if_unknown_label(label_str)
                parsed.append(DetectedObject(
                    label=label_str,
                    center_pixel=[int(cp[0]), int(cp[1])],
                    confidence=float(confidence),
                    status=str(obj.get("status", "detected")),
                ))
            except (TypeError, ValueError) as exc:
                log.warning("vision 객체 타입 변환 실패(%s): %r", exc, obj)

        self._objects = parsed
        log.debug("vision 업데이트(fallback): %d개 객체", len(self._objects))

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

    def has_any_label(self, labels) -> bool:
        """주어진 라벨 집합 중 하나라도 감지됐는지. (move 의 box 게이팅용)"""
        label_set = set(labels)
        return any(o.label in label_set for o in self._objects)

    def first_matching_label(self, labels) -> str | None:
        """주어진 라벨 집합 중 감지된 첫 라벨을 반환(없으면 None). 로그/메시지용."""
        label_set = set(labels)
        for o in self._objects:
            if o.label in label_set:
                return o.label
        return None

    def to_context_string(self) -> str:
        """OpenAI 프롬프트에 삽입할 한 줄 요약 문자열 생성."""
        if not self._objects:
            return "현재 카메라: 감지된 객체 없음"

        parts = []
        for obj in self._objects:
            if len(obj.center_pixel) >= 2:
                cx, cy = obj.center_pixel[0], obj.center_pixel[1]
                parts.append(f"{obj.label}(위치=[{cx},{cy}], 신뢰도 {obj.confidence:.2f})")
            else:
                parts.append(f"{obj.label}(신뢰도 {obj.confidence:.2f})")
        return "현재 카메라: " + ", ".join(parts)
