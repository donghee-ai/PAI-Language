# PAI_LE

LeRobot SO-ARM 기반 로봇 팔이 공을 집어 바구니에 담는 작업을 수행하는 시스템.
Vision / Language / Action 세 파트가 WebSocket으로 통신하는 모노레포 구조.

## 시스템 구조

```
[User]
  │ 자연어 입력 (stdin)
  ▼
[Language] ──── robot_command ────► [Action = WS Hub] ──► SO-ARM 제어
  ▲                                      │
  └──────── vision_update (relay) ────────┘
                                          ▲
                                     [Vision]
                                   (YOLO 감지 결과)
```

| 파트     | 역할                                               |
|----------|----------------------------------------------------|
| Vision   | YOLO를 통한 객체 감지, 위치 정보 제공              |
| Language | 사용자 자연어 수신 → OpenAI API → 구조화 명령 생성 |
| Action   | WS Hub 운영, LeRobot SO-ARM 제어 실행              |

## 실행 방법 (Language 파트)

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

프로젝트 루트에 `.env` 파일 생성 (`.env.example` 참고):

```bash
cp .env.example .env
```

`.env` 파일을 열어 OpenAI API 키를 입력:

```
OPENAI_API_KEY=sk-...      # 필수
OPENAI_MODEL=gpt-4o-mini   # 선택 (기본값: gpt-4o-mini)
WS_URL=wss://...           # 선택 (기본값: shared/constants.py 참고)
```

### 3. 실행

반드시 **프로젝트 루트**(`PAI_LE/`)에서 실행해야 합니다. (`shared/` 패키지 인식을 위해)

```bash
python -m language.main
```

### 사용 예시

```
==================================================
PAI_LE Language 모듈
  WS: wss://vision.yeoun.org/ws/scenes
  LLM: gpt-4o-mini
  종료: quit / exit / Ctrl+C
==================================================
> 공 잡아서 바구니에 넣어줘
처리 중...
[명령 전송] action=pick_and_place, target=ball, destination=basket
[근거] 공을 바구니에 담는 복합 동작 요청
> quit
종료합니다.
```

## 프로젝트 구조

```
PAI_LE/
├── shared/                   # 세 파트 공통 인터페이스 (스키마, 상수)
│   ├── constants.py
│   └── schemas/
│       ├── command.py        # robot_command 스키마
│       ├── vision.py         # vision_update 스키마
│       └── ws_message.py     # WS 공통 envelope
│
├── language/                 # 자연어 처리 파트
│   ├── main.py               # 진입점
│   ├── config.py             # 환경변수 설정
│   ├── input/
│   │   └── cli_handler.py    # 사용자 입력 처리
│   ├── context/
│   │   └── vision_state.py   # 최신 YOLO 감지 결과 관리
│   ├── llm/
│   │   ├── openai_client.py  # OpenAI API 비동기 호출
│   │   ├── prompt_builder.py # 프롬프트 생성
│   │   └── response_parser.py# LLM 출력 → RobotCommand 파싱
│   └── ws/
│       ├── client.py         # WebSocket 연결 관리
│       └── dispatcher.py     # 수신 메시지 라우팅
│
├── vision/                   # YOLO 감지 파트
├── action/                   # SO-ARM 제어 + WS Hub
│
├── docs/
│   ├── architecture.md       # 전체 시스템 아키텍처
│   └── command_schema.md     # Language ↔ Action 메시지 스키마
│
├── .env.example
├── requirements.txt
└── README.md
```

## 기술 스택

| 항목      | 선택                        |
|-----------|-----------------------------|
| 언어      | Python 3.10+                |
| WebSocket | `websockets` (asyncio 기반) |
| LLM       | OpenAI API (`gpt-4o-mini`)  |
| 데이터 검증 | `pydantic` v2             |
| 객체 감지 | YOLO11s-seg                 |
| 로봇 제어 | LeRobot + SO-ARM100         |

## 상세 문서

- [시스템 아키텍처](docs/architecture.md)
- [메시지 스키마](docs/command_schema.md)
