#!/usr/bin/env python3
"""Lattice check — objective number for the 'ground reads as a checkerboard' report.

Renders the real scene headless, samples mean colour in a small box around each
visible ground-cell centre, and reports how much brighter/darker a cell is than
its neighbours. A painted field keeps that delta small; a lattice of outlined
or differently-tinted diamonds shows a large one.

    .venv/bin/python tools/qa/lattice_check.py
    .venv/bin/python tools/qa/lattice_check.py --label after-tiles
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


def mean_box(surf, cx, cy, r=3):
    w, h = surf.get_size()
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    tr = tg = tb = n = 0
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            c = surf.get_at((x, y))
            if c.a > 200:
                tr += c.r; tg += c.g; tb += c.b; n += 1
    if n < 6:
        return None
    return (tr / n, tg / n, tb / n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scene", default="play")
    ap.add_argument("--label", default="lattice")
    ap.add_argument("--frames", type=int, default=120)
    args = ap.parse_args()

    from emberfall.src import app as app_mod
    from emberfall.src.mapgen import GRASS, ROCK, SAND, DIRT
    from emberfall.src.core import sx, sy

    g = app_mod.Game(app_mod.parse_args(["--qa", "--scene", args.scene]))
    g.running = True
    dt = 1 / 60

    def step(n=1):
        for _ in range(n):
            for ev in pygame.event.get():
                g.handle_event(ev)
            g.update(dt)
            g.draw()
            g.present()

    step(args.frames)
    frame = pygame.Surface.get_size(g.screen)
    cam = g.camera
    m = g.map
    left = cam.x - frame[0] / 2
    top = cam.y - frame[1] / 2

    cells = {}
    for y in range(m.h):
        for x in range(m.w):
            t = m.terr(x, y)
            if t not in (GRASS, ROCK, SAND, DIRT):
                continue
            h = m.height_at(x, y)
            px, py = g.renderer.w2s(x, y, h)
            px -= left
            py -= top
            if not (60 < px < frame[0] - 60 and 60 < py < frame[1] - 60):
                continue
            # only open ground (no props/buildings/units on it)
            if m.wood.get((x, y)) or m.blocked[y * m.w + x]:
                continue
            col = mean_box(g.screen, int(px), int(py), 3)
            if col:
                cells[(x, y)] = (t, col)

    # neighbour deltas on the iso lattice (right/down in tile space)
    deltas, within = [], []
    for (x, y), (t, c) in cells.items():
        for dx, dy in ((1, 0), (0, 1)):
            nb = cells.get((x + dx, y + dy))
            if nb and nb[0] == t:
                deltas.append(sum(abs(nb[1][i] - c[i]) for i in range(3)) / 3)
        # intra-cell spread: sample two boxes half a tile apart inside the cell
        h = m.height_at(x, y)
        px, py = g.renderer.w2s(x + 0.5, y + 0.5, h)
        px -= left; py -= top
        a = mean_box(g.screen, int(px) - 6, int(py), 2)
        b = mean_box(g.screen, int(px) + 6, int(py), 2)
        if a and b:
            within.append(sum(abs(a[i] - b[i]) for i in range(3)) / 3)

    import statistics as st
    mean_delta = st.mean(deltas) if deltas else None
    mean_within = st.mean(within) if within else None
    ratio = (mean_delta / mean_within) if (mean_delta and mean_within) else None

    out = {
        "label": args.label,
        "cells_sampled": len(cells),
        "neighbour_delta": round(mean_delta, 2) if mean_delta is not None else None,
        "within_cell_delta": round(mean_within, 2) if mean_within is not None else None,
        "lattice_ratio": round(ratio, 2) if ratio else None,
        "verdict": ("PASS" if ratio and ratio < 1.6 else
                    "WARN" if ratio and ratio < 2.4 else "FAIL"),
    }
    os.makedirs(os.path.join(ROOT, "design", "notes"), exist_ok=True)
    path = os.path.join(ROOT, "design", "notes", f"lattice-{args.label}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({"qa": out}))
    print(f"wrote {path}")
    return 0 if out["verdict"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
