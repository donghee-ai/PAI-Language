# 2026-05-26 — RobotCommand 에 instruction 필드 + ZMQ PUB 채널 추가

## 배경

PAI-Vision 은 이미 두 가지 채널로 출력하고 있다.

- WebSocket `/ws/scenes`: YOLO 추론 결과(scene JSON) → PAI-Language
- ZMQ PUB `:5555`: raw 카메라 프레임 (LeRobot `ZMQCamera` 와이어 포맷) → LeRobot

PAI-Language 는 LLM 출력으로 `RobotCommand{action, target, destination, ...}` 를 만들지만,
이걸 그대로 LeRobot 정책(VLA pi0/smolvla/wall_x 등) 에 넘길 수 없었다. VLA 정책은
영어 자연어 `task` 문자열을 받는다.

→ Language 에 `instruction` (영어 문자열) 출력을 추가하고, ZMQ PUB 채널로 LeRobot 에
직접 발행하여 *lang → action* 직결을 가능하게 만들었다. *lang → vision → action*
경로는 Vision 에 명령 라우터 책임을 떠넘기게 되어 채택하지 않았다.

## 결정 사항 (사용자 확정)

| 항목 | 결정 |
|------|------|
| LeRobot 인터페이스 | VLA policy `task` 문자열 |
| 출력 경로 | `lang → action` 직접 (Vision 우회 아님) |
| 채널 | ZMQ PUB (Vision 의 5555 와 같은 패턴; instruction 은 5557) |
| 언어/형식 | 영어, COCO 라벨 그대로 |

## 변경 파일

### 스키마
- `shared/schemas/command.py`
  - `RobotCommand.instruction: str = ""` 필드 추가.
  - `validate_action_fields` 가 instruction 이 비어있으면
    `_derive_instruction(action, target, destination)` 으로 폴백 생성.
  - 폴백 phrasing:
    - `pick` → `pick up the <target>`
    - `place` → `place the <target> in the <destination>`
    - `pick_and_place` → `pick up the <target> and place it in the <destination>`
    - `home` → `move to the home position`
    - `stop` → `stop`

### LLM
- `language/llm/prompt_builder.py`
  - JSON 출력 스키마에 `instruction` 필드 추가.
  - "instruction 작성 규칙" 섹션 추가 (영어, 라벨 그대로, 행동만, 예시 포함).
- `language/llm/response_parser.py`
  - `command_data.get("instruction", "")` 를 `RobotCommand` 생성 시 전달.
    누락 시 빈 문자열 → 스키마 폴백이 자동 채움.

### ZMQ Publisher
- `language/zmq_pub/__init__.py` (신규)
- `language/zmq_pub/instruction_publisher.py` (신규)
  - `InstructionPublisher`: PUB 소켓 bind, JSON envelope 발행, pyzmq 미설치 시 no-op.
  - `build_envelope(RobotCommand) -> dict`: LeRobot 측 SUB 이 받을 JSON 형식 정의.
    `{timestamp, instruction, action, target, destination, raw_input, reasoning, vision_confirmed}`.
  - `start()` 후 실제 bind endpoint(`tcp://0.0.0.0:5557` 등) 를 `endpoint` 프로퍼티로 노출.

### 상수 / 설정
- `shared/constants.py`
  - `INSTRUCTION_PUB_BIND_DEFAULT = "tcp://*:5557"`
- `language/config.py`
  - `instruction_pub_enabled` (env `INSTRUCTION_PUB_ENABLED`, 기본 1)
  - `instruction_pub_bind` (env `INSTRUCTION_PUB_BIND`, 기본 :5557)

### 진입점
- `language/main.py`
  - `LanguageApp.__init__` 에서 `InstructionPublisher` 생성.
  - `start_services()` / `stop_services()` 분리 → CLI/UI 양쪽에서 동일 라이프사이클.
  - `handle_user_input` 에서 명령 처리 시 publisher 로 발행 + emit 으로 `[instruction]`,
    `[ZMQ 발행 → LeRobot]` 로그.
- `language/ui.py`
  - 생성 시 `app.start_services()`, 종료 시 `app.stop_services()` 호출.
  - `_META_PREFIXES` 에 `[instruction]`, `[ZMQ` 추가.

### 의존성
- `requirements.txt` 에 `pyzmq>=25.0` 추가.

### 테스트
- `tests/test_command_schema.py` (신규, 9 케이스): instruction 자동 생성/명시값 보존/공백 처리.
- `tests/test_instruction_publisher.py` (신규, 4 케이스):
  envelope 직렬화, no-op 모드, PUB→SUB round-trip (pyzmq 의존).
- `tests/test_response_parser.py`: instruction 라운드트립 + 누락 시 폴백 검증 케이스 추가.

전체 81 테스트 통과 (lerobot venv 기준).

## LeRobot 측 연결 가이드 (다음 단계)

LeRobot 정책 쪽에서는 다음 형태로 SUB 구독하면 된다.

```python
import json
import zmq

ctx = zmq.Context.instance()
sub = ctx.socket(zmq.SUB)
sub.setsockopt(zmq.SUBSCRIBE, b"")
sub.connect("tcp://<language-host>:5557")

while True:
    msg = json.loads(sub.recv_string())
    task = msg["instruction"]  # ← VLA policy.predict(observation, task=task)
    # action = msg["action"]    # 메타용
```

## 미해결 / 후속

- LeRobot 측 SUB 구독 코드는 이 저장소 밖이라 미작성. 정책 호출 어디서 task 를 받을지
  결정되면 그 시점에 작성.
- Coordinator (Phase 2) 도입 시 `INSTRUCTION_PUB_ENABLED=0` 으로 끄고 robot_command 를
  Coordinator 로 WS 전송하는 경로로 전환.
