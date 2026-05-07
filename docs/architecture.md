# PAI_LE 시스템 아키텍처

## 1. 프로젝트 개요

LeRobot SO-ARM 기반 로봇 팔이 공을 집어 바구니에 담는 작업을 수행하는 시스템.
세 파트(Vision, Language, Action)가 WebSocket으로 통신하는 모노레포 구조.

| 파트 | 담당 | 역할 |
|------|------|------|
| Vision | 팀원 A | YOLO를 통한 객체 감지, 위치 정보 제공 |
| Language | 담당자 | 사용자 자연어 수신 → OpenAI API → 구조화 명령 생성 |
| Action | 팀원 B | WS Hub 운영, LeRobot SO-ARM 제어 실행 |

---

## 2. 전체 토폴로지

```
┌──────────────────────────────────────────────────────────────┐
│                      PAI_LE (mono-repo)                      │
│                                                              │
│   [User]                                                     │
│     │ stdin (자연어)                                          │
│     ▼                                                        │
│  [Language] ─────────── WS (robot_command) ──────────────┐  │
│     ▲                                                     ▼  │
│     │ relay (vision_update)               [Action = WS Hub]  │
│     └───────────────────────────────────────── WS ──────┘   │
│                                                     ▲        │
│                              [Vision] ─── WS ───────┘        │
│                               (vision_update)                │
└──────────────────────────────────────────────────────────────┘
```

**핵심 원칙:**
- Action 서버가 WebSocket 허브 역할을 겸함
- Vision과 Language 모두 Action에 클라이언트로 접속
- Action이 수신한 `vision_update`를 Language에 relay (broadcast)
- Language는 Vision 결과를 직접 받되, Action이 Vision과 명령을 최종 조합하여 실행

---

## 3. 모노레포 디렉토리 구조

```
PAI_LE/
│
├── shared/                         # 세 파트 공통 인터페이스 계약
│   ├── schemas/
│   │   ├── vision.py               # YOLO 출력 Pydantic 모델
│   │   ├── command.py              # Language→Action 명령 모델
│   │   └── ws_message.py           # WS 메시지 envelope 모델
│   └── constants.py                # WS URL, 토픽 이름, 레이블 상수
│
├── vision/                         # YOLO 감지 파트 (팀원 A)
│   └── ...
│
├── language/                       # 자연어 처리 파트 (담당자)
│   ├── main.py                     # 진입점, 이벤트 루프 조율
│   ├── config.py                   # 환경변수, OpenAI key, WS URL
│   ├── ws/
│   │   ├── client.py               # Action Hub WS 연결 및 재연결 관리
│   │   └── dispatcher.py           # 수신 메시지 type별 핸들러 라우팅
│   ├── input/
│   │   └── cli_handler.py          # asyncio stdin → user_input 이벤트
│   ├── context/
│   │   └── vision_state.py         # 최신 YOLO 결과 보관, 관심 객체 필터링
│   ├── llm/
│   │   ├── openai_client.py        # OpenAI API 비동기 래퍼
│   │   ├── prompt_builder.py       # user_input + vision_context → 프롬프트
│   │   └── response_parser.py      # LLM 출력 → RobotCommand 구조체 파싱
│   └── models/
│       └── robot_command.py        # Language 내부 명령 표현 (shared 참조)
│
├── action/                         # SO-ARM 제어 + WS Hub (팀원 B)
│   └── ...
│
└── docs/
    ├── architecture.md             # 이 문서
    └── command_schema.md           # Language↔Action 인터페이스 스키마
```

---

## 4. 파트별 역할 상세

### Vision
- YOLO 모델로 카메라 프레임 실시간 분석
- 감지된 객체(label, bbox, center_pixel 등) JSON을 `vision_update` 메시지로 Action Hub에 전송
- 출력 형식: `shared/schemas/vision.py` 참조

### Language (담당 파트)
- CLI(stdin)로 사용자 자연어 명령 수신
- Action Hub를 통해 relay된 `vision_update`에서 최소 context 추출 (label, center_pixel)
- `prompt_builder`가 "사용자 입력 + 현재 감지 객체"를 합쳐 OpenAI에 전달
- LLM 출력을 파싱해 `robot_command` 메시지를 Action Hub로 전송
- Action의 `action_status` 피드백을 수신해 사용자에게 결과 출력

### Action
- WebSocket 서버(Hub) 운영
- Vision, Language 클라이언트 연결 관리
- `vision_update`를 Language에 relay
- Language로부터 `robot_command` 수신 → LeRobot SO-ARM 실행
- 실행 상태(`action_status`)를 Language에 전송

---

## 5. WebSocket 메시지 타입

전체 메시지는 공통 envelope을 사용한다. 상세 스키마는 `docs/command_schema.md` 참조.

| type | 방향 | 설명 |
|------|------|------|
| `vision_update` | Vision → Action Hub | YOLO 프레임 감지 결과 |
| `vision_update` | Action Hub → Language | 위 메시지를 relay |
| `robot_command` | Language → Action Hub | 파싱된 로봇 명령 |
| `action_status` | Action Hub → Language | 명령 실행 상태 피드백 |

---

## 6. Language 파트 내부 데이터 흐름

```
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
  │                                               Action Hub (relay)
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
[ws/client.py] ───► Action Hub  (robot_command 전송)
  │
  ▼
[dispatcher.py] ◄─── Action Hub (action_status 수신)
  │
  ▼
[cli_handler.py] → 사용자에게 결과 출력
```

---

## 7. Language가 Vision에서 추출하는 최소 Context

전체 YOLO JSON을 수신하되 `vision_state.py`에서 필터링 후 보관:

```
보관 필드: label, center_pixel, confidence, status
제거 필드: bbox_xyxy, area_pixels, frame_id, inference_ms, loop_fps 등

→ OpenAI 프롬프트에 삽입하는 형태 예시:
   "현재 카메라: ball(화면 중앙 좌측, 신뢰도 0.91), basket(화면 우측, 신뢰도 0.87)"
```

---

## 8. 기술 스택

| 항목 | 선택 |
|------|------|
| 언어 | Python 3.10+ |
| WebSocket | `websockets` 라이브러리 (asyncio 기반) |
| OpenAI | `openai` SDK (async) |
| 데이터 검증 | `pydantic` v2 |
| 비동기 | `asyncio` |
| 로봇 제어 | LeRobot + SO-ARM100 |
| 객체 감지 | YOLO11s-seg |

---

## 9. 미결 사항

| 항목 | 상태 | 비고 |
|------|------|------|
| `robot_command` 스키마 필드 | 초안 작성 완료, Action팀 합의 필요 | `docs/command_schema.md` |
| YOLO target label 목록 확정 | Vision팀과 합의 필요 | ball, basket 등 |
| Action Hub WS 포트/URL | Action팀 결정 필요 | `shared/constants.py`에 반영 |
| OpenAI 모델 선택 | 추후 결정 | 초안: gpt-4o-mini |
