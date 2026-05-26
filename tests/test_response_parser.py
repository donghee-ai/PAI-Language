"""language.llm.response_parser.parse_llm_response 단위 테스트.

LLM JSON 응답 → LLMResponse(wrapper) 파싱 + 잘못된 입력에 대한 fallback 검증.
answer는 항상 존재 (일반 LLM 대화), command는 명령 의도가 있을 때만.
"""

from __future__ import annotations

import json

from language.llm.response_parser import parse_llm_response
from shared.schemas.command import ActionType


# --- 정상 파싱 (명령 케이스) ----------------------------------------------------


def test_parse_pick_command() -> None:
    raw = json.dumps(
        {
            "answer": {"text": "네, 공을 잡을게요."},
            "command": {"action": "pick", "target": "sports ball", "reasoning": "공 집기"},
            "reasoning": "명령 의도 확인",
        }
    )
    resp = parse_llm_response(raw, "공 잡아줘")
    assert resp.answer.text == "네, 공을 잡을게요."
    assert resp.command is not None
    assert resp.command.action == ActionType.PICK
    assert resp.command.target == "sports ball"
    assert resp.command.destination == "none"
    assert resp.command.reasoning == "공 집기"
    assert resp.command.raw_input == "공 잡아줘"
    assert resp.command.vision_confirmed is False


def test_parse_pick_and_place_full_fields() -> None:
    raw = json.dumps(
        {
            "answer": {"text": "공을 그릇에 넣어드릴게요."},
            "command": {
                "action": "pick_and_place",
                "target": "sports ball",
                "destination": "bowl",
                "reasoning": "공을 그릇에",
            },
            "reasoning": "복합 의도",
        }
    )
    resp = parse_llm_response(raw, "공 그릇에 넣어")
    assert resp.command is not None
    assert resp.command.action == ActionType.PICK_AND_PLACE
    assert resp.command.target == "sports ball"
    assert resp.command.destination == "bowl"


def test_parse_home_normalizes_target_destination_to_none() -> None:
    """RobotCommand validator가 home/stop 액션의 target/destination을 'none'으로 강제."""
    raw = json.dumps(
        {
            "answer": {"text": "원위치로 이동합니다."},
            "command": {
                "action": "home",
                "target": "sports ball",
                "destination": "bowl",
                "reasoning": "복귀",
            },
        }
    )
    resp = parse_llm_response(raw, "원위치")
    assert resp.command is not None
    assert resp.command.action == ActionType.HOME
    assert resp.command.target == "none"
    assert resp.command.destination == "none"


# --- 정상 파싱 (대화/질문 — command 없음) -----------------------------------------


def test_parse_pure_chat() -> None:
    raw = json.dumps(
        {"answer": {"text": "안녕하세요! 무엇을 도와드릴까요?"}, "command": None}
    )
    resp = parse_llm_response(raw, "안녕?")
    assert resp.answer.text == "안녕하세요! 무엇을 도와드릴까요?"
    assert resp.command is None


def test_parse_camera_question() -> None:
    raw = json.dumps(
        {
            "answer": {"text": "카메라에 sports ball과 bowl이 보입니다."},
            "command": None,
            "reasoning": "카메라 정보 조회",
        }
    )
    resp = parse_llm_response(raw, "지금 뭐 보여?")
    assert resp.command is None
    assert "sports ball" in resp.answer.text
    assert resp.reasoning == "카메라 정보 조회"


def test_command_field_omitted_treated_as_none() -> None:
    """command 필드 자체가 없어도 None으로 처리."""
    raw = json.dumps({"answer": {"text": "안녕!"}})
    resp = parse_llm_response(raw, "안녕")
    assert resp.command is None


def test_command_null_explicit() -> None:
    raw = json.dumps({"answer": {"text": "그냥 대화"}, "command": None})
    resp = parse_llm_response(raw, "x")
    assert resp.command is None


# --- 정상 파싱 (복합) ----------------------------------------------------------


