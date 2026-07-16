# 2026-07-16 — "정지" 발화 → 즉시 정지 + ACT 큐 비우기

## 배경 / 목적
쓰레기-모으기 롤아웃이 명령 1건당 `exec_seconds` 동안 구동되는데, 사용자가 도중에
말로 **즉시 멈추게** 할 방법이 없었다. Language UI 에 "정지/멈춰/그만/stop" 을 말하면
실행 중이던 ACT 롤아웃을 즉시 중단하고 ACT 액션 큐/temporal-ensemble 을 비우도록 추가했다.

**정지 시 거동(사용자 확정):** 그 자리 freeze 가 아니라 **초기 대기 자세로 복귀 후 정지**
— 기존 실행창 종료 동작(idle=hold_action=초기 자세)과 동일. ACT 큐는 즉시 비운다.

## 배선
```
PAI-Language UI  ──"정지" 키워드 감지(LLM 왕복 없이 최우선)──▶ ZMQ:5557 발행
   RobotCommand(action=STOP, instruction="stop")
        │
        ▼
rollout_with_zmq_task._on_msg  ── text=="stop" ─▶ executing=False, stop_requested=True
        │  (SUB 스레드는 플래그만 세움)
        ▼
_gated_get_action(다음 제어 스텝, ~50ms 내)  ─▶ engine.reset()(ACT 큐 비움) + hold_action(초기 자세)
```
- 정지는 **LLM 왕복 없이** `handle_user_input` 최상단에서 처리 → 즉각성 확보.
- 정지 판정이 쓰레기-모으기 판정보다 **우선**("쓰레기 그만" → 정지).
- `engine.reset()` 은 반드시 get_action(메인) 스레드에서만 호출(SUB 스레드는 플래그만) → 레이스 방지.
- `parse_instruction` 이 빈 instruction 을 None 으로 버리므로, stop sentinel 은 비지 않은
  `"stop"` 문자열(=`ActionType.STOP.value`) 로 발행.

## 변경 파일
- **shared/constants.py** — `STOP_KEYWORDS_DEFAULT`(정지/멈춰/그만/스톱/stop…), `STOP_TASK_INSTRUCTION="stop"` 추가.
- **language/config.py** — `_parse_stop_keywords()` + `Config.stop_keywords`(env `STOP_KEYWORDS` 로 덮어쓰기).
- **language/main.py** — `_is_stop_intent()`, `_publish_stop()` 추가. `handle_user_input` 최상단에 정지 최우선 분기.
- **scripts/rollout_with_zmq_task.py**
  - `TaskState.stop_requested` 필드 추가.
  - `--stop-instruction`(기본 `"stop"`) CLI 인자 추가.
  - `run_with_lerobot._on_msg`: `text==stop` 분기 → executing=False + stop_requested=True.
  - `_gated_get_action`: `stop_requested` 처리 → executing=False + `engine.reset()` + 초기 자세 복귀.
  - dry-run `_on_msg`: stop 수신 시 `[dry-run] STOP` 출력.

## 검증
- `py_compile` 4개 파일 통과.
- 유닛: STOP 커맨드 → `build_envelope` → `parse_instruction` == `"stop"`(비지 않음 확인), STOP validator(target/dest none), 키워드 매칭·우선순위.
- **ZMQ E2E**(포트 5599, `InstructionPublisher`↔`InstructionSubscriber`):
  trash→executing=True → stop→executing=False+stop_requested=True → 다음 tick=stop-reset(큐 비움)+초기자세 → 재트리거=executing=True(정상 복구). 통과.
- 실제 로봇 물리 검증은 창3(rollout) 재시작 후 UI 에 "정지" 입력으로 확인 필요(미검증).

## 적용 방법(실행 중 세션)
스크립트 수정은 실행 중 프로세스에 반영되지 않으므로, 현재 창2(Language)/창3(rollout)을
재시작해야 정지 기능이 활성화된다. 창3 은 `scripts/rollout-trash-zmq-host.sh 0 25` 로 재기동.
