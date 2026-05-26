"""Language → Coordinator robot_command 스키마."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, model_validator


class ActionType(str, Enum):
    PICK = "pick"
    PLACE = "place"
    PICK_AND_PLACE = "pick_and_place"
    HOME = "home"
    STOP = "stop"


class RobotCommand(BaseModel):
    """robot_command 메시지의 data 페이로드.

    instruction 필드는 LeRobot VLA policy(pi0/smolvla/wall_x 등)의 `task` 입력으로
    그대로 사용할 수 있는 영어 자연어 문자열이다. LLM이 명시적으로 채우지 않으면
    action/target/destination 으로부터 자동 생성된다.
    """

    action: ActionType
    target: str = "none"
    destination: str = "none"
    instruction: str = ""
    reasoning: str = ""
    raw_input: str = ""
    vision_confirmed: bool = False

    @model_validator(mode="after")
    def validate_action_fields(self) -> "RobotCommand":
        a = self.action
        if a == ActionType.PICK and self.target == "none":
            raise ValueError("pick 액션에는 target이 필요합니다")
        if a in (ActionType.PLACE, ActionType.PICK_AND_PLACE):
            if self.target == "none" or self.destination == "none":
                raise ValueError(f"{a.value} 액션에는 target과 destination이 모두 필요합니다")
        if a in (ActionType.HOME, ActionType.STOP):
            self.target = "none"
            self.destination = "none"

        if not self.instruction.strip():
            self.instruction = _derive_instruction(a, self.target, self.destination)
        return self


def _derive_instruction(action: ActionType, target: str, destination: str) -> str:
    """LLM이 instruction을 비워둔 경우의 폴백 — action/target/destination으로 영어 한 줄을 만든다.

    VLA policy 학습 코퍼스에 흔한 phrasing 을 따른다. 라벨 자체는 COCO 영어 그대로 사용.
    """
    if action == ActionType.PICK:
        return f"pick up the {target}"
    if action == ActionType.PLACE:
        return f"place the {target} in the {destination}"
    if action == ActionType.PICK_AND_PLACE:
        return f"pick up the {target} and place it in the {destination}"
    if action == ActionType.HOME:
        return "move to the home position"
    if action == ActionType.STOP:
        return "stop"
    return ""
