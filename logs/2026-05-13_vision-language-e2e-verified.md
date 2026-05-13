# 2026-05-13 — Vision ↔ Language 실연동 확인 (E2E 마일스톤)

## 배경

지난 며칠간 PAI-Language 측에 누적된 변경들 —

- LLM 일상 대화 / 카메라 질문 / 로봇 명령 / 복합 입력 통합 처리 ([`logs/2026-05-11_llm-conversation-and-command-split.md`](2026-05-11_llm-conversation-and-command-split.md))
- 데모 시나리오 라벨을 COCO 80 클래스로 통일 (`sports ball` → `bowl`) ([`logs/2026-05-12_label-set-to-coco80-and-demo-scenario.md`](2026-05-12_label-set-to-coco80-and-demo-scenario.md))
- 데스크톱 UI(Tkinter) 추가 + `LanguageApp` 출력 싱크(`emit`) 주입 리팩터 ([`logs/2026-05-13_language-tkinter-ui.md`](2026-05-13_language-tkinter-ui.md))

이것들이 실제로 PAI-Vision 과 함께 한 자리에서 동작하는지 로컬에서 통합 확인.

## 확인한 것 (로컬 E2E)

구성:

- Vision: `PAI-Vision` 에서 `python -m app.adapters.run_all` — 카메라 + YOLO11s-seg + uvicorn `:8000` (`/ws/scenes` 로 표준 envelope 송출, ~9 fps / infer ~68 ms).
- Language UI: `PAI-Language` 에서 `C:\Users\A\.conda\envs\PAI_LE\python.exe -m language.ui` — `VISION_WS_URL` 기본값 `ws://localhost:8000/ws/scenes` 로 자동 접속.

확인 결과 (책상 위 마우스 / 키보드 / 손 시야):

| 입력 | 결과 |
|---|---|
| "안녕" / "네 소개를 해줄래?" / "밥은 먹었어?" | 일반 LLM 답변만, `command=null`. `[근거]` 에 "일상 인사/대화이므로 명령 없음" 류로 분류 근거 표기 |
| "지금 화면에 뭐가 보여?" | 상단 상태줄의 Vision context(`mouse`/`keyboard`/`person` + center px + confidence)를 근거로 "마우스, 키보드, 사람이 보입니다" 답변 |
| "그러면 마우스를 들어서 키보드 위에 올려줘" | `[답변]` 자연어 + `[명령 파싱] action=pick_and_place, target=mouse, destination=keyboard` + `[근거]` + `[명령 미전송 — 송신 대상 없음]` |

- 답변(`answer`)과 분류/파싱 근거 라인은 UI 에서 색을 분리 — 답변은 본문 색, `[근거]`/`[명령 …]`/`[Action]`/`[오류]`/`처리 중` 은 회색(`meta` 태그). 디버깅 시 "사용자에게 보일 답변"과 "내부 처리 흔적"이 한눈에 구분됨.
- Vision 상태줄은 1초 주기 갱신 — 손이 들어오면 `person` 추가, 빠지면 사라지는 것이 즉시 반영됨.
- `httpx`/`websockets`/카메라 프레임 로그는 화면에 안 뜨고 `logs/ui_session.log` 로만 감 (UI 로그 정책대로 동작).

→ "사용자 자연어 입력 → (Vision context 주입된) LLM → 대화/질문/명령 자동 분기 → 화면 출력" 경로가 PAI-Vision 실시간 송출과 함께 의도대로 동작함을 확인. 스크린샷 보관.

## Phase 1 범위 (그대로)

- `robot_command` 는 여전히 wire 로 미전송 — Coordinator 미도입이라 송신 대상 없음. 명령은 파싱해서 화면에만 출력.
- Vision 은 PAI-Vision 자체 WS 서버(`/ws/scenes`)에 Language 가 직접 클라이언트로 붙는 직결합 구조 유지.
- Phase 2(Coordinator 중앙 허브) 도입 시 일괄 전환 예정 — 본 확인으로 Phase 1 경로는 닫힌 것으로 본다.

## 문서 갱신

- [`docs/architecture.md`](../docs/architecture.md) — 전체 점검:
  - 2.1 Phase 1 — "Vision 직결합 실연동 확인됨(2026-05-13)" 명시, 사용자 접점이 CLI(`python -m language.main`) 와 데스크톱 UI(`python -m language.ui`) 둘임을 토폴로지/설명에 반영.
  - 3장 디렉토리 트리 — `language/ui.py`(Tkinter UI 진입점) 추가, `main.py` 설명에 `emit` 출력 싱크 주입 가능 점 추가.
  - 4장 Language 역할 — 입력 채널이 stdin 외에 Tkinter UI 도 있음을, 사용자 대상 출력은 `emit` 싱크로 추상화됨을 반영.
  - 8장 기술 스택 — UI 항목에 Tkinter(표준 라이브러리) 추가.
  - 6장 내부 데이터 흐름 — stdout 출력 단계를 "emit 싱크(CLI=print / UI=큐)" 로 표기.

## 다음에 할 만한 것

- 대화 로그 파일 저장(현재 창에만) — 데모/디버깅 재현용.
- Vision 미연결 / 재연결 상태를 상태줄에 명시 표시.
- Coordinator 도입 시 `robot_command` 실제 송신 + `action_status` 를 UI 채팅에 표시 (emit 경로 그대로 재사용).
- main.py stdout 출력 정책 — `[명령 파싱]`/`[근거]`/`[명령 미전송 …]` 를 계속 사용자에게 보일지 logging.info 로 격하할지 ([`logs/2026-05-11_llm-conversation-and-command-split.md:142`](2026-05-11_llm-conversation-and-command-split.md)).
