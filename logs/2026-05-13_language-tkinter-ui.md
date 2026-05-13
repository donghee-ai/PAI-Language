# 2026-05-13 — Language 데스크톱 UI (Tkinter) 추가

## 배경

`python -m language.main` 으로 돌리면 CLI 한 창에 사용자 입력 prompt(`> `),
LLM 답변(`[답변]`/`[근거]`/`[명령 파싱]`), 그리고 카메라 10Hz 송출에서 나오는
`Vision 상태: ...` INFO 로그와 `httpx` HTTP 로그가 전부 섞여 출력돼서 입력이
묻히고 읽기 어렵다는 피드백. → 입력칸과 대화 내용이 분리되어 보이는 별도 UI 창 요청.

## 변경 사항

### 1. `language/main.py` — 출력 싱크 주입 가능하게 리팩터

- `LanguageApp.__init__(self, config, *, emit=None)` 추가. `emit` 미지정 시 기존처럼
  `print` (CLI 동작 그대로). GUI 등은 콜백을 주입해 사용자 대상 출력을 가로챈다.
- `handle_user_input` / `_on_action_status` 안의 `print(...)` 사용자 출력 →
  `self.emit(...)` 로 교체.
- `_on_action_status` 에서 CLI 전용 잔여물이던 `print("> ", end=...)` 프롬프트 재출력
  라인 제거 (Phase 1 에서는 `action_status` 자체가 수신되지 않음).
- `run()` 의 배너/`input_loop` 는 그대로 — CLI 진입점은 동작 변화 없음.

### 2. `language/ui.py` — 신규 Tkinter UI 진입점

- 실행: PAI-Language 루트에서 `python -m language.ui`
- 구성: 상단 상태줄(현재 Vision 장면 요약 한 줄 + WS/LLM 정보) / 가운데 채팅
  ScrolledText(사용자 입력은 `나> ...`, LLM 답변/근거/명령 파싱 표시) / 하단 입력칸 + 보내기 버튼.
  Enter 또는 버튼으로 전송, `quit`/`exit`/`q` 입력 시 종료.
- `LanguageApp(config, emit=...)` 을 백그라운드 스레드의 asyncio 루프에서
  `hub.run()` 으로 구동. 입력 전송은 `asyncio.run_coroutine_threadsafe`,
  emit 출력은 `queue.Queue` 경유로 메인 스레드가 50ms 마다 비워 위젯에 반영.
- LLM 호출 중에는 보내기 버튼 비활성화(중복 전송 방지). Vision 상태줄은 1초 주기 갱신.
- 로깅: import 최상단에서 root 로거를 `logs/ui_session.log` 파일 핸들러로 먼저 잡아둬서
  뒤이어 import 되는 `language.main` 의 `logging.basicConfig(...)` 가 no-op 이 되게 함.
  `httpx`/`httpcore`/`websockets` 로거는 WARNING 으로 낮춤. → 화면에는 잡음 안 뜸.
- 종료 시 asyncio 태스크 cancel 후 150ms 뒤 창 destroy (백그라운드 스레드는 daemon).

## 영향 / 호환성

- CLI(`python -m language.main`) 동작 불변.
- `pytest tests --ignore=tests/test_llm.py` 66건 전부 통과 확인.
- 새 런타임 의존성 없음 (Tkinter 는 표준 라이브러리; `PAI_LE` conda env Tk 8.6 확인).

## 실행 메모 (현재 로컬 환경)

- Vision: `PAI-Vision` 에서 `python -m app.adapters.run_all` (카메라 + uvicorn :8000, `/ws/scenes`).
- Language UI: `PAI-Language` 에서 `C:\Users\A\.conda\envs\PAI_LE\python.exe -m language.ui`.
- `VISION_WS_URL` 미설정 시 기본값 `ws://localhost:8000/ws/scenes` 사용.

## 후속 후보

- Vision 미연결 시 상태줄에 명시적 표시 / 재연결 상태 노출.
- 대화 로그를 파일로도 저장(현재는 창에만).
- Phase 2(Coordinator) 도입 시 `action_status` 피드백 라인도 채팅에 표시 (emit 경로 그대로 재사용 가능).
