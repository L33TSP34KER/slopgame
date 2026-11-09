#!/usr/bin/env python3
"""Run two DeepSeek-powered agents that collaborate over the broadcast broker.

    export DEEPSEEK_API_KEY=sk-...
    python main.py --goal "Agree on a name for our new game and a 3-line pitch"

The broker starts in-process (use --external-broker if you already run
`python broker.py` yourself). A "director" participant kicks off the task and
prints the whole conversation as it happens.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from agent import Agent
from broker import Hub
from brains import DeepSeekBrain
from deepseek_client import DeepSeekClient, DeepSeekError

log = logging.getLogger("main")


class Director:
    """Kicks off the task and prints the transcript."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

    async def kick_off(self, to: str, goal: str) -> None:
        assert self.writer is not None
        msg = {"from": "director", "to": to, "text": goal, "done": False}
        self.writer.write((json.dumps(msg) + "\n").encode())
        await self.writer.drain()

    async def listen_until_done(self, timeout: float) -> bool:
        """Print every relayed message; return True once someone signals done."""
        assert self.reader is not None
        try:
            async with asyncio.timeout(timeout):
                while True:
                    line = await self.reader.readline()
                    if not line:
                        return False
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        continue
                    src, dst = msg.get("from", "?"), msg.get("to")
                    arrow = f"{src} -> {dst if dst else '*'}:"
                    print(f"  {arrow:<20} {msg.get('text', '')}")
                    if msg.get("done"):
                        print("\n  ✔ agents signalled: task complete")
                        return True
        except TimeoutError:
            print("\n  ⏱ timeout waiting for agents to finish")
            return False

    async def close(self) -> None:
        if self.writer:
            self.writer.close()


async def run(args: argparse.Namespace) -> int:
    hub: Hub | None = None
    port = args.port
    if not args.external_broker:
        hub = Hub(args.host, 0)  # ephemeral port, no collisions
        await hub.start()
        port = hub.bound_port

    print(f"broker on {args.host}:{port}")
    print(f"goal: {args.goal}\n")

    try:
        client = DeepSeekClient(
            model=args.model, **({"base_url": args.base_url} if args.base_url else {})
        )
    except DeepSeekError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    director = Director(args.host, port)
    await director.connect()

    alpha = Agent(
        "alpha",
        DeepSeekBrain("alpha", "beta", args.goal, client),
        peer="beta", host=args.host, port=port, max_turns=args.rounds,
    )
    beta = Agent(
        "beta",
        DeepSeekBrain("beta", "alpha", args.goal, client),
        peer="alpha", host=args.host, port=port, max_turns=args.rounds,
    )
    await alpha.connect()
    await beta.connect()
    await director.kick_off("alpha", args.goal)

    tasks = [
        asyncio.create_task(alpha.run(), name="alpha"),
        asyncio.create_task(beta.run(), name="beta"),
        asyncio.create_task(director.listen_until_done(args.timeout), name="director"),
    ]
    director_task = tasks[2]
    try:
        # stop as soon as any participant finishes, then give the director a
        # moment to print the final message
        await asyncio.wait(tasks, timeout=args.timeout, return_when=asyncio.FIRST_COMPLETED)
        await asyncio.wait(tasks, timeout=3.0)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await alpha.close()
        await beta.close()
        await director.close()
        if hub:
            await hub.close()
    if director_task.done() and not director_task.cancelled() and director_task.exception() is None:
        return 0 if director_task.result() else 1
    return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Two DeepSeek agents collaborating over a broadcast broker")
    p.add_argument("--goal", default="Agree on a name for our new game and a 3-line pitch")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765, help="port for --external-broker")
    p.add_argument("--external-broker", action="store_true", help="connect to an already-running broker.py")
    p.add_argument("--rounds", type=int, default=6, help="max turns per agent")
    p.add_argument("--timeout", type=float, default=300.0, help="seconds to wait overall")
    p.add_argument("--model", default="deepseek-chat")
    p.add_argument("--base-url", default=None, help="override DeepSeek endpoint (e.g. a local mock)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("broker").setLevel(logging.WARNING)  # keep the chat readable
    try:
        sys.exit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
