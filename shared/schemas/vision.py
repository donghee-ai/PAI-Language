"""YOLO 감지 결과 Pydantic 모델 — Vision → Action Hub → Language."""

from __future__ import annotations

from pydantic import BaseModel


class VisionObject(BaseModel):
    """개별 감지 객체."""

    id: str
    track_id: str | None = None
    label: str
    confidence: float
    bbox_xyxy: list[float]
    center_pixel: list[int]
    area_pixels: int | None = None
    status: str = "tracked"


class VisionUpdate(BaseModel):
    """vision_update 메시지의 data 페이로드."""

    frame_id: int
    timestamp: str
    camera_id: str = "front_rgb"
    model: str = "yolo11s-seg.pt"
    image_size: list[int] = [1280, 720]
    inference_ms: float = 0.0
    loop_fps: float = 0.0
    objects: list[VisionObject] = []
