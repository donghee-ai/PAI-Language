# PAI-Language

LeRobot SO-ARM 기반 로봇 팔이 사용자 자연어를 따라 물체를 조작하는 PAI(Physical AI) 시스템의 **Language 파트**.

사용자 입력을 PAI-Vision의 실시간 장면 정보와 함께 OpenAI API에 넘겨, 한 번의 호출로

- **일상 대화** ("안녕?", "밥은 먹었어?") → 일반 LLM처럼 자연스럽게 응답
- **카메라 질문** ("지금 뭐가 보여?") → 현재 감지된 객체를 근거로 답변
- **로봇 명령** ("마우스 집어줘") → 구조화된 `robot_command`로 변환
- **복합 입력** ("저기 공 보여? 저거 바구니에 넣어줘") → 답변 + 명령 동시 추출

을 처리한다. 어떤 종류의 입력인지는 LLM이 Vision context와 함께 보고 직접 분류한다.

| 파트         | 역할                                                                       |
| ------------ | -------------------------------------------------------------------------- |
| Vision       | YOLO 기반 객체 감지, 위치/라벨 정보 제공                                    |
| **Language** | 사용자 자연어 수신 → Vision context 결합 → OpenAI → 대화 응답 / 명령 생성   |
| Action       | LeRobot SO-ARM 제어 실행                                                    |
| Coordinator  | WebSocket / ROS2 양쪽을 관리하는 중앙 브로커 (예정 — 아래 "현재 통신 구조") |

데모 시나리오: **"스포츠볼 집어서 그릇에 넣어줘"** (COCO 라벨 `sports ball` → `bowl`).

---

## 설치 & 실행

> 요약: ① `pip install -r requirements.txt` → ② `.env`에 `OPENAI_API_KEY` 넣기 → (③ `PAI-Vision/`에서 `python -m app.adapters.run_all` — 카메라 쓸 때) → ④ `PAI-Language/`에서 `python -m language.ui`

### 1. 설치 (한 번만)

Python 3.10+ 가 필요하다. 가상환경(venv 또는 conda) 사용을 권장한다.

```bash
# PAI-Language/ 안에서
python -m venv .venv
# Windows:  .venv\Scripts\activate     |  macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

데스크톱 UI가 쓰는 `tkinter`는 Python 표준 라이브러리라 별도 설치가 필요 없다 (일부 Linux 배포판은 `python3-tk` 패키지 필요).

### 2. 환경변수 설정 (`.env`)

프로젝트 루트(`PAI-Language/`)에 `.env` 파일을 만든다:

```env
OPENAI_API_KEY=sk-...                              # 필수 — OpenAI API 키
OPENAI_MODEL=gpt-4o-mini                           # 선택, 기본값 gpt-4o-mini
VISION_WS_URL=ws://localhost:8000/ws/scenes        # 선택, PAI-Vision의 /ws/scenes URL (기본값이 이 값)
```

키가 없거나 잘못되면 시작 시 바로 알려준다(UI는 오류창, CLI는 메시지). 원격 PAI-Vision 예: `VISION_WS_URL=wss://vision.yeoun.org/ws/scenes`.

### 3. (선택) PAI-Vision 먼저 띄우기

카메라 질문("지금 뭐 보여?")이나 명령에 장면 정보를 쓰려면 **PAI-Vision이 먼저 떠 있어야 한다.** 별도 레포 `PAI-Vision/`에서(설치는 그쪽 README 참고):

```bash
# PAI-Vision/ 안에서
python -m app.adapters.run_all
```

→ 카메라 + YOLO11s-seg 실시간 추론 + `http://localhost:8000` (`/ws/scenes`로 장면 송출). 이걸 띄우지 않아도 PAI-Language는 그대로 실행되며, 일상 대화와 명령 파싱은 정상 동작한다 — 다만 Vision 상태줄이 "(대기 중)"으로 남고 카메라 질문엔 보이는 객체 정보가 비어 있다. PAI-Vision은 나중에 켜도 자동으로 붙는다.

### 4. PAI-Language 실행

반드시 **프로젝트 루트**(`PAI-Language/`)에서, 가상환경을 활성화한 상태로 실행한다 — `shared/` 패키지 인식을 위해.

```bash
python -m language.ui      # 데스크톱 UI (Tkinter) — 권장
# 또는
python -m language.main    # CLI (터미널 한 창)
```

