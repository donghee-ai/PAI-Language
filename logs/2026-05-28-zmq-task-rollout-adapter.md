# 2026-05-28 — ZMQ instruction → lerobot-rollout task 자동 갱신 어댑터

PAI-Language UI에서 사용자가 자연어 명령 → LLM이 영어 instruction 생성 → ZMQ
PUB :5557 발행까지는 자동이지만, 거기서 끊겨 사용자가 영어 instruction을 손으로
복사해 `lerobot-rollout --task=` 에 붙여야 했음. 이번 변경으로 language → robot
끝까지 자동 흐름의 코드 경로를 만들었다. 실제 follower / 외부 카메라가 없어
런타임 검증은 보류, 코드 컴파일 + 단위 테스트 완성도까지 마무리.

## 결정 사항 (사용자 합의)

- lerobot 라이브러리 자체에는 손대지 않음 (외부 스크립트만 추가)
- 새 파일은 PAI-Language 안 `scripts/rollout_with_zmq_task.py` 에 둠
- 실행은 lerobot venv 에서 (lazy lerobot import — PAI-Language venv에는 lerobot 미설치)
- 초기 task 기본값: `"do nothing"` (첫 ZMQ instruction 도착 전까지 안전한 값)
- 완료 기준: 코드 컴파일 통과 + 단위 테스트 완성도. 실제 하드웨어 검증은 follower / 외부 카메라 도착 후 별도 단계.

## 동작 원리

### 핵심 helper (`scripts/rollout_with_zmq_task.py`)

- `parse_instruction(raw)` — `language.zmq_pub.instruction_publisher.build_envelope`
  가 만든 envelope JSON에서 `instruction` 영어 문자열만 추출. 빈 문자열/누락/잘못된 JSON/
  비-string 필드/UTF-8 디코드 실패는 모두 `None` 반환 — 호출측이 빈 task로 engine을
  덮어쓰지 않도록.
- `apply_task(engine, task)` — lerobot inference engine의 `_task` 필드를 직접 갱신.
  `SyncInferenceEngine` / `RTCInferenceEngine` 둘 다 task setter가 없고 `__init__`
  에서만 받기 때문에 private 필드를 핫스왑한다. lerobot가 다음 `get_action()` 호출에서
  `self._task` 를 그대로 observation에 넣으므로 다음 step부터 새 task로 추론이 이어진다.
  빈 task는 무시, `_task` 가 없는 객체에는 `AttributeError` (lerobot internal 변경 감지).
- `InstructionSubscriber(threading.Thread)` — `:5557` SUB 소켓을 폴링하면서 envelope이
  들어올 때마다 `on_instruction(text)` 콜백을 호출. `stop_event` 로 깔끔 종료. 멤버
  이름은 `threading.Thread._stop` 메서드와 충돌하지 않게 `_stop_event` 사용.
- `TaskState` — 메인 스레드와 SUB 스레드 사이의 공유 상태 (현재 task, 갱신 시각,
  수신 카운트).

### 메인 entry

CLI 인자는 우리 어댑터 전용 인자만 받고, `--` 이후는 `lerobot-rollout` 표준 CLI로
그대로 forward한다.

```bash
~/lerobot-workspace/.venv/bin/python -m scripts.rollout_with_zmq_task \
    --instruction-endpoint tcp://127.0.0.1:5557 \
    -- \
    --strategy.type=base \
    --policy.path=lerobot/smolvla_base \
    --robot.type=so101_follower \
    --robot.port=/dev/so101_follower \
    --robot.cameras='{front_rgb:{type:zmq, server_address:127.0.0.1, port:5555, camera_name:front_rgb}}' \
    --task='do nothing' \
    --duration=120
```

실 모드 동작:

1. `lerobot.rollout.context.build_rollout_context` 를 monkey-patch — RolloutContext가
   만들어지는 순간 `ctx.policy.inference` (SyncInferenceEngine 또는 RTC) 를 캡처하고
   ZMQ SUB 스레드를 시작한다. lerobot 라이브러리는 변경하지 않고 우리 프로세스 안에서만
   패치.
2. `lerobot.scripts.lerobot_rollout.main()` 을 호출 (sys.argv를 일시 교체해 lerobot
   CLI 인자 그대로 전달). 표준 추론 루프가 그대로 돈다.
3. ZMQ로 새 instruction이 도착할 때마다 `apply_task(engine, text)` 호출 → 다음 step부터
   lerobot이 새 task를 사용.
