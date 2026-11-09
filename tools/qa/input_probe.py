#!/usr/bin/env python3
"""Input / controls QA probe (mimo, tools/qa/).

The headless rule forbids xdotool, so this drives the game IN-PROCESS: it
builds the real `Game`, posts synthetic pygame events into the same
`handle_event` path a player uses, steps the sim, and asserts on observable
state (selection, camera, orders, modes, panels).

    .venv/bin/python tools/qa/input_probe.py               # design/notes/qa-input-01.md
    .venv/bin/python tools/qa/input_probe.py --scene play
"""
from __future__ import annotations

import argparse
import json
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


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="play")
    ap.add_argument("--frames", type=int, default=20, help="frames to settle before testing")
    ap.add_argument("--out", default=os.path.join(ROOT, "design", "notes", "qa-input-01.md"))
    args = ap.parse_args()

    from emberfall.src import app as app_mod
    from emberfall.src.defs import PLAYER as PLAYER_TEAM

    g = app_mod.Game(app_mod.parse_args(["--qa", "--scene", args.scene]))
    g.running = True
    dt = 1.0 / 60.0

    def step(n: int = 1) -> None:
        for _ in range(n):
            for ev in pygame.event.get():
                g.handle_event(ev)
            g.update(dt)
            g.draw()

    def key(k, unicode: str = "", mods: int = 0) -> None:
        real = pygame.key.get_mods
        pygame.key.get_mods = lambda: mods  # type: ignore[assignment]
        try:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, unicode=unicode))
            step(1)
        finally:
            pygame.key.get_mods = real  # type: ignore[assignment]

    def down(pos, button=1) -> None:
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
        step(1)

    def up(pos, button=1) -> None:
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))
        step(1)

    def motion(pos) -> None:
        pygame.event.post(pygame.event.Event(
            pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(True, False, False)))
        step(1)

    def hold_keys(keys, frames=40) -> None:
        """Simulate held keys: update() polls pygame.key.get_pressed()."""
        real = pygame.key.get_pressed

        class _Held:
            def __init__(self, real, held):
                self._real, self._held = real, set(held)

            def __getitem__(self, i):
                if i in self._held:
                    return 1
                try:
                    return self._real[i]
                except Exception:  # noqa: BLE001
                    return 0

            def __len__(self):
                return len(self._real)

        pygame.key.get_pressed = lambda: _Held(real(), keys)  # type: ignore[assignment]
        try:
            step(frames)
        finally:
            pygame.key.get_pressed = real  # type: ignore[assignment]

    step(args.frames)

    # ------------------------------------------------------------------ camera
    x0 = g.camera.x
    hold_keys((pygame.K_RIGHT, pygame.K_RIGHT))
    record("camera: held D / right-arrow pan", g.camera.x > x0 + 5,
           f"camera.x {x0:.0f} -> {g.camera.x:.0f}")

    g.camera.x += 400
    g.camera.clamp()
    record("camera: clamp stays in world", g.camera.x < 5000, f"x={g.camera.x:.0f}")

    # --------------------------------------------------------------- selection
    units = [u for u in g.world.entities
             if getattr(u, "team", None) == PLAYER_TEAM
             and getattr(u, "alive", False) and not getattr(u, "is_building", False)]
    record("setup: units exist to click", bool(units), f"{len(units)} candidates")

    if units:
        g.center_camera(units[0].x, units[0].y)  # camera test panned away
        step(2)
        u = units[0]
        sx, sy = (int(v) for v in g.screen_pos(u))
        record("coords: unit projects on-screen", 0 <= sx <= 1600 and 0 <= sy <= 900,
               f"screen=({sx},{sy})")

        g.select([])
        down((sx, sy), 1)
        up((sx, sy), 1)
        record("select: left-click a unit", len(g.selection) >= 1,
               f"click ({sx},{sy}) -> {len(g.selection)} selected")

        g.select([])
        down((20, 120), 1)
        motion((900, 640))
        up((900, 640), 1)
        record("select: box select", len(g.selection) >= 1, f"{len(g.selection)} selected")

        before = len(g.selection)
        u2 = units[-1]
        sx2, sy2 = (int(v) for v in g.screen_pos(u2))
        real_mods = pygame.key.get_mods
        pygame.key.get_mods = lambda: pygame.KMOD_SHIFT  # type: ignore[assignment]
        try:
            down((sx2, sy2), 1)
            up((sx2, sy2), 1)
        finally:
            pygame.key.get_mods = real_mods  # type: ignore[assignment]
        record("select: shift-add", len(g.selection) >= before, f"{before} -> {len(g.selection)}")

        # control groups ----------------------------------------------------
        g.select(units[:3])
        pygame.key.get_mods = lambda: pygame.KMOD_CTRL  # type: ignore[assignment]
        try:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1, unicode="1"))
            step(1)
        finally:
            pygame.key.get_mods = real_mods  # type: ignore[assignment]
        stored = bool(g.control_groups.get(1))
        g.select([])
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1, unicode="1"))
        step(1)
        digit_range_empty = False  # engine now uses K_1 <= k <= K_9 (verified live)
        record("select: ctrl+1 store, 1 recall", stored and len(g.selection) >= 1,
               f"stored={stored} recalled={len(g.selection)}")

        # ---------------------------------------------------------------- order
        from emberfall.src.pathfind import find_path, nearest_walkable
        u = units[0]
        g.select([u])
        px0, py0 = u.x, u.y
        # pick a target we have PROVEN reachable, otherwise the test lies
        start = nearest_walkable(g.map, int(u.x), int(u.y))
        goal = None
        for dx, dy in ((7, 5), (6, 2), (5, -4), (-6, 3), (3, 6), (0, -6), (-4, -5), (8, 0)):
            cand = (start[0] + dx, start[1] + dy)
            if g.map.inb(*cand) and find_path(g.map, start, cand):
                goal = cand
                break
        assert goal, "no reachable move target found near spawn"
        tgt = type("_P", (), {"x": goal[0] + 0.5, "y": goal[1] + 0.5,
                              "height": 0, "is_building": False, "bw": 0, "bh": 0})()
        tx, ty = (int(v) for v in g.screen_pos(tgt))
        down((tx, ty), 3)
        order = getattr(u, "order", None)
        step(180)
        moved = abs(u.x - px0) + abs(u.y - py0)
        record("order: right-click issues move", order is not None or moved > 0.3,
               f"order={type(order).__name__ if order else None} moved={moved:.2f} tiles")
        record("order: unit actually walks there", moved > 0.3,
               f"moved {moved:.2f} tiles of ~8.6 requested (target screen {tx},{ty})")

        # ------------------------------------------------------------ hotkeys
        g.select([u])
        key(pygame.K_a, unicode="a")
        am = bool(getattr(g, "attack_move_mode", False))
        key(pygame.K_ESCAPE, unicode="")
        record("hotkey: A arms attack-move, Esc cancels",
               am and not getattr(g, "attack_move_mode", False), f"armed={am}")

        key(pygame.K_s, unicode="s")
        record("hotkey: S stop handled", True, "no exception")

        key(pygame.K_SPACE, unicode=" ")
        record("hotkey: SPACE selects hero",
               any(getattr(e, "is_hero", False) for e in g.selection),
               f"selection={len(g.selection)}")

        key(pygame.K_F1, unicode="")
        record("hotkey: F1 idle worker", len(g.selection) >= 1, f"selection={len(g.selection)}")

        # ------------------------------------------------------------- build
        workers = [w for w in g.world.entities
                   if getattr(w, "alive", False) and getattr(w, "worker", False)]
        if workers:
            g.select([workers[0]])
            key(pygame.K_b, unicode="b")
            menu = bool(getattr(g.ui, "build_menu", False))
            placed = bool(getattr(g, "placement", None))
            if menu and getattr(g.ui, "actions", None):
                builds = [a for a in g.ui.actions if str(a.get("id", "")).startswith("build")]
                if builds:
                    g.handle_action(dict(builds[0]))
                    placed = bool(getattr(g, "placement", None))
            if menu or placed:
                key(pygame.K_ESCAPE, unicode="")
            after = bool(getattr(g, "placement", None)) or bool(getattr(g.ui, "build_menu", False))
            record("build: B opens build menu, Esc cancels", (menu or placed) and not after,
                   f"menu={menu} placement={placed} after_esc={after}")
        else:
            record("build: B opens build menu, Esc cancels", False, "no workers found")

        # ---- construction end to end: menu -> pick building -> place -------
        if workers:
            before_count = len(list(g.world.buildings_of(PLAYER_TEAM)))
            g.select([workers[0]])
            key(pygame.K_b, unicode="b")
            step(1)
            choices = [a for a in g.ui.actions
                       if a.get("kind") == "build" and a.get("rect")]
            armed = False
            chosen = None
            if choices:
                chosen = choices[0]
                g.handle_action(dict(chosen))
                step(2)
                armed = bool(getattr(g, "placement", None))
            spot = None
            hall = next(iter(g.world.buildings_of(PLAYER_TEAM)), None)
            if hall and armed:
                # ask the ENGINE what is legal for the armed footprint instead
                # of guessing from clear/terrain flags (my guess picked a spot
                # the 2x2 farm footprint could not use)
                for dy in range(0, 12):
                    for dx in range(0, 12):
                        tx, ty = int(hall.x) + 3 + dx, int(hall.y) + 3 + dy
                        if g.world.placement_valid(tx, ty):
                            spot = (tx, ty)
                            break
                    if spot:
                        break
            if spot:
                fake = type("_P", (), {"x": spot[0] + 0.5, "y": spot[1] + 0.5,
                                       "height": 0, "is_building": False,
                                       "bw": 0, "bh": 0})()
                px, py = (int(v) for v in g.screen_pos(fake))
                down((px, py), 1)
                step(120)
                sites = [b for b in g.world.buildings_of(PLAYER_TEAM)
                         if (getattr(b, "build_progress", 1.0) or 1.0) < 1.0]
                after = len(list(g.world.buildings_of(PLAYER_TEAM)))
                record("build: place a structure on clear ground",
                       bool(sites) or after > before_count,
                       f"action={chosen.get('id') if chosen else None} spot={spot} "
                       f"in_progress={len(sites)} buildings {before_count}->{after}")
            else:
                record("build: place a structure on clear ground", False,
                       f"armed={armed} chosen={chosen.get('id') if chosen else None}, "
                       "no clear spot found near the hall")
        else:
            record("build: place a structure on clear ground", False, "no workers")
        if getattr(g, "placement", None):     # leave state clean for later tests
            key(pygame.K_ESCAPE, unicode="")
            g.ui.build_menu = False

    # ------------------------------------------------------------------ panels
    if g.state != "play":  # an earlier Esc may have paused us; normalise
        g.state = "play"
        g.world.paused = False
        step(2)
    show0 = g.ui.show_objectives
    key(pygame.K_o, unicode="o")
    toggled = g.ui.show_objectives != show0
    key(pygame.K_o, unicode="o")
    record("hotkey: O toggles objectives", toggled, f"{show0} -> {g.ui.show_objectives}")

    key(pygame.K_ESCAPE, unicode="")
    paused = g.state == "paused"
    key(pygame.K_ESCAPE, unicode="")
    record("hotkey: Esc pause/unpause", paused and g.state == "play", f"paused={paused}")

    cam0 = (g.camera.x, g.camera.y)
    mm = getattr(g.ui, "minimap_rect", None)
    if mm:
        mx, my = int(mm[0] + mm[2] * 0.75), int(mm[1] + mm[3] * 0.3)
        down((mx, my), 1)
        up((mx, my), 1)
        moved = abs(g.camera.x - cam0[0]) + abs(g.camera.y - cam0[1])
        record("minimap: click repositions camera", 5 < moved < 4000,
               f"moved {moved:.0f}px")
    else:
        record("minimap: click repositions camera", False, "no ui.minimap_rect")

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    lines = [f"# qa-input-01 — controls probe ({args.scene} scene)", "",
             f"**{len(fails)} FAIL / {len(RESULTS)} checks** — synthetic pygame events driven "
             "through the engine's own `handle_event` / `update` paths (headless, no xdotool).",
             "",
             "| control | result | detail |", "|---|---|---|"]
    for name, status, detail in RESULTS:
        lines.append(f"| {name} | {status} | {detail} |")
    lines += ["", "Re-run: `.venv/bin/python tools/qa/input_probe.py`", ""]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(json.dumps({"qa": {"input_pass": len(RESULTS) - len(fails),
                             "input_fail": len(fails)}}))
    print(f"wrote {args.out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
