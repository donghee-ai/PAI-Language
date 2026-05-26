"""LeRobot Action 자리에 들어갈 미니 SUB — instruction 채널 확인용.

PAI-Language 가 ZMQ PUB :5557 으로 보내는 envelope 를 그대로 받아 stdout 에 찍는다.
LeRobot 정책 쪽 구독 코드가 작성되기 전까지의 손-검증 도구.

실행 (어느 venv 든 pyzmq 만 있으면 OK):

    python -m scripts.instruction_subscriber
    python -m scripts.instruction_subscriber --endpoint tcp://127.0.0.1:5557

연결 호스트는 같은 머신이면 127.0.0.1, 다른 머신이면 Language 가 떠 있는 호스트의 IP.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import zmq


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--endpoint",
        default="tcp://127.0.0.1:5557",
        help="PAI-Language 의 instruction PUB endpoint (기본 tcp://127.0.0.1:5557)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    ctx = zmq.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.connect(args.endpoint)
    print(f"[subscriber] connected to {args.endpoint}; instruction 대기 중...")
    print("[subscriber] 종료: Ctrl+C\n")

    try:
        while True:
            raw = sub.recv_string()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"[subscriber] JSON 파싱 실패: {exc}: {raw!r}")
                continue

            ts = msg.get("timestamp")
            ts_str = (
                datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%H:%M:%S")
                if isinstance(ts, (int, float))
                else "??:??:??"
            )
            print(f"[{ts_str}] instruction = {msg.get('instruction')!r}")
            print(
                f"           action={msg.get('action')}, target={msg.get('target')}, "
                f"destination={msg.get('destination')}, vision_confirmed={msg.get('vision_confirmed')}"
            )
            if msg.get("raw_input"):
                print(f"           raw_input={msg['raw_input']!r}")
            print()
    except KeyboardInterrupt:
        print("\n[subscriber] 종료됨.")
    finally:
        sub.close(linger=0)


if __name__ == "__main__":
    main()
