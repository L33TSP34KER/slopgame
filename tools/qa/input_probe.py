#!/usr/bin/env python3
"""Input / controls QA probe (mimo, tools/qa/).

The headless rule forbids xdotool, so this drives the game IN-PROCESS: it
builds the real `Game`, posts synthetic pygame events into the same
`handle_event` path a player uses, steps the sim, and asserts on observable
state (selection, camera, orders, modes, panels).

    python3 tools/qa/input_probe.py                 # design/notes/qa-input-01.md
    python3 tools/qa/input_probe.py --frames 30     # frames per step

Covers checklist section 2 (controls) plus bits of 3/7 that are reachable
without a scripted-input hook from the engine.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback

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
    ap.add_argument("--frames", type=int, default=20, help="frames per settle step")
    ap.add_argument("--out", default=os.path.join(ROOT, "design", "notes", "qa-input-01.md"))
    args = ap.parse_args()

    from emberfall.src import app as app_mod

    argv = ["--qa", "--scene", args.scene]
    g = app_mod.Game(app_mod.parse_args(argv))
    g.running = True

    dt = 1.0 / 60.0

    def step(n: int = 1) -> None:
        for _ in range(n):
            for ev in pygame.event.get():
                g.handle_event(ev)
            try:
                g.update(dt)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                raise
            g.draw()

    def key(k, unicode: str = "", mods: int = 0) -> None:
        real_get_mods = pygame.key.get_mods
        pygame.key.get_mods = lambda: mods  # type: ignore[assignment]
        try:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k, unicode=unicode))
            step(1)
        finally:
            pygame.key.get_mods = real_get_mods  # type: ignore[assignment]

    def mouse_down(pos, button=1) -> None:
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button))
        step(1)

    def mouse_up(pos, button=1) -> None:
        pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button))
        step(1)

    def motion(pos, rel=(0, 0)) -> None:
        pygame.event.post(pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=rel, buttons=(True, False, False)))
        step(1)

    step(args.frames)  # settle into the scene

    # ---------------------------------------------------------------- cameras
    # held-key camera (WASD/arrow panning is polled, not event-driven)
    real_pressed = pygame.key.get_pressed

    def fake_pressed():
        arr = real_pressed()
        try:
            arr = list(arr)
            for k in (pygame.K_d, pygame.K_RIGHT):
                arr[k] = 1
            return arr
        except Exception:  # noqa: BLE001
            return arr

    x0 = g.camera.x
    pygame.key.get_pressed = fake_pressed  # type: ignore[assignment]
    try:
        step(40)
    finally:
        pygame.key.get_pressed = real_pressed  # type: ignore[assignment]
    record("camera: held D / right-arrow pan", g.camera.x > x0 + 5,
           f"camera.x {x0:.0f} -> {g.camera.x:.0f}")

    x0 = g.camera.x
    g.camera.x += 400
    g.camera.clamp()
    record("camera: clamp stays in world", 0 <= g.camera.x <= 2000, f"x={g.camera.x:.0f}")

    # --------------------------------------------------------------- selection
    from emberfall.src.defs import PLAYER as PLAYER_TEAM
    player_units = [u for u in g.world.entities
                    if getattr(u, "team", None) == PLAYER_TEAM
                    and getattr(u, "alive", False) and not getattr(u, "is_building", False)]
    if not player_units:
        player_units = [u for u in g.world.entities
                        if getattr(u, "alive", False) and not getattr(u, "is_building", False)]
    record("setup: units exist to click", bool(player_units), f"{len(player_units)} candidates")

    if player_units:
        u = player_units[0]
        sx, sy = g.renderer.w2s(u.x, u.y, getattr(u, "height", 1) or 1)
        sx, sy = int(sx), int(sy)
        g.select([])
        mouse_down((sx, sy), 1)
        mouse_up((sx, sy), 1)
        record("select: left-click a unit", len(g.selection) >= 1,
               f"click ({sx},{sy}) -> {len(g.selection)} selected")

        # box select across the spawn cluster
        g.select([])
        mouse_down((20, 120), 1)
        motion((900, 640))
        mouse_up((900, 640), 1)
        record("select: box select", len(g.selection) >= 1,
               f"box -> {len(g.selection)} selected")

        # shift add
        before = len(g.selection)
        if player_units:
            u2 = player_units[-1]
            sx2, sy2 = g.renderer.w2s(u2.x, u2.y, getattr(u2, "height", 1) or 1)
            real_get_mods = pygame.key.get_mods
            pygame.key.get_mods = lambda: pygame.KMOD_SHIFT  # type: ignore[assignment]
            try:
                mouse_down((int(sx2), int(sy2)), 1)
                mouse_up((int(sx2), int(sy2)), 1)
            finally:
                pygame.key.get_mods = real_get_mods  # type: ignore[assignment]
            record("select: shift-add", len(g.selection) >= before,
                   f"{before} -> {len(g.selection)}")

        # control group
        g.select([])
        real_get_mods = pygame.key.get_mods
        pygame.key.get_mods = lambda: pygame.KMOD_CTRL  # type: ignore[assignment]
        try:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1, unicode="1"))
            step(1)
        finally:
            pygame.key.get_mods = real_get_mods  # type: ignore[assignment]
        grp_ok = bool(g.control_groups.get(1))
        g.select([])
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_1, unicode="1"))
        step(1)
        record("select: ctrl+1 group then 1 recall", grp_ok and len(g.selection) >= 1,
               f"group stored={grp_ok}, recalled={len(g.selection)}")

        # -------------------------------------------------------------- orders
        u = player_units[0]
        g.select([u])
        px0, py0 = u.x, u.y
        target_x = min(g.map.w - 3.0, u.x + 6.0)
        target_y = min(g.map.h - 3.0, u.y + 4.0)
        tx, ty = g.renderer.w2s(target_x, target_y, getattr(u, "height", 1) or 1)
        mouse_down((int(tx), int(ty)), 3)
        step(150)
        moved = abs(u.x - px0) + abs(u.y - py0)
        record("order: right-click move", moved > 0.3, f"unit moved {moved:.2f} tiles")

        # attack-move hotkey
        g.select([u])
        key(pygame.K_a, unicode="a")
        am = bool(getattr(g, "attack_move_mode", False))
        key(pygame.K_ESCAPE, unicode="")
        am2 = bool(getattr(g, "attack_move_mode", False))
        record("hotkey: A arms attack-move, Esc cancels", am and not am2, f"{am} -> {am2}")

        key(pygame.K_s, unicode="s")
        record("hotkey: S (stop) handled without error", True, "no exception")

        # hero select via SPACE
        key(pygame.K_SPACE, unicode=" ")
        heroes = [e for e in g.selection if getattr(e, "is_hero", False)]
        record("hotkey: SPACE selects hero", bool(heroes), f"selection={len(g.selection)}")

        # idle worker F1
        key(pygame.K_F1, unicode="")
        record("hotkey: F1 idle worker", len(g.selection) >= 1, f"selection={len(g.selection)}")

    # ------------------------------------------------------------------- panels
    show0 = g.ui.show_objectives
    key(pygame.K_o, unicode="o")
    record("hotkey: O toggles objectives", g.ui.show_objectives != show0,
           f"{show0} -> {g.ui.show_objectives}")
    key(pygame.K_o, unicode="o")

    st0 = g.state
    key(pygame.K_ESCAPE, unicode="")
    paused = g.state == "paused"
    key(pygame.K_ESCAPE, unicode="")
    record("hotkey: Esc pause/unpause", paused and g.state == "play",
           f"{st0} -> {g.state}")

    # ---------------------------------------------------------------- minimap
    cam0 = (g.camera.x, g.camera.y)
    try:
        mm = g.ui.minimap_rect if hasattr(g.ui, "minimap_rect") else None
        if mm:
            mx = int(mm[0] + mm[2] * 0.75)
            my = int(mm[1] + mm[3] * 0.3)
            mouse_down((mx, my), 1)
            mouse_up((mx, my), 1)
            moved = abs(g.camera.x - cam0[0]) + abs(g.camera.y - cam0[1])
            record("minimap: click repositions camera", moved > 5,
                   f"camera moved {moved:.0f}px")
        else:
            record("minimap: click repositions camera", False, "no ui.minimap_rect exposed")
    except Exception as exc:  # noqa: BLE001
        record("minimap: click repositions camera", False, f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------------ build UI
    try:
        workers = [u for u in g.world.entities
                   if getattr(u, "alive", False) and getattr(u, "worker", False)]
        if workers:
            g.select([workers[0]])
            key(pygame.K_b, unicode="b")
            placed = bool(getattr(g, "placement", None))
            key(pygame.K_ESCAPE, unicode="")
            record("build: B arms placement, Esc cancels", placed and not g.placement,
                   f"placement={placed}")
        else:
            record("build: B arms placement, Esc cancels", False, "no worker entities found")
    except Exception as exc:  # noqa: BLE001
        record("build: B arms placement, Esc cancels", False, f"{type(exc).__name__}: {exc}")

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    lines = [f"# qa-input-01 — controls probe ({args.scene} scene)", "",
             f"**{len(fails)} FAIL / {len(RESULTS)} checks** — synthetic pygame events "
             "driven through the engine's own `handle_event`.", "",
             "| control | result | detail |", "|---|---|---|"]
    for name, status, detail in RESULTS:
        lines.append(f"| {name} | {status} | {detail} |")
    lines.append("")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(json.dumps({"qa": {"input_pass": len(RESULTS) - len(fails),
                             "input_fail": len(fails)}}))
    print(f"wrote {args.out}")
    try:
        pygame.quit()
    except Exception:  # noqa: BLE001
        pass
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
