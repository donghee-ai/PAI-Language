# 2026-05-12 — 라벨 집합을 COCO 80개로, 데모 시나리오를 "스포츠볼 → 그릇"으로 변경

## 배경

[`docs/architecture.md`](../docs/architecture.md) 9장 미결 사항의 "YOLO target label 목록 확정 — Vision팀과 합의 필요" 항목과, [`docs/experiments/2026-05-05-live-camera-smoke-test.md:91`](../../PAI-Vision/docs/experiments/2026-05-05-live-camera-smoke-test.md) (PAI-Vision)의 "현재 객체 label은 COCO pretrained 기준이므로 tabletop 커스텀 객체 인식에는 fine-tuning이 필요하다"를 정리.

이전 상태:
- [`shared/constants.py`](../shared/constants.py)가 `LABEL_BALL = "ball"`, `LABEL_BASKET = "basket"`, `KNOWN_LABELS = ["ball", "basket"]` — Vision팀 미확정 가정의 임시값
- PAI-Vision은 COCO 사전학습 `yolo11s-seg.pt`를 그대로 사용 → 실제 emit 라벨은 COCO 80개 (`result.names`). 공은 `"ball"`이 아니라 `"sports ball"`, `"basket"`은 COCO에 **없음**
- [`language/llm/prompt_builder.py`](../language/llm/prompt_builder.py)의 SYSTEM_PROMPT가 `target`을 `<YOLO 라벨 또는 none>`이라고만 하고 **유효 라벨 목록을 LLM에게 제시하지 않음** → LLM이 라벨을 추측, Vision 출력과 불일치, `vision_confirmed` 사실상 항상 False
- [`language/context/vision_state.py`](../language/context/vision_state.py)는 받은 label을 검증 없이 그대로 보관 → 라벨 합의 어긋남을 감지할 방법 없음

사용자 결정 (확정):
1. 옵션으로 검토한 임베딩 라벨 유사도 매칭은 **채택 안 함** — 사용자 한국어→라벨 매핑은 LLM이 이미 함, COCO→canonical은 dict가 더 안정적, COCO에 없는 객체는 유사도로 못 만듦 (그건 fine-tuning / open-vocab 영역)
2. **COCO 80개 전부를 Language의 라벨 집합으로 채택**, 기존 `ball`/`basket` 상수 삭제
3. LLM 프롬프트에 **라벨 목록 전부 주입**
4. 알 수 없는 라벨 수신 시 **경고 로그** 추가
5. 데모 시나리오를 **"스포츠볼 집어서 그릇에 넣어줘"** (`target="sports ball"`, `destination="bowl"`)로 변경 — COCO에 `basket`이 없으므로

## 결정 사항

| 항목 | 선택 | 근거 |
|---|---|---|
| 라벨 출처 | `shared/constants.py`에 COCO 80개 하드코딩 | 모델이 바뀌기 전까지 고정. 단일 출처. (Phase 2에서 Coordinator로 이전 예정인 것은 변함없음) |
| 자료형 | `COCO_LABELS: tuple`(순서=class id) + `KNOWN_LABELS: frozenset` | tuple은 프롬프트 나열용, frozenset은 멤버십 체크용. 둘 다 실제 사용됨 |
| 프롬프트 주입 범위 | 80개 전부 나열 | 부분집합으로 줄이면 LLM이 못 본 라벨을 만들 여지. gpt-4o-mini에 80개 ≈ 토큰 부담 없음(프롬프트 총 ~2.5KB) |
| 한국어→라벨 | LLM이 변환 (프롬프트에 예시 명시: 공→`sports ball`, 컵→`cup`, 그릇→`bowl`) | 별도 임베딩/매핑 레이어 불필요 |
| 미지 라벨 처리 | 보관은 하되 최초 1회만 경고 | vision_update ~10Hz → 매 프레임 경고 시 로그 폭주. 객체를 버리진 않음(서비스 graceful) |
| `basket` 부재 | 데모를 `bowl`로 변경. 진짜 `basket`은 Vision fine-tuning / open-vocab 도입 후 | 코드/문서 합의 변경만으로 당장 동작 가능한 길 선택 |

## 변경 사항

### `shared/constants.py`
- **삭제**: `LABEL_BALL`, `LABEL_BASKET`, 기존 `KNOWN_LABELS = [LABEL_BALL, LABEL_BASKET]`
- **추가**: `COCO_LABELS: tuple[str, ...]` — COCO 80개 클래스, 튜플 인덱스 = YOLO class id (예: `COCO_LABELS[32] == "sports ball"`, `[41] == "cup"`, `[45] == "bowl"`)
- **변경**: `KNOWN_LABELS = frozenset(COCO_LABELS)` — `target in KNOWN_LABELS` 형태 멤버십 체크용
- 주석: 모델이 커스텀 fine-tuning / open-vocab으로 바뀌면 이 목록도 갱신 필요함을 명시

