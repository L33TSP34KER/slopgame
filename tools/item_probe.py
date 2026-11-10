#!/usr/bin/env python3
"""Item shop / crafting probe — Emberfall.

Drives the real engine headless through the real UI hit-testing path (the same
rects the mouse uses), not a private copy of the rules:

    .venv/bin/python tools/item_probe.py

Every check prints PASS/FAIL, and the run writes design/notes/item-probe.md so
the numbers sit next to the other QA notes.
"""
from __future__ import annotations
import json
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
from emberfall.src.defs import (ITEMS, ITEM_SLOTS, HERO_GROWTH, UNITS, PLAYER,  # noqa: E402
                                item_tree_cost, item_sell_value)
from emberfall.src.pathfind import nearest_walkable  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(("PASS " if ok else "FAIL ") + name + (("  — " + str(detail)) if detail else ""))


def frame(g, n=1):
    for _ in range(n):
        g.update(1.0 / 60.0)
        g.draw()
        g.frame += 1


def simulate(g, seconds):
    steps = max(1, int(seconds * 30))
    for _ in range(steps):
        g.world.update(1.0 / 30.0)


def key(g, k, unicode_="p"):
    g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, unicode=unicode_, mod=0))
    frame(g)


def click(g, pos, button=1):
    g.ui.mouse = pos
    frame(g)                      # rebuild the action list with the cursor there
    for et in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
        g.handle_event(pygame.event.Event(et, button=button, pos=pos))
    frame(g)


def action(g, **kw):
    for a in g.ui.actions:
        if all(a.get(k) == v for k, v in kw.items()):
            return a
    return None


def centre(act):
    r = act["rect"]
    return (r.centerx, r.centery)


def tile(g, iid):
    act = action(g, kind="buy", item=iid)
    if not act:
        raise AssertionError(f"shop tile for {iid} not on screen")
    return centre(act)


def slot(g, i):
    act = action(g, kind="slot", slot=i)
    if not act:
        raise AssertionError(f"satchel slot {i} not on screen")
    return centre(act)


