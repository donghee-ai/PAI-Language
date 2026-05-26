"""language.zmq_pub.instruction_publisher 단위 테스트.

build_envelope 의 직렬화 형식과 PUB→SUB 1회 전송 smoke test 를 검증한다.
pyzmq 미설치 환경에서는 PUB/SUB 테스트는 skip 한다 (no-op 모드만 별도 검증).
"""

from __future__ import annotations

import json
import time

import pytest

from language.zmq_pub.instruction_publisher import (
    InstructionPublisher,
    build_envelope,
)
from shared.schemas.command import ActionType, RobotCommand

try:
    import zmq  # type: ignore[import-not-found]
except ImportError:
    zmq = None  # type: ignore[assignment]


# --- envelope 직렬화 형식 -----------------------------------------------------


def test_build_envelope_basic_fields() -> None:
    cmd = RobotCommand(
        action=ActionType.PICK_AND_PLACE,
        target="sports ball",
        destination="bowl",
        reasoning="공을 그릇에",
        raw_input="공 그릇에 넣어",
        vision_confirmed=True,
    )
    env = build_envelope(cmd)

    assert env["instruction"] == "pick up the sports ball and place it in the bowl"
    assert env["action"] == "pick_and_place"
    assert env["target"] == "sports ball"
    assert env["destination"] == "bowl"
    assert env["reasoning"] == "공을 그릇에"
    assert env["raw_input"] == "공 그릇에 넣어"
    assert env["vision_confirmed"] is True
    assert isinstance(env["timestamp"], float)


def test_build_envelope_serializes_to_json() -> None:
    """LeRobot 측이 json.loads 로 파싱하므로 직렬화 가능해야 한다."""
    cmd = RobotCommand(action=ActionType.HOME)
    payload = json.dumps(build_envelope(cmd))
    parsed = json.loads(payload)
    assert parsed["instruction"] == "move to the home position"
    assert parsed["action"] == "home"


# --- no-op 모드 ---------------------------------------------------------------


def test_publish_when_not_started_is_noop() -> None:
    """start() 호출 전에는 publish 가 False 를 반환하고 어떤 부작용도 없어야 한다."""
    pub = InstructionPublisher(bind_address="tcp://*:0")
    cmd = RobotCommand(action=ActionType.STOP)
    assert pub.publish(cmd) is False
    assert pub.enabled is False


# --- 실제 PUB → SUB smoke test (pyzmq 필요) ----------------------------------


@pytest.mark.skipif(zmq is None, reason="pyzmq 미설치")
def test_pub_sub_roundtrip() -> None:
    """SUB 소켓을 띄워 publish 한 메시지를 받아 내용까지 확인한다."""
    assert zmq is not None

    # OS 가 할당하는 임시 포트 사용 → 다른 테스트/프로세스와의 충돌 회피.
    pub = InstructionPublisher(bind_address="tcp://127.0.0.1:*")
    pub.start()
    assert pub.enabled
    assert pub.endpoint is not None

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.setsockopt(zmq.RCVTIMEO, 2000)  # ms
    try:
        sub.connect(pub.endpoint)
        # PUB→SUB 슬로우 조이너: connect 직후 한 박자 쉬어야 첫 메시지가 유실되지 않는다.
        time.sleep(0.2)

        cmd = RobotCommand(action=ActionType.PICK, target="sports ball")
        assert pub.publish(cmd) is True

        raw = sub.recv_string()
        msg = json.loads(raw)
        assert msg["instruction"] == "pick up the sports ball"
        assert msg["action"] == "pick"
        assert msg["target"] == "sports ball"
    finally:
        pub.stop()
        sub.close(linger=0)
