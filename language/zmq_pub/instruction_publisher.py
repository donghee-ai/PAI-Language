"""ZMQ PUB publisher — Language → LeRobot Action.

PAI-Language가 만들어낸 RobotCommand 를 LeRobot 정책(VLA pi0/smolvla/wall_x 등)이
바로 먹을 수 있는 JSON envelope로 변환해 PUB 소켓에 발행한다. LeRobot 측은 SUB
소켓으로 동일 엔드포인트에 connect 하면 된다.

Envelope (JSON 한 줄):

    {
        "timestamp": <unix epoch float>,
        "instruction": "pick up the sports ball and place it in the bowl",
        "action": "pick_and_place",
        "target": "sports ball",
        "destination": "bowl",
        "raw_input": "공을 그릇에 넣어",
        "reasoning": "...",
        "vision_confirmed": true
    }

VLA policy 입장에서는 `instruction` 만 task 입력으로 쓰면 되고, 나머지는 디버깅/
로깅용 메타데이터다.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from shared.schemas.command import RobotCommand

log = logging.getLogger(__name__)

try:
    import zmq
except ImportError:  # pyzmq optional — 미설치 시 publisher는 no-op
    zmq = None  # type: ignore[assignment]


class InstructionPublisher:
    """LeRobot Action 으로 instruction을 ZMQ PUB 으로 발행하는 thin wrapper.

    pyzmq 가 설치되지 않은 환경에서는 자동으로 no-op 모드로 동작하여
    PAI-Language 자체 실행은 막지 않는다 (stdout 출력은 그대로 유지).
    """

    def __init__(self, *, bind_address: str = "tcp://*:5557", sndhwm: int = 100) -> None:
        self._bind_address = bind_address
        self._endpoint: str | None = None
        self._sndhwm = int(sndhwm)
        self._ctx: Any = None
        self._socket: Any = None
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def bind_address(self) -> str:
        return self._bind_address

    @property
    def endpoint(self) -> str | None:
        """bind 후 OS 가 실제로 할당한 endpoint (ex: tcp://0.0.0.0:5557).

        bind 주소에 포트 0 또는 와일드카드를 쓴 경우 실제 포트를 알아내는 용도.
        start() 전에는 None.
        """
        return self._endpoint

    def start(self) -> None:
        if self._enabled:
            return
        if zmq is None:
            log.warning(
                "pyzmq 가 설치되지 않아 InstructionPublisher 가 비활성화됩니다. "
                "LeRobot 으로 instruction을 보내려면 `pip install pyzmq` 후 재시작하세요."
            )
            return

        self._ctx = zmq.Context.instance()
        self._socket = self._ctx.socket(zmq.PUB)
        self._socket.setsockopt(zmq.SNDHWM, self._sndhwm)
        self._socket.setsockopt(zmq.LINGER, 0)
        self._socket.bind(self._bind_address)
        raw_endpoint = self._socket.getsockopt(zmq.LAST_ENDPOINT)
        if isinstance(raw_endpoint, bytes):
            self._endpoint = raw_endpoint.decode()
        else:
            self._endpoint = str(raw_endpoint) if raw_endpoint else self._bind_address
        self._enabled = True
        log.info("InstructionPublisher bound at %s", self._endpoint)

    def stop(self) -> None:
        if not self._enabled:
            return
        try:
            if self._socket is not None:
                self._socket.close(linger=0)
        finally:
            self._socket = None
        self._enabled = False

    def publish(self, command: RobotCommand) -> bool:
        """RobotCommand 를 JSON envelope로 직렬화해 PUB 소켓에 발행.

        반환값은 실제로 전송이 이루어졌는지(=publisher가 enabled 인지). 미연결/HWM
        초과 같은 ZMQ 내부 사정으로 드롭된 경우에도 False 가 아닌 True 를 반환하므로,
        호출측은 "발행을 시도했는지" 지표로만 사용해야 한다.
        """
        if not self._enabled:
            return False
        assert self._socket is not None

        envelope = build_envelope(command)
        payload = json.dumps(envelope)
        try:
            self._socket.send_string(payload, zmq.NOBLOCK)
        except zmq.Again:
            log.debug("ZMQ instruction send dropped: HWM reached")
        except Exception as exc:  # noqa: BLE001
            log.warning("ZMQ instruction send error: %s", exc)
        return True


def build_envelope(command: RobotCommand) -> dict[str, Any]:
    """RobotCommand → LeRobot Action 이 받을 JSON envelope."""
    return {
        "timestamp": time.time(),
        "instruction": command.instruction,
        "action": command.action.value,
        "target": command.target,
        "destination": command.destination,
        "raw_input": command.raw_input,
        "reasoning": command.reasoning,
        "vision_confirmed": command.vision_confirmed,
    }
