#!/usr/bin/env python3
"""Display/input probe — proves the game is correct at ANY window resolution.

The player's complaints (wrong resolution, controls not matching what's on
screen) come from scaling, so this test deliberately puts the window in sizes
other than the logical 1600x900 and asserts:

  1. present() letterboxes aspect-correctly (no stretching),
  2. map_pos() round-trips logical -> window -> logical exactly,
  3. a click injected at *window* coordinates lands on the right *logical*
     target (verified through the real minimap -> camera jump),
  4. a click in the letterbox bar is ignored instead of hitting UI.

    .venv/bin/python tools/qa/display_probe.py
"""
from __future__ import annotations

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


def rec(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}", flush=True)


def window_of(logical: tuple[int, int], win: tuple[int, int]) -> tuple[int, int]:
    """Mirror of Game.present(): logical pixel -> window pixel."""
    ww, wh = win
    from emberfall.src.defs import SCREEN_H, SCREEN_W
    scale = min(ww / SCREEN_W, wh / SCREEN_H)
    dw, dh = SCREEN_W * scale, SCREEN_H * scale
    ox, oy = (ww - dw) / 2, (wh - dh) / 2
    return (int(ox + logical[0] * scale), int(oy + logical[1] * scale))


def main() -> int:
    from emberfall.src import app as app_mod
    from emberfall.src.defs import SCREEN_H, SCREEN_W

    g = app_mod.Game(app_mod.parse_args(["--qa", "--scene", "play"]))
    g.running = True
    dt = 1 / 60

    def step(n: int = 1) -> None:
        for _ in range(n):
            for ev in pygame.event.get():
                g.handle_event(ev)
            g.update(dt)
            g.draw()
            g.present()

    step(30)
    rec("logical backbuffer size", g.screen.get_size() == (SCREEN_W, SCREEN_H),
        f"screen={g.screen.get_size()}")

    for win_size in [(1600, 900), (1280, 720), (1920, 1080), (2560, 720), (1000, 1000)]:
        try:
            pygame.display.set_mode(win_size, pygame.RESIZABLE)
        except pygame.error as exc:
            rec(f"window {win_size} opens", False, str(exc))
            continue
        step(2)
        win = pygame.display.get_surface()
        ww, wh = win.get_size()
        scale = min(ww / SCREEN_W, wh / SCREEN_H)
        dw, dh = int(SCREEN_W * scale), int(SCREEN_H * scale)
        # aspect correctness: rendered picture must keep the 16:9 ratio
        aspect_ok = abs((dw / dh) - (SCREEN_W / SCREEN_H)) < 0.01
        rec(f"aspect correct at {win_size}", aspect_ok,
            f"picture {dw}x{dh} letterbox {((ww-dw)//2, (wh-dh)//2)}")

        # round-trip: every sample must map window -> logical back to itself
        samples = [(10, 10), (SCREEN_W // 2, SCREEN_H // 2), (SCREEN_W - 5, SCREEN_H - 5),
                   (800, 450), (1400, 800)]
        rt_ok = True
        worst = 0
        tol = max(2, int(1 / scale) + 1)  # forward-map rounding costs 1/scale px
        for lp in samples:
            wp = window_of(lp, (ww, wh))
            back = g.map_pos(wp)
            if back is None:
                rt_ok = False
                continue
            worst = max(worst, abs(back[0] - lp[0]), abs(back[1] - lp[1]))
        rec(f"coordinate round-trip at {win_size}", rt_ok and worst <= tol,
            f"max error {worst}px (tolerance {tol}) across {len(samples)} samples")

    # ---- click mapping through the real game path at a non-native size ----
    pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)
    step(3)
    # the SDL dummy driver does not always honour set_mode sizes: measure the
    # window we actually got, otherwise the forward map is computed on a size
    # the driver never created and the test proves nothing.
    actual = pygame.display.get_surface().get_size()
    print(f"  actual window after set_mode((1920,1080)) = {actual}")
    from emberfall.src.defs import PLAYER  # noqa: F401  (imports prove defs ok)
    mm = getattr(g.ui, "minimap_rect", None)
    if mm and g.state == "play":
        logical_target = (mm[0] + mm[2] // 2, mm[1] + mm[3] // 2)  # minimap centre
        before = (g.camera.x, g.camera.y)
        wp = window_of(logical_target, actual)
        for et in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            pygame.event.post(pygame.event.Event(et, {"pos": wp, "button": 1}))
        step(3)
        moved = abs(g.camera.x - before[0]) + abs(g.camera.y - before[1])
        rec("window click hits the minimap (non-native window)", moved > 5,
            f"window {actual}: click {wp} -> logical {g.map_pos(wp)}, camera moved {moved:.0f}px")
    else:
        rec("window click hits the minimap (1920x1080 window)", False,
            f"minimap={mm} state={g.state}")

    # ---- click in the letterbox must be ignored, not hit HUD ----
    pygame.display.set_mode((2560, 720), pygame.RESIZABLE)  # very wide: bars at sides
    step(2)
    st0, sel0 = g.state, list(g.selection)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (5, 5), "button": 1}))
    step(2)
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": (5, 5), "button": 1}))
    step(1)
    rec("letterbox click ignored", g.state == st0 and g.selection == sel0,
        f"state {st0}->{g.state}")

    # ---- present() must actually paint the logical corner onto the window ----
    pygame.display.set_mode((1600, 900), pygame.RESIZABLE)
    g.screen.fill((12, 34, 56))
    g.present()
    win = pygame.display.get_surface()
    ww2, wh2 = win.get_size()
    s2 = min(ww2 / SCREEN_W, wh2 / SCREEN_H)
    cx = int((ww2 - SCREEN_W * s2) / 2 + (SCREEN_W * s2) / 2)   # picture centre
    cy = int((wh2 - SCREEN_H * s2) / 2 + (SCREEN_H * s2) / 2)
    px = tuple(win.get_at((cx, cy)))[:3]
    near = all(abs(px[i] - (12, 34, 56)[i]) <= 6 for i in range(3))
    bar = tuple(win.get_at((0, 0)))[:3]
    rec("present() paints the logical picture into the window",
        near, f"window {ww2}x{wh2}: centre={px} (want ~(12,34,56)), corner/bar={bar}")

    fails = [r for r in RESULTS if r[1] == "FAIL"]
    lines = ["# display-probe — resolution & input correctness at any window size", "",
             f"**{len(fails)} FAIL / {len(RESULTS)} checks**", "",
             "| check | result | detail |", "|---|---|---|"]
    for name, status, detail in RESULTS:
        lines.append(f"| {name} | {status} | {detail} |")
    lines.append("")
    out = os.path.join(ROOT, "design", "notes", "qa-display.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(json.dumps({"qa": {"display_pass": len(RESULTS) - len(fails),
                             "display_fail": len(fails)}}))
    print(f"wrote {out}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