def test_parse_compound_input() -> None:
    """질문 + 명령이 섞인 복합 입력 — answer와 command 모두 채워짐."""
    raw = json.dumps(
        {
            "answer": {"text": "네, 공이 보여요. 그릇에 넣어드릴게요."},
            "command": {
                "action": "pick_and_place",
                "target": "sports ball",
                "destination": "bowl",
                "reasoning": "복합 명령",
            },
            "reasoning": "질문에 답하고 명령 수행",
        }
    )
    resp = parse_llm_response(raw, "저기 공 보여? 저거 집어서 그릇에 넣어줘")
    assert "공이 보여" in resp.answer.text
    assert resp.command is not None
    assert resp.command.action == ActionType.PICK_AND_PLACE
    assert resp.command.target == "sports ball"
    assert resp.command.destination == "bowl"


# --- 마크다운 코드 블록 추출 ---------------------------------------------------


def test_strip_markdown_json_fence() -> None:
    raw = (
        '```json\n{"answer": {"text": "정지합니다."}, '
        '"command": {"action": "stop", "target": "none", "destination": "none", "reasoning": "정지"}}\n```'
    )
    resp = parse_llm_response(raw, "멈춰")
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP
    assert resp.command.reasoning == "정지"


def test_strip_plain_code_fence_without_language_tag() -> None:
    raw = (
        '```\n{"answer": {"text": "정지"}, '
        '"command": {"action": "stop", "target": "none", "destination": "none"}}\n```'
    )
    resp = parse_llm_response(raw, "멈춰")
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP


# --- Fallback (응답 자체가 깨진 경우 — placeholder answer + STOP command) -------


def test_invalid_json_falls_back_to_stop() -> None:
    resp = parse_llm_response("이건 JSON이 아닙니다", "잘못된 입력")
    assert resp.answer.text != ""
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP
    assert "파싱 실패" in resp.command.reasoning
    assert resp.answer.raw_input == "잘못된 입력"
    assert resp.command.raw_input == "잘못된 입력"


def test_response_not_an_object_falls_back_to_stop() -> None:
    """JSON 배열이거나 스칼라면 wrapper 형식 위반 → fallback."""
    resp = parse_llm_response("[1, 2, 3]", "x")
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP


def test_missing_answer_falls_back_to_stop() -> None:
    """answer 필드가 없으면 wrapper 자체가 무효 → fallback (placeholder answer + STOP)."""
    raw = json.dumps({"command": {"action": "stop"}})
    resp = parse_llm_response(raw, "x")
    assert resp.answer.text != ""
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP
    assert "파싱 실패" in resp.command.reasoning


def test_empty_answer_text_falls_back_to_stop() -> None:
    """answer.text가 빈 문자열이면 Pydantic min_length=1 위반 → fallback."""
    raw = json.dumps({"answer": {"text": ""}, "command": None})
    resp = parse_llm_response(raw, "x")
    assert resp.answer.text != ""  # placeholder answer
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP


def test_answer_field_wrong_type_falls_back_to_stop() -> None:
    """answer가 dict가 아닌 경우 (문자열) → fallback."""
    raw = json.dumps({"answer": "그냥 문자열", "command": None})
    resp = parse_llm_response(raw, "x")
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP


# --- command만 잘못된 경우 (answer는 LLM이 준 것 보존, command만 STOP으로 대체) ---


def test_unknown_action_value_preserves_answer() -> None:
    """ActionType enum에 없는 action → answer 보존, command만 STOP으로 대체."""
    raw = json.dumps(
        {
            "answer": {"text": "그건 못 합니다."},
            "command": {"action": "fly", "target": "sports ball"},
        }
    )
    resp = parse_llm_response(raw, "날아라")
    assert resp.answer.text == "그건 못 합니다."  # answer 보존
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP
    assert "파싱 실패" in resp.command.reasoning


