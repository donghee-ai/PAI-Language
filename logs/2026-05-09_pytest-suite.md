# 2026-05-09 — pytest 단위 테스트 도입 (핵심 4개 모듈)

## 배경

이전 작업으로 `tests/test_adapters.py`가 envelope 어댑터와 함께 제거되면서 자동 단위 테스트가 0개인 상태가 됐다. 남은 `test_llm.py`는 OPENAI_API_KEY + stdin 입력이 필요한 대화형 E2E라 자동 검증으로 쓸 수 없음. 회귀 보호를 위해 외부 의존성 없이 돌릴 수 있는 단위 테스트 스위트를 도입한다.

사용자 결정:
- 프레임워크: **pytest** (사실상 표준)
- 범위: **핵심 로직 4개 모듈** — response_parser, vision_state, prompt_builder, dispatcher

## 변경 사항

### 의존성

[`requirements.txt`](../requirements.txt) 에 테스트 섹션 추가:

```
pytest>=7.0
pytest-asyncio>=0.21
```

`pytest-asyncio`는 [`tests/test_dispatcher.py`](../tests/test_dispatcher.py)의 `async def dispatch` 라우팅 검증에 필요.

### 신규 테스트 파일 (4개)

| 파일 | 케이스 수 | 대상 |
|---|---|---|
| [`tests/test_response_parser.py`](../tests/test_response_parser.py) | 11 | `parse_llm_response` — 정상 파싱, 마크다운 fence 추출, STOP fallback (잘못된 JSON / 알 수 없는 action / 필수 필드 누락 / RobotCommand validator 위반) |
| [`tests/test_vision_state.py`](../tests/test_vision_state.py) | 12 | `VisionState` — Pydantic typed 경로, 라벨 조회 (max confidence), context string, dict fallback (필수 필드 누락 / 잘못된 center_pixel / objects 비list) |
| [`tests/test_prompt_builder.py`](../tests/test_prompt_builder.py) | 8 | `SYSTEM_PROMPT` 회귀 보호 (모든 action 옵션 명시, JSON-only 규칙, 안전 fallback 규칙), `build_user_prompt` 포매팅 |
| [`tests/test_dispatcher.py`](../tests/test_dispatcher.py) | 6 | `Dispatcher` — type별 라우팅, 핸들러 덮어쓰기, type 필드 결손 / 미등록 type / 빈 메시지 무시 |

총 **37 케이스**.

### 의도적으로 테스트하지 않은 영역

- `language/llm/openai_client.py` — OpenAI API 호출. 외부 의존성, 단위 테스트 가치 < mocking 비용
- `language/ws/client.py` — WebSocket 연결·재연결 루프. 통합 테스트 영역
- `language/input/cli_handler.py` — stdin 비동기 입력. 통합 테스트 영역
- `language/main.py` — orchestrator. E2E 영역 (test_llm.py가 이 자리)

## 검증

PAI_Language 루트(`c:\Users\A\Desktop\PAI_project\PAI_Language`)에서:

```powershell
conda activate PAI_LE
pytest tests --ignore=tests/test_llm.py
```

결과: **37 passed in 0.41s** — 워닝 0, 실패 0.

## 문서 업데이트

- [`README.md`](../README.md)
  - "## 테스트" 섹션 신규 — pytest 실행 명령 + 대화형 test_llm.py 별도 실행 안내
  - 프로젝트 구조 트리에서 tests/ 항목 4개 파일로 확장

## 다음에 할 만한 것

- `RobotCommand` / `ActionType` 자체 (Pydantic validator 동작) 단위 테스트 — 현재 response_parser 테스트가 간접 커버
- `VisionUpdate` Pydantic 스키마 자체 검증 — `frame_id`, `timestamp` 필수 여부 등
- pytest 설정 파일(`pyproject.toml` 또는 `pytest.ini`) 도입 — 현재는 데코레이터 방식으로 동작하지만 향후 fixture 공유 시 필요
- CI 통합 — GitHub Actions 등에서 자동 실행
