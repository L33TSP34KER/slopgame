#!/usr/bin/env python3
"""Screenshots for the item shop / satchel (headless, no window).

    .venv/bin/python tools/item_shots.py

Writes:
  design/shot-shop.png          the purveyor with a forged satchel
  design/shot-shop-tooltip.png  hover card on a forged item
  design/shot-item-hud.png      satchel in the hero selection panel, shop closed
"""
from __future__ import annotations
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("EMBERFALL_NO_AUDIO", "1")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame  # noqa: E402
from emberfall.src.app import Game, parse_args  # noqa: E402


def main() -> int:
    g = Game(parse_args(["--qa", "--scene", "base"]))
    w, hero = g.world, g.world.hero

    def frame(n=2):
        for _ in range(n):
            g.update(1.0 / 60.0)
            g.draw()
            g.frame += 1

    def shot(name):
        path = os.path.join(ROOT, "design", name)
        pygame.image.save(g.screen, path)
        print("wrote", path)

    for iid in ("blade", "whet", "buckler", "tonic", "greaves", "focus"):
        w.buy_item(hero, iid, quiet=True)
    for iid in ("warbrand", "bulwark", "ashenstep"):
        w.buy_item(hero, iid, quiet=True)
    w.gold = 1480
    g.shop_open = g.ui.shop_open = True
    g.ui.mouse = (10, 10)
    frame()
    shot("shot-shop.png")
    for a in g.ui.actions:
        if a.get("kind") == "buy" and a.get("item") == "bulwark":
            r = a["rect"]
            g.ui.mouse = (r.centerx, r.centery)
            break
    frame()
    shot("shot-shop-tooltip.png")
    g.shop_open = g.ui.shop_open = False
    g.select([hero])
    g.ui.mouse = (10, 10)
    frame(3)
    shot("shot-item-hud.png")
    print("satchel", hero.items, "dmg", hero.dmg_min, hero.dmg_max, "armor", hero.armor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
