#!/usr/bin/env python3
"""Agent brains.

- DeepSeekBrain: asks the DeepSeek API what to say next (used by main.py).
- StubBrain:     deterministic, offline (used by smoke_test.py).
"""

from __future__ import annotations

import json
import re
from typing import Awaitable, Callable

from deepseek_client import DeepSeekClient

Brain = Callable[[list[dict], str], Awaitable[dict]]

SYSTEM_PROMPT = """You are {name}, one of exactly two AI agents ({name} and {peer}) \
collaborating over a simple broadcast channel. Whoever holds the conversation \
replies to {peer} next; when the shared task is finished you say so.

Task: {task}

Reply with ONLY a JSON object, no prose, no code fences:
{{"text": "<what you say to {peer}>", "to": "{peer}", "done": false}}

Rules:
- "text" is your contribution to the shared work — be concrete and short.
- Keep "to" as "{peer}" so the conversation ping-pongs (use null only for a public broadcast).
- Set "done" to true only when the task is genuinely complete or blocked and unwinnable.
"""


def parse_reply(raw: str) -> dict:
    """Pull {"text","to","done"} out of a model reply; fall back to the raw text."""
    s = raw.strip()
    s = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(s[start : end + 1])
            if isinstance(obj, dict) and "text" in obj:
                return {
                    "text": str(obj["text"]),
                    "to": obj.get("to"),
                    "done": bool(obj.get("done", False)),
                }
        except ValueError:
            pass
    return {"text": raw.strip(), "to": None, "done": False}


class DeepSeekBrain:
    def __init__(self, name: str, peer: str, task: str, client: DeepSeekClient | None = None):
        self.name = name
        self.peer = peer
        self.task = task
        self.client = client or DeepSeekClient()

    async def __call__(self, history: list[dict], incoming: str) -> dict:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT.format(name=self.name, peer=self.peer, task=self.task)}
        ]
        for entry in history:
            who = entry.get("who")
            prefix = "" if who == self.name else f"{who}: "
            messages.append(
                {
                    "role": "assistant" if who == self.name else "user",
                    "content": f"{prefix}{entry.get('text', '')}",
                }
            )
        raw = await self.client.chat(messages, temperature=0.7, max_tokens=600)
        reply = parse_reply(raw)
        if reply["text"]:
            reply["to"] = reply["to"] or self.peer
        return reply


class StubBrain:
    """Scripted brain for offline testing — no API key needed."""

    def __init__(self, name: str, peer: str, script: list[str], done_at: int = 2):
        self.name = name
        self.peer = peer
        self.script = list(script)
        self.done_at = done_at
        self.calls = 0

    async def __call__(self, history: list[dict], incoming: str) -> dict:
        line = self.script[self.calls] if self.calls < len(self.script) else "acknowledged."
        self.calls += 1
        done = self.calls >= self.done_at
        return {"text": f"[{self.name}] {line}", "to": self.peer, "done": done}
