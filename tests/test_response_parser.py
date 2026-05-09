"""language.llm.response_parser.parse_llm_response 단위 테스트.

LLM JSON 출력 → RobotCommand 파싱 + 잘못된 입력에 대한 STOP fallback 검증.
"""

from __future__ import annotations

import json

from language.llm.response_parser import parse_llm_response
from shared.schemas.command import ActionType


# --- 정상 파싱 ---------------------------------------------------------------


def test_parse_pick_command() -> None:
    raw = json.dumps({"action": "pick", "target": "ball", "reasoning": "공 집기"})
    cmd = parse_llm_response(raw, "공 잡아줘")
    assert cmd.action == ActionType.PICK
    assert cmd.target == "ball"
    assert cmd.destination == "none"
    assert cmd.reasoning == "공 집기"
    assert cmd.raw_input == "공 잡아줘"
    assert cmd.vision_confirmed is False


def test_parse_pick_and_place_full_fields() -> None:
    raw = json.dumps(
        {
            "action": "pick_and_place",
            "target": "ball",
            "destination": "basket",
            "reasoning": "공을 바구니에",
        }
    )
    cmd = parse_llm_response(raw, "공 바구니에 넣어")
    assert cmd.action == ActionType.PICK_AND_PLACE
    assert cmd.target == "ball"
    assert cmd.destination == "basket"


def test_parse_home_normalizes_target_destination_to_none() -> None:
    """RobotCommand validator가 home/stop 액션의 target/destination을 'none'으로 강제."""
    raw = json.dumps(
        {"action": "home", "target": "ball", "destination": "basket", "reasoning": "복귀"}
    )
    cmd = parse_llm_response(raw, "원위치")
    assert cmd.action == ActionType.HOME
    assert cmd.target == "none"
    assert cmd.destination == "none"


# --- 마크다운 코드 블록 추출 -------------------------------------------------


def test_strip_markdown_json_fence() -> None:
    raw = '```json\n{"action": "stop", "target": "none", "destination": "none", "reasoning": "정지"}\n```'
    cmd = parse_llm_response(raw, "멈춰")
    assert cmd.action == ActionType.STOP
    assert cmd.reasoning == "정지"


def test_strip_plain_code_fence_without_language_tag() -> None:
    raw = '```\n{"action": "stop", "target": "none", "destination": "none", "reasoning": "정지"}\n```'
    cmd = parse_llm_response(raw, "멈춰")
    assert cmd.action == ActionType.STOP


# --- Fallback (STOP으로 안전 회귀) -------------------------------------------


def test_invalid_json_falls_back_to_stop() -> None:
    cmd = parse_llm_response("이건 JSON이 아닙니다", "잘못된 입력")
    assert cmd.action == ActionType.STOP
    assert cmd.target == "none"
    assert cmd.destination == "none"
    assert "파싱 실패" in cmd.reasoning
    assert cmd.raw_input == "잘못된 입력"


def test_unknown_action_value_falls_back_to_stop() -> None:
    """ActionType enum에 없는 값은 ValueError → STOP fallback."""
    raw = json.dumps({"action": "fly", "target": "ball", "reasoning": "x"})
    cmd = parse_llm_response(raw, "날아라")
    assert cmd.action == ActionType.STOP
    assert "파싱 실패" in cmd.reasoning


def test_missing_action_field_falls_back_to_stop() -> None:
    raw = json.dumps({"target": "ball", "reasoning": "x"})
    cmd = parse_llm_response(raw, "x")
    assert cmd.action == ActionType.STOP


def test_pick_without_target_falls_back_to_stop() -> None:
    """RobotCommand validator: pick + target='none' → ValueError → STOP fallback."""
    raw = json.dumps({"action": "pick", "reasoning": "타겟 없음"})
    cmd = parse_llm_response(raw, "x")
    assert cmd.action == ActionType.STOP
    assert "파싱 실패" in cmd.reasoning


def test_place_without_destination_falls_back_to_stop() -> None:
    raw = json.dumps({"action": "place", "target": "ball", "reasoning": "x"})
    cmd = parse_llm_response(raw, "x")
    assert cmd.action == ActionType.STOP


# --- 기본값 채움 -------------------------------------------------------------


def test_optional_fields_default_to_safe_values() -> None:
    """target/destination/reasoning이 없어도 (action 제약을 만족하면) 기본값으로 채워짐."""
    raw = json.dumps({"action": "stop"})
    cmd = parse_llm_response(raw, "멈춰")
    assert cmd.action == ActionType.STOP
    assert cmd.target == "none"
    assert cmd.destination == "none"
    assert cmd.reasoning == ""
    assert cmd.raw_input == "멈춰"
