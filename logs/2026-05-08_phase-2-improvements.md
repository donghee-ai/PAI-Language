# Phase 2 — 직결합 통합 후속 개선 (구조적 정리 + 운영 편의)

**작업일**: 2026-05-08 (오후, `2026-05-08_vision-direct-integration.md` 후속)
**작업자**: Language 파트
**선행 로그**: `2026-05-08_vision-direct-integration.md`

---

## 배경

직결합 통합(phase 1) 직후 진행한 E2E 검증에서 코드는 정상 동작 가능하지만 다음
관찰이 있었다:

1. 어댑터 로직이 `language/ws/client.py`에 섞여 있어 향후 다른 외부 시스템 어댑터가
   합류하면 client.py가 비대해짐 (단일 책임 원칙 위반 우려)
2. `Vision 업데이트:` 로그를 매 프레임 INFO로 찍어 10Hz × 콘솔 = 사용자 입력
   prompt가 묻힘 (운영 편의 저하)
3. default `VISION_WS_URL = "wss://vision.yeoun.org/ws/scenes"` 가 외부 URL로
   되어 있어 로컬 개발 시 매번 `.env`에 덮어쓰기 필요
4. `shared/schemas/vision.py` 의 `VisionObject`/`VisionUpdate` Pydantic 모델이
   선언만 되어 있고 어디서도 사용되지 않음 — schema drift 감지 불가
5. `ACTION_HUB_ENABLED=1` 설정 시, 단일 `HubClient`가 Vision 서버에 연결된 상태에서
   robot_command를 잘못된 대상에 송신할 수 있음 (silent failure)
6. 어댑터 로직에 대한 테스트 없음 — 향후 회귀 검출 어려움

이 단계에서는 통합 동작을 깨지 않으면서 구조적/운영적 부채를 정리한다.

## 결정 사항

| 항목 | 선택 | 근거 |
|---|---|---|
| 어댑터 위치 | 전용 모듈 `language/ws/adapters.py` 분리 | 단일 책임. 향후 어댑터 추가 시 client.py 무수정 |
| Vision 로그 | 프레임마다 DEBUG, 1초마다 INFO 요약 | 콘솔 노이즈 제거하면서 라이브 가시성 유지 |
| Default WS URL | `ws://localhost:8000/ws/scenes`로 변경 | 로컬-우선 개발. 원격은 `.env` override |
| Pydantic 모델 활용 | `VisionUpdate.model_validate` 1순위, dict fallback | schema drift 빠른 감지 + graceful 운영 |
| ACTION_HUB_ENABLED 가드 | `Config.validate()`에서 명시적 RuntimeError | silent 잘못된 송신 방지 |
| 테스트 | `language/test_adapters.py` (plain Python, pytest 무관) | 외부 의존 없이 회귀 방지 |

---

## 변경 파일

### 신규
- `language/ws/adapters.py` — `normalize_envelope()` 와 내부 헬퍼 `_wrap_vision_raw()`.
  TODO 주석으로 "PAI-Vision envelope 표준화 PR 후 raw scene 분기 제거 가능" 명시.
- `language/test_adapters.py` — 6개 단위 테스트 (envelope passthrough, raw scene 래핑,
  알 수 없는 메시지 통과, 빈 objects 처리, objects 비-list 통과, timestamp fallback).
  실행: `python -m language.test_adapters`. 6/6 통과 확인됨.

### 수정
- `language/ws/client.py` — `_normalize_envelope` 제거, `from language.ws.adapters import
  normalize_envelope` 사용. 불필요해진 `datetime`, `shared.constants` import 정리.
- `language/main.py` — `_on_vision_update` 로그 정책 변경. 매 프레임은 DEBUG, INFO는
  `VISION_LOG_THROTTLE_SEC=1.0` 간격 throttle. `LanguageApp._last_vision_info_log`
  필드 추가, `time.monotonic()` 기반 throttle.
- `language/context/vision_state.py` — `VisionState.update()`를 1순위 Pydantic 검증,
  실패 시 기존 dict 기반을 `_update_from_dict()`로 분리해 fallback. 로그에 어느 경로를
  탔는지 표시 ("typed" vs "fallback").
- `language/config.py` — `Config.validate()`에 `action_hub_enabled` 가드 추가.
  현재 단일 클라이언트 구조에서 활성화 시 명시적 RuntimeError로 거부.
- `shared/constants.py` — `VISION_WS_URL` default를 `ws://localhost:8000/ws/scenes`로
  변경. 원격 사용 안내 주석 추가.
- `.env.example` — `VISION_WS_URL` 라인을 주석 처리(default가 로컬이라 평소 불필요).
  원격 사용 시에만 주석 해제하라는 안내.

