# 2026-07-15 — ACT 쓰레기-모으기 트리거 게이트 + 3창 파이프라인 통합

## 배경
donghee-ai/PAI-Language + yeounhyeok/PAI-Vision + 이번에 학습한 LeRobot 정책
(`danny1002/act-trash-gathering`, ACT/양팔)을 창 3개로 띄워 "말 → 로봇" 데모를 구성.

## 핵심 이슈: ACT는 언어 비조건부
기존 ZMQ instruction 파이프라인(`rollout_with_zmq_task.py`, `EXECUTABLE_MOVE_COMMANDS`)은
언어 조건부 SmolVLA(`move_box_left`)용으로 설계됨. 그런데 붙일 모델은 **ACT** 라
instruction '내용'으로 행동이 바뀌지 않고 학습된 단일 태스크(쓰레기 모으기)만 수행한다.
→ 해결: **Language가 의미 게이트를 담당** — 사용자 입력이 쓰레기-모으기 의도(키워드)일
때만 5557로 트리거 발행. 그 외 입력은 대화 답변만, 로봇 미실행.

## 변경 (PAI-Language)
- `shared/schemas/command.py`: `ActionType.TRASH_GATHER` 추가 + `_derive_instruction`에서
  `"trash_gathering"`(학습 task명) 반환.
- `shared/constants.py`: `TRASH_KEYWORDS_DEFAULT`(쓰레기/모아/치워/정리/trash/gather…),
  `TRASH_TASK_INSTRUCTION="trash_gathering"`.
- `language/config.py`: `trash_keywords`(env `TRASH_KEYWORDS`로 조정).
- `language/main.py`: `_is_trash_intent()` 게이트. `handle_user_input`에서 쓰레기 의도일
  때만 `TRASH_GATHER` 커맨드를 만들어 5557 발행(그 외 미발행). 기존 move 화이트리스트
  실행경로는 이 ACT 셋업에선 트리거 게이트로 대체.
- `.env`: OpenAI 값은 USB-DANNY/.env 에서 병합, `INSTRUCTION_PUB_ENABLED=1`.

## 신규 (PAI-setup)
- `scripts/run-trash-zmq.sh` — 컨테이너 내부 롤아웃(bi_so_follower + **ZMQ 카메라** front/wrist).
- `scripts/rollout-trash-zmq-host.sh` — 호스트 래퍼(도커+CUDA13/cuDNN 마운트+PAI-Language 마운트).
- `scripts/pai-run-all.sh` — 3창 런처(Vision→Language UI→LeRobot).
- `PAI-3WINDOW-RUNBOOK.md` — 실행/검증 런북.

## 검증 결과 (2026-07-15)
- 기존 pytest 113개 통과. TRASH_GATHER envelope `instruction='trash_gathering'` 확인.
- **5557 채널 E2E**(실 Publisher↔Subscriber): trash 커맨드 → 어댑터가 task 수신 ✓.
- **Vision 단독**: WS:8000 + ZMQ:5555 바인딩, 카메라 2대(front=idx2/wrist=idx0),
  YOLO **GPU(cuda:0)** 구동, 5555 프레임 이름 `front`/`wrist` ✓, scene `front`/`wrist` 200,
  `overhead` 404.
- **전체 소프트웨어 E2E**(Vision + 실제 OpenAI + dry-run 5557 수신):
  - "쓰레기 좀 모아줘" → 발행 1건 ✓
  - "마우스 집어줘" / "안녕? 뭐 보여?" → 미발행 ✓
  - dry-run 수신 `trash_gathering` 1건 ✓

## 미결/주의
- **실제 로봇 롤아웃(팔 물리 구동)은 아직 미실행** — 안전 확인 후 진행 예정.
- **overhead 카메라 없음**: `.env`의 `VISION_WS_URL=...?camera_id=overhead` 는 404라
  Language 장면 컨텍스트가 항상 비어 있음(트리거엔 무관). 장면 인지 답변을 원하면
  `?camera_id=front` 로 바꾸거나 overhead 카메라 추가 필요.
- torch 2.13+cu130 host YOLO는 GPU 정상이었으나 sm_110 장시간 안정성은 지속 관찰.
