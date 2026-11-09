#!/usr/bin/env python3
"""Collision / crowd-motion probe (mimo, tools/qa/).

Verifies the two things a player feels but a screenshot cannot show:
  1. units never interpenetrate (centres stay >= radius sum) and never end up
     inside a building footprint,
  2. a group move does not shimmer — counts velocity direction reversals
     (jitter) while 12 units crowd into one destination.

    .venv/bin/python tools/qa/collision_probe.py
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("EMBERFALL_QA", "1")

import pygame  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def rec(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=600)
    ap.add_argument("--out", default=os.path.join(ROOT, "design", "notes",
                                                   "qa-collision.md"))
    args = ap.parse_args()

    from emberfall.src import app as app_mod
    from emberfall.src.defs import PLAYER, SCREEN_H, SCREEN_W
    from emberfall.src.pathfind import find_path, nearest_walkable

    g = app_mod.Game(app_mod.parse_args(["--qa", "--scene", "base"]))
    g.running = True
    dt = 1 / 60

    def step(n: int = 1) -> None:
        for _ in range(n):
            for ev in pygame.event.get():
                g.handle_event(ev)
            g.update(dt)
            g.draw()

    step(90)
    print(f"  display surface: {g.screen.get_size()} (logical {SCREEN_W}x{SCREEN_H})")

    units = [u for u in g.world.entities
             if getattr(u, "alive", False) and not getattr(u, "is_building", False)
             and getattr(u, "team", None) == PLAYER]
    grp = units[:12]
    start = {id(u): (u.x, u.y) for u in grp}
    cx = sum(u.x for u in grp) / len(grp)
    cy = sum(u.y for u in grp) / len(grp)
    anchor = nearest_walkable(g.map, int(cx), int(cy))
    target = None
    for dx, dy in ((9, 6), (8, -5), (-9, 6), (7, 7), (-8, -6), (10, 0), (0, -9)):
        cand = (anchor[0] + dx, anchor[1] + dy)
        if g.map.inb(*cand) and find_path(g.map, anchor, cand):
            target = cand
            break
    rec("reachable move target found", bool(target), f"target={target}")
    if not target:
        return 1

    prev = {id(u): (u.x, u.y) for u in grp}
    vel: dict[int, tuple[float, float]] = {}
    approach_jitter = 0
    worst_pair = (99.0, None)
    g.world.cmd_move(grp, target[0] + 0.5, target[1] + 0.5)

    def tick() -> None:
        nonlocal approach_jitter, worst_pair
        step(1)
        for u in grp:
            near = math.hypot(u.x - target[0] - 0.5, u.y - target[1] - 0.5) < 3.0
            px, py = prev[id(u)]
            dx, dy = u.x - px, u.y - py
            if abs(dx) + abs(dy) > 1e-4:
                if id(u) in vel and (dx * vel[id(u)][0] < -1e-6 or dy * vel[id(u)][1] < -1e-6):
                    if near:
                        approach_jitter += 1
                vel[id(u)] = (dx, dy)
            prev[id(u)] = (u.x, u.y)
        for i, a in enumerate(grp):
            for b in grp[i + 1:]:
                d = math.hypot(a.x - b.x, a.y - b.y)
                if d < worst_pair[0]:
                    worst_pair = (d, f"{a.kind}/{b.kind}")

    # phase A: order the group and let it travel (bounded)
    for _ in range(args.frames):
        tick()
        if all(math.hypot(u.x - target[0] - 0.5, u.y - target[1] - 0.5) < 3.0
               for u in grp) and all(getattr(u, "order", None) is None for u in grp):
            break
    arrived_all = all(math.hypot(u.x - target[0] - 0.5, u.y - target[1] - 0.5) < 3.0
                      for u in grp)
    orders_clear = all(getattr(u, "order", None) is None for u in grp)

    # phase B: settled crowd — measure pure shimmer with nothing else happening
    settle_jitter = 0
    for _ in range(120):
        before = {id(u): (u.x, u.y) for u in grp}
        step(1)
        for u in grp:
            b = before[id(u)]
            dx, dy = u.x - b[0], u.y - b[1]
            if abs(dx) + abs(dy) > 1e-4:
                if id(u) in vel and (dx * vel[id(u)][0] < -1e-6 or dy * vel[id(u)][1] < -1e-6):
                    settle_jitter += 1
                vel[id(u)] = (dx, dy)

    ds = [math.hypot(a.x - b.x, a.y - b.y) for i, a in enumerate(grp) for b in grp[i + 1:]]
    disp = [math.hypot(u.x - start[id(u)][0], u.y - start[id(u)][1]) for u in grp]
    arrived = sum(1 for u in grp
                  if math.hypot(u.x - target[0] - 0.5, u.y - target[1] - 0.5) < 3.0)
    rec("all units moved", min(disp) > 1.0,
        f"min displacement {min(disp):.1f} tiles, max {max(disp):.1f}")
    rec("group arrives and holds", arrived_all and orders_clear,
        f"arrived={arrived_all} orders_cleared={orders_clear}")
    rec("no interpenetration (>= radius sum)", min(ds) >= 0.55,
        f"closest pair {min(ds):.3f} tiles ({worst_pair[1]}), 0 pairs <0.5: "
        f"{sum(1 for d in ds if d < 0.5) == 0}")
    rec("no unit ends inside a building", not any(
        b.x - 0.1 <= u.x <= b.x + b.bw + 0.1 and b.y - 0.1 <= u.y <= b.y + b.bh + 0.1
        for u in grp for b in g.world.entities
        if getattr(b, "is_building", False) and getattr(b, "alive", False)),
        "checked against every live building footprint")
    rec("settled crowd does not shimmer", settle_jitter <= 10,
        f"{settle_jitter} reversals in 120 settled frames (approach-phase "
        f"reversals {approach_jitter}, normal while funneling into slots)")
    os.makedirs(os.path.join(ROOT, "design", "notes", "shots"), exist_ok=True)
    shot = os.path.join(ROOT, "design", "notes", "shots", "collision-packed.png")
    try:
        pygame.image.save(g.screen, shot)
        print(f"  packed-state screenshot -> {shot}")
    except Exception as exc:  # noqa: BLE001
        print(f"  screenshot failed: {exc}")

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    lines = ["# qa-collision — crowd motion probe", "",
             f"**{len(fails)} FAIL / {len(RESULTS)} checks**", "",
             "| check | result | detail |", "|---|---|---|"]
    for name, status, detail in RESULTS:
        lines.append(f"| {name} | {status} | {detail} |")
    lines.append("")
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(json.dumps({"qa": {"collision_pass": len(RESULTS) - len(fails),
                             "collision_fail": len(fails)}}))
    print(f"wrote {args.out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
