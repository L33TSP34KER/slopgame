#!/usr/bin/env python3
"""Tiny broadcast hub: every line a client sends is relayed to every OTHER client.

That's the whole protocol. Messages are newline-delimited JSON, forwarded as-is:

    {"from": "alpha", "to": "beta", "text": "...", "done": false}

- "to": "<name>"  -> only that agent acts on it
- "to": null      -> everyone hears it (a public broadcast)

Run:  python broker.py [--host 127.0.0.1] [--port 8765]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

log = logging.getLogger("broker")


class Hub:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.writers: set[asyncio.StreamWriter] = set()
        self.transcript: list[bytes] = []  # every message, for inspection
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        log.info("broker listening on %s:%d", self.host, self.port)

    @property
    def bound_port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        for w in list(self.writers):
            w.close()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.writers.add(writer)
        log.info("agent connected (%d total)", len(self.writers))
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                self.transcript.append(line)
                self._blast(line, sender=writer)
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            pass
        finally:
            self.writers.discard(writer)
            writer.close()
            log.info("agent disconnected (%d left)", len(self.writers))

    def _blast(self, line: bytes, sender: asyncio.StreamWriter) -> None:
        for w in list(self.writers):
            if w is sender or w.is_closing():
                continue
            try:
                w.write(line if line.endswith(b"\n") else line + b"\n")
            except ConnectionError:
                self.writers.discard(w)
        log.info("relayed %s", line.decode("utf-8", "replace").rstrip())


async def main() -> None:
    parser = argparse.ArgumentParser(description="Agent broadcast broker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    hub = Hub(args.host, args.port)
    await hub.start()
    print(f"broker on {args.host}:{hub.bound_port} — waiting for agents (Ctrl-C to stop)")
    try:
        async with hub._server:  # type: ignore[union-attr]
            await hub._server.serve_forever()  # type: ignore[union-attr]
    except asyncio.CancelledError:
        pass
    finally:
        await hub.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
