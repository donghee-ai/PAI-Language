"""language.llm.prompt_builder 단위 테스트.

회귀 보호 — SYSTEM_PROMPT 핵심 규칙(LLM wrapper 형식 + 분류 가이드 + 명령/답변
규칙)과 build_user_prompt 포매팅 안정성.
"""

from __future__ import annotations

from language.llm.prompt_builder import SYSTEM_PROMPT, build_user_prompt
from shared.constants import COCO_LABELS


# --- SYSTEM_PROMPT 회귀 보호 -------------------------------------------------


def test_system_prompt_lists_all_action_types() -> None:
    """SYSTEM_PROMPT가 모든 action 옵션을 명시해야 한다."""
    for action in ("pick", "place", "pick_and_place", "home", "stop"):
        assert f'"{action}"' in SYSTEM_PROMPT, f"{action} action 누락"


def test_system_prompt_lists_every_known_label() -> None:
    """target/destination 후보가 되는 COCO 라벨 전부가 프롬프트에 나열되어야 함."""
    for label in COCO_LABELS:
        assert label in SYSTEM_PROMPT, f"라벨 누락: {label!r}"


def test_system_prompt_mentions_demo_labels_and_korean_mapping() -> None:
    """데모 객체(sports ball / bowl)와 한국어→라벨 매핑 안내가 명시되어야 함."""
    assert "sports ball" in SYSTEM_PROMPT
    assert "bowl" in SYSTEM_PROMPT
    assert "인식 가능한 객체 라벨" in SYSTEM_PROMPT


def test_system_prompt_specifies_json_only_output() -> None:
    """LLM이 JSON 외 텍스트를 내지 않도록 명시되어야 함."""
    assert "JSON" in SYSTEM_PROMPT
    assert "JSON 외의 텍스트는 절대 출력하지 마세요" in SYSTEM_PROMPT


def test_system_prompt_has_safety_fallback_rule() -> None:
    """모호/위험한 명령은 command=null로 두고 다시 묻는 규칙."""
    assert "stop" in SYSTEM_PROMPT
    assert "모호" in SYSTEM_PROMPT


def test_system_prompt_describes_answer_and_command_fields() -> None:
    """wrapper의 두 필드 — answer, command — 가 모두 명시되어야 함."""
    assert '"answer"' in SYSTEM_PROMPT
    assert '"command"' in SYSTEM_PROMPT


def test_system_prompt_describes_classification_scenarios() -> None:
    """일상 대화 / 카메라 질문 / 로봇 명령 / 복합 — 4가지 시나리오 가이드 등장."""
    assert "일상 대화" in SYSTEM_PROMPT
    assert "질문" in SYSTEM_PROMPT
    assert "로봇 명령" in SYSTEM_PROMPT
    assert "복합" in SYSTEM_PROMPT


def test_system_prompt_forbids_empty_answer_text() -> None:
    """answer.text는 빈 문자열이 될 수 없다는 규칙이 명시되어야 함."""
    assert "빈 문자열" in SYSTEM_PROMPT


def test_system_prompt_allows_command_null() -> None:
    """일상 대화/단순 질문에서는 command=null이 가능함이 명시되어야 함."""
    assert "null" in SYSTEM_PROMPT


# --- build_user_prompt -------------------------------------------------------


def test_user_prompt_includes_both_sections() -> None:
    out = build_user_prompt("공 잡아줘", "현재 카메라: sports ball(0.91)")
    assert "[카메라 상태]" in out
    assert "[사용자 명령]" in out
    assert "현재 카메라: sports ball(0.91)" in out
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
    out = build_user_prompt("그릇에 공을 넣어줘", "현재 카메라: sports ball, bowl")
    assert "그릇에 공을 넣어줘" in out
    assert "현재 카메라: sports ball, bowl" in out