def main() -> int:
    g = Game(parse_args(["--qa", "--scene", "base"]))
    w = g.world
    hero = w.hero
    check("probe boots into a playable mission", g.state == "play" and hero is not None,
          f"state={g.state} hero={hero.kind if hero else None}")

    base_gold = w.gold
    base_dmg = (hero.dmg_min, hero.dmg_max)
    base_armor = hero.armor
    base_speed = hero.speed
    base_cd = hero.cooldown

    # ---- open the purveyor through the real key path
    key(g, pygame.K_p, "p")
    check("P opens the purveyor", g.shop_open and g.ui.shop_open, f"open={g.shop_open}")
    check("every shop tile is on screen", all(action(g, kind="buy", item=i) for i in ITEMS),
          f"{len([i for i in ITEMS if action(g, kind='buy', item=i)])}/{len(ITEMS)} tiles")

    # ---- buy a component
    click(g, tile(g, "blade"))
    check("buy Ashwood Blade: gold and satchel",
          w.gold == base_gold - 240 and hero.items == ["blade"], f"gold={w.gold} items={hero.items}")
    check("buy Ashwood Blade: +8 damage applied",
          round(hero.dmg_min - base_dmg[0]) == 8 and round(hero.dmg_max - base_dmg[1]) == 8,
          f"dmg {base_dmg}->{(hero.dmg_min, hero.dmg_max)}")
    check("buying the same item twice is refused", not w.buy_item(hero, "blade", quiet=True))

    # ---- buy the second part, then forge
    click(g, tile(g, "whet"))
    check("buy Whetstone", w.gold == base_gold - 520 and set(hero.items) == {"blade", "whet"},
          f"gold={w.gold} items={hero.items}")
    click(g, tile(g, "warbrand"))
    check("forge Ember Warbrand consumes both parts",
          hero.items == ["warbrand"] and w.gold == base_gold - 640,
          f"gold={w.gold} items={hero.items}")
    check("Ember Warbrand gives +18 damage and +20% attack speed",
          round(hero.dmg_min - base_dmg[0]) == 18 and abs(hero.cooldown - base_cd / 1.2) < 1e-6,
          f"dmg {base_dmg}->{(hero.dmg_min, hero.dmg_max)} cd {base_cd:.3f}->{hero.cooldown:.3f}")
    check("forging out of parts is refused", not w.buy_item(hero, "bulwark", quiet=True))

    # ---- shop reach
    fx, fy = hero.x, hero.y
    hero.x, hero.y = 62.0, 30.0
    frame(g)
    g0 = w.gold
    click(g, tile(g, "buckler"))
    check("out of shop range: purchase refused",
          "buckler" not in hero.items and w.gold == g0, f"gold={w.gold} items={hero.items}")
    hero.x, hero.y = fx, fy
    frame(g)

    # ---- sell at 50 %
    g0 = w.gold
    click(g, slot(g, 0), button=3)
    check("right-click sells for 50% of the tree",
          hero.items == [] and w.gold == g0 + item_sell_value("warbrand"),
          f"gold={g0}->{w.gold} (expected +{item_sell_value('warbrand')})")
    check("selling restores the stats",
          round(hero.dmg_min) == round(base_dmg[0]) and abs(hero.cooldown - base_cd) < 1e-6,
          f"dmg={hero.dmg_min} cd={hero.cooldown:.3f}")

    # ---- blink active, through targeting + a real click on the ground
    click(g, tile(g, "greaves"))
    click(g, tile(g, "focus"))
    click(g, tile(g, "ashenstep"))
    check("forge Ashen Step", hero.items == ["ashenstep"], f"items={hero.items}")
    check("Ashen Step gives +10% move speed",
          abs(hero.speed - base_speed * 1.10) < 1e-6, f"speed {base_speed:.2f}->{hero.speed:.2f}")
    click(g, slot(g, 0))
    check("clicking an active item starts ground targeting",
          g.targeting is not None and g.targeting.get("item") == 0, f"targeting={g.targeting}")
    hx, hy = hero.x, hero.y
    dest = nearest_walkable(w.map, int(hx) + 3, int(hy), w.blocked) or (int(hx) + 3, int(hy))
    px, py = g.renderer.w2s(dest[0] + 0.5, dest[1] + 0.5, 1)
    click(g, (int(px), int(py)))
    moved = ((hero.x - hx) ** 2 + (hero.y - hy) ** 2) ** 0.5
    check("Ashen Step blinks the hero onto the clicked tile",
          moved > 1.5 and hero.item_cd.get("ashenstep", 0) > 0,
          f"moved {moved:.2f} tiles, cd={hero.item_cd.get('ashenstep', 0):.1f}s")
    hx, hy = hero.x, hero.y
    click(g, slot(g, 0))
    px, py = g.renderer.w2s(hx + 2.0, hy, 1)
    click(g, (int(px), int(py)))
    check("Ashen Step is refused while cooling down",
          abs(hero.x - hx) < 1e-6 and abs(hero.y - hy) < 1e-6,
          f"cd={hero.item_cd.get('ashenstep', 0):.1f}s, position unchanged")

    # ---- flask: heal over time (back at the counter after the blink)
    hero.x, hero.y = fx, fy
    frame(g)
    key(g, pygame.K_p, "p")
    click(g, tile(g, "tonic"))
    click(g, tile(g, "greaves"))
    click(g, tile(g, "flask"))
    check("forge Ember Flask from tonic + greaves", "flask" in hero.items, f"items={hero.items}")
    hero.hp = hero.max_hp - 350.0
    hurt = hero.hp
    if "flask" in hero.items:
        click(g, slot(g, hero.items.index("flask")))
    immediate = hero.hp
    simulate(g, 6.5)
    check("Ember Flask heals over its duration",
          immediate - hurt < 30 and hero.hp - hurt >= 260,
          f"hp {hurt:.0f} -> {immediate:.0f} (cast) -> {hero.hp:.0f} (6.5s later)")
    check("Ember Flask goes on cooldown", hero.item_cd.get("flask", 0) > 0,
          f"cd={hero.item_cd.get('flask', 0):.0f}s")

    # ---- durability: the satchel survives the hero's death
    hero.xp = 900
    w.gain_xp(hero, 0)
    level = hero.level
    carried = list(hero.items)
    dmg_carried = hero.dmg_min
    altar = next((b for b in w.buildings_of(PLAYER) if b.bid == "altar"), None)
    if altar is None:
        altar = w.spawn_building("altar", int(hero.x) + 3, int(hero.y) + 2, PLAYER)
    w.kill(hero, None)
    hero.hero_revive_t = 0.05          # the timer lives on the fallen hero
    for _ in range(40):
        w.update(1.0 / 30.0)
        if w.hero and w.hero.alive:
            break
    new_hero = w.hero
    check("hero revives with level, growth and satchel intact",
          new_hero is not hero and new_hero.alive and new_hero.level == level
          and new_hero.items == carried and new_hero.dmg_min == dmg_carried,
          f"level {level}->{new_hero.level}, items={new_hero.items}, "
          f"dmg {dmg_carried}->{new_hero.dmg_min}")

    # ---- QA state carries the satchel
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        g.qa_state()
    line = buf.getvalue().strip().splitlines()[-1]
    data = json.loads(line)
    check("qa_state exposes items / stats / shop reach",
          data.get("items") == new_hero.items and "hero_dmg" in data and "shop" in data,
          f"items={data.get('items')} shop={data.get('shop')}")

    # ---- report
    ok = sum(1 for r in RESULTS if r["ok"])
    total = len(RESULTS)
    print(f"\n{ok}/{total} checks passed")
    out_md = os.path.join(ROOT, "design", "notes", "item-probe.md")
    out_json = os.path.join(ROOT, "design", "notes", "item-probe.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(dict(ok=ok, total=total, checks=RESULTS), f, indent=1)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("# item / shop probe\n\n")
        f.write(f"`tools/item_probe.py` — {ok}/{total} PASS, headless, driving the real "
                "UI hit-test path (shop key, tile clicks, satchel clicks, ground targeting).\n\n")
        f.write("| check | result | detail |\n|---|---|---|\n")
        for r in RESULTS:
            f.write(f"| {r['name']} | {'**PASS**' if r['ok'] else '**FAIL**'} | {r['detail']} |\n")
        f.write("\n## Item economy as implemented\n\n")
        f.write("| item | tier | parts | forge fee | full tree | sells for | stats |\n|---|---|---|---|---|---|---|\n")
        for iid, it in ITEMS.items():
            parts = " + ".join(it.get("parts", [])) or "—"
            stats = ", ".join(f"{k} {v}" for k, v in it.get("stats", {}).items())
            f.write(f"| {it['name']} | {it['tier']} | {parts} | {it.get('cost', {}).get('g', 0)}g | "
                    f"{item_tree_cost(iid)}g | {item_sell_value(iid)}g | {stats} |\n")
    print("wrote", out_md)
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
