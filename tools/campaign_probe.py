#!/usr/bin/env python3
"""Campaign probe — headless proof that every mission exists and works.

Council p-3f9a1c02 condition: "every scenario gets release-gate coverage".
tools/qa/ belongs to mimo, so this probe lives in tools/ and prints a matrix
mimo can paste into release_check later.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python tools/campaign_probe.py
    .venv/bin/python tools/campaign_probe.py --no-win     # skip the autoplay win

Checks per mission:
  * map generates at the scenario size (84 < w <= 128) with the scenario flip
  * mission starts: correct difficulty tier, Necropolis HP, boss presence/identity
  * the Renderer bakes a surface sized for THAT map (the old code always baked
    84x84 — 5656x5796 — which is why bigger maps needed render.py changes)
  * camera bounds are sane (min < max)
  * mission 1 is novice, bossless, <=2 guards — the human's "super easy"
Plus: progression unlock chain, restart-in-campaign, and (by default) an
autoplay WIN of mission 1 — the mission the human called impossible.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402
from emberfall.src.app import Game  # noqa: E402
from emberfall.src import campaign  # noqa: E402
from emberfall.src.defs import ENEMY, PLAYER, TILE_W, TILE_H, UNITS  # noqa: E402

FAILS: list[str] = []
WARNS: list[str] = []
RESULTS: list[dict] = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)
        print(f"  FAIL  {msg}")
    return cond


def mk_game(autoplay=False, speed=1.0):
    return Game(argparse.Namespace(difficulty="squire", qa=False, shot=None, frames=0,
                                   scene="base", speed=speed, fullscreen=False, music=0.0,
                                   sfx=0.0, autoplay=autoplay, autoshop=False))


def expected_surface(w, h):
    # render.py bake: MW = MH = (W + H) * (TILE // 2) + {280, 420}
    half = TILE_W // 2
    return ((w + h) * half + 280, (w + h) * half + 420)


def matrix():
    print("== scenario matrix ==")
    g = mk_game()
    for i in range(campaign.count()):
        sc = dict(campaign.scenario(i))
        sc["_index"] = i
        g.start_mission(scenario=sc, skip_intro=True)
        w = g.world
        m = w.map
        tag = f"m{i + 1} {sc['name']}"
        check(m.w == sc["w"] and m.h == sc["h"], f"{tag}: size {m.w}x{m.h} != {sc['w']}x{sc['h']}")
        check(84 < m.w <= 128 and 84 < m.h <= 128, f"{tag}: size not in (84, 128] band")
        check(w.diff_id == sc["diff"], f"{tag}: tier {w.diff_id} != {sc['diff']}")
        necro = next((b for b in w.buildings_of(ENEMY) if b.bid == "necropolis"), None)
        check(necro is not None, f"{tag}: no Necropolis")
        if necro:
            check(necro.max_hp == sc["necro_hp"], f"{tag}: necro hp {necro.max_hp} != {sc['necro_hp']}")
        bosses = [u for u in w.units_of(ENEMY) if u.boss]
        if sc["boss"]:
            check(len(bosses) == 1, f"{tag}: expected 1 boss, got {len(bosses)}")
            if bosses:
                check(bosses[0].kind == sc["boss"],
                      f"{tag}: boss is {bosses[0].kind}, want {sc['boss']}")
                # spawn_unit scatters units by <=0.33 tile so stacked spawns
                # do not overlap, so seat-check with 0.5 tolerance
                if necro:
                    check(abs(bosses[0].x - (necro.x + 3.5)) <= 0.5
                          and abs(bosses[0].y - (necro.y + 7.0)) <= 0.5,
                          f"{tag}: boss at ({bosses[0].x:.1f},{bosses[0].y:.1f}) "
                          f"is not seated by the Necropolis at ({necro.x},{necro.y})")
            check(w.ai.boss_wake_time == sc["boss_wake"], f"{tag}: boss_wake not applied")
        else:
            check(not bosses, f"{tag}: unexpected boss {bosses}")
        exp = expected_surface(m.w, m.h)
        got = g.renderer.surface.get_size()
        check(got == exp, f"{tag}: renderer surface {got} != {exp} (map {m.w}x{m.h})")
        cb = g.renderer.cam_bounds()
        check(cb[0] < cb[2] and cb[1] < cb[3], f"{tag}: broken camera bounds {cb}")
        check(g.state == "play", f"{tag}: state {g.state}")
        # player start must be reachable: hall exists, hero exists
        hall = next((b for b in w.buildings_of(PLAYER) if b.bid == "townhall"), None)
        check(hall is not None, f"{tag}: no player hall")
        check(w.hero is not None and w.hero.alive, f"{tag}: no living hero")
        RESULTS.append(dict(mission=i + 1, name=sc["name"], size=[m.w, m.h], tier=sc["diff"],
                            boss=sc["boss"], necro=necro.max_hp if necro else 0,
                            foes=len(w.units_of(ENEMY)), surface=list(got)))
        print(f"  ok    {tag:34} {m.w}x{m.h} {w.diff_id:7} "
              f"boss={sc['boss'] or '-':20} surface={got[0]}x{got[1]}")
    pygame.quit()


def mission1_easiness():
    print("== mission 1 easy-mode contract ==")
    g = mk_game()
    sc = dict(campaign.scenario(0)); sc["_index"] = 0
    g.start_mission(scenario=sc, skip_intro=True)
    w = g.world
    check(w.diff_id == "novice", "m1 not novice")
    check(w.ai.boss_wake_time >= 9999.0, "m1 boss_wake should never fire")
    check(not [u for u in w.units_of(ENEMY) if u.boss], "m1 has a boss")
    check(len([u for u in w.units_of(ENEMY) if not u.boss]) <= 2, "m1 has >2 guards")
    necro = next(b for b in w.buildings_of(ENEMY) if b.bid == "necropolis")
    check(necro.max_hp == 3200, "m1 necro hp")
    # council p-7b4e55d1 bug fixes must be live: hall revive + scheduled waves
    hero = w.hero
    hero.alive = False
    hero.hero_revive_t = 0.05
    for _ in range(30):
        w.update_mission(1 / 30)
    check(w.hero is not None and w.hero.alive, "hero never revives without an Altar")
    w.ai.update(0.01)   # first AI tick applies the per-tier wave schedule
    check(w.ai.next_wave == w.diff.get("first_wave"), "first wave not scheduled from tier")
    print("  ok    novice tier, no boss, 2 guards, necro 3200, hero revives, wave scheduled")
    pygame.quit()


def progression():
    print("== progression save ==")
    before = campaign.load_progress()
    # isolate: a stale best (even 0.0 from an earlier scripted victory) must
    # not mask the assertions below — clear it, test, then restore the file
    trial = json.loads(json.dumps(before))
    trial.setdefault("best", {}).pop("0", None)
    campaign.save_progress(trial)
    campaign.unlock(0)
    check(campaign.is_unlocked(1), "m2 not unlocked after m1")
    check(not campaign.is_unlocked(2), "m3 unlocked too early")
    campaign.record_best(0, 123.0)
    check(abs(campaign.best_time(0) - 123.0) < 0.01, "best time not recorded")
    campaign.record_best(0, 50.0)
    check(abs(campaign.best_time(0) - 50.0) < 0.01, "better time not kept")
    campaign.record_best(0, 900.0)
    check(abs(campaign.best_time(0) - 50.0) < 0.01, "worse time overwrote the best")
    campaign.save_progress(before)
    check(campaign.load_progress() == before, "save not restored")
    print("  ok    unlock chain + best-time semantics round-trip")


def mission1_autoplay_win(cap_s=1800.0):
    print(f"== mission 1 autoplay win (cap {int(cap_s)}s game time) ==")
    g = mk_game(autoplay=True, speed=6.0)
    sc = dict(campaign.scenario(0)); sc["_index"] = 0
    g.start_mission(scenario=sc, skip_intro=True)
    t0 = time.time()
    outcome = "timeout"
    while time.time() - t0 < 420:  # wall-clock guard
        g.update(1 / 60)
        if g.state in ("victory", "defeat"):
            outcome = g.state
            break
        if g.world.time > cap_s:
            break
    w = g.world
    necro = next((b for b in w.buildings_of(ENEMY) if b.bid == "necropolis"), None)
    hall = next((b for b in w.buildings_of(PLAYER) if b.bid in ("townhall", "keep")), None)
    row = dict(outcome=outcome, game_time=round(w.time, 1),
               hall=(f"{int(hall.hp)}/{int(hall.max_hp)}" if hall else "DESTROYED"),
               army=len(w.units_of(PLAYER)), foes=len(w.units_of(ENEMY)),
               kills=w.stats["kills"], losses=w.stats["losses"],
               necro_hp=necro.hp if necro else 0, hero_alive=bool(w.hero and w.hero.alive),
               waves=w.ai.wave, wall=round(time.time() - t0, 1))
    RESULTS.append(dict(mission=1, autoplay=row))
    print("  ", json.dumps(row))
    check(outcome == "victory", f"mission 1 autoplay outcome={outcome} (must be victory — "
                                f"the human called this mission impossible)")
    check(hall is not None, "mission 1 hall was destroyed — 'super easy' must be impossible to lose")
    check(row["waves"] <= 1, f"mission 1 launched {row['waves']} waves — too hot for 'super easy'")
    pygame.quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-win", action="store_true", help="skip the autoplay win check")
    args = ap.parse_args()
    matrix()
    mission1_easiness()
    progression()
    if not args.no_win:
        mission1_autoplay_win()
    out = os.path.join(ROOT, ".council", "evidence", "campaign-probe-01.json")
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(dict(results=RESULTS, fails=FAILS, warns=WARNS), f, indent=1)
        print(f"report: {out}")
    except Exception as exc:
        print(f"report not written: {exc}")
    if FAILS:
        print(f"\nCAMPAIGN PROBE: {len(FAILS)} FAIL")
        for f_ in FAILS:
            print(" -", f_)
        return 1
    print("\nCAMPAIGN PROBE: ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