### 변경하지 않은 것
- PAI-Vision 레포 (여전히 외부 의존 0 유지)
- `shared/schemas/command.py`, `shared/schemas/ws_message.py`
- `language/llm/*`, `language/input/*`
- 기존 작업 로그 (`2026-05-07_*`, `2026-05-08_vision-direct-integration.md`) — 역사 기록 보존

---

## 검증

### 단위 테스트 (수행 완료)
```
cd C:\Users\A\Desktop\PAI_LE
python -m language.test_adapters
```
**결과**: 6/6 통과
- `[OK] test_passthrough_when_envelope_present`
- `[OK] test_wrap_pai_vision_raw_scene`
- `[OK] test_passthrough_when_neither_type_nor_objects`
- `[OK] test_wrap_empty_objects_list`
- `[OK] test_objects_not_list_passthrough`
- `[OK] test_timestamp_fallback_when_missing`

### vision_state 경로 검증 (수행 완료)
- 정상 PAI-Vision payload (모든 필드 present) → typed 경로 통과, 객체 정확히 파싱
- frame_id 누락 payload → ValidationError → fallback 경로, 객체 파싱 정상
- 빈 dict `{}` → ValidationError → fallback, 객체 0개

### config 가드 검증 (수동 확인 권장)
`.env`에 `ACTION_HUB_ENABLED=1` 설정 후 `python -m language.main` 실행 시:
```
RuntimeError: ACTION_HUB_ENABLED=1 이지만 별도 Action Hub URL이 분리되어 있지 않습니다.
              ...
```
명시적 에러로 즉시 종료.

### 통합 검증 (다음 세션)
1. PAI-Vision: `python -m app.run_all --no-display`
2. PAI_LE: `python -m language.main`
   - `.env`의 `VISION_WS_URL`을 비워두면 default `ws://localhost:8000/ws/scenes` 사용
3. 기대:
   - "WS 연결 성공" 로그
   - 매 1초마다 (10초 아님) `Vision 상태: 현재 카메라: ...` INFO 한 줄
   - DEBUG 로그를 보려면 logging level을 DEBUG로 변경
   - 사용자 입력 prompt가 vision 로그에 묻히지 않음
   - 사용자 입력 시 `[명령 파싱]` + `[명령 미전송 — Action Hub 없음]` 출력

---

## 구조적 개선 효과

1. **`language/ws/` 책임 분리**:
   - `client.py` — WS 연결/재연결/송수신 (네트워크 책임)
   - `adapters.py` — 메시지 형식 변환 (프로토콜 어댑터 책임)
   - `dispatcher.py` — type별 핸들러 라우팅 (분배 책임)
   향후 Action Hub 어댑터 추가 시 `adapters.py`에만 함수 1개 추가하면 됨.

2. **Schema drift 조기 감지**:
   - PAI-Vision이 필드 추가/제거하면 typed 경로에서 ValidationError 로그가 떠
   "schema 변경됐다"는 신호가 즉시 보임. 동시에 fallback 경로가 graceful 운영 보장.

3. **운영 콘솔 가독성**:
   - 10Hz INFO → 1Hz INFO 요약 + DEBUG 상세. 사용자 입력 prompt가 묻히지 않음.

4. **Silent failure 차단**:
   - `ACTION_HUB_ENABLED=1` 잘못 설정 시 명시적 RuntimeError. 이전엔 robot_command가
   Vision 서버로 잘못 송신되어 무시되는 silent failure였음.

5. **회귀 방지 인프라 도입**:
   - `language/test_*.py` 패턴 + plain Python 실행 (pytest 무관). 외부 의존 0.
   향후 다른 모듈도 같은 패턴으로 테스트 추가 가능 (`test_vision_state.py` 등).

---

## 향후 (이 단계 범위 밖)

### 단기 (다음 세션)
- 실제 카메라 + LLM 호출까지 E2E 통합 테스트 (PAI-Vision 띄우고 PAI_LE 띄우기)
- 통합 검증 결과를 별도 로그로 기록

### 중기 (팀 합의 후)
- 팀원 A에 envelope 표준 PR 제안 → 머지 후 `adapters.py`의 raw scene 분기 제거
- `language/test_vision_state.py` 추가 (typed/fallback 경로 회귀 테스트)
- `language/test_main.py` 추가 (action_hub_enabled 가드 동작 회귀 테스트)

### 장기 (Action Hub 도입 후)
- `Config`에 `action_ws_url: str | None = None` 추가
- `HubClient`를 `VisionClient` + `ActionClient`로 리팩토링
- `main.py`에서 두 클라이언트를 동시 실행 (`asyncio.gather`)
- `Config.validate()`의 ACTION_HUB_ENABLED 가드를 "URL 분리됐는지" 체크로 완화
- 통합 후 `adapters.py`에 Action Hub 메시지 정규화 어댑터 추가
