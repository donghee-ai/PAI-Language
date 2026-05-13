# PAI-Language 시스템 아키텍처

## 1. 프로젝트 개요

LeRobot SO-ARM 기반 로봇 팔이 스포츠볼(COCO 라벨 `"sports ball"`)을 집어 그릇(`"bowl"`)에 담는 작업을 수행하는 시스템.
세 파트(Vision, Language, Action)가 중앙 Coordinator를 통해 통신하는 모노레포 구조.
(데모 시나리오: "스포츠볼 집어서 그릇에 넣어줘". 초기에 `ball`/`basket`으로 잡았으나, COCO 사전학습 YOLO에 `basket`이 없어 `bowl`로 변경 — 2026-05-12.)

| 파트        | 담당   | 역할                                                                |
| ----------- | ------ | ------------------------------------------------------------------- |
| Vision      | 팀원 A | YOLO를 통한 객체 감지, 위치 정보 제공                               |
| Language    | 담당자 | 사용자 자연어 수신 → OpenAI API → 대화 응답 / 카메라 질문 답변 / 구조화 명령 생성 (CLI·Tkinter UI) |
| Action      | 팀원 B | LeRobot SO-ARM 제어 실행                                            |
| Coordinator | (공동) | WebSocket / ROS2 양쪽을 관리하는 중앙 브로커 (Phase 2 도입 예정)    |

---

## 2. 전체 토폴로지

본 시스템은 두 단계를 거쳐 진화한다.

### 2.1 Phase 1 — 현재: Vision 직결합 (2026-05-08~, 실연동 확인 2026-05-13)

```text
┌──────────────────────────────────────────────────────────────┐
│                  PAI-Language (Phase 1: 직결합)               │
│                                                              │
│   [User]                                                     │
│     │ stdin(CLI) 또는 Tkinter UI 입력칸 (자연어)             │
│     ▼                                                        │
│  [Language] ──────── WS (vision_update 수신만) ─────► [Vision = WS 서버] │
│     │                                                        │
│     ▼ emit 싱크 (CLI=stdout / UI=채팅창)                     │
│  [답변 + (명령 있으면) 명령 파싱 결과 출력]                  │
│   ※ robot_command 미전송                                     │
│                                                              │
│   ※ Coordinator 미도입 — robot_command/action_status 비활성  │
└──────────────────────────────────────────────────────────────┘
```

**Phase 1 핵심:**

- PAI-Vision이 이미 WS 서버 (`@app.websocket("/ws/scenes")`)
- PAI-Vision이 표준 envelope(`{type, timestamp, sender, data}`) 형태로 송출 (PAI-Vision `app/main.py`의 `_build_scene_envelope`). PAI-Language 측 별도 어댑터 불필요.
- `Config.coordinator_enabled = False` 기본값 → 명령은 화면 출력만
- 사용자 접점은 둘 — CLI 진입점 `python -m language.main`, 데스크톱 UI 진입점 `python -m language.ui`(Tkinter). 둘 다 동일한 `LanguageApp` 을 쓰며, 사용자 대상 출력은 `emit` 싱크로 추상화됨 (CLI=`print`, UI=메인 스레드 큐 경유 채팅창 + Vision 상태줄).
- **2026-05-13 실연동 확인:** PAI-Vision 실시간 송출(`/ws/scenes`)과 함께, 일상 대화 / 카메라 질문 / 로봇 명령 / 복합 입력 자동 분기가 의도대로 동작함을 로컬 E2E 로 확인 ([`logs/2026-05-13_vision-language-e2e-verified.md`](../logs/2026-05-13_vision-language-e2e-verified.md)).
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
│   │   ├── command.py              # Language→Coordinator 명령 모델
│   │   └── llm_response.py         # LLM 응답 wrapper (answer 필수 + command Optional)
│   └── constants.py                # WS URL, 토픽 이름, 레이블 상수
│
├── language/                       # 자연어 처리 파트 (담당자)
│   ├── main.py                     # CLI 진입점, 이벤트 루프 조율 (LanguageApp; emit 출력 싱크 주입 가능)
│   ├── ui.py                       # 데스크톱 UI 진입점 (Tkinter; LanguageApp 을 백그라운드 asyncio 루프에서 구동)
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
│       └── response_parser.py      # LLM 출력 → LLMResponse(answer + Optional command) 파싱
│
├── tests/                          # 단위 / E2E 테스트
│   ├── test_response_parser.py
│   ├── test_vision_state.py
│   ├── test_prompt_builder.py
│   ├── test_dispatcher.py
│   ├── test_llm_response_schema.py # LLMResponse / AssistantAnswer Pydantic 모델 검증
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

