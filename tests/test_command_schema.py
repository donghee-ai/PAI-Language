"""shared.schemas.command.RobotCommand 단위 테스트.

instruction 자동 생성(폴백)과 명시값 보존 동작을 검증한다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.schemas.command import ActionType, RobotCommand


# --- instruction 자동 생성 (LLM이 비워둔 경우의 폴백) ---------------------------


def test_pick_derives_instruction() -> None:
    cmd = RobotCommand(action=ActionType.PICK, target="sports ball")
    assert cmd.instruction == "pick up the sports ball"


def test_place_derives_instruction() -> None:
    cmd = RobotCommand(action=ActionType.PLACE, target="sports ball", destination="bowl")
    assert cmd.instruction == "place the sports ball in the bowl"


def test_pick_and_place_derives_instruction() -> None:
    cmd = RobotCommand(
        action=ActionType.PICK_AND_PLACE, target="sports ball", destination="bowl"
    )
    assert cmd.instruction == "pick up the sports ball and place it in the bowl"


def test_move_derives_instruction() -> None:
    cmd = RobotCommand(action=ActionType.MOVE, target="box", direction="left")
    # 학습 데이터셋 task("Move the box to the left")와 동일 표기여야 함.
    assert cmd.instruction == "Move the box to the left"


def test_move_other_direction_derives_instruction() -> None:
    cmd = RobotCommand(action=ActionType.MOVE, target="box", direction="right")
    assert cmd.instruction == "Move the box to the right"


def test_move_requires_target_and_direction() -> None:
    with pytest.raises(ValidationError):
        RobotCommand(action=ActionType.MOVE, target="box")  # direction 누락
    with pytest.raises(ValidationError):
        RobotCommand(action=ActionType.MOVE, direction="left")  # target 누락


def test_non_move_action_clears_direction() -> None:
    """move 외 액션에 direction 이 들어와도 강제로 none 이 된다."""
    cmd = RobotCommand(action=ActionType.PICK, target="cup", direction="left")
    assert cmd.direction == "none"


def test_move_command_key_assembly() -> None:
    """(target, direction) → 'move_{target}_{direction}' 조립."""
    assert (
        RobotCommand(action=ActionType.MOVE, target="box", direction="left").move_command_key()
        == "move_box_left"
    )
    assert (
        RobotCommand(action=ActionType.MOVE, target="mouse", direction="left").move_command_key()
        == "move_mouse_left"
    )


def test_move_command_key_none_for_non_move() -> None:
    assert RobotCommand(action=ActionType.PICK, target="cup").move_command_key() is None


def test_home_derives_instruction() -> None:
    cmd = RobotCommand(action=ActionType.HOME)
    assert cmd.instruction == "move to the home position"


def test_stop_derives_instruction() -> None:
    cmd = RobotCommand(action=ActionType.STOP)
    assert cmd.instruction == "stop"


# --- instruction 명시값 보존 ---------------------------------------------------


def test_explicit_instruction_is_preserved() -> None:
    cmd = RobotCommand(
        action=ActionType.PICK,
        target="sports ball",
        instruction="grasp the red ball carefully",
    )
    assert cmd.instruction == "grasp the red ball carefully"


def test_whitespace_only_instruction_is_treated_as_empty() -> None:
    """공백만 있는 instruction은 비어있는 것으로 간주, 폴백 생성."""
    cmd = RobotCommand(action=ActionType.PICK, target="cup", instruction="   ")
    assert cmd.instruction == "pick up the cup"


# --- 기존 validator 동작이 instruction 추가로 깨지지 않는지 확인 ---------------


def test_pick_without_target_still_raises() -> None:
    with pytest.raises(ValidationError):
        RobotCommand(action=ActionType.PICK)


def test_home_normalizes_target_destination_and_derives_instruction() -> None:
    """home/stop 은 target/destination 을 강제로 'none' 으로 만든 뒤 instruction을 폴백."""
    cmd = RobotCommand(action=ActionType.HOME, target="sports ball", destination="bowl")
    assert cmd.target == "none"
    assert cmd.destination == "none"
    assert cmd.instruction == "move to the home position"
