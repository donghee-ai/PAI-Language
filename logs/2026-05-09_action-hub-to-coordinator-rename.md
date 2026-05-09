# Action Hub → PAI-Coordinator 일괄 명칭 변경

**작성일**: 2026-05-09
**작업자**: Language 파트

---

## 배경

2026-05-09 회의에서 "Action 서버가 WebSocket Hub를 겸한다"는 기존 안을 폐기하고,
**전용 PAI-Coordinator 모듈**이 WebSocket / ROS2 양쪽을 관리하는 단순 브로커가 되도록
구조 변경에 합의함. 이에 따라 코드·문서 전반의 "Action Hub" 표현을 "Coordinator" 또는
중립 표현으로 일괄 교체.

배경 결정의 근거:
- 어차피 ROS2도 도입해야 함 — 그러면 WebSocket과 ROS2를 한 모듈에서 관리하는 게 단순
- Vision / Language / Action을 각자 모델 연산만 담당하는 단일 책임 모듈로 단순화
- Action이 허브를 겸하면 Action 모듈에 통신 로직이 섞여 단일 책임이 흐려짐

---

## 변경 사항

### 코드

| 파일 | 변경 |
|------|------|
| `language/config.py` | `action_hub_enabled` → `coordinator_enabled`, 환경변수 `ACTION_HUB_ENABLED` → `COORDINATOR_ENABLED`. `validate()` 가드 메시지에서 "Action Hub URL" → "Coordinator URL", "ACTION_WS_URL" → "COORDINATOR_WS_URL" |
| `language/main.py` | `self.config.action_hub_enabled` → `self.config.coordinator_enabled`. stdout `"[명령 미전송 — Action Hub 없음]"` → `"[명령 미전송 — 송신 대상 없음]"`. 오류 메시지 `"[오류] Action Hub에 연결되어 있지 않아..."` → `"[오류] Coordinator에 연결되어 있지 않아..."` |
| `language/ws/client.py` | 모듈 docstring을 Phase 1/2 분기 설명으로 갱신, `HubClient` 클래스 docstring을 "Phase 1: Vision, Phase 2: Coordinator"로 표기 |
| `shared/constants.py` | 주석에서 `ACTION_WS_URL` 도입 계획 → `COORDINATOR_WS_URL` 도입 계획으로 갱신, "Action Hub 도입 시" → "Phase 2 (Coordinator 도입) 시" |
| `shared/schemas/command.py` | 모듈 docstring "Language → Action Hub" → "Language → Coordinator" |
| `shared/schemas/vision.py` | 모듈 docstring "Vision → Action Hub → Language" → "Vision → Coordinator → Language" |

### 문서

| 파일 | 변경 |
|------|------|
| `README.md` | 아키텍처 진화 단계를 3단계(현재 → Action Hub → Coordinator)에서 2단계(현재 → Coordinator)로 단순화. `.env` 예시에서 `ACTION_HUB_ENABLED` 제거. WebSocket 메시지 타입 표 단계별 분리 |
| `docs/architecture.md` | 2.1/2.2/2.3 → 2.1(Phase 1 Vision 직결합) / 2.2(Phase 2 Coordinator) 두 단락으로 재구성. "Action Hub" 언급을 모두 Coordinator로 치환. 4장에 Coordinator 역할 추가. 5장 메시지 타입 표를 Phase 1/Phase 2 두 표로 분리(Phase 2는 Coordinator relay 6줄). 6장 데이터 흐름 다이어그램에 `coordinator_enabled` 분기 표시. 9장 미결사항을 Coordinator 기준으로 갱신 |
| `docs/command_schema.md` | 제목 "Language ↔ Action" → "Language ↔ Coordinator". 본문 전반의 "Action Hub" → "Coordinator" 일괄 교체. 7장 합의 필요 사항을 Coordinator 기준으로 재정리. 변경 이력에 v0.2(2026-05-09) 항목 추가 |

### 로그

기존 `logs/` 안의 과거 작업 로그(`2026-05-07_*`, `2026-05-08_*`)는 **시점 기록**이므로
수정하지 않고 그대로 보존. 그 시점의 합의 상태(Action Hub 안)를 그대로 남겨 둠.

---

## 동작 영향

런타임 동작 변경 없음:

- `Config.coordinator_enabled` 기본값 `False` (`COORDINATOR_ENABLED` 환경변수 미설정 시).
- `validate()` 가드는 동일하게 작동 — `COORDINATOR_ENABLED=1` + 별도 Coordinator URL 미분리 시 `RuntimeError`.
- 사용자의 기존 `.env`에 `ACTION_HUB_ENABLED=...`가 있더라도 새 코드는 그 키를 읽지 않으므로 기본값 `0`으로 처리. 어차피 가드 때문에 운용 중에는 항상 0이었으므로 실질 영향 없음.

---

## 검증

```bash
pytest tests --ignore=tests/test_llm.py --ignore=tests/test_dispatcher.py
```

→ 31 passed (test_prompt_builder, test_response_parser, test_vision_state).

`test_dispatcher.py`는 `pytest-asyncio` 미설치로 collect 실패 — 본 변경과 무관한 기존
환경 이슈. AST 파싱으로 `language/main.py`, `language/config.py`, `language/ws/client.py`
구문 무결성 추가 확인.

```bash
python -c "from language.config import Config; c = Config(); print(c.coordinator_enabled)"
# False
```

---

## 후속 작업

- Coordinator 레포 신설 시 `shared/` (스키마 + 상수)를 그쪽으로 이전
- Coordinator 스펙 확정 시 `COORDINATOR_WS_URL` 환경변수 추가, `HubClient` 연결 대상 분기 또는 듀얼 클라이언트 전환 결정
- `pytest-asyncio` 미설치 환경 이슈는 별도 정리 (`pip install -r requirements.txt` 필요)
