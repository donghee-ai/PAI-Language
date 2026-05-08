# 아키텍처 무결성 점검 후속 수정 (2026-05-07)

## 배경

`docs/architecture.md` 및 `docs/command_schema.md`와 실제 코드를 대조 분석하여
호환성·무결성 이슈 11건을 식별했고, 그 중 영향도 높은 5건을 수정했다.
(미수정: Action Hub WS URL 확정 — Action 팀 결정 대기)

---

## 수정 내역

### 1. `Config.ws_url` 기본값을 `shared.constants.WS_URL`로 통일
- **파일**: `language/config.py`
- **문제**: WS URL 기본값이 `Config`와 `shared.constants.WS_URL` 양쪽에 하드코딩되어
  drift 위험이 있었다 (단일 소스 위반).
- **수정**:
  - `from shared.constants import WS_URL` 추가
  - `ws_url` 기본값을 `os.getenv("WS_URL", WS_URL)`로 변경하여
    환경변수 미설정 시 `shared.constants` 값을 사용하도록 통일.

### 2. `HubClient.send()` 타임아웃 예외 처리
- **파일**: `language/main.py` (`LanguageApp.handle_user_input`)
- **문제**: WS 미연결 상태에서 사용자 입력 처리 시 `asyncio.wait_for`가 던지는
  `TimeoutError`를 catch하지 않아 unhandled exception 발생 → 사용자에게도 안내가 없었다.
- **수정**:
  - `await self.hub.send(envelope)`을 `try/except`로 감싸 `asyncio.TimeoutError`,
    `TimeoutError`, 일반 `Exception`을 분리 처리.
  - 타임아웃 시 `"[오류] Action Hub에 연결되어 있지 않아 명령 전송에 실패했습니다."`,
    그 외 송신 오류는 `"[오류] 명령 전송 중 오류: {exc}"`를 출력하고 정상 입력 루프로 복귀.

### 3. `VisionState.update` 방어적 파싱
- **파일**: `language/context/vision_state.py`
- **문제**:
  - `obj["label"]` 등 직접 인덱싱과 `cx, cy = obj.center_pixel` unpack에 길이/타입 검증이 없어
    비정상 vision 메시지 한 건이 들어오면 `_recv_loop`까지 예외가 전파될 수 있었다.
  - `data["objects"]`가 list가 아닌 경우 `for` 루프 단계에서 깨짐.
- **수정**:
  - `objects`가 list인지 먼저 검사. 비-list면 경고 로그 후 빈 상태로 초기화.
  - 각 객체에 대해 (a) dict 여부, (b) 필수 키(`label`, `center_pixel`, `confidence`) 존재,
    (c) `center_pixel`이 length-2 list/tuple, (d) 타입 변환(int/float/str) 성공 여부를
    개별 검사. 실패 항목은 경고 로그 남기고 스킵, 나머지는 정상 보존.
  - `to_context_string()`도 `center_pixel` 길이를 한 번 더 확인해 unpack 실패 방지.

### 4. dead import 제거
- **파일**: `language/main.py`, `language/input/cli_handler.py`
- **문제**: `import sys`가 두 파일에서 사용되지 않은 채 남아 있었다.
- **수정**: 두 파일 모두 `import sys` 라인 제거.

### 5. WS 수신 루프 비차단 dispatch
- **파일**: `language/ws/client.py`
- **문제**: `_recv_loop`이 `await self._on_message(msg)`를 직접 await하여
  핸들러가 처리되는 동안 다음 메시지 수신이 블로킹됨. `vision_update`가 빈번하면
  처리 지연이 누적되고, 핸들러에서 발생한 예외가 수신 루프 자체를 종료시킬 수 있었다.
- **수정**:
  - `HubClient`에 `_dispatch_tasks: set[asyncio.Task]` 필드 추가 (GC 방지용 보관소).
  - 메시지 수신 시 `asyncio.create_task(self._safe_dispatch(msg))`로 fire-and-forget.
  - `_safe_dispatch()`에서 핸들러 예외를 `try/except`로 격리하고 `log.exception`으로 기록 → 수신 루프는 영향 없음.
  - 태스크 완료 시 `add_done_callback`으로 set에서 자동 제거.

---

## 검증

### 정적 검증
- 5개 수정 파일 모두 `ast.parse` 통과 (구문 오류 없음).

### 동작 검증
의존성 stub 환경에서 다음 입력으로 `VisionState.update` 직접 호출:

| 입력 객체 | 결과 |
|---|---|
| 정상 (label/center_pixel/confidence 모두 OK) | 보존 ✓ |
| `center_pixel` 키 누락 | 경고 후 스킵 ✓ |
| `center_pixel=[1]` (길이 1) | 경고 후 스킵 ✓ |
| `center_pixel="xy"` (타입 오류) | 경고 후 스킵 ✓ |
| 비-dict 항목 | 경고 후 스킵 ✓ |

`to_context_string()` 출력에 정상 객체만 포함됨을 확인.
`Config().ws_url`이 `shared.constants.WS_URL`과 일치함을 확인.

---

## 미수정 / 후속 과제

| 항목 | 사유 |
|---|---|
| Action Hub WS URL을 `shared/constants.py`에 확정 반영 | Action 팀 합의 대기 (`docs/architecture.md` §9, `docs/command_schema.md` §7) |
| `WSMessage` / `VisionUpdate` Pydantic 모델 활용 | 영향도 중. 향후 schema drift 방지를 위해 `main.py`의 envelope 조립과 `VisionState.update`에 적용 검토 |
| `response_parser`에서 LLM이 반환한 `target=null` 정규화 | 현재도 STOP fallback으로 안전. 명시 정규화는 명료성 개선 차원의 후속 과제 |
| `language/models/robot_command.py` 단순 re-export 정리 | placeholder 의도가 있다면 유지, 아니라면 직접 `shared.schemas.command` 사용으로 단순화 |
