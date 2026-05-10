# 2026-05-11 — LLM 일반 대화 + 카메라 질문 + 로봇 명령 통합 처리

## 배경

[`logs/2026-05-09_single-module-refactor.md:67-68`](2026-05-09_single-module-refactor.md)에 다음 단계로 명시된 두 항목 — "LLM에서 물체에 대한 질문을 받을 수 있게 하기"와 "로봇 행동 명령 따로, 질문 따로 가능하게 구성하기" — 를 구현.

이전 상태:
- [`language/llm/prompt_builder.py`](../language/llm/prompt_builder.py)의 `SYSTEM_PROMPT`가 LLM에게 robot_command JSON만 출력하도록 강제 (`"JSON 외의 텍스트는 출력하지 마세요"`)
- [`language/llm/response_parser.py`](../language/llm/response_parser.py)는 JSON 파싱 실패 시 무조건 `RobotCommand(action=STOP)`로 회귀
- 자연어 답변 경로 자체가 없고 명령/질문 분류 로직 전무
- "안녕?", "지금 뭐 보여?", "공 잡아줘" 모두 동일하게 명령으로 처리됨

사용자 요구 (확정):
- "안녕?" 같은 **일상 대화**도 일반 LLM처럼 자연스럽게 응답
- "지금 뭐 보여?" 같은 **카메라 기반 질문**에 답변
- "공 잡아줘" 같은 **단순 명령** 처리
- "저기 공 보여? 저거 집어서 바구니에 넣어줘" 같이 **질문 + 명령이 섞인 복합 입력**도 처리 — 답변과 명령을 동시에 추출

## 결정 사항

| 항목 | 선택 | 근거 |
|---|---|---|
| 분류 방식 | LLM이 응답 wrapper에서 직접 판단 | vision context + 사용자 입력 모두 보고 판단 가능. 추가 호출 없음 |
| 출력 채널 | Phase 1은 stdout 전용 | Coordinator 신규 메시지 타입은 스펙 확정 시점에 별도 |
| 모델 구조 | 단일 wrapper (answer 필수, command Optional) | 복합 입력(질문+명령)을 한 wrapper에 동시 표현. 이전 안의 discriminated union(`type: command` 또는 `answer`)으로는 표현 불가 |
| reasoning 위치 | wrapper 레벨(분류 근거) + command 내부(명령 근거) 분리 | 의미가 다름. command.reasoning은 기존 출력 흐름 호환 |
| 빈 답변 차단 | Pydantic `min_length=1` | 모델 한 곳에서 강제 |

## 변경 사항

### 신규

- [`shared/schemas/llm_response.py`](../shared/schemas/llm_response.py)
  - `AssistantAnswer(text: str[min_length=1], raw_input: str = "")`
  - `LLMResponse(answer: AssistantAnswer, command: Optional[RobotCommand] = None, reasoning: str = "")`
  - `answer`는 필수, `command`는 명령 의도가 있을 때만. 일상 대화/단순 질문은 command=None.

- [`tests/test_llm_response_schema.py`](../tests/test_llm_response_schema.py) (9 케이스)
  - LLMResponse 인스턴스화 (answer만 / answer+command / command default None / dict→RobotCommand 자동 변환)
  - 검증 실패 (answer 누락, command validator 위반)
  - AssistantAnswer (정상, 빈 text → ValidationError, raw_input 전파)

### 수정

- [`shared/schemas/__init__.py`](../shared/schemas/__init__.py) — `LLMResponse`, `AssistantAnswer` export 추가.

- [`language/llm/prompt_builder.py`](../language/llm/prompt_builder.py) — SYSTEM_PROMPT 전면 재작성. 4가지 시나리오 가이드(일상 대화/카메라 질문/로봇 명령/복합) + wrapper JSON 형식 + answer/command 작성 규칙. `build_user_prompt`는 변경 없음.

