"""language.llm.prompt_builder 단위 테스트.

회귀 보호 — SYSTEM_PROMPT 핵심 규칙과 build_user_prompt 포매팅 안정성.
"""

from __future__ import annotations

from language.llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt


# --- SYSTEM_PROMPT 회귀 보호 -------------------------------------------------


def test_system_prompt_lists_all_action_types() -> None:
    """SYSTEM_PROMPT가 모든 action 옵션을 명시해야 한다."""
    for action in ("pick", "place", "pick_and_place", "home", "stop"):
        assert f'"{action}"' in SYSTEM_PROMPT, f"{action} action 누락"


def test_system_prompt_specifies_json_only_output() -> None:
    """LLM이 JSON 외 텍스트를 내지 않도록 명시되어야 함."""
    assert "JSON" in SYSTEM_PROMPT
    assert "JSON 외의 텍스트는 출력하지 마세요" in SYSTEM_PROMPT


def test_system_prompt_has_safety_fallback_rule() -> None:
    """모호/위험 명령은 stop으로 회귀하라는 규칙이 있어야 함."""
    assert "stop" in SYSTEM_PROMPT
    assert "모호하거나 위험" in SYSTEM_PROMPT


# --- build_user_prompt -------------------------------------------------------


def test_user_prompt_includes_both_sections() -> None:
    out = build_user_prompt("공 잡아줘", "현재 카메라: ball(0.91)")
    assert "[카메라 상태]" in out
    assert "[사용자 명령]" in out
    assert "현재 카메라: ball(0.91)" in out
    assert "공 잡아줘" in out


def test_user_prompt_camera_section_precedes_command_section() -> None:
    """카메라 컨텍스트가 사용자 명령보다 먼저 와야 (LLM이 컨텍스트를 먼저 읽도록)."""
    out = build_user_prompt("명령", "컨텍스트")
    assert out.index("[카메라 상태]") < out.index("[사용자 명령]")


def test_user_prompt_handles_empty_user_text() -> None:
    out = build_user_prompt("", "현재 카메라: 없음")
    assert "[카메라 상태]" in out
    assert "[사용자 명령]" in out
    assert "현재 카메라: 없음" in out


def test_user_prompt_handles_empty_vision_context() -> None:
    out = build_user_prompt("공 잡아줘", "")
    assert "[카메라 상태]" in out
    assert "[사용자 명령]" in out
    assert "공 잡아줘" in out


def test_user_prompt_handles_korean_text() -> None:
    out = build_user_prompt("바구니에 공을 넣어줘", "현재 카메라: ball, basket")
    assert "바구니에 공을 넣어줘" in out
    assert "현재 카메라: ball, basket" in out
