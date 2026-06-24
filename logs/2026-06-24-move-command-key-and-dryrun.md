# 2026-06-24 — move 커맨드 키 조립 + move_mouse_left + ZMQ dry-run 실행

[2026-06-23-move-action-box-gating] 의 후속. move 명령을 "실행 가능한 커맨드 키" 로
조립/화이트리스트 검증하도록 바꾸고, 카메라가 박스를 못 잡는 문제를 우회하기 위한
`move_mouse_left` 복사본을 등록한 뒤, ZMQ 어댑터(dry-run)로 끝까지 한 번 실행해 검증했다.

## 사용자 요청

- 파싱한 (move, target, direction) 을 **언더스코어로 조립** → `move_box_left` 같은 실행
  커맨드 키를 만들고, 그 키에 부합할 때만 명령으로 넣는다.
- 카메라가 'box' 를 못 잡으므로, 감지 가능한 'mouse' 로 테스트할 **`move_mouse_left`
  복사본**을 만든다.
- ZMQ 띄우고 한 번 실행해본다.

## 변경 내용

- `shared/constants.py`
  - `TRAINED_MOVE_DIRECTIONS` 제거 → `EXECUTABLE_MOVE_COMMANDS = {"move_box_left",
    "move_mouse_left"}` 화이트리스트로 대체.
- `shared/schemas/command.py`
  - `RobotCommand.move_command_key()` 추가 — move 를 `"move_{target}_{direction}"` 로 조립
    (move 아니면 None).
- `language/main.py` `handle_user_input` move 분기:
  - ① 조립된 키가 `EXECUTABLE_MOVE_COMMANDS` 에 있는지(화이트리스트) → 없으면 `[move 보류]`.
  - ② 대상 감지 게이팅(box→BOX_LABELS, 그 외→라벨 직접) → 없으면 `[move 보류]`.
  - 둘 다 통과 시 `[move 명령 조립] {key}` 출력 후 발행.
- `language/zmq_pub/instruction_publisher.py`
  - envelope 에 `command_key`(조립된 키) 메타데이터 추가.
- `language/llm/prompt_builder.py`
  - move 규칙에 mouse 예시 추가("마우스 왼쪽으로 옮겨" → target="mouse", direction="left").
- 테스트: `move_command_key` 조립/None 케이스 2개 추가 → 전체 **113 passed**.

## 조립 규칙

```
입력 "마우스 왼쪽으로 옮겨"
  → action=move, target=mouse, direction=left   (LLM 파싱)
  → key = "move_" + target + "_" + direction = "move_mouse_left"   (조립)
  → EXECUTABLE_MOVE_COMMANDS 에 있음 → 통과
  → mouse 감지됨 → 통과
  → instruction "Move the mouse to the left" 발행
```

`move_box_left` 는 box 게이팅(BOX_LABELS) 에 막혀(카메라가 박스 못 잡음) 현재는 실행
보류됨. `move_mouse_left` 는 mouse 가 COCO 라벨이라 게이팅 통과 → 파이프라인 테스트 가능.

## 실행 검증 (ZMQ dry-run, 격리 포트 :5558)

사용자 UI(:5557)를 건드리지 않으려 :5558 로 격리 실행:

```bash
# 1) dry-run 어댑터 (lerobot/GPU 없이 ZMQ 구독만)
.venv/bin/python -m scripts.rollout_with_zmq_task \
  --instruction-endpoint tcp://127.0.0.1:5558 --dry-run

# 2) Language(신규 코드)로 발행 — INSTRUCTION_PUB_BIND=tcp://*:5558,
#    vision 에 mouse 주입 후 handle_user_input("마우스 왼쪽으로 옮겨")
```

결과:
```
[move 명령 조립] move_mouse_left
[instruction] Move the mouse to the left
[ZMQ 발행 → LeRobot] tcp://*:5558
→ 어댑터: [dry-run] task ← 'Move the mouse to the left' (#1)
```

→ 실모드(`--dry-run` 제거 + lerobot venv + SmolVLA 정책 로드 + follower)였다면 이 task 가
`SyncInferenceEngine._task` 로 핫스왑되어 다음 스텝부터 로봇이 움직인다.

## 실로봇으로 끝까지 가려면 (다음 단계)

1. overhead/gripper 비전 ON (이미 가능).
2. 실모드 어댑터 실행 (GPU, :5557):
   ```bash
   HF_HUB_OFFLINE=1 .venv/bin/python -m scripts.rollout_with_zmq_task \
     --instruction-endpoint tcp://127.0.0.1:5557 --initial-task "do nothing" -- \
     --robot.type=so101_follower --robot.port=/dev/so101_follower --robot.id=so101_follower \
     --robot.cameras='{...overhead,gripper...}' \
     --policy.path=yeopeter1031/so101_smolvla_move_box_left --policy.device=cuda \
     --task="do nothing" --fps=25 --duration=120
   ```
3. Language UI(신규 코드) 재시작 후 "마우스 왼쪽으로 옮겨" 입력.
   주의: mouse 전용 정책은 없어 로드된 move_box_left 정책이 동작 → 동작 품질은 box 기준.
