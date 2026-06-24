"""scripts.rollout_with_zmq_task 단위 테스트.

핵심 helper(`parse_instruction`, `apply_task`, `InstructionSubscriber`)와 argv
분리/엔트리 동작을 검증한다. lerobot 라이브러리는 import하지 않으므로 PAI-Language
venv에서 그대로 실행 가능하다.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest

from scripts.rollout_with_zmq_task import (
    InstructionSubscriber,
    TaskState,
    _split_argv,
    apply_task,
    build_arg_parser,
    main,
    parse_instruction,
)
from shared.schemas.command import ActionType, RobotCommand
from language.zmq_pub.instruction_publisher import InstructionPublisher

try:
    import zmq  # type: ignore[import-not-found]
except ImportError:
    zmq = None  # type: ignore[assignment]


# --- parse_instruction -------------------------------------------------------


def test_parse_instruction_extracts_string_from_envelope() -> None:
    envelope = json.dumps(
        {
            "timestamp": 1.0,
            "instruction": "pick up the sports ball",
            "action": "pick",
            "target": "sports ball",
        }
    ).encode("utf-8")
    assert parse_instruction(envelope) == "pick up the sports ball"


def test_parse_instruction_accepts_str_input() -> None:
    payload = json.dumps({"instruction": "stop"})
    assert parse_instruction(payload) == "stop"


def test_parse_instruction_strips_whitespace() -> None:
    payload = json.dumps({"instruction": "  move home  "}).encode("utf-8")
    assert parse_instruction(payload) == "move home"


def test_parse_instruction_returns_none_for_empty_instruction() -> None:
    payload = json.dumps({"instruction": ""}).encode("utf-8")
    assert parse_instruction(payload) is None


def test_parse_instruction_returns_none_for_whitespace_only() -> None:
    payload = json.dumps({"instruction": "   "}).encode("utf-8")
    assert parse_instruction(payload) is None


def test_parse_instruction_returns_none_for_missing_field() -> None:
    payload = json.dumps({"action": "pick"}).encode("utf-8")
    assert parse_instruction(payload) is None


def test_parse_instruction_returns_none_for_non_string_field() -> None:
    payload = json.dumps({"instruction": 123}).encode("utf-8")
    assert parse_instruction(payload) is None


def test_parse_instruction_returns_none_for_invalid_json() -> None:
    assert parse_instruction(b"{not json") is None


def test_parse_instruction_returns_none_for_non_dict_root() -> None:
    payload = json.dumps(["pick up", "the ball"]).encode("utf-8")
    assert parse_instruction(payload) is None


def test_parse_instruction_returns_none_for_invalid_utf8() -> None:
    assert parse_instruction(b"\xff\xfe\xfd") is None


def test_parse_instruction_matches_real_envelope_from_publisher() -> None:
    """PAI-Language의 실제 build_envelope 출력이 그대로 파싱되는지 확인."""
    from language.zmq_pub.instruction_publisher import build_envelope

    cmd = RobotCommand(
        action=ActionType.PICK_AND_PLACE,
        target="sports ball",
        destination="bowl",
        raw_input="공을 그릇에 넣어",
    )
    payload = json.dumps(build_envelope(cmd)).encode("utf-8")
    assert (
        parse_instruction(payload)
        == "pick up the sports ball and place it in the bowl"
    )


# --- apply_task --------------------------------------------------------------


def test_apply_task_sets_private_field() -> None:
    engine = SimpleNamespace(_task="do nothing")
    apply_task(engine, "pick up the cube")
    assert engine._task == "pick up the cube"


def test_apply_task_skips_empty_task() -> None:
    engine = SimpleNamespace(_task="do nothing")
    apply_task(engine, "")
    assert engine._task == "do nothing"


def test_apply_task_raises_when_field_missing() -> None:
    engine = SimpleNamespace(other_attr="x")
    with pytest.raises(AttributeError, match="_task"):
        apply_task(engine, "pick up the cube")


def test_apply_task_overwrites_repeatedly() -> None:
    engine = SimpleNamespace(_task="initial")
    apply_task(engine, "first")
    apply_task(engine, "second")
    apply_task(engine, "third")
    assert engine._task == "third"


# --- _split_argv -------------------------------------------------------------


def test_split_argv_separates_on_double_dash() -> None:
    ours, theirs = _split_argv(
        ["--instruction-endpoint", "tcp://x", "--", "--task=foo", "--duration=10"]
    )
    assert ours == ["--instruction-endpoint", "tcp://x"]
    assert theirs == ["--task=foo", "--duration=10"]


def test_split_argv_without_double_dash_keeps_all_ours() -> None:
    ours, theirs = _split_argv(["--dry-run", "--instruction-endpoint", "tcp://x"])
    assert ours == ["--dry-run", "--instruction-endpoint", "tcp://x"]
    assert theirs == []


def test_split_argv_double_dash_at_end_is_empty_lerobot() -> None:
    ours, theirs = _split_argv(["--dry-run", "--"])
    assert ours == ["--dry-run"]
    assert theirs == []


# --- arg parser --------------------------------------------------------------


def test_arg_parser_defaults() -> None:
    parser = build_arg_parser()
    args = parser.parse_args([])
    assert args.instruction_endpoint == "tcp://127.0.0.1:5557"
    assert args.initial_task == "do nothing"
    assert args.dry_run is False


def test_arg_parser_dry_run_flag() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True


# --- main entry --------------------------------------------------------------


def test_main_without_lerobot_args_returns_error() -> None:
    """`--` 뒤가 비어 있고 dry-run 도 아니면 사용법 오류로 종료."""
    assert main(["--instruction-endpoint", "tcp://127.0.0.1:5557"]) == 2


# --- InstructionSubscriber (실제 PUB → SUB) ---------------------------------


@pytest.mark.skipif(zmq is None, reason="pyzmq 미설치")
def test_subscriber_invokes_callback_on_real_publisher_message() -> None:
    """PAI-Language의 InstructionPublisher 가 PUB 한 메시지를 우리 SUB가 받아 콜백 호출."""
    assert zmq is not None

    pub = InstructionPublisher(bind_address="tcp://127.0.0.1:*")
    pub.start()
    assert pub.enabled
    assert pub.endpoint is not None

    received: list[str] = []
    received_event = threading.Event()
    stop = threading.Event()

    def _on_msg(text: str) -> None:
        received.append(text)
        received_event.set()

    sub = InstructionSubscriber(
        endpoint=pub.endpoint,
        on_instruction=_on_msg,
        stop_event=stop,
        poll_interval_ms=50,
    )
    sub.start()

    # PUB→SUB slow joiner: connect 직후 첫 메시지가 유실되지 않게 잠시 대기.
    time.sleep(0.3)

    cmd = RobotCommand(action=ActionType.PICK, target="sports ball")
    assert pub.publish(cmd) is True

    try:
        assert received_event.wait(timeout=2.0), "SUB가 메시지를 받지 못함"
        assert received == ["pick up the sports ball"]
    finally:
        stop.set()
        sub.join(timeout=2.0)
        pub.stop()


@pytest.mark.skipif(zmq is None, reason="pyzmq 미설치")
def test_subscriber_ignores_malformed_envelope() -> None:
    """잘못된 JSON / 빈 instruction 메시지는 콜백을 호출하지 않는다."""
    assert zmq is not None

    ctx = zmq.Context.instance()
    pub_sock = ctx.socket(zmq.PUB)
    pub_sock.setsockopt(zmq.LINGER, 0)
    pub_sock.bind("tcp://127.0.0.1:*")
    raw_endpoint = pub_sock.getsockopt(zmq.LAST_ENDPOINT)
    endpoint = raw_endpoint.decode() if isinstance(raw_endpoint, bytes) else str(raw_endpoint)

    received: list[str] = []
    stop = threading.Event()

    def _on_msg(text: str) -> None:
        received.append(text)

    sub = InstructionSubscriber(
        endpoint=endpoint,
        on_instruction=_on_msg,
        stop_event=stop,
        poll_interval_ms=50,
    )
    sub.start()
    time.sleep(0.3)

    try:
        pub_sock.send(b"{not json")
        pub_sock.send_string(json.dumps({"instruction": ""}))
        pub_sock.send_string(json.dumps({"action": "pick"}))  # instruction 누락
        # 잘 만든 메시지 — 이것만 받아야 함
        pub_sock.send_string(json.dumps({"instruction": "valid task"}))

        deadline = time.time() + 2.0
        while time.time() < deadline and not received:
            time.sleep(0.05)
        # malformed 3건이 콜백을 호출하지 않았고 valid 1건만 받았는지
        assert received == ["valid task"]
    finally:
        stop.set()
        sub.join(timeout=2.0)
        pub_sock.close(linger=0)


# --- TaskState ---------------------------------------------------------------


def test_task_state_defaults() -> None:
    state = TaskState(task="do nothing", updated_at=0.0)
    assert state.task == "do nothing"
    assert state.received_count == 0
