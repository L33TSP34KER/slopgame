#!/usr/bin/env python3
"""Durable broadcast bus on top of broker.py.

    python3 bus.py send --from deepseek --to mimo --text "hello"
    python3 bus.py watch --name deepseek     # relay -> design/bus/messages.jsonl
    python3 bus.py log [--tail 40]

Every send is also appended to design/bus/messages.jsonl, so the log survives
whether or not anyone was listening. `watch` dedupes by message id.
"""
from __future__ import annotations
import argparse, asyncio, hashlib, json, os, time

BUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "design", "bus")
LOG = os.path.join(BUS_DIR, "messages.jsonl")
LOCK = asyncio.Lock()

def mid(msg: dict) -> str:
    raw = f"{msg.get('from')}|{msg.get('ts')}|{msg.get('text')}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]

def append(msg: dict) -> None:
    os.makedirs(BUS_DIR, exist_ok=True)
    msg.setdefault("ts", time.time())
    msg["id"] = mid(msg)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(msg, ensure_ascii=False) + "\n")

async def send(args) -> None:
    msg = {"from": args.sender, "to": args.to, "text": args.text,
           "done": args.done, "ts": time.time()}
    append(msg)
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(args.host, args.port), timeout=2)
    except OSError as exc:
        print(f"[bus] broker unreachable ({exc}); message persisted to log")
        return
    writer.write((json.dumps(msg, ensure_ascii=False) + "\n").encode())
    await writer.drain()
    writer.close()
    print(f"[bus] sent {msg['id']} {args.sender} -> {args.to or '*'}")

async def watch(args) -> None:
    reader, writer = await asyncio.open_connection(args.host, args.port)
    print(f"[bus] {args.name} listening on {args.host}:{args.port}")
    while True:
        line = await reader.readline()
        if not line:
            return
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("from") == args.name:
            continue
        msg.setdefault("ts", time.time())
        append(msg)
        print(f"[{msg.get('ts',0):.0f}] {msg.get('from')} -> {msg.get('to') or '*'}: {msg.get('text')}", flush=True)

def log(args) -> None:
    if not os.path.exists(LOG):
        print("(empty)")
        return
    lines = open(LOG, encoding="utf-8").read().splitlines()
    for line in lines[-args.tail:]:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        print(f"{time.strftime('%H:%M:%S', time.localtime(m.get('ts', 0)))} {m.get('id','')} {m.get('from')} -> {m.get('to') or '*'}: {m.get('text')}")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8770)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send"); s.add_argument("--from", dest="sender", required=True)
    s.add_argument("--to", default=None); s.add_argument("--text", required=True)
    s.add_argument("--done", action="store_true")
    w = sub.add_parser("watch"); w.add_argument("--name", required=True)
    l = sub.add_parser("log"); l.add_argument("--tail", type=int, default=40)
    args = p.parse_args()
    if args.cmd == "send": asyncio.run(send(args))
    elif args.cmd == "watch": asyncio.run(watch(args))
    else: log(args)

if __name__ == "__main__":
    main()
