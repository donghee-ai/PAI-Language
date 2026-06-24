"""ZMQ instruction → lerobot-rollout task 자동 갱신 어댑터.

PAI-Language가 ZMQ PUB :5557로 발행하는 instruction envelope을 같은 프로세스에서
구독하면서, lerobot의 표준 rollout 추론 루프를 그대로 돌린다. 새 instruction이
도착하면 그 안의 `instruction` 영어 문자열을 lerobot `SyncInferenceEngine` /
`RTCInferenceEngine`의 `_task` 필드에 직접 주입해 다음 step부터 새 task로 추론이
이어지게 한다.

`lerobot.scripts.lerobot_rollout` 자체의 인자 파서/실행 흐름은 그대로 사용한다.
우리는 `lerobot.rollout.context.build_rollout_context`만 monkey-patch 해서 컨텍스트가
만들어지는 순간 inference engine을 캡처하고 ZMQ subscriber 사이드카 스레드를
시작한다. lerobot 라이브러리 자체에는 손대지 않는다.

실행 (lerobot venv 에서):

    cd ~/lerobot-workspace/PAI-Language
    ~/lerobot-workspace/.venv/bin/python -m scripts.rollout_with_zmq_task \
        --instruction-endpoint tcp://127.0.0.1:5557 \
        -- \
        --strategy.type=base \
        --policy.path=lerobot/smolvla_base \
        --robot.type=so101_follower \
        --robot.port=/dev/so101_follower \
        --robot.cameras='{front_rgb:{type:zmq, server_address:127.0.0.1, port:5555, camera_name:front_rgb}}' \
        --task='do nothing' \
        --duration=120

`--` 이후의 인자는 lerobot-rollout 표준 CLI 그대로 사용한다. `--task=` 의 초기값은
첫 ZMQ instruction이 들어오기 전까지 사용되므로 "do nothing" 같은 안전한 값을
권장한다.

dry-run 모드: `--dry-run` 을 주면 lerobot을 import 하지 않고 ZMQ subscriber만 띄워
들어오는 instruction을 stdout에 출력한다. lerobot venv가 아니어도 동작하고 ZMQ
연결만 검증하는 용도이다.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger("rollout_with_zmq_task")


# --- ZMQ envelope → task 문자열 -------------------------------------------------


def parse_instruction(raw: bytes | str) -> str | None:
    """PAI-Language envelope에서 instruction 영어 문자열만 추출.

    Envelope 스키마는 `language/zmq_pub/instruction_publisher.py:build_envelope`
    가 만든 그대로. `instruction` 필드가 비-빈 문자열이면 strip 결과를, 아니면
    None을 반환한다 — 호출측이 빈 instruction으로 task를 덮어쓰지 않게 한다.
    """
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    else:
        text = raw
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    instruction = payload.get("instruction")
    if not isinstance(instruction, str):
        return None
    instruction = instruction.strip()
    return instruction or None


# --- engine._task 강제 갱신 ----------------------------------------------------


def apply_task(engine: Any, task: str) -> None:
    """lerobot inference engine 의 private `_task` 필드를 직접 갱신.

    lerobot의 SyncInferenceEngine / RTCInferenceEngine 둘 다 task를 `__init__`
    시점에만 받고 공개 setter를 제공하지 않는다 (lerobot 코드 확인됨). 다음
    `get_action()` 호출 때 `self._task` 가 그대로 observation dict에 들어가므로
    여기서 필드를 교체하면 다음 step부터 새 task로 추론이 진행된다.

    빈 문자열은 무시한다. `_task` 필드가 없는 객체에는 AttributeError를 던져
    lerobot 내부 변경을 호출측이 알 수 있게 한다.
    """
    if not task:
        return
    if not hasattr(engine, "_task"):
        raise AttributeError(
            f"engine {type(engine).__name__} has no `_task` attribute; "
            "lerobot internals may have changed — adjust apply_task accordingly."
        )
    engine._task = task


# --- 공유 상태 (SUB 스레드 ↔ 메인) ---------------------------------------------


@dataclass
class TaskState:
    """SUB 스레드가 메인 스레드와 공유하는 최신 task 상태.

    `engine` 이 캡처되기 전에 도착한 instruction은 여기에 버퍼링되고,
    engine 캡처 직후 메인이 한 번 flush 한다.
    """

    task: str
    updated_at: float
    received_count: int = 0
    # 원샷 실행 게이팅: 명령 수신 시 executing=True 로 켜지고, exec_seconds 경과 후
    # 다시 False(=idle). idle 동안에는 get_action 이 None 을 돌려줘 로봇이 멈춰 있는다.
    executing: bool = False
    exec_started_at: float = 0.0


# --- ZMQ SUB 스레드 -------------------------------------------------------------


class InstructionSubscriber(threading.Thread):
    """:5557 (또는 지정 endpoint)에 connect 한 SUB 소켓 폴링 스레드.

    새 메시지가 도착할 때마다 `on_instruction(text)` 콜백을 호출한다. 콜백은
    파싱 실패/빈 instruction에 대해서는 호출되지 않는다. `stop_event` 가 set
    되면 다음 폴 사이클에 종료한다.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        on_instruction: Callable[[str], None],
        stop_event: threading.Event,
        poll_interval_ms: int = 200,
        topic: bytes = b"",
        zmq_module: Any | None = None,
    ) -> None:
        super().__init__(daemon=True, name="zmq-instruction-sub")
        self._endpoint = endpoint
        self._on_instruction = on_instruction
        self._stop_event = stop_event
        self._poll_ms = int(poll_interval_ms)
        self._topic = topic
        self._zmq = zmq_module

    def run(self) -> None:
        zmq_mod = self._zmq
        if zmq_mod is None:
            try:
                import zmq as zmq_mod  # type: ignore[import-not-found]
            except ImportError:
                log.error("pyzmq 미설치 — InstructionSubscriber 비활성")
                return

        ctx = zmq_mod.Context.instance()
        sub = ctx.socket(zmq_mod.SUB)
        sub.setsockopt(zmq_mod.SUBSCRIBE, self._topic)
        sub.setsockopt(zmq_mod.LINGER, 0)
        poller = zmq_mod.Poller()
        poller.register(sub, zmq_mod.POLLIN)
        try:
            sub.connect(self._endpoint)
            log.info("InstructionSubscriber connected to %s", self._endpoint)
            while not self._stop_event.is_set():
                events = dict(poller.poll(timeout=self._poll_ms))
                if sub in events:
                    try:
                        raw = sub.recv(flags=zmq_mod.NOBLOCK)
                    except zmq_mod.Again:
                        continue
                    text = parse_instruction(raw)
                    if text is None:
                        log.debug("envelope skipped (malformed or empty instruction)")
                        continue
                    try:
                        self._on_instruction(text)
                    except Exception:  # noqa: BLE001
                        log.exception("on_instruction callback raised")
        finally:
            sub.close(linger=0)