- [`language/llm/response_parser.py`](../language/llm/response_parser.py) — 시그니처 교체.
  - `parse_llm_response(raw, raw_input) -> LLMResponse` (기존 `-> RobotCommand` 폐기)
  - 3단계 fallback 분기:
    1. 응답 자체가 깨짐 (JSON 파싱 실패 / dict 아님 / answer 누락 / answer 빈 text) → placeholder answer + STOP command (`_fallback_stop`)
    2. command만 잘못됨 (action enum 위반 / RobotCommand validator 위반 / dict 아님) → answer는 LLM이 준 것 보존, command만 STOP으로 대체 (`_stop_command`)
    3. 정상 → 그대로
  - `_extract_json` 헬퍼 재사용.

- [`language/main.py`](../language/main.py) — `handle_user_input` 분기 구조 재구성.
  - `[답변] {response.answer.text}` 항상 출력
  - `response.reasoning` 있으면 `[근거] ...` 출력
  - `response.command is None`이면 종료 (순수 대화/질문)
  - 명령 있으면 `vision_confirmed` 설정 후 기존 Phase 1/Phase 2 분기 (`coordinator_enabled`)
  - 복합 입력 시 stdout 순서: 답변 먼저, 명령 정보 다음

- [`tests/test_response_parser.py`](../tests/test_response_parser.py) — 11 → 25 케이스로 확장.
  - 기존 케이스 전부 wrapper 형식(`{"answer":{...},"command":{...}}`)으로 갱신
  - 신규: 일상 대화 / 카메라 질문 / 복합 / command 누락 / command null 명시
  - 신규: 응답 깨짐 fallback 4종 (잘못된 JSON, 객체 아님, answer 누락, answer 빈 text, answer 잘못된 타입)
  - 신규: command만 잘못됨 5종 (unknown action, action 누락, pick 타겟 없음, place destination 없음, command 잘못된 타입) — 모두 answer 보존 + command만 STOP 검증
  - 신규: raw_input 전파 (answer / command)

- [`tests/test_prompt_builder.py`](../tests/test_prompt_builder.py) — 기존 8 → 12 케이스.
  - 신규: wrapper의 `"answer"`/`"command"` 두 필드 명시
  - 신규: 4가지 시나리오 가이드 등장 (일상 대화 / 질문 / 로봇 명령 / 복합)
  - 신규: 빈 답변 금지 규칙 / `command=null` 가능 명시
  - 기존 "JSON 외의 텍스트는 출력하지 마세요" / "모호" / "stop" 회귀 보호 유지

- [`tests/test_llm.py`](../tests/test_llm.py) — 디버깅 출력을 새 LLMResponse 형식에 맞춤.
  - `[답변] {text}` + (있으면) `[근거] {reasoning}` + 명령 있을 때만 `[명령 파싱 결과]` JSON dump

## 문서 갱신

- [`docs/architecture.md`](../docs/architecture.md)
  - 2.1 Phase 1 토폴로지 다이어그램 — "명령 파싱 결과 출력" → "답변 + (있으면) 명령 파싱 결과 출력"
  - 3장 디렉토리 트리 — `shared/schemas/llm_response.py`, `tests/test_llm_response_schema.py` 추가, `response_parser.py` 설명을 `LLMResponse(answer + Optional command)` 파싱으로 갱신
  - 4장 Language 역할 — LLM 출력이 `RobotCommand` 단일이 아니라 `LLMResponse`(자연어 답변 항상 + 명령 옵션)임을 반영. Phase 1/Phase 2 동작 설명 정밀화
  - 6장 내부 데이터 흐름 다이어그램 — response_parser 출력을 LLMResponse로 갱신, 답변은 항상 stdout, command 분기는 Phase 1/2 로직 그대로
  - 9장 미결 사항 — "LLM 답변(`answer`)의 wire화" 항목 추가 (Phase 2에서 `assistant_answer` 같은 신규 메시지 타입을 둘지 결정 필요)

