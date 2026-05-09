# PAI-Language 시스템 아키텍처

## 1. 프로젝트 개요

LeRobot SO-ARM 기반 로봇 팔이 공을 집어 바구니에 담는 작업을 수행하는 시스템.
세 파트(Vision, Language, Action)가 중앙 Coordinator를 통해 통신하는 모노레포 구조.

| 파트        | 담당   | 역할                                                                |
| ----------- | ------ | ------------------------------------------------------------------- |
| Vision      | 팀원 A | YOLO를 통한 객체 감지, 위치 정보 제공                               |
| Language    | 담당자 | 사용자 자연어 수신 → OpenAI API → 구조화 명령 생성                  |
| Action      | 팀원 B | LeRobot SO-ARM 제어 실행                                            |
| Coordinator | (공동) | WebSocket / ROS2 양쪽을 관리하는 중앙 브로커 (Phase 2 도입 예정)    |

---

## 2. 전체 토폴로지

본 시스템은 두 단계를 거쳐 진화한다.

### 2.1 Phase 1 — 현재: Vision 직결합 (2026-05-08~)

```text
┌──────────────────────────────────────────────────────────────┐
│                  PAI-Language (Phase 1: 직결합)               │
│                                                              │
│   [User]                                                     │
│     │ stdin (자연어)                                         │
│     ▼                                                        │
│  [Language] ──────── WS (vision_update 수신만) ─────► [Vision = WS 서버] │
│     │                                                        │
│     ▼ stdout                                                 │
│  [명령 파싱 결과 출력]   ※ robot_command 미전송              │
│                                                              │
│   ※ Coordinator 미도입 — robot_command/action_status 비활성  │
└──────────────────────────────────────────────────────────────┘
```

**Phase 1 핵심:**

- PAI-Vision이 이미 WS 서버 (`@app.websocket("/ws/scenes")`)
- PAI-Vision이 표준 envelope(`{type, timestamp, sender, data}`) 형태로 송출 (PAI-Vision `app/main.py`의 `_build_scene_envelope`). PAI-Language 측 별도 어댑터 불필요.
- `Config.coordinator_enabled = False` 기본값 → 명령은 stdout 출력만
- 본 단계는 Coordinator 스펙이 확정될 때까지의 임시 구조이며, Phase 2 도입 시 일괄 전환된다.

### 2.2 Phase 2 — 합의됨(2026-05-09): PAI-Coordinator 중앙 허브

```text
PAI-Vision ──► PAI-Coordinator ◄── PAI-Language
                     │
                     ▼
              PAI-Action / ROS2
                     │
                     ▼
                 Real Robot
```

**Phase 2 핵심 원칙:**

- **전용 Coordinator 모듈**이 WebSocket과 ROS2 양쪽을 모두 관리하는 단순 브로커 역할
- Vision / Language / Action은 각자 모델 연산만 담당하는 **단일 모듈**로 단순화
- Vision / Language / Action 모두 Coordinator에 클라이언트로 접속
- Coordinator가 `vision_update`를 Language에 relay
- Language → Coordinator로 `robot_command` 송신 → Action이 수신 후 실행
- Action → Coordinator로 `action_status` 송신 → Language로 relay
- 어차피 ROS2도 써야 하고 WebSocket은 이미 갖춰져 있으니, 중앙에 허브 하나 두고 두 통신을 모두 거기서 처리하자는 결론

이 변경에 따른 PAI-Language 측 영향:

- `shared/`의 스키마·상수는 결국 Coordinator 모듈로 이전될 운명 (현재는 PAI-Language 내부에 임시 거주)
- WebSocket 연결 방식 자체는 Coordinator 스펙 확정 시점에 한꺼번에 변경 예정 — 그 전까지는 Phase 1(Vision 직결합) 유지

---

## 3. 모노레포 디렉토리 구조

```text
PAI-Language/
│
├── shared/                         # 공통 인터페이스 계약 (Phase 2에서 Coordinator로 이전 예정)
│   ├── schemas/
│   │   ├── vision.py               # YOLO 출력 Pydantic 모델
│   │   └── command.py              # Language→Coordinator 명령 모델
│   └── constants.py                # WS URL, 토픽 이름, 레이블 상수
│
├── language/                       # 자연어 처리 파트 (담당자)
│   ├── main.py                     # 진입점, 이벤트 루프 조율
│   ├── config.py                   # 환경변수, OpenAI key, WS URL
│   ├── ws/
│   │   ├── client.py               # WS 연결 및 재연결 관리
│   │   └── dispatcher.py           # 수신 메시지 type별 핸들러 라우팅
│   ├── input/
│   │   └── cli_handler.py          # asyncio stdin → user_input 이벤트
│   ├── context/
│   │   └── vision_state.py         # 최신 YOLO 결과 보관, 관심 객체 필터링
│   └── llm/
│       ├── openai_client.py        # OpenAI API 비동기 래퍼
│       ├── prompt_builder.py       # user_input + vision_context → 프롬프트
│       └── response_parser.py      # LLM 출력 → RobotCommand 구조체 파싱
│
├── tests/                          # 단위 / E2E 테스트
│   ├── test_response_parser.py
│   ├── test_vision_state.py
│   ├── test_prompt_builder.py
│   ├── test_dispatcher.py
│   └── test_llm.py
│
├── logs/                           # 작업 로그 (날짜별 마크다운)
│
└── docs/
    ├── architecture.md             # 이 문서
    └── command_schema.md           # Language↔Coordinator 인터페이스 스키마
```

---

## 4. 파트별 역할 상세

### Vision

