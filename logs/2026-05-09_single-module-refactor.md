# 2026-05-09 — 단일 모듈 정리 (Phase 1: 잡티 제거 + 테스트 분리)

## 배경

팀에서 새 시스템 아키텍처에 합의함:

```
PAI-Vision ──► PAI-Coordinator ◄── PAI-Language
                     │
                     ▼
              PAI-Action / ROS2
                     │
                     ▼
                 Real Robot
```

이전 안의 "Action이 WebSocket Hub를 겸한다" 대신, **전용 Coordinator 모듈**이 중앙 브로커 역할을 맡는다 (WebSocket + ROS2 양쪽 모두 관리). Vision / Language / Action은 각자 모델 연산만 담당하는 **단일 모듈**로 단순화된다.

이 변경에 맞춰 PAI_Language도 모노레포 형태(`language/` + `shared/`)에서 단일 모듈로 정돈할 필요가 있으나, 본 단계에서는 다음 두 가지만 정리한다 (사용자 결정):

1. 잡티 제거 — 미사용 파일 + 5줄짜리 re-export 껍데기
2. 테스트 위치 표준화 — 소스 폴더에 굴러다니던 `test_*.py`를 `tests/`로

`shared/` 폴더 자체의 위치, 웹소켓 연결 방식은 Coordinator 스펙 확정 시점에 한꺼번에 변경.

## 변경 사항

### 삭제

- `shared/schemas/ws_message.py` — `WSMessage` 클래스가 정의만 있고 어디서도 import되지 않았음. envelope은 `language/main.py`에서 dict literal로 직접 조립 중. 향후 envelope 모델은 Coordinator 도입 시점에 재설계.
- `language/models/robot_command.py` — `from shared.schemas.command import ActionType, RobotCommand` re-export 5줄짜리 껍데기. 사용처(`language/llm/response_parser.py`)는 이미 `shared.schemas.command`를 직접 import 중.
- `language/models/` 폴더째 — `__init__.py`가 패키지 표시자 주석만 가진 상태로 남아있어 통째로 제거.

### 이동

- `language/test_adapters.py` → `tests/test_adapters.py`
- `language/test_llm.py` → `tests/test_llm.py`
- `tests/__init__.py` 신규 (빈 파일)

두 테스트 모두 절대 import만 사용했기에 위치 변경으로 import 깨짐 없음. docstring의 실행 안내만 갱신:
`python -m language.test_adapters` → `python -m tests.test_adapters`

### 수정

- `shared/schemas/__init__.py` — `from .ws_message import WSMessage` 제거.
- `README.md` — 프로젝트 구조 트리에서 `ws_message.py` 제거, `tests/` / `logs/` 추가, `ws/adapters.py` 누락 보완.
- `docs/architecture.md` — 새 Coordinator 토폴로지 섹션 (2.3) 추가, 디렉터리 트리에서 삭제 항목 반영.

## 손대지 않은 영역

- `language/ws/` (client.py, dispatcher.py, adapters.py) — WS·통신 로직 일체
- `shared/` 폴더 위치
- `shared/constants.py`, `shared/schemas/{command,vision}.py` — 핵심 인터페이스

## 검증

PAI_Language 루트에서:

- import 스모크 — `import language.main`, `import language.llm.response_parser`, `from shared.schemas import RobotCommand, VisionUpdate` 등 정상
- `python -m tests.test_adapters` — 6/6 통과

## 다음 단계 (별도 작업)

- Coordinator 스펙 확정 시 `shared/` → Coordinator 패키지로 추출
- WebSocket 듀얼 클라이언트화 (Vision + Coordinator 또는 Coordinator 단일 채널)
- envelope 모델 재도입 (Coordinator wire 스펙 기반)
- LLM에서 물체에 대한 질문을 받을 수 있게 하기
- 로봇 행동 명령 따로, 질문 따로 가능하게 구성하기
