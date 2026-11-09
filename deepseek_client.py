#!/usr/bin/env python3
"""Minimal DeepSeek chat-completions client built on the standard library.

No third-party dependencies: uses urllib for HTTP and asyncio.to_thread so the
event loop never blocks on network I/O.

Requires the environment variable DEEPSEEK_API_KEY.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request

log = logging.getLogger("deepseek")


class DeepSeekError(RuntimeError):
    """Raised when the DeepSeek API cannot be reached or returns an error."""


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DeepSeekClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 60.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            raise DeepSeekError(
                "DEEPSEEK_API_KEY is not set. Export it first, e.g.\n"
                "  export DEEPSEEK_API_KEY=sk-..."
            )
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    # ------------------------------------------------------------------ HTTP core

    def _post_sync(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = DeepSeekError(f"HTTP {exc.code}: {detail}")
                if exc.code not in RETRYABLE_STATUS:
                    raise last_error from None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = DeepSeekError(f"network error: {exc}")
            if attempt < self.max_retries:
                delay = min(2 ** attempt, 8)
                log.warning("attempt %d failed (%s); retrying in %ds", attempt, last_error, delay)
                time.sleep(delay)
        raise last_error or DeepSeekError("request failed")

    # ------------------------------------------------------------------ public API

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        response_format: dict | None = None,
    ) -> str:
        """One chat completion. Returns the assistant's text content."""
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        data = await asyncio.to_thread(self._post_sync, payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekError(f"unexpected response shape: {data!r}") from exc
