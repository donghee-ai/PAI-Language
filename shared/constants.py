"""프로젝트 공통 상수 — WS URL, 토픽 이름, 라벨 등."""

# WebSocket
WS_URL = "wss://vision.yeoun.org/ws/scenes"

# 메시지 타입
TOPIC_VISION_UPDATE = "vision_update"
TOPIC_ROBOT_COMMAND = "robot_command"
TOPIC_ACTION_STATUS = "action_status"

# sender 식별자
SENDER_LANGUAGE = "language"
SENDER_VISION = "vision"
SENDER_ACTION = "action"

# YOLO 라벨 (Vision팀 확정 시 갱신)
LABEL_BALL = "ball"
LABEL_BASKET = "basket"
KNOWN_LABELS = [LABEL_BALL, LABEL_BASKET]