- YOLO 모델로 카메라 프레임 실시간 분석
- 감지된 객체(label, bbox, center_pixel 등) JSON을 `vision_update` 메시지로 송출
- Phase 1: 자체 WS 서버(`/ws/scenes`)로 송출 → Language가 직접 클라이언트로 접속
- Phase 2: Coordinator로 송신 → Coordinator가 Language로 relay
- 출력 형식: `shared/schemas/vision.py` 참조

### Language (담당 파트)

- CLI(stdin)로 사용자 자연어 명령 수신
- `vision_update`에서 최소 context 추출 (label, center_pixel)
- `prompt_builder`가 "사용자 입력 + 현재 감지 객체"를 합쳐 OpenAI에 전달
- LLM 출력을 파싱해 `robot_command` 메시지를 생성
- Phase 1: stdout 출력만
- Phase 2: Coordinator로 `robot_command` 송신, Coordinator가 relay한 `action_status`를 사용자에게 출력

### Action

- LeRobot SO-ARM 실행
- Phase 2: Coordinator로부터 `robot_command` 수신 → 실행 후 `action_status` 송신

### Coordinator (Phase 2)

- WebSocket 서버 + ROS2 노드를 동시에 관리하는 중앙 브로커
- Vision / Language / Action 클라이언트 연결 관리
- `vision_update` 를 Language로 relay
- `robot_command` 를 Action으로 전달
- `action_status` 를 Language로 relay

---

## 5. WebSocket 메시지 타입

전체 메시지는 공통 envelope을 사용한다. 상세 스키마는 `docs/command_schema.md` 참조.

### Phase 1 (현재 — Vision 직결합)

| type            | 방향              | 설명                                                       |
| --------------- | ----------------- | ---------------------------------------------------------- |
| `vision_update` | Vision → Language | PAI-Vision이 표준 envelope으로 직접 송출 (어댑터 불필요)   |
| `robot_command` | (미전송)          | 송신 대상 없음 — stdout 출력만                             |
| `action_status` | (미수신)          | 송신 주체 없음                                             |

### Phase 2 (Coordinator 도입 후)

| type            | 방향                   | 설명                          |
| --------------- | ---------------------- | ----------------------------- |
| `vision_update` | Vision → Coordinator   | YOLO 프레임 감지 결과         |
| `vision_update` | Coordinator → Language | 위 메시지를 relay             |
| `robot_command` | Language → Coordinator | 파싱된 로봇 명령              |
| `robot_command` | Coordinator → Action   | 위 메시지 전달                |
| `action_status` | Action → Coordinator   | 명령 실행 상태                |
| `action_status` | Coordinator → Language | 위 메시지를 relay             |

---

## 6. Language 파트 내부 데이터 흐름

```text
[User]
  │ stdin 자연어 입력
  ▼
[cli_handler.py]
  │ user_text 이벤트
  ▼
[main.py / orchestrator] ◄────── vision_context ──── [vision_state.py]
  │                                                        ▲
  │                                               [dispatcher.py]
  │                                                        ▲
  │                                               WS (Phase 1: Vision / Phase 2: Coordinator)
  │
  ▼
[prompt_builder.py]
  user_text + vision_context → 시스템 프롬프트 조합
  │
  ▼
[openai_client.py] ───► OpenAI API
  │
  ▼
[response_parser.py]
  LLM JSON 출력 → RobotCommand 구조체 + 유효성 검증
  │
  ▼
┌────────── coordinator_enabled? ──────────┐
▼                                          ▼
Phase 1 (False)                     Phase 2 (True)
stdout 출력만                       [ws/client.py] ───► Coordinator (robot_command 송신)
                                                         │
                                                         ▼
                                    [dispatcher.py] ◄─── Coordinator (action_status 수신)
                                                         │
                                                         ▼
                                    [cli_handler.py] → 사용자에게 결과 출력
```

---

## 7. Language가 Vision에서 추출하는 최소 Context

전체 YOLO JSON을 수신하되 `vision_state.py`에서 필터링 후 보관:

```text
보관 필드: label, center_pixel, confidence, status
제거 필드: bbox_xyxy, area_pixels, frame_id, inference_ms, loop_fps 등

→ OpenAI 프롬프트에 삽입하는 형태 예시:
   "현재 카메라: ball(화면 중앙 좌측, 신뢰도 0.91), basket(화면 우측, 신뢰도 0.87)"
```

---

## 8. 기술 스택

| 항목        | 선택                                   |
| ----------- | -------------------------------------- |
| 언어        | Python 3.10+                           |
| WebSocket   | `websockets` 라이브러리 (asyncio 기반) |
| OpenAI      | `openai` SDK (async)                   |
| 데이터 검증 | `pydantic` v2                          |
| 비동기      | `asyncio`                              |
| 로봇 제어   | LeRobot + SO-ARM100                    |
| 객체 감지   | YOLO11s-seg                            |

---

## 9. 미결 사항

| 항목                          | 상태                                     | 비고                                                    |
| ----------------------------- | ---------------------------------------- | ------------------------------------------------------- |
| Coordinator 모듈 구현         | **미구현 — Vision 직결합으로 임시 우회** | 완성 시 `COORDINATOR_WS_URL` 추가 + 연결 대상 전환      |
| Envelope 표준 wire 적용       | PAI-Vision 측에서 이미 적용              | Coordinator 도입 시 동일 envelope을 그대로 사용         |
| `robot_command` 스키마 필드   | 초안 작성 완료, Action팀 합의 필요       | `docs/command_schema.md`                                |
| YOLO target label 목록 확정   | Vision팀과 합의 필요                     | ball, basket 등                                         |
| OpenAI 모델 선택              | 추후 결정                                | 초안: gpt-4o-mini                                       |
| `shared/` → Coordinator 이전  | Phase 2 도입 시                          | 스키마·상수의 단일 출처를 Coordinator 레포로 이동       |
