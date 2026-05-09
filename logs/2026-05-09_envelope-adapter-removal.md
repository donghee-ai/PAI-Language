# 2026-05-09 — envelope 어댑터 제거 (Vision 표준 송출에 맞춤)

## 배경

PAI-Vision이 그동안 raw scene(envelope 없음)을 그대로 WS로 송출하고 있어서, PAI_LE 측에서 [`language/ws/adapters.py`](../language/ws/adapters.py)의 `normalize_envelope`로 표준 envelope(`{type, timestamp, sender, data}`)을 씌우는 어댑터를 두고 있었다.

오늘 PAI-Vision 측 코드를 확인한 결과, `app/main.py`에 이미 `_build_scene_envelope` 헬퍼가 추가되어 있고 WS 핸들러가 `send_json(_build_scene_envelope(scene))` 형태로 envelope을 직접 보내고 있다 ([PAI-Vision/app/main.py:461, 481-487](../../PAI-Vision/app/main.py#L461)). envelope 형식도 `WS_TOPIC_VISION_UPDATE` / `WS_SENDER_VISION` 등 PAI_LE의 `shared/constants.py`와 같은 표준을 따름.

따라서 PAI_LE 측 `normalize_envelope`은:

- 첫 번째 분기(`"type" in msg`) — 모든 메시지가 이 경로로 즉시 통과
- 두 번째 분기(`objects` list 휴리스틱으로 raw scene 래핑) — 더 이상 발생하지 않는 죽은 코드

`adapters.py:29-32`의 TODO 주석에도 "Vision이 envelope으로 감싸 송출하도록 변경되면 제거 가능"이라고 미리 명시해 둔 상태였음.

## 변경 사항

### 삭제

- [`language/ws/adapters.py`](../language/ws/adapters.py) — `normalize_envelope`, `_wrap_vision_raw` 둘 다 제거. 다른 어댑터가 없으므로 파일째 삭제.
- [`tests/test_adapters.py`](../tests/test_adapters.py) — 테스트 대상이 사라졌으므로 삭제.

### 수정

- [`language/ws/client.py`](../language/ws/client.py)
  - `from language.ws.adapters import normalize_envelope` import 제거
  - `_recv_loop` 안의 `msg = normalize_envelope(msg)` 호출 제거
- [`README.md`](../README.md) — 프로젝트 트리에서 `ws/adapters.py`, `tests/test_adapters.py` 줄 제거.
- [`docs/architecture.md`](architecture.md)
  - 섹션 2.1 "현 단계 핵심" — "어댑터에서 envelope 정규화" 표현을 "Vision이 표준 envelope으로 직접 송출"로 갱신
  - 섹션 3 디렉터리 트리 — `adapters.py`, `test_adapters.py` 제거
  - 섹션 5 메시지 타입 표 — "(envelope 없음) … 어댑터로 정규화" 행을 "`vision_update` … 직접 송출" 행으로 갱신

## 검증

PAI_Language 루트에서:

- `python -c "import language.ws.client"` — 정상 (`websockets` 패키지가 설치된 환경 기준)
- `python -m tests.test_llm` — LLM 파이프라인 자체에는 영향 없음

## 손대지 않은 영역

- `shared/constants.py`의 `TOPIC_VISION_UPDATE`, `SENDER_VISION` — 송신·수신·dispatcher 등에서 여전히 사용
- `language/ws/dispatcher.py` — type 필드 기반 라우팅, envelope 형식 의존하지만 이미 envelope으로 들어오므로 변경 불필요

## 참고

이전 기록:

- [`2026-05-08_vision-direct-integration.md`](2026-05-08_vision-direct-integration.md) — 어댑터를 처음 도입한 작업 (Vision 직결합 단계)
- [`2026-05-08_phase-2-improvements.md`](2026-05-08_phase-2-improvements.md) — `_normalize_envelope`을 `language/ws/adapters.py`로 분리한 작업