# --- argparse + 인자 분리 ------------------------------------------------------


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """`--` 를 기준으로 우리 인자와 lerobot-rollout 으로 forward 할 인자 분리."""
    if "--" in argv:
        idx = argv.index("--")
        return argv[:idx], argv[idx + 1 :]
    return argv, []


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rollout_with_zmq_task",
        description=(
            "PAI-Language ZMQ instruction 채널을 lerobot-rollout 의 task 입력으로 "
            "동적 주입하는 어댑터. `--` 이후 인자는 lerobot-rollout 표준 CLI 로 "
            "그대로 전달됨."
        ),
    )
    parser.add_argument(
        "--instruction-endpoint",
        default="tcp://127.0.0.1:5557",
        help="PAI-Language의 instruction PUB endpoint (기본 tcp://127.0.0.1:5557)",
    )
    parser.add_argument(
        "--initial-task",
        default="do nothing",
        help=(
            "첫 ZMQ instruction이 도착하기 전까지 engine._task에 들어갈 안전한 기본값. "
            "lerobot-rollout의 --task= 와는 별개로, 우리 어댑터가 추적/덮어쓰는 값."
        ),
    )
    parser.add_argument(
        "--exec-seconds",
        type=float,
        default=8.0,
        help=(
            "원샷 실행 모드: 명령 1건당 정책을 구동할 시간(초). 이 시간 동안만 로봇이 "
            "움직이고, 그 외(시작 직후 포함)에는 현재 자세를 유지하며 멈춰 있는다. "
            "0 이하면 게이팅 없이 연속 구동(기존 동작)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="lerobot import 없이 ZMQ subscriber만 띄워 instruction을 stdout에 출력.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="logging level (DEBUG/INFO/WARNING/ERROR).",
    )
    return parser


# --- dry-run 모드 ---------------------------------------------------------------


def run_dry(args: argparse.Namespace) -> int:
    """lerobot 없이 ZMQ subscriber + 콜백만 돌려 채널 동작을 확인.

    들어오는 instruction을 받아 stdout에 한 줄씩 출력하고 카운트를 유지한다.
    SIGINT/SIGTERM 으로 깔끔히 종료한다.
    """
    state = TaskState(task=args.initial_task, updated_at=time.time(), received_count=0)
    stop = threading.Event()

    def _on_msg(text: str) -> None:
        state.task = text
        state.updated_at = time.time()
        state.received_count += 1
        print(f"[dry-run] task ← {text!r} (#{state.received_count})", flush=True)

    sub = InstructionSubscriber(
        endpoint=args.instruction_endpoint,
        on_instruction=_on_msg,
        stop_event=stop,
    )

    def _stop(_signum: int, _frame: Any) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    sub.start()
    print(
        f"[dry-run] subscribed to {args.instruction_endpoint}; "
        f"initial task = {state.task!r}",
        flush=True,
    )
    try:
        while not stop.wait(timeout=1.0):
            pass
    finally:
        stop.set()
        sub.join(timeout=2.0)
    return 0


# --- 실 모드 (lerobot rollout + ZMQ 사이드카) ----------------------------------


def run_with_lerobot(args: argparse.Namespace, lerobot_argv: list[str]) -> int:
    """lerobot-rollout 표준 진입점을 호출하면서 ZMQ 사이드카를 붙인다.

    구현 노트:
    - `lerobot.rollout.context.build_rollout_context` 를 monkey-patch 해서
      RolloutContext 가 만들어지는 즉시 engine 을 캡처한다. 그 시점에 SUB
      스레드를 start 하고, 이미 버퍼링된 마지막 task 가 있으면 한 번 flush 한다.
    - lerobot 의 표준 CLI 진입점 `lerobot.scripts.lerobot_rollout.main()` 을
      호출한다. argv 는 sys.argv 를 일시적으로 교체해 전달한다 (lerobot 이
      내부에서 sys.argv 를 본다고 가정 — draccus/argparse 표준 패턴).
    - lerobot 라이브러리에는 손대지 않는다. monkey-patch 는 우리 프로세스 안에서만.

    하드웨어(follower / 외부 카메라) 미연결 환경에서는 이 함수가 정상적으로
    끝까지 돌아가지 않는다 — 실제 검증은 하드웨어 도착 후.
    """
    state = TaskState(task=args.initial_task, updated_at=time.time(), received_count=0)
    state_lock = threading.Lock()
    stop = threading.Event()
    engine_ref: dict[str, Any] = {}

    gate_enabled = args.exec_seconds > 0

    def _on_msg(text: str) -> None:
        with state_lock:
            state.task = text
            state.updated_at = time.time()
            state.received_count += 1
            # 명령 수신 → 실행 창 시작 (원샷). 게이팅 비활성(exec_seconds<=0)이면 항상 실행.
            state.executing = True
            state.exec_started_at = time.time()
        engine = engine_ref.get("engine")
        if engine is not None:
            try:
                apply_task(engine, text)
                if gate_enabled:
                    log.info(
                        "task updated → %r (#%d) — %.1fs 동안 실행 후 정지",
                        text, state.received_count, args.exec_seconds,
                    )
                else:
                    log.info("task updated → %r (#%d)", text, state.received_count)
            except AttributeError:
                log.exception("apply_task 실패 — lerobot internals 변경 가능성")

    sub = InstructionSubscriber(
        endpoint=args.instruction_endpoint,
        on_instruction=_on_msg,
        stop_event=stop,
    )

    def _stop(_signum: int, _frame: Any) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    # SUB 스레드는 lerobot import / 컨텍스트 빌드보다 먼저 시작해 둔다. 그래야
    # build_rollout_context 가 calibration wizard 같은 인터랙션을 요구하다
    # 예외로 종료해도 finally 의 join 이 "thread not started" 로 깨지지 않는다.
    # 첫 instruction 이 도착해도 engine_ref 가 비어 있으면 _on_msg 는 state 만
    # 갱신하므로 무방.
    sub.start()

    # Lazy imports — lerobot venv에서만 실행되는 부분이므로 모듈 로드 시점이 아닌
    # 호출 시점에 import. dry-run 모드는 lerobot 없이도 동작해야 함.
    try:
        from lerobot.rollout import context as _ctx_mod  # type: ignore[import-not-found]
        from lerobot.scripts import lerobot_rollout as _rollout_mod  # type: ignore[import-not-found]
    except ImportError as exc:
        log.error("lerobot import 실패: %s. lerobot venv 에서 실행하세요.", exc)
        stop.set()
        sub.join(timeout=2.0)
        return 2

    _lerobot_main = _rollout_mod.main
    # lerobot_rollout.py 는 `from lerobot.rollout import build_rollout_context` 로
    # 자기 네임스페이스에 이름을 박아두고 그걸 호출한다. 따라서 context 서브모듈만
    # 패치하면 무효 — lerobot_rollout 모듈의 참조를 직접 갈아끼워야 hooked_build 가
    # 실제로 호출된다(= engine 캡처 + 게이팅 + task 교체 활성화).
    original_build = _rollout_mod.build_rollout_context

    def hooked_build(*build_args: Any, **build_kwargs: Any) -> Any:
        ctx = original_build(*build_args, **build_kwargs)
        # ctx.policy.inference 가 SyncInferenceEngine / RTCInferenceEngine.
        # lerobot.rollout.context.PolicyContext 의 필드 (Explore 확인).
        engine = None
        try:
            engine = ctx.policy.inference
        except AttributeError:
            log.warning("ctx.policy.inference 접근 실패 — engine 캡처 못함")
        if engine is not None:
            engine_ref["engine"] = engine
            # 원샷 게이팅: get_action 을 감싸 idle 동안 "초기 자세"를 계속 명령한다.
            # → 시작 직후(움츠린 초기 포즈)에 능동적으로 고정되고, 명령 1건이 끝나면
            #   다시 그 초기 포즈로 돌아와 정지한다. 초기 포즈 액션을 못 만들면 None
            #   (무명령)으로 폴백 — 어느 쪽이든 새 동작은 발생하지 않는다.
            if gate_enabled and hasattr(engine, "get_action"):
                hold_action = None
                try:
                    import torch  # lerobot venv

                    init_pos = getattr(ctx.hardware, "initial_position", None)
                    ordered_keys = getattr(ctx.data, "ordered_action_keys", None)
                    if init_pos and ordered_keys and all(k in init_pos for k in ordered_keys):
                        hold_action = torch.tensor([float(init_pos[k]) for k in ordered_keys])
                        log.info("idle 유지용 초기 자세 캡처 — 관절 %d개", len(ordered_keys))
                    else:
                        log.warning(
                            "초기 자세 액션 생성 실패(키 불일치) — idle 시 무명령(None)으로 대체. "
                            "init_pos=%s ordered=%s",
                            list(init_pos)[:3] if init_pos else None,
                            list(ordered_keys)[:3] if ordered_keys else None,
                        )
                except Exception:  # noqa: BLE001
                    log.exception("초기 자세 액션 생성 중 예외 — idle 시 무명령(None)으로 대체")

                _orig_get_action = engine.get_action

                def _gated_get_action(obs_frame: Any) -> Any:
                    now = time.time()
                    with state_lock:
                        if state.executing and (now - state.exec_started_at) >= args.exec_seconds:
                            state.executing = False
                            log.info("실행 창 종료 → 초기 자세로 복귀/유지")
                        active = state.executing
                    if not active:
                        # idle: 초기 자세를 계속 명령해 그 포즈에 고정 (없으면 무명령)
                        return hold_action
                    return _orig_get_action(obs_frame)

                engine.get_action = _gated_get_action  # type: ignore[method-assign]
                log.info(
                    "원샷 게이팅 활성 — 시작 시 초기 자세 유지, 명령 1건당 %.1fs 만 구동",
                    args.exec_seconds,
                )
            with state_lock:
                buffered = state.task
            # 초기 task 와 다르거나(=이미 새 instruction 수신) 일단 적용
            try:
                apply_task(engine, buffered)
                log.info("initial task applied: %r", buffered)
            except AttributeError:
                log.exception("초기 apply_task 실패")
        return ctx

    # lerobot_rollout 가 실제로 호출하는 참조를 패치 (핵심). context 서브모듈도 같이
    # 갈아끼워 다른 경로의 호출까지 커버한다.
    _rollout_mod.build_rollout_context = hooked_build
    _ctx_mod.build_rollout_context = hooked_build

    saved_argv = sys.argv[:]
    sys.argv = ["lerobot-rollout", *lerobot_argv]
    try:
        _lerobot_main()
        return 0
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        sys.argv = saved_argv
        _rollout_mod.build_rollout_context = original_build
        _ctx_mod.build_rollout_context = original_build
        stop.set()
        if sub.is_alive():
            sub.join(timeout=2.0)


# --- entry ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else list(argv)
    our_argv, lerobot_argv = _split_argv(raw)
    parser = build_arg_parser()
    args = parser.parse_args(our_argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.dry_run:
        if lerobot_argv:
            log.info("--dry-run: lerobot forward 인자 %d개 무시", len(lerobot_argv))
        return run_dry(args)

    if not lerobot_argv:
        log.error(
            "lerobot-rollout 표준 인자가 비어 있음. `--` 뒤에 --strategy/--policy/"
            "--robot 등을 지정하세요. 또는 `--dry-run` 으로 ZMQ만 검증."
        )
        return 2
    return run_with_lerobot(args, lerobot_argv)


if __name__ == "__main__":
    raise SystemExit(main())