- 사용자 자연어 입력 수신 (일상 대화 / 카메라 질문 / 로봇 명령 / 복합) — 입력 채널은 CLI(stdin) 또는 데스크톱 UI(Tkinter 입력칸). 둘 다 같은 `LanguageApp.handle_user_input` 으로 들어간다.
- `vision_update`에서 최소 context 추출 (label, center_pixel)
- `prompt_builder`가 "사용자 입력 + 현재 감지 객체"를 합쳐 OpenAI에 전달
- LLM 출력을 `LLMResponse`로 파싱 — 자연어 답변(`answer`)은 항상 생성, 로봇 명령(`command`)은 사용자 입력에 명령 의도가 있을 때만 추출
- 사용자 대상 출력은 `emit` 싱크로 추상화 — CLI 는 `print`, UI 는 메인 스레드 큐를 거쳐 채팅창에 표시(답변은 본문 색, `[근거]`/`[명령 …]` 등 처리 흔적은 회색으로 구분)
- Phase 1: 답변과 (있으면) 명령 파싱 결과를 화면 출력. `robot_command`는 wire로 미전송
- Phase 2: 답변은 계속 로컬 출력, `command`만 Coordinator로 송신. Coordinator가 relay한 `action_status`는 사용자에게 출력

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
  │ 자연어 입력
  ▼
[cli_handler.py] (CLI)  /  [ui.py] 입력칸 → run_coroutine_threadsafe (UI)
  │ user_text
  ▼
[main.py / LanguageApp.handle_user_input] ◄────── vision_context ──── [vision_state.py]
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
  LLM JSON 출력 → LLMResponse(answer 필수 + Optional command) + 유효성 검증
  │
  ├─► [답변] answer.text 항상 emit 싱크로 출력 (CLI=stdout / UI=채팅창)
  │
  ▼ command is not None?
  ├─ None  → 종료 (순수 대화/질문)
  └─ 있음
     │
     ▼
┌────────── coordinator_enabled? ──────────┐
▼                                          ▼
Phase 1 (False)                     Phase 2 (True)
[명령 파싱] emit 싱크로 출력만      [ws/client.py] ───► Coordinator (robot_command 송신)
                                                         │
                                                         ▼
                                    [dispatcher.py] ◄─── Coordinator (action_status 수신)
                                                         │
                                                         ▼
                                    emit 싱크 → 사용자에게 결과 출력
```

---

## 7. Language가 Vision에서 추출하는 최소 Context

전체 YOLO JSON을 수신하되 `vision_state.py`에서 필터링 후 보관:

```text
보관 필드: label, center_pixel, confidence, status
제거 필드: bbox_xyxy, area_pixels, frame_id, inference_ms, loop_fps 등

→ OpenAI 프롬프트에 삽입하는 형태 예시:
   "현재 카메라: sports ball(위치=[674,188], 신뢰도 0.91), bowl(위치=[980,540], 신뢰도 0.87)"
   (※ 현재 코드는 center_pixel을 raw px로 전달. 의미 구역화는 미적용 — 미결 사항 참조)
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
| 데스크톱 UI | `tkinter` (Python 표준 라이브러리)     |
| 로봇 제어   | LeRobot + SO-ARM100                    |
| 객체 감지   | YOLO11s-seg                            |

---

## 9. 미결 사항

| 항목                          | 상태                                     | 비고                                                    |
| ----------------------------- | ---------------------------------------- | ------------------------------------------------------- |
| Coordinator 모듈 구현         | **미구현 — Vision 직결합으로 임시 우회** | 완성 시 `COORDINATOR_WS_URL` 추가 + 연결 대상 전환      |
| Envelope 표준 wire 적용       | PAI-Vision 측에서 이미 적용              | Coordinator 도입 시 동일 envelope을 그대로 사용         |
| `robot_command` 스키마 필드   | 초안 작성 완료, Action팀 합의 필요       | `docs/command_schema.md`                                |
| YOLO target label 목록 확정   | COCO 80개로 임시 확정 (2026-05-12)       | `shared/constants.py` `COCO_LABELS`. 커스텀 객체(basket 등)는 추후 fine-tuning / open-vocab 필요 |
| OpenAI 모델 선택              | 추후 결정                                | 초안: gpt-4o-mini                                       |
| `shared/` → Coordinator 이전  | Phase 2 도입 시                          | 스키마·상수의 단일 출처를 Coordinator 레포로 이동       |
| LLM 답변(`answer`)의 wire화   | 미정 — 현재 stdout 전용                  | Phase 2에서 `assistant_answer` 같은 신규 메시지 타입을 둘지, 답변은 Language 로컬 출력에만 머물게 둘지 결정 필요 |