- **UI** (`language.ui`): 상단에 현재 Vision 장면 한 줄 + 사용 중인 LLM 모델, 가운데 채팅창, 아래 입력칸 + "보내기" 버튼. Enter 또는 버튼으로 전송, `quit`/`exit`/`q` 입력 시 종료. 카메라 프레임·HTTP 같은 잡음 로그는 화면 대신 `logs/ui_session.log`로 간다.
- **CLI** (`language.main`): 같은 동작을 터미널에서. `quit`/`exit` 또는 Ctrl+C로 종료. (이쪽은 Vision INFO 로그가 같은 창에 섞여 나온다.)
- 두 진입점 모두 동일한 `LanguageApp`을 구동한다 — 차이는 입출력 표면뿐.

### 5. 입력해 보기 (UI / CLI 공통 출력)

```text
나> 지금 화면에 뭐가 보여?
[답변] 현재 화면에는 마우스, 키보드, 그리고 사람이 보입니다.
[근거] 카메라가 인식한 객체 정보를 바탕으로 답변했습니다.

나> 그러면 마우스를 들어서 키보드 위에 올려줘
[답변] 네, 마우스를 키보드 위에 올려드릴게요.
[근거] 사용자가 마우스를 키보드 위에 올려달라고 요청했습니다.
[명령 파싱] action=pick_and_place, target=mouse, destination=keyboard
[근거] 마우스를 키보드 위에 올리는 복합 동작 요청
[명령 미전송 — 송신 대상 없음]
```

UI에서는 `[답변]`은 본문 색, `[근거]`·`[명령 …]` 등 처리 흔적 라인은 회색으로 구분 표시된다(디버깅 가시성). `[명령 미전송 …]`은 아래 "현재 통신 구조" 참조 — Coordinator 도입 후에는 `[명령 전송]` + `[Action] received | …` 실행 피드백으로 바뀐다.

---

## LLM 응답 모델

LLM은 항상 다음 wrapper를 출력하고, `response_parser`가 `LLMResponse`로 검증한다:

```text
LLMResponse
├── answer    : AssistantAnswer   # 항상 — 사용자에게 보일 자연어 답변 (빈 문자열 불가)
├── command   : RobotCommand?     # 명령 의도가 있을 때만 — pick / place / pick_and_place / stop
└── reasoning : str               # 이 입력을 대화/질문/명령 중 무엇으로 봤는지의 근거
```

- 순수 대화·질문이면 `command`는 `None`.
- LLM 출력이 깨졌으면 placeholder 답변 + `stop` 명령으로, `command`만 잘못됐으면 답변은 보존하고 `command`만 `stop`으로 회귀한다.
- `robot_command` 자체의 필드 스펙은 [docs/command_schema.md](docs/command_schema.md).

---

## 현재 통신 구조 (Vision 직결합)

```text
[User] ──(CLI stdin / Tkinter 입력칸)──► [Language] ──WS client──► [PAI-Vision = WS 서버 /ws/scenes]
                                              │
                                              └─ emit 싱크 (CLI=stdout / UI=채팅창):
                                                 답변 + (명령 있으면) robot_command 파싱 결과
                                                 ※ robot_command는 wire로 미전송
```

- PAI-Vision이 이미 `/ws/scenes`를 표준 envelope(`{type, timestamp, sender, data}`)으로 송출하므로, Language는 **클라이언트로 직접 접속**해 `vision_update`만 수신한다.
- 명령을 받아줄 상대(Coordinator)가 아직 없어 `robot_command`는 **전송하지 않고 파싱 결과만 화면에 출력**한다.
- 이 구조는 PAI-Vision 실시간 송출과 함께 로컬 E2E로 동작 확인됨 (2026-05-13, [logs/2026-05-13_vision-language-e2e-verified.md](logs/2026-05-13_vision-language-e2e-verified.md)).

**예정 — PAI-Coordinator 중앙 허브:** WebSocket·ROS2를 모두 관리하는 전용 브로커를 두고 Vision/Language/Action이 각각 클라이언트로 접속하는 구조. 도입 시 Language는 Coordinator로 `robot_command`를 송신하고 `action_status`를 피드백받으며, 본 레포의 `shared/`(스키마·상수)는 Coordinator 쪽으로 이전된다. `COORDINATOR_WS_URL` 같은 변수가 추가될 예정. 상세는 [docs/architecture.md](docs/architecture.md).

---

## 프로젝트 구조

