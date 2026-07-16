# 2026-07-16 — 청소(트리거) 명령 2초 시작 지연

## 배경 / 목적
청소(쓰레기-모으기) 명령을 받으면 곧바로 로봇이 움직여, 사용자가 손을 뺄 틈이 없었다.
**명령 수신 후 2초 대기했다가 실행을 시작**하도록 지연을 추가했다. 정지 명령은 기존대로
즉시 처리(지연 없음).

## 동작 (확정 가정)
- 청소 명령 수신 → **2초 대기**(그동안 초기 대기 자세 유지) → 실행 시작.
- exec-seconds 창은 **지연이 끝난 시점부터** 카운트(지연이 구동 시간을 잡아먹지 않음).
- 대기 중(pending) 정지가 오면 **청소를 취소**하고 시작하지 않는다. 실행 중 정지는 즉시 멈춤.
- 지연은 `--start-delay`(기본 2.0초) 로 조정. 0 이하면 즉시 시작. 게이팅(exec-seconds>0)에서만 적용.

## 변경 파일
- **scripts/rollout_with_zmq_task.py**
  - `--start-delay`(기본 2.0) CLI 인자 추가.
  - `TaskState.pending`, `TaskState.pending_start_at` 필드 추가.
  - `_on_msg`(트리거): 즉시 executing 대신 `pending=True`, `pending_start_at=now+delay` 설정.
  - `_gated_get_action`: `pending && now>=pending_start_at` → executing 전환(+`exec_started_at=now`),
    대기 동안엔 hold_action(초기 자세). 정지 시 `pending`도 함께 취소.

Language 쪽은 변경 없음(트리거는 즉시 1회 발행, 지연은 rollout 타이밍에서 처리).

## 검증
- `py_compile` 통과.
- ZMQ E2E(포트 5601, 지연 0.5s): ① 수신 직후 pending·초기자세 유지 → ② 지연 경과 후 실행
  시작+큐 reset → ③ 실행 중 정지=즉시 정지 → ④ 대기 중 정지=청소 취소. 모두 통과.
- 실제 로봇 물리 검증은 창3(rollout) 재시작 후 필요(미검증).

## 적용
창3(rollout) 재시작 시 자동 적용(기본 2초). 다른 값은
`scripts/run-trash-zmq.sh` 의 python 호출에 `--start-delay N` 을 추가해 조정.
