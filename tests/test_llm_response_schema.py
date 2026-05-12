"""shared.schemas.llm_response Pydantic 모델 단위 테스트.

parser를 거치지 않은 모델 자체의 정합성 검증 — answer 필수, command Optional,
text min_length 등.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.schemas.command import ActionType, RobotCommand
from shared.schemas.llm_response import AssistantAnswer, LLMResponse


# --- LLMResponse: 정상 인스턴스화 ---------------------------------------------


def test_llm_response_with_answer_only() -> None:
    """일상 대화 케이스 — answer만, command는 None."""
    resp = LLMResponse(answer=AssistantAnswer(text="안녕하세요!"), command=None)
    assert resp.answer.text == "안녕하세요!"
    assert resp.command is None
    assert resp.reasoning == ""


def test_llm_response_with_answer_and_command() -> None:
    """명령 케이스 — answer + command 둘 다."""
    resp = LLMResponse(
        answer=AssistantAnswer(text="공을 잡을게요."),
        command=RobotCommand(action=ActionType.PICK, target="sports ball"),
        reasoning="명령 의도 확인",
    )
    assert resp.command is not None
    assert resp.command.action == ActionType.PICK
    assert resp.reasoning == "명령 의도 확인"


def test_llm_response_command_default_is_none() -> None:
    """command는 명시 안 해도 None으로 default."""
    resp = LLMResponse(answer=AssistantAnswer(text="hi"))
    assert resp.command is None


def test_llm_response_accepts_command_as_dict() -> None:
    """dict로 command를 줘도 RobotCommand로 자동 변환."""
    resp = LLMResponse(
        answer=AssistantAnswer(text="ok"),
        command={"action": "pick", "target": "sports ball"},
    )
    assert isinstance(resp.command, RobotCommand)
    assert resp.command.action == ActionType.PICK


# --- LLMResponse: 검증 실패 ----------------------------------------------------


def test_llm_response_missing_answer_raises() -> None:
    """answer 필드 없으면 ValidationError."""
    with pytest.raises(ValidationError):
        LLMResponse()  # type: ignore[call-arg]


def test_llm_response_invalid_command_raises() -> None:
    """RobotCommand validator 위반 (pick + target=none) → ValidationError."""
    with pytest.raises(ValidationError):
        LLMResponse(
            answer=AssistantAnswer(text="ok"),
            command={"action": "pick", "target": "none"},
        )


# --- AssistantAnswer ---------------------------------------------------------


def test_assistant_answer_normal() -> None:
    a = AssistantAnswer(text="공이 보입니다.")
    assert a.text == "공이 보입니다."
    assert a.raw_input == ""


def test_assistant_answer_empty_text_raises() -> None:
    """text의 min_length=1 — 빈 문자열은 ValidationError."""
    with pytest.raises(ValidationError):
        AssistantAnswer(text="")


def test_assistant_answer_preserves_raw_input() -> None:
    a = AssistantAnswer(text="hi", raw_input="안녕?")
    assert a.raw_input == "안녕?"
