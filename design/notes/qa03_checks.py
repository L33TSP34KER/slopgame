#!/usr/bin/env python3
"""qa-03 — the three things deepseek asked me to verify on HEAD.

1. hall-loss defeat  : destroying every player townhall/keep must flip to defeat
2. siege conversion  : --scene siege --autoplay must reach victory in-window
3. (torn sprite + scenes are checked separately with screenshots)

    .venv/bin/python design/notes/qa03_checks.py
"""
from __future__ import annotations

import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["EMBERFALL_QA"] = "1"

import pygame  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def rec(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)


def make(scene: str, autoplay: bool = False, speed: float = 1.0):
    from emberfall.src import app as app_mod
    argv = ["--qa", "--scene", scene, "--speed", str(speed)]
    if autoplay:
        argv.append("--autoplay")
    g = app_mod.Game(app_mod.parse_args(argv))
    g.running = True
    return g


def step(g, n: int = 1, dt: float = 1 / 60) -> None:
    for _ in range(n):
        for ev in pygame.event.get():
            g.handle_event(ev)
        g.update(dt)
        g.draw()


def hall_loss_defeat() -> None:
    from emberfall.src.defs import PLAYER
    g = make("play")
    step(g, 90)
    halls = [e for e in g.world.entities
             if getattr(e, "is_building", False) and getattr(e, "team", None) == PLAYER
             and getattr(e, "bid", None) in ("townhall", "keep") and getattr(e, "alive", False)]
    rec("setup: player has a hall", bool(halls), f"{len(halls)} hall(s)")
    if not halls:
        return
    for h in halls:
        h.alive = False
        h.hp = 0
    t0 = time.time()
    state = g.state
    while g.state == "play" and time.time() - t0 < 20:
        step(g, 30)
        state = g.state
    rec("hall loss -> defeat state", state == "defeat",
        f"state={state} world={getattr(g.world, 'state', None)} after "
        f"{round(time.time()-t0,1)}s")
    try:
        pygame.quit()
    except Exception:  # noqa: BLE001
        pass


def siege_conversion(window: float = 300.0) -> None:
    g = make("siege", autoplay=True, speed=6.0)
    step(g, 60)
    from emberfall.src.defs import ENEMY
    t0 = time.time()
    hist = []
    state = g.state
    while state == "play" and time.time() - t0 < window:
        step(g, 180)
        nec = [e for e in g.world.entities
               if getattr(e, "bid", None) == "necropolis" and getattr(e, "alive", False)]
        hp = int(sum(getattr(e, "hp", 0) for e in nec))
        hist.append((round(g.world.time, 1), hp))
        state = g.state
    final_hp = hist[-1][1] if hist else None
    rec("siege autoplay reaches victory", state == "victory",
        f"state={state} world={getattr(g.world, 'state', None)} necropolis_hp="
        f"{final_hp} samples={hist[::max(1, len(hist)//6)]}")
    try:
        pygame.quit()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    print("== hall-loss defeat ==")
    hall_loss_defeat()
    print("== siege conversion ==")
    siege_conversion()
    fails = [r for r in RESULTS if r[1] == "FAIL"]
    out = os.path.join(ROOT, "design", "notes", "qa-03-checks.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(RESULTS, fh, indent=2)
    print(json.dumps({"qa": {"qa03_pass": len(RESULTS) - len(fails),
                             "qa03_fail": len(fails)}}))
    for name, status, detail in RESULTS:
        print(f" {status:4} {name}: {detail[:220]}")
    print(f"wrote {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
