#!/usr/bin/env python3
"""Offline stand-in for the DeepSeek API (chat-completions compatible).

Lets you watch the whole two-agent demo without a key:

    python mock_api.py --port 8099 &
    DEEPSEEK_API_KEY=anything python3 main.py --base-url http://127.0.0.1:8099

Scripted turn-taking: alpha proposes, beta approves with a pitch, alpha signs off.
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CALLS: dict[str, int] = {}

SCRIPT = {
    "alpha": [
        '{"text": "Proposal: call it Emberfall — embers falling into a dying world.", "to": "beta", "done": false}',
        '{"text": "Deal. Emberfall, the emberlight keeps the last city alive. Done!", "to": "beta", "done": true}',
    ],
    "beta": [
        '{"text": "Emberfall works. Pitch: keep the last flame alive as you descend through ash-swallowed ruins.", "to": "alpha", "done": false}',
    ],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep stdout quiet
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        request = json.loads(self.rfile.read(length) or b"{}")
        messages = request.get("messages") or []
        system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
        match = re.search(r"You are (\w+)", system)
        name = match.group(1) if match else "alpha"

        call = CALLS.get(name, 0)
        CALLS[name] = call + 1
        lines = SCRIPT.get(name, ["acknowledged."])
        content = lines[min(call, len(lines) - 1)]

        body = json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"mock DeepSeek API on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