```text
PAI-Language/
├── shared/                       # 세 파트 공통 인터페이스 (Coordinator 도입 시 그쪽으로 이전 예정)
│   ├── constants.py              # WS URL, 토픽 이름, COCO 라벨 상수
│   └── schemas/
│       ├── vision.py             # vision_update Pydantic 모델
│       ├── command.py            # robot_command Pydantic 모델
│       └── llm_response.py       # LLMResponse (answer 필수 + command Optional)
│
├── language/                     # 자연어 처리 파트 (본 모듈)
│   ├── main.py                   # CLI 진입점, 이벤트 루프 조율 (LanguageApp; emit 출력 싱크 주입 가능)
│   ├── ui.py                     # 데스크톱 UI 진입점 (Tkinter; LanguageApp을 백그라운드 asyncio 루프에서 구동)
│   ├── config.py                 # 환경변수 + 가드(validate)
│   ├── input/
│   │   └── cli_handler.py        # asyncio stdin → user_input 이벤트
│   ├── context/
│   │   └── vision_state.py       # vision_update 최신 상태 보관 + 라벨 조회
│   ├── llm/
│   │   ├── openai_client.py      # OpenAI API 비동기 래퍼
│   │   ├── prompt_builder.py     # user_input + vision_context → 프롬프트
│   │   └── response_parser.py    # LLM 출력 → LLMResponse 파싱 (+ stop fallback)
│   └── ws/
│       ├── client.py             # WS 연결/재연결 관리
│       └── dispatcher.py         # 수신 메시지 type별 핸들러 라우팅
│
├── tests/                        # pytest (단위 + 대화형 E2E)
│   ├── test_response_parser.py
│   ├── test_llm_response_schema.py
│   ├── test_prompt_builder.py
│   ├── test_vision_state.py
│   ├── test_dispatcher.py
│   └── test_llm.py               # 실제 OpenAI 호출 + 사용자 입력 — 별도 실행
│
├── docs/
│   ├── architecture.md           # 토폴로지·진화 단계 상세
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
[User] (CLI stdin / UI 입력칸)
   │
   ▼
[cli_handler] / [ui.py]  ──►  [LanguageApp.handle_user_input]  ◄── [vision_state] ◄── [dispatcher] ◄── WS(PAI-Vision)
                                       │
                                       ▼
                               [prompt_builder]  (user_text + vision_context)
                                       │
                                       ▼
                               [openai_client] ───► OpenAI API
                                       │
                                       ▼
                               [response_parser] ──► LLMResponse (answer 필수 + Optional command)
                                       │
                          ┌────────────┴───────────────┐
                          ▼                            ▼
                  answer → emit 싱크로            command 있으면:
                  항상 출력                       Phase 1 — 파싱 결과만 emit 싱크로 출력
                                                  (Coordinator 도입 후 — envelope로 감싸 송신)
```

**Vision context 추출 규칙** (전체 YOLO JSON 중 Language가 실제로 쓰는 필드):

| 필드                     | 용도                    |
| ------------------------ | ----------------------- |
| `objects[].label`        | 어떤 객체가 보이는지    |
| `objects[].center_pixel` | 대략적 위치 (화면 기준) |
| `objects[].confidence`   | 감지 신뢰도             |
| `objects[].status`       | tracked 여부            |

→ 프롬프트 삽입 형태: `"현재 카메라: sports ball(위치=[674,188], 신뢰도 0.91), bowl(위치=[980,540], 신뢰도 0.87)"`

---

## WebSocket 메시지 타입

전 메시지는 공통 envelope `{type, timestamp, sender, data}` 사용. 상세는 [docs/command_schema.md](docs/command_schema.md).

| type            | 현재(Vision 직결합)                              | Coordinator 도입 후                     |
| --------------- | ------------------------------------------------ | --------------------------------------- |
| `vision_update` | Vision → Language (직접 수신)                     | Vision → Coordinator → Language (relay)  |
| `robot_command` | 미전송 — 파싱 결과만 화면 출력                    | Language → Coordinator → Action          |
| `action_status` | 미수신 — 송신 주체 없음                           | Action → Coordinator → Language (relay)  |

---

## 테스트

프로젝트 루트(`PAI-Language/`)에서:

```bash
pytest tests --ignore=tests/test_llm.py
```

`tests/test_llm.py`는 실제 OpenAI 호출 + 사용자 입력이 필요한 대화형 E2E라 별도 실행:

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
| 데스크톱 UI | `tkinter` (표준 라이브러리)         |
| 객체 감지   | YOLO11s-seg (PAI-Vision 측)         |
| 로봇 제어   | LeRobot + SO-ARM100 (PAI-Action 측) |

---

## 상세 문서

- [시스템 아키텍처](docs/architecture.md)
- [robot_command / action_status 스키마](docs/command_schema.md)
- 작업 로그: [logs/](logs/)