def test_missing_action_field_preserves_answer() -> None:
    raw = json.dumps(
        {"answer": {"text": "명령 인식 실패"}, "command": {"target": "sports ball"}}
    )
    resp = parse_llm_response(raw, "x")
    assert resp.answer.text == "명령 인식 실패"
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP


def test_pick_without_target_preserves_answer() -> None:
    """RobotCommand validator: pick + target='none' → command만 STOP으로 대체."""
    raw = json.dumps(
        {
            "answer": {"text": "무엇을 잡을지 모르겠어요."},
            "command": {"action": "pick", "reasoning": "타겟 없음"},
        }
    )
    resp = parse_llm_response(raw, "x")
    assert resp.answer.text == "무엇을 잡을지 모르겠어요."
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP


def test_place_without_destination_preserves_answer() -> None:
    raw = json.dumps(
        {
            "answer": {"text": "어디에 둘지 알려주세요."},
            "command": {"action": "place", "target": "sports ball"},
        }
    )
    resp = parse_llm_response(raw, "x")
    assert resp.answer.text == "어디에 둘지 알려주세요."
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP


def test_command_field_wrong_type_preserves_answer() -> None:
    """command가 dict가 아닌 (예: 문자열) 경우 → answer 보존, command STOP."""
    raw = json.dumps({"answer": {"text": "정지"}, "command": "stop"})
    resp = parse_llm_response(raw, "x")
    assert resp.answer.text == "정지"
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP


# --- raw_input 전파 -----------------------------------------------------------


def test_raw_input_preserved_in_answer() -> None:
    raw = json.dumps({"answer": {"text": "안녕!"}, "command": None})
    resp = parse_llm_response(raw, "안녕?")
    assert resp.answer.raw_input == "안녕?"


def test_raw_input_preserved_in_command() -> None:
    raw = json.dumps(
        {
            "answer": {"text": "공을 잡을게요."},
            "command": {"action": "pick", "target": "sports ball"},
        }
    )
    resp = parse_llm_response(raw, "공 잡아줘")
    assert resp.command is not None
    assert resp.command.raw_input == "공 잡아줘"


# --- 기본값 채움 -------------------------------------------------------------


def test_optional_command_fields_default_to_safe_values() -> None:
    """target/destination/reasoning이 없어도 (action 제약을 만족하면) 기본값으로 채워짐."""
    raw = json.dumps(
        {"answer": {"text": "정지합니다."}, "command": {"action": "stop"}}
    )
    resp = parse_llm_response(raw, "멈춰")
    assert resp.command is not None
    assert resp.command.action == ActionType.STOP
    assert resp.command.target == "none"
    assert resp.command.destination == "none"
    assert resp.command.reasoning == ""
    assert resp.command.raw_input == "멈춰"
    assert resp.command.instruction == "stop"  # 폴백 생성


# --- instruction 라운드트립 / 폴백 ---------------------------------------------


def test_instruction_explicit_value_is_preserved() -> None:
    """LLM이 instruction을 명시한 경우 그대로 보존."""
    raw = json.dumps(
        {
            "answer": {"text": "공을 그릇에 넣어드릴게요."},
            "command": {
                "action": "pick_and_place",
                "target": "sports ball",
                "destination": "bowl",
                "instruction": "pick up the sports ball and place it in the bowl",
                "reasoning": "복합 명령",
            },
        }
    )
    resp = parse_llm_response(raw, "공 그릇에 넣어")
    assert resp.command is not None
    assert resp.command.instruction == "pick up the sports ball and place it in the bowl"


def test_instruction_missing_is_auto_derived() -> None:
    """LLM이 instruction 필드를 누락해도 action/target/destination 으로부터 폴백 생성."""
    raw = json.dumps(
        {
            "answer": {"text": "네, 잡을게요."},
            "command": {"action": "pick", "target": "sports ball"},
        }
    )
    resp = parse_llm_response(raw, "공 잡아줘")
    assert resp.command is not None
    assert resp.command.instruction == "pick up the sports ball"
