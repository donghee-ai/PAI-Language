"""LLM 출력 → RobotCommand 구조체 파싱 + 유효성 검증."""

from __future__ import annotations

import json
import logging
import re

from shared.schemas.command import ActionType, RobotCommand

log = logging.getLogger(__name__)


def parse_llm_response(raw: str, raw_input: str) -> RobotCommand:
    """LLM의 JSON 응답을 RobotCommand로 파싱한다.

    파싱 실패 시 안전한 stop 명령을 반환한다.
    vision_confirmed는 호출측에서 파싱 후 별도로 설정해야 한다.
    """
    try:
        # LLM이 ```json ... ``` 으로 감쌀 수 있으므로 추출
        cleaned = _extract_json(raw)
        data = json.loads(cleaned)

        return RobotCommand(
            action=ActionType(data["action"]),
            target=data.get("target", "none"),
            destination=data.get("destination", "none"),
            reasoning=data.get("reasoning", ""),
            raw_input=raw_input,
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        log.warning("LLM 응답 파싱 실패 (%s), stop 명령으로 대체: %s", exc, raw[:300])
        return RobotCommand(
            action=ActionType.STOP,
            target="none",
            destination="none",
            reasoning=f"LLM 응답 파싱 실패: {exc}",
            raw_input=raw_input,
        )


def _extract_json(text: str) -> str:
    """마크다운 코드 블록이 있으면 내부 JSON만 추출."""
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return match.group(1).strip()
    return text.strip()
