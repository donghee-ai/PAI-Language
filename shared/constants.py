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

# YOLO 라벨 (Vision팀 확정 시 갱신)
LABEL_BALL = "ball"
LABEL_BASKET = "basket"
KNOWN_LABELS = [LABEL_BALL, LABEL_BASKET]
