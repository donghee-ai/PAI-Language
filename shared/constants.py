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


# ----------------------------------------------------------------------------
# move 액션의 "box" 게이팅.
#
# COCO 80개 클래스에는 'box' 가 없다. 따라서 move(=박스 옮기기) 명령은 실제 박스가
# YOLO 에 잡히는 COCO 라벨로 매핑해 "박스가 감지됐는지" 를 판단한다. 사용자는 실제
# 박스가 overhead 캠에서 어떤 라벨로 잡히는지 확인 후, 환경변수 BOX_LABELS(쉼표 구분)
# 로 이 기본값을 덮어쓰면 된다. 예: BOX_LABELS="suitcase,book"
BOX_LABELS_DEFAULT: tuple[str, ...] = ("suitcase", "book", "cell phone")

# move 의 target 으로 박스를 가리킬 때 쓰는 특수 토큰(COCO 라벨이 아님).
# instruction 은 학습 task("Move the box to the left")와 맞추기 위해 이 단어를 쓴다.
BOX_TARGET_TOKEN = "box"

# 실행 가능한(=등록된) move 커맨드 화이트리스트.
#
# move 명령은 파싱된 (action, target, direction) 을 언더스코어로 조립해
# "move_{target}_{direction}" 키를 만든다 (예: "박스 왼쪽으로 옮겨" → move_box_left).
# 이 집합에 있는 키만 로봇으로 발행/실행한다.
#
#   - move_box_left   : 유일하게 실제 학습된 정책(yeopeter1031/so101_smolvla_move_box_left).
#   - move_mouse_left : 카메라가 'box' 를 못 잡으므로, 감지 가능한 COCO 라벨 'mouse' 로
#                       파이프라인을 끝까지 테스트하기 위한 복사본. 실제 구동 시에는
#                       로드된 move_box_left 정책이 그대로 동작한다(전용 mouse 정책 없음).
EXECUTABLE_MOVE_COMMANDS = frozenset({"move_box_left", "move_mouse_left"})


# ----------------------------------------------------------------------------
# LeRobot Action 으로 instruction을 내보낼 ZMQ PUB 채널.
#
# Vision의 raw frame은 :5555 (lerobot.cameras.zmq.ZMQCamera 와이어 포맷),
# Language의 instruction은 :5557 PUB. LeRobot 측에서는 ZMQ SUB 소켓을 만들어
# JSON envelope를 받으면 된다. envelope 스키마는 InstructionPublisher 참고.
# ----------------------------------------------------------------------------
INSTRUCTION_PUB_BIND_DEFAULT = "tcp://*:5557"
