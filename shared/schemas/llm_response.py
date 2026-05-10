"""LLM 응답 wrapper — 일반 대화 + 카메라 질문 + 로봇 명령 통합 처리."""

from __future__ import annotations

from typing import Annotated, Optional

from pydantic import BaseModel, StringConstraints

from shared.schemas.command import RobotCommand


class AssistantAnswer(BaseModel):
    """사용자에게 보여줄 자연어 답변. 모든 LLM 응답에 항상 포함된다."""

    text: Annotated[str, StringConstraints(min_length=1)]
    raw_input: str = ""


class LLMResponse(BaseModel):
    """LLM 응답 wrapper.

    - answer: 항상 존재. 사용자에게 보여줄 한국어 답변 (대화/질문 답변/명령 확인).
    - command: 사용자 입력에 명령 의도가 있을 때만. 일상 대화/질문은 None.
    - reasoning: 분류·판단 근거 한 문장.
    """

    answer: AssistantAnswer
    command: Optional[RobotCommand] = None
    reasoning: str = ""
