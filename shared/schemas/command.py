"""Language → Coordinator robot_command 스키마."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, model_validator


class ActionType(str, Enum):
    PICK = "pick"
    PLACE = "place"
    PICK_AND_PLACE = "pick_and_place"
    MOVE = "move"
    HOME = "home"
    STOP = "stop"
    # 쓰레기-모으기(ACT) 단일 태스크 트리거. target/destination 불필요 — Language의
    # 키워드 의도 게이트가 만들어내는 전용 액션이며, LLM이 직접 내보내지는 않는다.
    TRASH_GATHER = "trash_gather"


class RobotCommand(BaseModel):
    """robot_command 메시지의 data 페이로드.

    instruction 필드는 LeRobot VLA policy(pi0/smolvla/wall_x 등)의 `task` 입력으로
    그대로 사용할 수 있는 영어 자연어 문자열이다. LLM이 명시적으로 채우지 않으면
    action/target/destination/direction 으로부터 자동 생성된다.

    direction 필드는 move 액션에서만 의미가 있다(left/right/forward/backward 등).
    move 외 액션에서는 강제로 "none" 이 된다.
    """

    action: ActionType
    target: str = "none"
    destination: str = "none"
    direction: str = "none"
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
        if a == ActionType.MOVE:
            if self.target == "none" or self.direction == "none":
                raise ValueError("move 액션에는 target과 direction이 모두 필요합니다")
        if a in (ActionType.HOME, ActionType.STOP):
            self.target = "none"
            self.destination = "none"
        # direction 은 move 에서만 의미가 있다.
        if a != ActionType.MOVE:
            self.direction = "none"

        if not self.instruction.strip():
            self.instruction = _derive_instruction(
                a, self.target, self.destination, self.direction
            )
        return self

    def move_command_key(self) -> str | None:
        """move 액션을 'move_{target}_{direction}' 실행 커맨드 키로 조립.

        예: target="box", direction="left" → "move_box_left". move 가 아니면 None.
        이 키를 shared.constants.EXECUTABLE_MOVE_COMMANDS 화이트리스트와 대조해
        실행 가능 여부를 판단한다.
        """
        if self.action != ActionType.MOVE:
            return None
        return f"move_{self.target}_{self.direction}"


def _derive_instruction(
    action: ActionType, target: str, destination: str, direction: str = "none"
) -> str:
    """LLM이 instruction을 비워둔 경우의 폴백 — action 필드들로 영어 한 줄을 만든다.

    VLA policy 학습 코퍼스에 흔한 phrasing 을 따른다. 라벨 자체는 COCO 영어 그대로 사용.
    move 는 학습 데이터셋 task("Move the box to the left")와 동일한 표기를 쓴다.
    """
    if action == ActionType.PICK:
        return f"pick up the {target}"
    if action == ActionType.PLACE:
        return f"place the {target} in the {destination}"
    if action == ActionType.PICK_AND_PLACE:
        return f"pick up the {target} and place it in the {destination}"
    if action == ActionType.MOVE:
        return f"Move the {target} to the {direction}"
    if action == ActionType.HOME:
        return "move to the home position"
    if action == ActionType.STOP:
        return "stop"
    if action == ActionType.TRASH_GATHER:
        # 학습 task 명과 동일하게 유지 (rollout 어댑터가 engine._task 로 주입).
        return "trash_gathering"
    return ""
