#!/usr/bin/env python3
"""Offline smoke test: broker + 2 agents + scripted brains, no API key needed.

    python smoke_test.py

Exits 0 when the pair of agents exchange turns and one of them signals done.
"""

from __future__ import annotations

import asyncio
import json
import sys

from agent import Agent
from broker import Hub
from brains import StubBrain


async def smoke() -> tuple[bool, list[str]]:
    hub = Hub("127.0.0.1", 0)
    await hub.start()
    port = hub.bound_port
    lines: list[str] = []

    # --- a minimal "director" that will start the task and collect the chat ---
    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    # --- the two agents ---
    alpha = Agent("alpha", StubBrain("alpha", "beta", ["Emberfall", "pitch: light vs dark"],
                                     done_at=10),
                  peer="beta", host="127.0.0.1", port=port, max_turns=5)
    beta = Agent("beta", StubBrain("beta", "alpha", ["Emberfall it is, here is the pitch"],
                                   done_at=1),
                 peer="alpha", host="127.0.0.1", port=port, max_turns=5)
    await alpha.connect()
    await beta.connect()

    tasks = [
        asyncio.create_task(alpha.run(), name="alpha"),
        asyncio.create_task(beta.run(), name="beta"),
    ]

    # everyone is connected now — start the conversation
    kickoff = {"from": "director", "to": "alpha", "text": "pick a game name", "done": False}
    writer.write((json.dumps(kickoff) + "\n").encode())
    await writer.drain()

    done_seen = False
    try:
        async with asyncio.timeout(10):
            while True:
                line = await reader.readline()
                if not line:
                    break
                msg = json.loads(line)
                lines.append(f"{msg['from']} -> {msg['to']}: {msg['text']}")
                if msg.get("done"):
                    done_seen = True
                    break
    except TimeoutError:
        pass

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await alpha.close()
    await beta.close()
    writer.close()
    await hub.close()

    return done_seen, lines


def main() -> None:
    ok, lines = asyncio.run(smoke())
    for line in lines:
        print(" ", line)
    senders = {ln.split(" -> ")[0] for ln in lines}
    problems = []
    if not ok:
        problems.append("no agent signalled done")
    if not {"alpha", "beta"} <= senders:
        problems.append(f"both agents must speak (spoke: {sorted(senders)})")
    if problems:
        print("FAIL:", "; ".join(problems))
        sys.exit(1)
    print("OK: broker relayed, both agents took turns, task signalled complete")


if __name__ == "__main__":
    main()
