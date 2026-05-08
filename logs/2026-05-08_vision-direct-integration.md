# Vision 직결합 통합 — Action Hub 우회

**작업일**: 2026-05-08
**작업자**: Language 파트
**플랜**: `C:\Users\A\.claude\plans\vision-ws-rippling-brooks.md`

---

## 배경

PAI_LE의 `docs/architecture.md`는 "Action Hub가 WS 서버, Vision/Language가 클라이언트"
토폴로지를 전제했으나 현 시점 코드베이스 상태는:

1. Action Hub 미구현 (팀원 B 담당, 일정 미정)
2. PAI-Vision은 이미 자체 WS 서버(`/ws/scenes`) 운영 중 — `send_json(scene)`을 envelope
   없이 raw로 송출
3. PAI_LE의 `WS_URL`은 사실상 PAI-Vision URL을 가리켜 임시 직결합 구성을 일부 반영
4. 결과: Language를 실행해도 PAI-Vision 메시지가 envelope 없어 dispatcher가 모두
   무시 → `vision_state` 비어있음

Action Hub를 기다리지 않고 Language ↔ Vision 직결합을 완성하면서, 향후 Action Hub
도입 시 최소 변경으로 전환 가능한 구조를 만들었다.

## 결정 사항

| 항목 | 선택 | 근거 |
|---|---|---|
| Envelope 정규화 위치 | PAI_LE 측 어댑터 (단기) → 팀원 A 합의 후 PAI-Vision으로 이전 (하이브리드) | 외부 의존 없이 즉시 통합 + 장기 표준화 경로 확보 |
| robot_command 송신 | Action Hub 도입 전까지 미전송, stdout만 출력 | wire에 대상 없음, 무용한 전송 회피 |
| 페이로드 스키마 | PAI-Vision 쪽에 맞춤 | Vision 변경 최소화, PAI_LE는 default 값만 정합 |
| 문서 갱신 | 이번 라운드에 같이 갱신 | 코드/문서 동기 유지 |

## 변경 파일

### 코드
- `language/ws/client.py` — `_normalize_envelope()` 어댑터 추가, `_recv_loop`에서 호출.
  envelope 없는 raw scene을 `{type: vision_update, sender: vision, data: <scene>}`로
  변환. envelope 이미 있으면 통과.
- `language/main.py` — `handle_user_input`에 `config.action_hub_enabled` 가드 추가.
  False(기본값) 면 stdout 출력 후 송신 생략.
- `language/config.py` — `action_hub_enabled` 필드 추가 (`ACTION_HUB_ENABLED` 환경변수
  연동, default False). `WS_URL` → `VISION_WS_URL` import/사용처 변경.
- `language/context/vision_state.py` — `DetectedObject.status` 및 dict fallback 기본값
  `"tracked"` → `"detected"` (PAI-Vision의 `SceneObject` 기본값과 정합).
- `shared/schemas/vision.py` — `VisionObject.status` 기본값 `"detected"`로 변경.
- `shared/constants.py` — `WS_URL` 상수명을 `VISION_WS_URL`로 개명, 의도 주석 추가.
- `.env.example` — `WS_URL` → `VISION_WS_URL`, `ACTION_HUB_ENABLED=0` 라인 추가.

### 문서
- `README.md` — `.env` 변수 안내 갱신 (`VISION_WS_URL`, `ACTION_HUB_ENABLED` 추가).
- `docs/architecture.md` — 2장 토폴로지에 "현 단계 (Vision 직결합)" / "목표 단계
  (Action Hub 도입 후)" 두 다이어그램 분리. 5장 메시지 타입 표도 두 단계로 분리.
  9장 미결사항에 Action Hub 구현, Envelope 표준 wire 적용 항목 추가.
- `docs/command_schema.md` — 헤더 blockquote에 "현 단계 미전송" 안내 추가. 7장 합의
  필요 사항에 "Envelope wire 적용 위치" 항목 추가.

## 변경하지 않은 것

- PAI-Vision 레포 (하이브리드 전략의 단기 단계 — 외부 의존 0)
- `shared/schemas/command.py`, `shared/schemas/ws_message.py` (Action Hub 도입 시 그대로 사용)
- `language/llm/*`, `language/input/*` (LLM 흐름은 정상)
- `mask_polygon` 등 Vision의 추가 필드 (Language 미사용)

## 검증

### Import 체크 (수행 가능)
```bash
cd C:\Users\A\Desktop\PAI_LE
python -c "from shared.constants import VISION_WS_URL, TOPIC_VISION_UPDATE; print(VISION_WS_URL)"
python -c "from language.ws.client import HubClient, _normalize_envelope; print(_normalize_envelope({'objects': []}))"
```

### 통합 검증 (다음 작업 세션)
1. PAI-Vision 측: `python -m app.run_all --no-display --max-frames 50`
2. PAI_LE `.env`에 `VISION_WS_URL=ws://localhost:8000/ws/scenes` 설정
3. `python -m language.main` 실행
4. 기대:
   - `WS 연결 성공` 로그
   - 매 프레임 `Vision 업데이트: 현재 카메라: ...` 출력
   - 사용자 입력 시 `[명령 파싱] action=..., target=...` + `[명령 미전송 — Action Hub 없음]` 출력

## 향후 (다음 단계)

1. 팀원 A에 envelope 표준 PR 제안 (PAI-Vision `send_json` envelope 래핑 + viewer HTML 수정)
2. PR 머지 후 PAI_LE 측 `_normalize_envelope` 어댑터 제거, 작업 로그에 이력 추가
3. 팀원 B의 Action Hub 완성 시:
   - `shared/constants.py`에 `ACTION_WS_URL` 추가
   - `Config`에 `action_ws_url` 필드 추가
   - 듀얼 클라이언트 구조로 전환 (Vision 클라이언트 + Action 클라이언트 동시 운영)
   - `ACTION_HUB_ENABLED=1` 활성화
