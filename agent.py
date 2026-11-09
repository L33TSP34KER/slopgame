#!/usr/bin/env python3
"""A broadcast agent: connects to the broker, hears everything, speaks when spoken to.

Message shape (newline-delimited JSON, relayed by broker.py):

    {"from": "alpha", "to": "beta", "text": "...", "done": false}

An agent acts on a message when "to" equals its own name. The brain decides
what to say and who the next speaker is ("to"), plus when the pair is done.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

log = logging.getLogger("agent")

# brain(history, incoming_text) -> {"text": str, "to": str | None, "done": bool}
Brain = Callable[[list[dict], str], Awaitable[dict]]


class Agent:
    def __init__(self, name: str, brain: Brain, peer: str,
                 host: str = "127.0.0.1", port: int = 8765, max_turns: int = 10):
        self.name = name
        self.peer = peer          # who this agent expects to talk with
        self.brain = brain
        self.host = host
        self.port = port
        self.max_turns = max_turns
        self.history: list[dict] = []   # {"who": ..., "text": ...}
        self.inbox: asyncio.Queue[dict] = asyncio.Queue()
        self._reader: asyncio.Task | None = None
        self._writer: asyncio.StreamWriter | None = None

    # ------------------------------------------------------------------ plumbing

    async def connect(self) -> None:
        reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._reader = asyncio.create_task(self._read_loop(reader))
        log.info("[%s] connected to broker", self.name)

    async def _read_loop(self, reader: asyncio.StreamReader) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                await self.inbox.put(msg)
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass

    async def say(self, to: str | None, text: str, done: bool = False) -> None:
        envelope = {"from": self.name, "to": to, "text": text, "done": done}
        assert self._writer is not None
        self._writer.write((json.dumps(envelope, ensure_ascii=False) + "\n").encode("utf-8"))
        await self._writer.drain()

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    # ------------------------------------------------------------------ the loop

    async def run(self) -> None:
        """Take turns with the peer until someone says done or max_turns is hit."""
        turns = 0
        while turns < self.max_turns:
            msg = await self.inbox.get()
            if msg.get("from") == self.name:
                continue
            if msg.get("to") is not None and msg.get("to") != self.name:
                continue  # not addressed to me

            incoming = str(msg.get("text", ""))
            self.history.append({"who": msg.get("from"), "text": incoming})

            reply = await self.brain(self.history, incoming)
            text = str(reply.get("text", ""))
            done = bool(reply.get("done", False))
            nxt = reply.get("to", self.peer)

            self.history.append({"who": self.name, "text": text})
            await self.say(nxt, text, done)
            turns += 1
            if done:
                log.info("[%s] signalling done", self.name)
                return
        log.info("[%s] reached max turns (%d)", self.name, self.max_turns)
        await self.say(None, f"[{self.name}] yielding: max turns reached", done=True)