### `language/llm/prompt_builder.py`
- `from shared.constants import COCO_LABELS` → `_VALID_LABELS = ", ".join(COCO_LABELS)`
- SYSTEM_PROMPT을 plain 문자열 `+` 결합으로 재구성 (f-string 아님 → JSON 중괄호 이스케이프 불필요):
  - 신규 절 **"## 인식 가능한 객체 라벨"** — 80개 전부 나열 + "한국어로 말해도 이 표기로 변환(공→`sports ball`, 컵→`cup`, 병→`bottle`, 그릇→`bowl`)" + "목록에 없는 물체(basket 등)는 인식 불가 → answer에서 알리거나 가장 가까운 라벨로 대체하고 reasoning에 명시"
  - JSON 템플릿의 `target`/`destination` 설명을 `<위 라벨 목록 중 하나 또는 none>`으로
  - command 작성 규칙 6번 추가: "target/destination은 위 목록 문자열 그대로, 목록에 없는 문자열은 절대 만들지 않는다" (이후 규칙 번호 한 칸씩 밀림)
  - 복합 입력 예시 `"...바구니에 넣어줘"` → `"...그릇에 넣어줘"`, 확인 멘트 예시 `"...바구니에 넣어드릴게요"` → `"...그릇에 넣어드릴게요"`
- `build_user_prompt`는 변경 없음

### `language/context/vision_state.py`
- `from shared.constants import KNOWN_LABELS`
- `VisionState.__init__`에 `self._warned_labels: set[str] = set()` 추가
- 신규 메서드 `_warn_if_unknown_label(label)` — `KNOWN_LABELS`에 없고 아직 경고 안 한 라벨이면 `log.warning(...)` 후 `_warned_labels`에 기록 (라벨당 1회)
- typed 경로(`update`의 성공 분기) — list comprehension을 for 루프로 바꾸고 객체 생성 전 `_warn_if_unknown_label` 호출
- dict fallback 경로(`_update_from_dict`) — `label_str = str(label)` 후 `_warn_if_unknown_label(label_str)` 호출
- 객체를 버리진 않음 — 미지 라벨이어도 그대로 보관(기존 graceful 동작 유지)

### `tests/`
- [`tests/test_vision_state.py`](../tests/test_vision_state.py) — 픽스처 라벨을 `ball`/`basket` → `sports ball`/`bowl`(둘 다 COCO)로 정렬. 신규: `test_unknown_label_warns_once`(미지 라벨 1회 경고 + 객체는 보관), `test_known_label_does_not_warn` — 둘 다 `caplog` 사용
- [`tests/test_prompt_builder.py`](../tests/test_prompt_builder.py) — 신규: `test_system_prompt_lists_every_known_label`(`COCO_LABELS` 전부 프롬프트에 등장), `test_system_prompt_mentions_demo_labels_and_korean_mapping`. `build_user_prompt` 픽스처 문자열을 `sports ball`/`bowl`로 정렬
- [`tests/test_response_parser.py`](../tests/test_response_parser.py) — 모든 `target`/`destination` 픽스처를 `sports ball`/`bowl`로, 복합/카메라 질문 케이스의 한국어 문구를 "그릇"으로 정렬
- [`tests/test_llm_response_schema.py`](../tests/test_llm_response_schema.py), [`tests/test_llm.py`](../tests/test_llm.py) — `target="ball"`/더미 vision 라벨을 `sports ball`/`bowl`로 정렬
- 전체 60 passed (이전 56 → 신규 4). `tests/test_dispatcher.py` 6건은 `pytest-asyncio` 미설치 환경 이슈로 무관(requirements.txt에는 명시됨 — `pip install -r requirements.txt`로 해소)

## 문서 갱신

- [`docs/architecture.md`](../docs/architecture.md)
  - 1장 프로젝트 개요 — "공을 집어 바구니에 담는" → "스포츠볼(`"sports ball"`)을 집어 그릇(`"bowl"`)에 담는", 데모 시나리오 변경 사유 한 줄 추가
  - 7장 Context 예시 — `"ball(화면 중앙 좌측 ...), basket(...)"` → `"sports ball(위치=[674,188] ...), bowl(...)"` + 현재 코드는 raw px 전달이고 의미 구역화 미적용임을 명시
  - 9장 미결 사항 — "YOLO target label 목록 확정" 행을 "COCO 80개로 임시 확정 (2026-05-12)"로 갱신, 커스텀 객체는 fine-tuning/open-vocab 필요로 표기

