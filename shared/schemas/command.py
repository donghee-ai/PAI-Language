"""Language → Action Hub robot_command 스키마."""

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
    """robot_command 메시지의 data 페이로드."""

    action: ActionType
    target: str = "none"
    destination: str = "none"
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
        return self