- [`docs/command_schema.md`](../docs/command_schema.md) — v0.2 → v0.3
  - 헤더 blockquote — Phase 1 동작 설명을 "stdout으로만 출력된다" → "자연어 답변과 (있으면) 명령 파싱 결과를 stdout으로 출력"으로 정밀화
  - 7장 합의 필요 사항 — `answer` wire화 항목 추가
  - 8장 변경 이력 — v0.3 (2026-05-11) 추가

wire 자체는 변경 없음 — `robot_command`/`action_status` envelope과 스키마는 그대로 유지. 답변은 Phase 1에서 stdout 전용이라 wire 영향 없음.

## 손대지 않은 영역

- [`language/llm/openai_client.py`](../language/llm/openai_client.py) — JSON mode(`response_format`) 도입은 본 작업 범위 밖
- [`language/ws/`](../language/ws/) (client, dispatcher) — 답변은 stdout 전용, WS 라우팅 영향 없음
- [`language/input/cli_handler.py`](../language/input/cli_handler.py) — 분류는 LLM이 함, prefix 기반 사전 분기 없음
- [`language/context/vision_state.py`](../language/context/vision_state.py) — 답변/명령 모두 같은 `to_context_string()` 사용
- [`shared/constants.py`](../shared/constants.py), [`shared/schemas/command.py`](../shared/schemas/command.py) — Coordinator 계약 안정 유지
- 기존 [`tests/test_dispatcher.py`](../tests/test_dispatcher.py), [`tests/test_vision_state.py`](../tests/test_vision_state.py) — 본 변경과 무관

## 검증

PAI_Language 루트에서:

```powershell
conda activate PAI_LE
pytest tests --ignore=tests/test_llm.py -v
```

결과: **62 passed in 0.72s** (이전 37 → 25 신규 케이스 추가).

수동 E2E (실제 OpenAI 호출, `python -m tests.test_llm`):

복합 입력 `"저기 빨간 공 보여? 저거 주워서 바구니에 넣고 싶어"` (vision: ball, basket) →

```
[답변] 네, 빨간 공이 보입니다. 공을 바구니에 넣어드릴게요.
[근거] 사용자가 공을 주워서 바구니에 넣고 싶다고 하여 명령을 수행하기로 했습니다.
[명령 파싱 결과]
{"action": "pick_and_place", "target": "ball", "destination": "basket", ...}
```

answer + command 동시 추출, 한 LLM 호출로 자연스러운 응답과 구조화 명령을 모두 생성. 의도대로 동작 확인.

## 책임 분리 (유지)

[`logs/2026-05-08_phase-2-improvements.md:117-121`](2026-05-08_phase-2-improvements.md)에서 정리한 책임 분리를 그대로 유지:

| 책임 | 위치 |
|---|---|
| 데이터 모델 | `shared/schemas/llm_response.py` 신규, `command.py` 미변경 |
| LLM 입출력 변환 (분류 + 답변 생성 + 명령 추출) | `language/llm/{prompt_builder,response_parser}.py` |
| 부수효과 분기 (stdout, WS 송신) | `language.main.LanguageApp.handle_user_input` |
| WS 라우팅 / Vision state | 변경 없음 |

## 다음에 할 만한 것

- main.py stdout 출력 정책 정리 — 명령 정보 줄들(`[명령 파싱]`/`[근거]`/`[명령 미전송 — 송신 대상 없음]`)을 사용자에게 그대로 보여줄지 logging.info로 격하할지. UX vs Phase 1 검증 가시성 trade-off
- OpenAI JSON mode 도입 (`response_format={"type":"json_object"}`) — fallback 견고성 측면에서 매력적이나 비용/안정성 측정 필요
- Coordinator 도입 시 `assistant_answer` 같은 신규 WS 메시지 타입을 둘지, robot_command만 송신하고 답변은 계속 stdout 전용으로 둘지 결정
- `RobotCommand` / `ActionType` 자체 단위 테스트 ([`logs/2026-05-09_pytest-suite.md:60`](2026-05-09_pytest-suite.md))