- [`docs/command_schema.md`](../docs/command_schema.md) — v0.3 → v0.4
  - 헤더 blockquote — 데모 시나리오(`sports ball`/`bowl`)와 라벨 출처(`COCO_LABELS`) 명시
  - 3장 robot_command Envelope 예시 — `target:"ball"`/`destination:"basket"` → `"sports ball"`/`"bowl"`
  - 3장 data 필드 정의 — `target`/`destination` 설명에 "(`COCO_LABELS` 중 하나)" 추가
  - 5장 vision_update 예시 — `label:"ball"` → `"sports ball"`
  - 6장 시나리오 1 — "공 잡아서 바구니에 담기" → "스포츠볼 집어서 그릇에 넣기 (메인 데모)", 시나리오 2 — `target:"ball"` → `"sports ball"`, Vision 상태 `ball 미감지` → `sports ball 미감지`
  - 7장 합의 표 — `target`/`destination` 행을 `COCO_LABELS` 기준으로 갱신, 커스텀 객체 시 fine-tuning 일정 확인 항목 추가
  - 8장 변경 이력 — v0.4 (2026-05-12) 추가

- [`README.md`](../README.md)
  - 사용 예시 — 입력을 `"공 집어서 그릇에 넣어줘"`로, 출력에 `[답변]` 줄 추가, `target=sports ball, destination=bowl`로 갱신
  - Context 추출 절 — 프롬프트 삽입 예시를 `sports ball`/`bowl`로 갱신

wire 자체는 변경 없음 — envelope·`robot_command`·`vision_update` 스키마는 그대로. `target`/`destination`의 **허용 문자열 집합**만 합의가 바뀐 것.

## 손대지 않은 영역

- [`shared/schemas/`](../shared/schemas/) (vision.py, command.py, llm_response.py) — 스키마 구조 변경 없음. `RobotCommand.target`은 여전히 `str` (enum화하지 않음 — 80개 + 추후 확장 고려)
- [`language/ws/`](../language/ws/), [`language/main.py`](../language/main.py), [`language/llm/openai_client.py`](../language/llm/openai_client.py), [`language/input/`](../language/input/) — 변경 없음
- PAI-Vision 측 — `result.names`를 canonical로 매핑하거나 fine-tuning하는 작업은 Vision 파트 범위. 현재는 Language가 COCO 라벨을 그대로 수용하는 방향
- `tests/test_dispatcher.py` — `pytest-asyncio` 미설치 환경 이슈로 본 변경과 무관 (이번에 손대지 않음)

## 검증

PAI-Language 루트에서:

```powershell
python -m pytest -q
```

결과: **56 passed**, `tests/test_dispatcher.py` 6건은 `pytest-asyncio` 미설치로 인한 **기존 환경 이슈**(본 변경과 무관, `pip install pytest-asyncio`로 해소). 영향받는 `tests/test_vision_state.py` + `tests/test_prompt_builder.py` 24건 전부 통과.

```python
from language.llm.prompt_builder import SYSTEM_PROMPT
# len(SYSTEM_PROMPT) == 2521, "sports ball" in SYSTEM_PROMPT, "toothbrush" in SYSTEM_PROMPT
from shared.constants import COCO_LABELS, KNOWN_LABELS
# len(COCO_LABELS) == 80, len(KNOWN_LABELS) == 80 (중복 없음)
```

## 한계 / 다음에 할 만한 것

- `basket`(바구니)는 여전히 COCO에 없음 → 진짜 바구니 인식이 필요하면 PAI-Vision에서 (a) tabletop 객체 fine-tuning, (b) open-vocab 검출기(YOLO-World / GroundingDINO 등) 도입. 후자는 추론 시 클래스 이름을 텍스트로 넘김 → fine-tuning 없이 임의 객체 가능하나 느리고 마스크 품질 떨어짐
- `vision_state`가 `to_context_string()`에서 raw `center_pixel`을 그대로 LLM에 넣는데(architecture.md 7장은 의미 구역 예시), `image_size` 기준 구역화 또는 최소 `image_size` 동봉 검토 — 별도 미결 사항
- `RobotCommand.target`을 Literal/Enum으로 좁힐지 — 지금은 `str` + 프롬프트 규칙 + `KNOWN_LABELS` 경고로만 가드. 커스텀 라벨 확장 빈도 보고 결정
