# PAI-Language

LeRobot SO-ARM 기반 로봇 팔이 사용자 자연어 명령을 따라 물체를 조작하는 PAI(Physical AI) 시스템의 **Language 파트**.
사용자의 자연어 입력을 받아 Vision의 실시간 장면 정보와 결합하여 OpenAI API로 구조화된 `robot_command`로 변환한다.

| 파트         | 역할                                                                |
| ------------ | ------------------------------------------------------------------- |
| Vision       | YOLO 기반 객체 감지, 위치/라벨 정보 제공                            |
| **Language** | 사용자 자연어 수신 → Vision context 결합 → OpenAI → 구조화 명령     |
| Action       | LeRobot SO-ARM 제어 실행                                            |
| Coordinator  | WebSocket / ROS2 양쪽을 관리하는 중앙 브로커 (Phase 2 도입 예정)    |

---

## 아키텍처 진화 단계

본 모듈의 통신 구조는 두 단계를 거친다. 각 단계의 다이어그램은 [docs/architecture.md](docs/architecture.md)에 상세히 기록되어 있다.

### Phase 1 — 현재: Vision 직결합 (2026-05-08~)

```text
[User] ── stdin ──► [Language] ── WS(client) ──► [Vision = WS 서버]
                         │
                         └─ stdout: robot_command 파싱 결과만 출력 (미전송)
```

- PAI-Vision이 이미 `/ws/scenes`를 표준 envelope(`{type, timestamp, sender, data}`)으로 송출하므로 Language는 **클라이언트로 직접 접속**하여 `vision_update`를 수신한다.
- 명령을 받아줄 상대(Coordinator)가 아직 없으므로 `robot_command`는 **wire로 전송되지 않고 stdout으로만 출력**한다.
- 본 단계는 Coordinator 스펙이 확정될 때까지의 임시 구조이며, Phase 2 도입 시 일괄 전환된다.

### Phase 2 — 합의됨(2026-05-09): PAI-Coordinator 중앙 허브

```text
PAI-Vision ──► PAI-Coordinator ◄── PAI-Language
                     │
                     ▼
              PAI-Action / ROS2
                     │
                     ▼
                 Real Robot
```

- **전용 Coordinator 모듈**이 WebSocket과 ROS2 양쪽을 모두 관리하는 단순 브로커 역할.
- Vision / Language / Action은 각자 모델 연산만 담당하는 **단일 모듈**로 단순화된다.
- Language는 Coordinator에 단일 클라이언트로 접속해 `vision_update`를 수신하고 `robot_command`를 송신, `action_status`를 피드백받는다.
- 본 레포 내 `shared/` (스키마·상수)는 Coordinator 도입 시 그쪽으로 이전될 운명이며, 현재는 임시 거주 상태.

---

## 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

Python 3.10+ 필요.

### 2. 환경변수 설정 (`.env`)

프로젝트 루트(`PAI-Language/`)에 `.env` 파일을 생성한다:

```env
OPENAI_API_KEY=sk-...                              # 필수
OPENAI_MODEL=gpt-4o-mini                           # 선택, 기본값 gpt-4o-mini
VISION_WS_URL=ws://localhost:8000/ws/scenes        # 선택, PAI-Vision의 /ws/scenes URL
```

원격 PAI-Vision 사용 예: `VISION_WS_URL=wss://vision.yeoun.org/ws/scenes`.

> Phase 2 도입 시 `COORDINATOR_WS_URL` 등 Coordinator 접속용 변수가 추가될 예정이다.

### 3. 실행

반드시 **프로젝트 루트**(`PAI-Language/`)에서 실행해야 한다 — `shared/` 패키지 인식을 위해.

```bash
python -m language.main
```

### 사용 예시

```text
==================================================
PAI-Language 모듈
  WS: ws://localhost:8000/ws/scenes
  LLM: gpt-4o-mini
  종료: quit / exit / Ctrl+C
==================================================
> 공 잡아서 바구니에 넣어줘
처리 중...
[명령 파싱] action=pick_and_place, target=ball, destination=basket
[근거] 공을 바구니에 담는 복합 동작 요청
[명령 미전송 — 송신 대상 없음]
> quit
종료됨.
```

> Phase 2(Coordinator 도입) 이후에는 마지막 두 줄이 `[명령 전송]` + `[Action] received | …` 같은 실행 피드백으로 바뀐다.

---

## 프로젝트 구조

