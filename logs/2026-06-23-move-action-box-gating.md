# 2026-06-23 — move 액션 + 박스 감지 게이팅 추가

"박스 왼쪽으로 옮겨" 류 명령을 PAI-Language 가 처리해, 박스가 감지됐을 때만 LeRobot
SmolVLA 정책(`move_box_left`)으로 instruction 을 발행하도록 확장했다.

## 사용자 결정 (AskUserQuestion)

1. **구동 방식 = 기존 ZMQ 어댑터 경로.** Language 는 instruction 만 :5557 로 발행하고,
   실제 로봇 구동은 미리 띄운 `scripts/rollout_with_zmq_task.py` 가 task 를 갱신해 처리.
   (Language 는 lerobot 을 직접 실행하지 않음 — 안전/단순.)
2. **박스 감지 = 특정 YOLO 라벨 매핑.** COCO 에 'box' 클래스가 없어, 실제 박스가 잡히는
   COCO 라벨 집합으로 "박스 감지" 를 판단. `BOX_LABELS` env 로 설정.
3. **move 방향 = 일반(left/right/forward/backward).** 단 실제 학습된 정책은 `left` 뿐이라
   그 외 방향은 instruction 만 발행되고 로봇은 안 움직임 — 경고를 출력.

## 동작 흐름

```
사용자 "박스 왼쪽으로 옮겨"
  → LLM: action=move, target="box", direction="left"
  → instruction 폴백: "Move the box to the left"  (학습 task 와 동일 표기)
  → 박스 게이팅: overhead 비전에 BOX_LABELS 중 하나가 보이면 통과, 없으면 [move 보류]
  → 방향 체크: left=학습됨(통과), 그 외=경고
  → InstructionPublisher → ZMQ :5557 envelope 발행
  → rollout_with_zmq_task.py 가 envelope.instruction 을 SmolVLA task 로 주입 → 로봇 구동
```

## 변경 파일

- `shared/schemas/command.py`
  - `ActionType.MOVE` 추가.
  - `RobotCommand.direction` 필드 추가 (move 외엔 강제 "none").
  - validator: move 는 target·direction 필수.
  - `_derive_instruction`: move → `"Move the {target} to the {direction}"`.
- `shared/constants.py`
  - `BOX_LABELS_DEFAULT = ("suitcase", "book", "cell phone")` — 박스로 인정할 COCO 라벨 기본값.
  - `BOX_TARGET_TOKEN = "box"` — move target 으로 박스를 가리키는 특수 토큰.
  - `TRAINED_MOVE_DIRECTIONS = {"left"}` — 실제 정책이 있는 방향.
- `language/config.py`
  - `box_labels` 설정 + `BOX_LABELS`(쉼표 구분) env 파싱.
- `language/context/vision_state.py`
  - `has_any_label(labels)`, `first_matching_label(labels)` 추가.
- `language/llm/prompt_builder.py`
  - 시스템 프롬프트에 move 액션 / direction 필드 / "box" target / 예시 추가.
- `language/llm/response_parser.py`
  - command 파싱에 `direction` 추가.
- `language/main.py`
  - `handle_user_input`: move 액션의 박스 게이팅 + 미학습 방향 경고 로직.
- `language/zmq_pub/instruction_publisher.py`
  - envelope 에 `direction` 메타데이터 추가 (정책은 instruction 만 사용).
- 테스트
  - `tests/test_command_schema.py`: move 폴백/필수필드/direction 정리 (5 케이스).
  - `tests/test_response_parser.py`: move 라운드트립/방향 누락 fallback (2 케이스).
  - 전체 **111 passed** (기존 105 + 신규 6).

## 설정 / 운영 메모

- **`BOX_LABELS` 를 실제 박스에 맞게 설정해야 함.** 현재 overhead 캠은 박스를 COCO
  라벨로 무엇으로 잡는지 미확인(예: suitcase/book/cell phone 중 하나일 수도, 아닐 수도).
  실제 박스를 overhead 에 놓고 YOLO 라벨을 확인한 뒤 `.env` 에
  `BOX_LABELS="<그 라벨>"` 로 지정할 것. 안 맞으면 move 가 계속 `[move 보류]` 로 막힘.
- 실제 로봇 구동까지 가려면: ① overhead/gripper 비전, ② `rollout_with_zmq_task.py`
  (SmolVLA 정책 로드, GPU), ③ Language UI(본 변경 반영) 가 모두 떠 있어야 함.
- left 외 방향은 정책이 없어 구동되지 않음(instruction 만 발행). 다른 방향을 구동하려면
  해당 방향 데이터 수집 + 학습 필요 ([SMOLVLA-TRAINING.md] 참고).

## 검증

- 단위/통합 테스트 111 passed.
- 자체 스크립트로 move 폴백 instruction / 박스 게이팅 / ZMQ PUB→SUB 발행(direction 포함)
  라운드트립 확인.
