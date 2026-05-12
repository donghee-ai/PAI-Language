"""프로젝트 공통 상수 — WS URL, 토픽 이름, 라벨 등."""

# WebSocket
# Phase 1 (현재, Vision 직결합): Language가 PAI-Vision의 /ws/scenes 서버에 직접 붙는다.
# 기본값은 로컬 개발용. 원격 배포 시 환경변수 VISION_WS_URL로 덮어쓴다
# (예: VISION_WS_URL=wss://vision.yeoun.org/ws/scenes).
# Phase 2 (Coordinator 도입) 시 COORDINATOR_WS_URL 을 별도 상수/환경변수로 추가하고
# 클라이언트 연결 대상을 Coordinator로 전환한다.
VISION_WS_URL = "ws://localhost:8000/ws/scenes"

# 메시지 타입
TOPIC_VISION_UPDATE = "vision_update"
TOPIC_ROBOT_COMMAND = "robot_command"
TOPIC_ACTION_STATUS = "action_status"

# sender 식별자
SENDER_LANGUAGE = "language"
SENDER_VISION = "vision"
SENDER_ACTION = "action"

# YOLO 라벨
#
# 현재 PAI-Vision은 COCO 사전학습 `yolo11s-seg.pt`를 쓰므로 emit 가능한 label은
# 아래 COCO 80개 클래스가 전부다 (`result.names` 가 그대로 이 문자열들을 반환).
# 튜플 인덱스 = YOLO class id. Vision이 커스텀 fine-tuning / open-vocab 모델로
# 바꾸면 이 목록도 그 모델의 names로 갱신해야 한다.
#
# 주의: 공은 "ball"이 아니라 "sports ball"(공백 포함)이고, "basket"은 COCO에 없다.
COCO_LABELS: tuple[str, ...] = (
    "person", "bicycle", "car", "motorcycle", "airplane",
    "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird",
    "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat",
    "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut",
    "cake", "chair", "couch", "potted plant", "bed",
    "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
)

# robot_command 의 target / destination 으로 허용되는 label 집합 (멤버십 체크용).
KNOWN_LABELS = frozenset(COCO_LABELS)
