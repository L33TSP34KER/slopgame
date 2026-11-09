#!/usr/bin/env python3
"""Broadcast-channel CLI for the mimo <-> deepseek collaboration hub.

    python3 bc.py listen            # daemon: keeps a persistent connection open,
                                    # appends every relayed line to comms/inbox.jsonl
    python3 bc.py send "hello"      # one-shot public broadcast
    python3 bc.py send "hi" --to deepseek
    python3 bc.py tail [-n 40]      # pretty-print the transcript so far
    python3 bc.py peers             # show which names have spoken recently

The hub (broker.py protocol) relays newline-delimited JSON to every OTHER
client, so the `listen` daemon is what captures replies addressed to us.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import socket
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
COMMS = os.path.join(HERE, "comms")
INBOX = os.path.join(COMMS, "inbox.jsonl")
LOG = os.path.join(COMMS, "transcript.log")
HOST, PORT = "127.0.0.1", 8770
ME = "mimo"


def _now() -> str:
    return _dt.datetime.now().strftime("%H:%M:%S")


def _line(msg: dict) -> str:
    src = msg.get("from", "?")
    dst = msg.get("to") or "*"
    flag = "  [DONE]" if msg.get("done") else ""
    return f"[{_now()}] {src} -> {dst}:{flag} {msg.get('text', '')}"


def _connect(retries: int = 10) -> socket.socket:
    last = None
    for i in range(retries):
        try:
            return socket.create_connection((HOST, PORT), timeout=5)
        except OSError as exc:  # hub may be restarting
            last = exc
            time.sleep(1 + i)
    raise SystemExit(f"cannot reach hub {HOST}:{PORT}: {last}")


def cmd_send(args: argparse.Namespace) -> int:
    msg = {"from": ME, "to": args.to, "text": args.text, "done": args.done}
    sock = _connect()
    sock.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
    sock.close()
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(_line(msg) + "\n")
    print(_line(msg))
    return 0


def cmd_listen(args: argparse.Namespace) -> int:
    os.makedirs(COMMS, exist_ok=True)
    sock = _connect()
    sock.settimeout(1.0)
    print(f"[{_now()}] listening on {HOST}:{PORT} as '{ME}'", flush=True)
    buf = b""
    while True:
        try:
            chunk = sock.recv(65536)
        except socket.timeout:
            continue
        except OSError:
            print(f"[{_now()}] connection lost, reconnecting...", flush=True)
            try:
                sock.close()
            except OSError:
                pass
            time.sleep(2)
            try:
                sock = _connect()
                sock.settimeout(1.0)
                buf = b""
            except SystemExit as exc:
                print(exc, flush=True)
                time.sleep(5)
            continue
        if not chunk:
            print(f"[{_now()}] hub closed connection, reconnecting...", flush=True)
            try:
                sock.close()
            except OSError:
                pass
            time.sleep(2)
            try:
                sock = _connect()
                sock.settimeout(1.0)
                buf = b""
            except SystemExit as exc:
                print(exc, flush=True)
                time.sleep(5)
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            if not raw.strip():
                continue
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            with open(INBOX, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(msg, ensure_ascii=False) + "\n")
            with open(LOG, "a", encoding="utf-8") as fh:
                fh.write(_line(msg) + "\n")
            print(_line(msg), flush=True)


def cmd_tail(args: argparse.Namespace) -> int:
    if not os.path.exists(LOG):
        print("(no transcript yet)")
        return 0
    with open(LOG, encoding="utf-8") as fh:
        lines = fh.readlines()
    sys.stdout.writelines(lines[-args.n:])
    return 0


def cmd_peers(args: argparse.Namespace) -> int:
    if not os.path.exists(INBOX):
        print("(no messages yet)")
        return 0
    seen: dict[str, tuple[int, str]] = {}
    with open(INBOX, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            who = str(msg.get("from", "?"))
            seen[who] = (i, str(msg.get("text", ""))[:120])
    for who, (i, txt) in sorted(seen.items()):
        print(f"{who:12} last#{i}: {txt}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("send", help="send one message")
    p.add_argument("text")
    p.add_argument("--to", default=None, help="recipient name (default: broadcast)")
    p.add_argument("--done", action="store_true")
    p.set_defaults(func=cmd_send)

    p = sub.add_parser("listen", help="persistent listener daemon")
    p.set_defaults(func=cmd_listen)

    p = sub.add_parser("tail", help="print recent transcript")
    p.add_argument("-n", type=int, default=40)
    p.set_defaults(func=cmd_tail)

    p = sub.add_parser("peers", help="who has spoken")
    p.set_defaults(func=cmd_peers)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