4. SIGINT/SIGTERM 시 stop_event를 세팅해 SUB 스레드를 정리하고, monkey-patch를 원복.

### dry-run 모드

`--dry-run` 을 주면 lerobot을 import 하지 않고 ZMQ subscriber만 띄워 들어오는
instruction을 stdout에 출력. lerobot venv 없이도 동작하므로 채널 검증 / 디버깅용:

```bash
cd ~/lerobot-workspace/PAI-Language
.venv/bin/python -m scripts.rollout_with_zmq_task --dry-run
```

## 단위 테스트 (`tests/test_rollout_with_zmq_task.py`)

24 테스트, 전체 105 통과 (회귀 없음).

- `parse_instruction` 정상/엣지 11 케이스 — JSON envelope, 빈/누락/비-str/잘못된 JSON/잘못된 UTF-8/dict 아닌 루트. 실제 `build_envelope` 출력과의 라운드트립도 검증.
- `apply_task` 4 케이스 — 정상 갱신, 빈 task 스킵, `_task` 없는 객체 AttributeError, 반복 덮어쓰기.
- `_split_argv` 3 케이스 — `--` 분리, `--` 없음, `--` 끝.
- `build_arg_parser` 2 케이스 — 디폴트, dry-run 플래그.
- `main` 1 케이스 — lerobot 인자 없고 dry-run 도 아니면 usage error 반환.
- `InstructionSubscriber` 2 케이스 (pyzmq 필요) — 실제 PUB→SUB 라운드트립으로 콜백 호출 확인, malformed 메시지(JSON 오류/빈 instruction/필드 누락)는 콜백 무시.
- `TaskState` 1 케이스 — 디폴트 필드.

## 알려진 한계

- **하드웨어 미연결**: SO-101 follower 도, 외부 SO-101 카메라도 현재 미연결. 실모드는
  코드 컴파일 + import 검증까지만. 첫 실제 실행은 하드웨어 도착 후 별도 검증 필요.
- **monkey-patch 의존성**: `lerobot.rollout.context.build_rollout_context` 와
  `lerobot.scripts.lerobot_rollout.main` 의 위치/시그니처가 lerobot 업그레이드 시
  바뀌면 패치가 깨질 수 있음. `_task` private 필드 직접 접근도 동일 위험. lerobot 가
  공개 `set_task()` 를 추가하면 `apply_task` 한 함수만 그쪽으로 swap 하면 된다.
- **multi-cam ZMQ 통합 미해결**: 현재 PAI-Vision 은 [project_pai_vision_multicam] 제약
  때문에 한 ZMQ PUB(:5555)에 한 카메라만 활성. lerobot 쪽 `--robot.cameras=` 에 두
  카메라를 등록하려면 PAI-Vision의 단일 프로세스 multi-cam PUB이 먼저 해결되어야 함.
- **연속 동작 안정성 미검증**: 한 instruction 추론 중에 다음 instruction이 들어오면
  현재는 즉시 `_task` 를 덮어쓴다. 진행 중인 chunk(RTC) 폐기 등 안전한 전환 로직은
  추후 필요시 추가.
- **자체 검증 어려움**: lerobot venv 에서의 실제 import 통합 시험은 follower / 외부
  카메라 도착 후. 현재 단계에서는 import path 가 맞다는 것만 코드 리뷰로 확인.

## 변경 파일

- `scripts/rollout_with_zmq_task.py` (신규) — helpers + main entry
- `tests/test_rollout_with_zmq_task.py` (신규) — 24 단위/통합 테스트
- 본 로그 파일

PAI-Vision / lerobot 라이브러리 측: 변경 없음.

## 다음 단계 후보

1. SO-101 follower 연결 + 외부 카메라 2개 USB 1.3/1.4 포트 연결 후 `lerobot-find-cameras`
   로 OpenCV 인덱스 확정 → `.env` `CAMERAS=` 갱신.
2. 첫 실 모드 dry-run: `--dry-run` 으로 ZMQ 채널만 검증, PAI-Language UI에서 입력 →
   stdout에 task 갱신 로그가 뜨는지 확인.
3. lerobot 실모드 첫 호출: 짧은 duration (예: 10초) + `--task='do nothing'` 으로 정책
   로드 + monkey-patch 가 깨지지 않는지 확인.
4. PAI-Vision 의 multi-cam single-process PUB 구조 정리 (별 작업) — front+wrist 두
   카메라를 한 :5555 PUB 으로 multiplex.
5. RTC inference engine 사용 시 task 전환 도중 chunk 폐기 로직이 필요한지 평가.
