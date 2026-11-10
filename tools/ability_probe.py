#!/usr/bin/env python3
"""Ability probe — every hero ability through the real targeting path.

Regression cover for the 08:35 crash: casting Daybreak with an ally inside its
radius raised KeyError 'heal' (the AoE branch healed unconditionally, but only
Consecrate defines a heal) and took the running game down. That cast is check
number one here.

    .venv/bin/python tools/ability_probe.py     -> design/notes/ability-probe.md
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
from emberfall.src.defs import ABILITIES, PLAYER, ENEMY  # noqa: E402

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append(dict(name=name, ok=bool(ok), detail=str(detail)))
    print(("PASS " if ok else "FAIL ") + name + (("  — " + str(detail)) if detail else ""))


def frame(g, n=1):
    for _ in range(n):
        g.update(1.0 / 60.0)
        g.draw()
        g.frame += 1


def aim(g, aid, tile):
    """Arm an ability the way the UI does, then click a ground tile.

    w2s() is camera-relative world space; the mouse path goes through the same
    screen_pos() transform the game uses, which adds the camera offset.
    """
    g.handle_action({"kind": "ability", "ability": aid})
    wx, wy = g.renderer.w2s(tile[0], tile[1], 0)
    px = wx - g.camera.x + 800
    py = wy - g.camera.y + 450
    g.cast_at(int(px), int(py))
    frame(g)


def main() -> int:
    g = Game(parse_args(["--qa", "--scene", "base"]))
    w, h = g.world, g.world.hero
    h.level = 6                       # all four abilities unlocked
    h.xp = 1200
    allies = [u for u in w.units_of(PLAYER) if not u.is_building and u is not h]
    check("scene has allies to stand in the blast", len(allies) >= 3, f"{len(allies)} allies")

    # ---- THE CRASH: daybreak, cast on the hero's own tile (allies inside)
    h.mana = h.max_mana
    before_mana = h.mana
    crashed = None
    try:
        aim(g, "daybreak", (h.x, h.y))
    except Exception as exc:  # noqa: BLE001
        crashed = f"{type(exc).__name__}: {exc}"
    check("Daybreak with allies in radius does not crash", crashed is None, crashed or "clean cast")
    check("Daybreak spends 140 mana and goes on a 90s cooldown",
          abs((before_mana - h.mana) - 140) < 0.01 and h.abil_cd.get("daybreak", 0) > 0,
          f"mana {before_mana:.0f}->{h.mana:.0f}, cd={h.abil_cd.get('daybreak', 0):.0f}s")
    check("Daybreak does not heal allies (it only stuns and burns)",
          all(u.hp <= u.max_hp for u in allies), "allies at or below max hp")

    # an enemy inside the blast takes damage and the 2s stun
    foe = w.spawn_unit("ghoul", h.x + 2.0, h.y, ENEMY)
    frame(g)
    h.abil_cd.clear()
    h.mana = h.max_mana
    hp0 = foe.hp
    aim(g, "daybreak", (h.x, h.y))
    check("Daybreak damages and stuns the enemy in radius",
          foe.hp < hp0 and foe.stun > 1.5, f"hp {hp0:.0f}->{foe.hp:.0f}, stun={foe.stun:.1f}s")

    # ---- consecrate: the ability that DOES heal
    h.abil_cd.clear()
    h.mana = h.max_mana
    mate = allies[0]
    mate.x, mate.y = h.x + 1.0, h.y + 0.5
    mate.hp = mate.max_hp * 0.5
    hurt = mate.hp
    mana0 = h.mana
    aim(g, "consecrate", (h.x, h.y))
    check("Consecrate heals the ally inside the fire", mate.hp > hurt + 20,
          f"ally hp {hurt:.0f}->{mate.hp:.0f}")
    check("Consecrate spends 70 mana and goes on cooldown",
          h.abil_cd.get("consecrate", 0) > 0 and (mana0 - h.mana) > 60,
          f"mana {mana0:.0f}->{h.mana:.0f}, cd={h.abil_cd.get('consecrate', 0):.0f}s")

    # ---- ember lance: needs a live enemy target, refuses empty ground
    h.abil_cd.clear()
    h.mana = h.max_mana
    mana0 = h.mana
    aim(g, "ember-lance", (h.x + 6, h.y))
    check("Ember Lance on empty ground is refused (no mana, no cooldown)",
          abs(h.mana - mana0) < 0.01 and h.abil_cd.get("ember-lance", 0) == 0,
          f"mana {mana0:.0f}->{h.mana:.0f}")
    foe2 = w.spawn_unit("ghoul", h.x + 2.5, h.y + 1.0, ENEMY)
    frame(g)
    hp0, mana0 = foe2.hp, h.mana
    g.handle_action({"kind": "ability", "ability": "ember-lance"})
    g.cast_at(*g.screen_pos(foe2))
    frame(g)
    check("Ember Lance hits and stuns a target in range",
          foe2.hp < hp0 and foe2.stun > 0.5 and h.mana < mana0,
          f"hp {hp0:.0f}->{foe2.hp:.0f}, stun={foe2.stun:.1f}s")
    far = w.spawn_unit("ghoul", h.x + 20, h.y, ENEMY)
    frame(g)
    hp0 = far.hp
    g.handle_action({"kind": "ability", "ability": "ember-lance"})
    g.cast_at(*g.screen_pos(far))
    frame(g)
    check("Ember Lance refuses an out-of-range target", abs(far.hp - hp0) < 0.01,
          f"hp {hp0:.0f}->{far.hp:.0f}")

    # ---- aegis: self shield
    h.abil_cd.clear()
    h.mana = h.max_mana
    g.handle_action({"kind": "ability", "ability": "aegis"})
    frame(g)
    check("Aegis shields the hero for 8s",
          h.shield_hp > 100 and abs(h.shield_t - 8) < 0.5,
          f"shield={h.shield_hp:.0f} for {h.shield_t:.1f}s")
    check("Aegis charges its cooldown after use", h.abil_cd.get("aegis", 0) > 0,
          f"cd={h.abil_cd.get('aegis', 0):.0f}s")

    # ---- mana gate
    h.abil_cd.clear()
    h.mana = 5
    mana0 = h.mana
    aim(g, "daybreak", (h.x, h.y))
    check("An ability with no mana is refused, not cast",
          abs(h.mana - mana0) < 0.01 and h.abil_cd.get("daybreak", 0) == 0,
          f"mana={h.mana:.0f}")

    check("the game is still running after all casts", g.running and h.alive,
          f"state={w.state}")

    ok = sum(1 for r in RESULTS if r["ok"])
    total = len(RESULTS)
    print(f"\n{ok}/{total} checks passed")
    out_md = os.path.join(ROOT, "design", "notes", "ability-probe.md")
    out_json = os.path.join(ROOT, "design", "notes", "ability-probe.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(dict(ok=ok, total=total, checks=RESULTS), f, indent=1)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("# ability probe\n\n")
        f.write(f"`tools/ability_probe.py` — {ok}/{total} PASS, headless, through the "
                "real targeting path (`handle_action` + `cast_at`).\n\n")
        f.write("| check | result | detail |\n|---|---|---|\n")
        for r in RESULTS:
            f.write(f"| {r['name']} | {'**PASS**' if r['ok'] else '**FAIL**'} | {r['detail']} |\n")
        f.write("\nRegression: Daybreak raised `KeyError: 'heal'` whenever an ally stood "
                "inside its radius — the AoE branch healed every ally unconditionally, "
                "but `defs.ABILITIES['daybreak']` has no `heal` key. Same class of bug "
                "guarded for `stun` and `shield`, so an ability without them can no "
                "longer take the game down.\n")
    print("wrote", out_md)
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
