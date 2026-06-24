# 2026-06-24 — 원샷 실행 게이팅 (시작 시 무동작)

## 배경
`rollout_with_zmq_task.py` 실모드 첫 실행 시 로봇이 **계속 움직이는** 문제.
원인: lerobot rollout 은 연속 폐루프 제어라, 초기 `--task='do nothing'`(학습된 적
없는 OOD 문구)으로도 정책(`move_box_left`)이 매 스텝 액션을 뱉어 로봇이 멈추지 않음.

## 사용자 결정 (AskUserQuestion)
- **명령당 1회 실행(one-shot)**: 평소 정지, 명령 오면 정해진 시간만 구동 후 다시 정지.
- 추가 요구: **첫 실행에는 절대 움직이지 않게.**
- 신경망 "do nothing 정책" 학습이 아니라 **제어 루프 게이팅**으로 해결.

## 구현 (`scripts/rollout_with_zmq_task.py`)
액션 생성 지점인 `engine.get_action` 을 감싸, idle 동안 **초기 자세(움츠린 시작 포즈)를
계속 명령**해 그 포즈에 능동적으로 고정한다. (처음엔 `None` 반환으로 했으나, 사용자가
"초기 자세 그대로 유지"를 요청 — 토크 스냅/중력 처짐까지 그 포즈로 잡으려면 능동 명령이
더 확실.) 초기 포즈 액션을 못 만들면 `None`(무명령)으로 폴백.

- `TaskState` 에 `executing: bool`, `exec_started_at: float` 추가.
- `--exec-seconds`(기본 8.0) 인자 추가 — 명령 1건당 구동 시간. `<=0` 이면 게이팅 꺼짐(연속 구동 = 기존 동작).
- `_on_msg`(ZMQ instruction 수신): task 갱신과 함께 `executing=True`, `exec_started_at=now`.
- `hooked_build`(engine 캡처 직후):
  - `ctx.hardware.initial_position`(연결 시 캡처한 `<motor>.pos`) + `ctx.data.ordered_action_keys`
    로 **초기 자세 액션 텐서 `hold_action`** 을 1회 생성(키 매칭 검증, 실패 시 None).
  - `engine.get_action` 을 `_gated_get_action` 으로 교체.
    - idle(`executing=False`) → `hold_action` 반환 (정책 추론 스킵 → idle 시 GPU 미사용).
    - 실행 중 + 경과 ≥ exec_seconds → `executing=False` 전환(로그) 후 `hold_action`.
    - 실행 중 + 시간 내 → 원래 get_action 그대로.

## 동작
- 어댑터 기동 직후: **초기(움츠린) 자세 유지**. 로그 `원샷 게이팅 활성 — 시작 시 초기 자세 유지, 명령 1건당 8.0s 만 구동`.
- UI 자연어 명령("마우스 왼쪽으로 옮겨") 수신 → 8초 구동 → `실행 창 종료 → 초기 자세로 복귀/유지` → 초기 포즈로 돌아와 정지.
- 다음 명령까지 초기 포즈 유지.

## 핵심 버그 수정 — 몽키패치 대상 오류 (게이팅·task교체가 아예 안 먹던 원인)
증상: 터미널 3 기동 시 게이팅과 무관하게 로봇이 바로 정책을 구동(계속 움직임).
원인: `lerobot.scripts.lerobot_rollout` 은 `from lerobot.rollout import build_rollout_context`
로 **import 시점에 자기 네임스페이스에 이름을 바인딩**하고 그걸 호출한다. 어댑터는
`lerobot.rollout.context.build_rollout_context`(다른 참조)만 패치해서 **hooked_build 가
한 번도 호출되지 않았다** → engine 캡처 실패 → 게이팅도, task 핫스왑(명령 반영)도 둘 다
무효. 그래서 정책이 초기 task 로 계속 돌고, 시작 직후부터 움직였다.
수정: `from lerobot.scripts import lerobot_rollout as _rollout_mod` 후
`_rollout_mod.build_rollout_context = hooked_build` 로 **실제 호출되는 참조**를 패치
(+ context 서브모듈도 함께, finally 에서 둘 다 원복). 이로써 engine 캡처/게이팅/task교체가
실제로 활성화됨.

## 검증
- `py_compile` OK.
- `tests/test_rollout_with_zmq_task.py` 24 passed (회귀 없음).
- 실로봇 첫 무동작/원샷 거동은 하드웨어로 확인 예정.

## 한계 / 후속
- 실행 창 종료 시 interpolator 에 남은 마지막 청크가 1~2틱 더 흘러 미세 잔여 동작 가능(안전 범위).
- `exec_seconds` 는 시간 기반 고정 — "동작 완료 감지 후 자동 정지"는 아님. 필요 시 정책의 종료 신호/도달 판정으로 고도화 가능.
- 여전히 단일 정책(`move_box_left`)만 로드 — 다른 명령은 별도 정책/스위칭 필요.
