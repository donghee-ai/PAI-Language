"""LLM 출력 → LLMResponse(wrapper) 파싱 + 유효성 검증.

LLMResponse는 항상 answer를 가지며, command는 명령 의도가 있을 때만 채워진다.
파싱 실패 / answer 검증 실패는 안전한 STOP wrapper로, command만 잘못된 경우는
answer는 보존하고 command만 STOP으로 대체한다.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from pydantic import ValidationError

from shared.schemas.command import ActionType, RobotCommand
from shared.schemas.llm_response import AssistantAnswer, LLMResponse

log = logging.getLogger(__name__)

_FALLBACK_ANSWER_TEXT = "죄송합니다, 응답을 처리하지 못해 안전 정지합니다."


def parse_llm_response(raw: str, raw_input: str) -> LLMResponse:
    """LLM의 JSON 응답을 LLMResponse로 파싱한다.

    파싱 실패 시 placeholder answer + STOP command로 안전하게 회귀한다.
    command만 잘못된 경우 answer는 LLM이 준 것을 보존하고 command만 STOP으로 대체.
    vision_confirmed는 호출측에서 파싱 후 별도로 설정해야 한다.
    """
    try:
        cleaned = _extract_json(raw)
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        log.warning("LLM 응답 JSON 파싱 실패 (%s): %s", exc, raw[:300])
        return _fallback_stop(raw_input, f"JSON 파싱 실패: {exc}")

    if not isinstance(data, dict):
        return _fallback_stop(raw_input, "응답이 객체가 아님")

    # answer는 필수 — 누락/잘못된 형식이면 fallback 회귀
    answer_data = data.get("answer")
    if not isinstance(answer_data, dict):
        return _fallback_stop(raw_input, "answer 필드 누락 또는 형식 오류")
    try:
        answer = AssistantAnswer(
            text=answer_data.get("text", ""),
            raw_input=raw_input,
        )
    except ValidationError as exc:
        log.warning("answer 검증 실패: %s", exc)
        return _fallback_stop(raw_input, f"answer 검증 실패: {exc}")

    reasoning = data.get("reasoning") or ""
    if not isinstance(reasoning, str):
        reasoning = ""

    # command는 옵션 — null/누락이면 그대로 None, 있으면 검증
    command = _parse_command(data.get("command"), raw_input)

    return LLMResponse(answer=answer, command=command, reasoning=reasoning)


def _parse_command(command_data: object, raw_input: str) -> Optional[RobotCommand]:
    """command 필드를 RobotCommand로 변환. None이면 그대로 None,
    잘못된 형식/검증 실패면 STOP command로 대체 (answer는 별도로 보존됨).
    """
    if command_data is None:
        return None
    if not isinstance(command_data, dict):
        return _stop_command(raw_input, "command 필드가 객체가 아님")
    try:
        return RobotCommand(
            action=ActionType(command_data["action"]),
            target=command_data.get("target", "none"),
            destination=command_data.get("destination", "none"),
            instruction=command_data.get("instruction", ""),
            reasoning=command_data.get("reasoning", ""),
            raw_input=raw_input,
        )
    except (KeyError, ValueError, ValidationError) as exc:
        log.warning("command 검증 실패 (%s), STOP으로 대체", exc)
        return _stop_command(raw_input, f"command 파싱 실패: {exc}")


def _stop_command(raw_input: str, reason: str) -> RobotCommand:
    return RobotCommand(
        action=ActionType.STOP,
        target="none",
        destination="none",
        reasoning=f"파싱 실패: {reason}",
        raw_input=raw_input,
    )


def _fallback_stop(raw_input: str, reason: str) -> LLMResponse:
    """answer까지 만들 수 없는 상황의 안전 회귀.

    placeholder answer + STOP command + 회귀 사유를 reasoning에 담는다.
    """
    return LLMResponse(
        answer=AssistantAnswer(text=_FALLBACK_ANSWER_TEXT, raw_input=raw_input),
        command=_stop_command(raw_input, reason),
        reasoning=f"파싱 실패: {reason}",
    )


def _extract_json(text: str) -> str:
    """마크다운 코드 블록이 있으면 내부 JSON만 추출."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    return text.strip()
