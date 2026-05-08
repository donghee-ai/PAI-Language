# API 연동 버그 수정 (2026-05-07)

## 수정 내역

### 1. confidence KeyError 수정
- **파일**: `language/context/vision_state.py` (line 40)
- **문제**: vision 데이터에서 `confidence` 키 존재 여부를 체크하지 않아 KeyError 발생 가능
- **수정**: 필터 조건에 `"confidence" in obj` 추가

### 2. load_dotenv() 경로 고정
- **파일**: `language/config.py` (line 10-11)
- **문제**: `load_dotenv()` 호출 시 경로를 지정하지 않아 CWD에 따라 `.env`를 못 찾을 수 있음
- **수정**: `Path(__file__).resolve().parent.parent / ".env"` 로 프로젝트 루트 기준 절대 경로 지정

### 3. WS send() 타임아웃 추가
- **파일**: `language/ws/client.py` (line 33-39)
- **문제**: `_connected.wait()`가 타임아웃 없이 무한 대기하여, WS 서버 다운 시 블로킹
- **수정**: `asyncio.wait_for()`로 감싸서 기본 10초 타임아웃 적용, 초과 시 `TimeoutError` 발생 및 로그 출력

### 4. LLM 에러 구분 처리
- **파일**: `language/main.py` (line 75-86)
- **문제**: 모든 OpenAI API 예외를 `Exception`으로 일괄 처리하여 원인 파악 불가
- **수정**: `AuthenticationError`, `RateLimitError`, `APIConnectionError`, `APIError`를 개별 catch하여 각각 다른 안내 메시지 출력

### 5. vision_confirmed 로직 개선
- **파일**: `language/llm/response_parser.py`, `language/main.py`
- **문제**: `vision_confirmed`가 아무 객체나 감지되면 True로 설정되어, 실제 대상 객체 존재 여부와 무관하게 동작
- **수정**:
  - `parse_llm_response()`에서 `vision_confirmed` 파라미터 제거
  - `main.py`에서 파싱 후 `command.target`을 기준으로 `self.vision.has_label(command.target)`을 호출하여 정확한 대상 확인