```text
PAI-Language/
├── shared/                       # 세 파트 공통 인터페이스 (Phase 2에서 Coordinator로 이전 예정)
│   ├── constants.py              # WS URL, 토픽 이름, 라벨 상수
│   └── schemas/
│       ├── vision.py             # vision_update Pydantic 모델
│       └── command.py            # robot_command Pydantic 모델
│
├── language/                     # 자연어 처리 파트 (본 모듈)
│   ├── main.py                   # 진입점, 이벤트 루프 조율
│   ├── config.py                 # 환경변수 + Phase 별 가드(validate)
│   ├── input/
│   │   └── cli_handler.py        # asyncio stdin → user_input 이벤트
│   ├── context/
│   │   └── vision_state.py       # vision_update 최신 상태 보관 + 라벨 조회
│   ├── llm/
│   │   ├── openai_client.py      # OpenAI API 비동기 래퍼
│   │   ├── prompt_builder.py     # user_input + vision_context → 프롬프트
│   │   └── response_parser.py    # LLM 출력 → RobotCommand 파싱 (+ STOP fallback)
│   └── ws/
│       ├── client.py             # WS 연결/재연결 관리
│       └── dispatcher.py         # 수신 메시지 type별 핸들러 라우팅
│
├── tests/                        # pytest (단위 + 대화형 E2E)
│   ├── test_response_parser.py
│   ├── test_vision_state.py
│   ├── test_prompt_builder.py
│   ├── test_dispatcher.py
│   └── test_llm.py               # 대화형 E2E (별도 실행)
│
├── docs/
│   ├── architecture.md           # 토폴로지 상세
│   └── command_schema.md         # robot_command / action_status 스키마
│
├── logs/                         # 작업 로그 (날짜별 마크다운)
├── .env                          # 환경변수 (직접 작성)
├── requirements.txt
└── README.md
```

---

## 내부 데이터 흐름

```text
[User] stdin
   │
   ▼
[cli_handler] ──► [main.handle_user_input] ◄── [vision_state] ◄── [dispatcher] ◄── WS
                          │                                                          ▲
                          ▼                                                          │
                  [prompt_builder] (user_text + vision_context)                      │
                          │                                                          │
                          ▼                                                          │
                  [openai_client] ───► OpenAI API                                    │
                          │                                                          │
                          ▼                                                          │
                  [response_parser] ──► RobotCommand (vision_confirmed 보강)         │
                          │                                                          │
              ┌───────────┴───────────────┐                                          │
              ▼                           ▼                                          │
       Phase 1 (현재)              Phase 2 (Coordinator)                             │
       stdout 출력만               envelope으로 감싸 Coordinator에 송신 ────────────┘
```

**Vision context 추출 규칙** (전체 YOLO JSON 중 Language가 실제로 쓰는 필드):

| 필드                     | 용도                    |
| ------------------------ | ----------------------- |
| `objects[].label`        | 어떤 객체가 보이는지    |
| `objects[].center_pixel` | 대략적 위치 (화면 기준) |
| `objects[].confidence`   | 감지 신뢰도             |
| `objects[].status`       | tracked 여부            |

→ 프롬프트 삽입 형태: `"현재 카메라: ball(화면 중앙 좌측, 신뢰도 0.91), basket(화면 우측, 신뢰도 0.87)"`

---

## WebSocket 메시지 타입

전 메시지는 공통 envelope `{type, timestamp, sender, data}` 사용. 상세 스키마는 [docs/command_schema.md](docs/command_schema.md).

### Phase 1 (현재 단계)

| type            | 방향              | 비고                                                     |
| --------------- | ----------------- | -------------------------------------------------------- |
| `vision_update` | Vision → Language | PAI-Vision이 표준 envelope으로 직접 송출 (어댑터 불필요) |
| `robot_command` | (미전송)          | 송신 대상 없음 — stdout 출력만                           |
| `action_status` | (미수신)          | 송신 주체 없음                                           |

### Phase 2 (Coordinator 도입 후)

| type            | 방향                   | 설명                          |
| --------------- | ---------------------- | ----------------------------- |
| `vision_update` | Vision → Coordinator   | YOLO 프레임 결과              |
| `vision_update` | Coordinator → Language | 위 메시지 relay               |
| `robot_command` | Language → Coordinator | 파싱된 로봇 명령              |
| `action_status` | Coordinator → Language | 명령 실행 상태 피드백 (relay) |

---

## 테스트

프로젝트 루트(`PAI-Language/`)에서 pytest 실행:

```bash
pytest tests --ignore=tests/test_llm.py
```

`tests/test_llm.py`는 OpenAI API 호출 + 사용자 입력이 필요한 대화형 E2E라 별도 실행:

```bash
python -m tests.test_llm
```

---

## 기술 스택

| 항목        | 선택                                |
| ----------- | ----------------------------------- |
| 언어        | Python 3.10+                        |
| WebSocket   | `websockets` (asyncio)              |
| LLM         | OpenAI API (`gpt-4o-mini` 기본)     |
| 데이터 검증 | `pydantic` v2                       |
| 비동기      | `asyncio`                           |
| 객체 감지   | YOLO11s-seg (PAI-Vision 측)         |
| 로봇 제어   | LeRobot + SO-ARM100 (PAI-Action 측) |

---

## 상세 문서

- [시스템 아키텍처](docs/architecture.md)
- [Language ↔ Action 메시지 스키마](docs/command_schema.md)
- 작업 로그: [logs/](logs/)
