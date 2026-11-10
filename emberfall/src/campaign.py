"""EMBERFALL campaign — nine scenario missions, bosses, saved progression.

Council p-3f9a1c02 (decision: scenario-campaign). Conditions that shaped it:
  * scenario sizes capped at 128 tiles (renderer bakes one full-map surface,
    cost is quadratic — see .council/evidence/survey-architecture.md);
  * mission 1 keeps today's Ashen Vale layout character (only scaled 84->96)
    so a revert to the single-map game stays one commit;
  * every scenario is DATA: size, seed, layout flip, difficulty tier, boss,
    guard intensity, objectives, lore — no per-mission code branches.

Progression lives in ~/.emberfall/campaign.json (falling back to the game
directory, then to nothing — the campaign never crashes over a save file).
"""
from __future__ import annotations

import json
import os

from .defs import ENEMY, PLAYER, UNITS

# --------------------------------------------------------------------------
# scenario table
# --------------------------------------------------------------------------
# keys:
#   name     mission title
#   w, h     map size in tiles (84 = the classic Ashen Vale size; all mission
#            maps are bigger, per the human's directive, capped at 128)
#   seed     mapgen seed (different skeleton per mission)
#   variant  None | "flipx" | "flipy" | "flipxy" layout mirror
#   diff     DIFFICULTY tier for this mission (p-7b4e55d1: mission 1 = novice)
#   boss     unit id of the mission boss, or None (mission 1 has none)
#   boss_wake seconds before the boss stirs on his own (ai.check_boss)
#   guards   "quiet" | "guarded" | "host" — how much standing army guards the
#            Necropolis (mission 1 is quiet: this is part of "super easy")
#   necro_hp Necropolis hitpoints (mission 1's falls fast so the first win is
#            short and certain)
#   lore     briefing text, main/bonus objective text, hint
SCENARIOS = [
    dict(
        id="m1", name="The First Ember", w=96, h=96, seed=20261110,
        variant=None, diff="novice", boss=None, boss_wake=9999.0,
        guards="quiet", necro_hp=3200,
        lore=("The vale is quiet on your first watch. Four workers, one hall, "
              "and no enemy worth the name — the Hollow Host has not yet noticed "
              "you. Build, gather, learn the feel of steel, then walk east and "
              "burn their shrine. Nothing here is meant to kill you."),
        main="Destroy the undefended Necropolis.",
        bonus="Break the goblin warrens for practice coin.",
        hint="Right-click to move · A attack-move · B build · QWER hero",
    ),
    dict(
        id="m2", name="The Blackford Crossing", w=96, h=96, seed=20262087,
        variant="flipx", diff="novice", boss="boss-grave-warden",
        boss_wake=720.0, guards="quiet", necro_hp=4200,
        lore=("Blackford runs cold and the Host has set a warden on the far "
              "bank. He is slow to anger and slower to think, but he is the "
              "first of them that will not simply fall over. Cross the water, "
              "take the fight to the shrine, and make him answer for it."),
        main="Destroy the Necropolis; the Grave Warden will rise to stop you.",
        bonus="Hold both fords — the crossing is worth more dead than taken.",
        hint="Waves arrive later here. Expand greedily.",
    ),
    dict(
        id="m3", name="The Sunken Chapel", w=104, h=104, seed=20263064,
        variant="flipy", diff="squire", boss="boss-crypt-herald",
        boss_wake=660.0, guards="guarded", necro_hp=4600,
        lore=("A chapel drowned in ash, and something in it learned to preach. "
              "The Crypt Herald sends his first converts across the vale at "
              "dusk; you will hear them before you see them. Raise walls where "
              "the ground allows and answer the sermon with steel."),
        main="Destroy the Necropolis and silence the Crypt Herald.",
        bonus="Clear the warrens before the second wave musters.",
        hint="First real wave pressure — keep a footman on the ramp.",
    ),
    dict(
        id="m4", name="Warren of Bones", w=104, h=104, seed=20264041,
        variant="flipxy", diff="squire", boss="boss-bone-tyrant",
        boss_wake=620.0, guards="guarded", necro_hp=5000,
        lore=("Every gully here opens into a warren, and the Bone Tyrant "
              "hunts between them. He is armoured like a gate and hits like "
              "one. Take the mines first — a war of attrition favors whoever "
              "is still being paid."),
        main="Destroy the Necropolis; break the Bone Tyrant in the warrens.",
        bonus="Take all four gold mines before the Tyrant wakes.",
        hint="Expansion wins this one. Towers on the chokepoints.",
    ),
    dict(
        id="m5", name="The Ashen Fields", w=112, h=112, seed=20265018,
        variant=None, diff="squire", boss="boss-ash-lich",
        boss_wake=580.0, guards="host", necro_hp=5400,
        lore=("Where the farms burned, the ash holds no footprints — except "
              "his. The Ash Lich walks the fields with a retinue that does not "
              "need to breathe. Your own ranks will start to thin at the third "
              "wave; the question is what you built behind them."),
        main="Destroy the Necropolis before the Ash Lich burns the field clean.",
        bonus="Keep your army above twenty through the third wave.",
        hint="Priests pay for themselves here. Keep Aldric alive.",
    ),
    dict(
        id="m6", name="Slaughter Row", w=112, h=112, seed=20265995,
        variant="flipx", diff="knight", boss="boss-slaughter-king",
        boss_wake=540.0, guards="host", necro_hp=5800,
        lore=("Row upon row of pens, and the thing that keeps them. The "
              "Slaughter King feeds the Host from the front of every wave, "
              "and on Knight's watch the waves come early. Trade blows, not "
              "armies — you cannot outlive him in the open."),
        main="Destroy the Necropolis; the Slaughter King defends it in person.",
        bonus="Trade efficiently: fewer losses than kills.",
        hint="Waves come fast — fight at your own gates, not theirs.",
    ),
    dict(
        id="m7", name="The Frost March", w=120, h=120, seed=20266972,
        variant="flipy", diff="knight", boss="boss-frost-sovereign",
        boss_wake=500.0, guards="host", necro_hp=6200,
        lore=("North of the ridge the vale is a grave with a sky over it. The "
              "Frost Sovereign marches his dead in step and his cold slows "
              "everything it touches. You have room here — most of it wrong. "
              "Use the size; he will come to you either way."),
        main="Destroy the Necropolis and unmake the Frost Sovereign.",
        bonus="Win without losing your Hall.",
        hint="The biggest map yet — wall the passes, strike once.",
    ),
    dict(
        id="m8", name="Before the Hollow Throne", w=120, h=120, seed=20267949,
        variant="flipxy", diff="knight", boss="boss-hollow-champion",
        boss_wake=460.0, guards="host", necro_hp=6600,
        lore=("His champion stands between you and the crown: a knight of the "
              "old Emberhold, taken whole and turned. He remembers every "
              "formation you have beaten him with. Break him, and the throne "
              "room is only stone and bone."),
        main="Destroy the Necropolis; the Hollow Champion awaits your army.",
        bonus="Bring Aldric to level 8 before the gates.",
        hint="Boss fights are won with numbers and QWER, not duels.",
    ),
    dict(
        id="m9", name="The Hollow Crown", w=128, h=128, seed=20268926,
        variant=None, diff="warlord", boss="hollow-king",
        boss_wake=420.0, guards="host", necro_hp=7200,
        lore=("The whole vale, corner to corner, and at the far end of it the "
              "crownless thing that wears it. Warlord's watch: his income is "
              "yours doubled, his waves early, his King unafraid. End it. "
              "Break the Necropolis and the Hollow King with it."),
        main="Destroy the Necropolis and kill the Hollow King.",
        bonus="Finish with Aldric alive.",
        hint="The war you came for. Spend everything.",
    ),
]

BOSS_IDS = tuple(s["boss"] for s in SCENARIOS if s["boss"])


# --------------------------------------------------------------------------
# progression save
# --------------------------------------------------------------------------
_DEFAULT = {"unlocked": 1, "best": {}}


def _save_candidates():
    out = []
    try:
        out.append(os.path.join(os.path.expanduser("~"), ".emberfall", "campaign.json"))
    except Exception:
        pass
    out.append(os.path.join(os.getcwd(), ".emberfall_campaign.json"))
    return out


def load_progress():
    """Best-effort read; any failure means fresh progress, never a crash."""
    for p in _save_candidates():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("unlocked", 1)
                data.setdefault("best", {})
                return data
        except Exception:
            continue
    return dict(_DEFAULT)


def save_progress(prog):
    for p in _save_candidates():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(prog, f, indent=1)
            return True
        except Exception:
            continue
    return False


def unlocked_count():
    """How many missions are playable (1-based count)."""
    n = load_progress().get("unlocked", 1)
    return max(1, min(int(n), len(SCENARIOS)))


def is_unlocked(index0):
    return index0 < unlocked_count()


def unlock(index0):
    """Unlock mission index0+1 (0-based). Returns True when progress changed."""
    prog = load_progress()
    need = index0 + 2  # missions playable count required
    if int(prog.get("unlocked", 1)) < need and need <= len(SCENARIOS):
        prog["unlocked"] = need
        save_progress(prog)
        return True
    return False


def record_best(index0, seconds):
    prog = load_progress()
    best = prog.setdefault("best", {})
    key = str(index0)
    if key not in best or float(seconds) < float(best[key]):
        best[key] = float(seconds)
        save_progress(prog)
        return True
    return False


def best_time(index0):
    try:
        return float(load_progress().get("best", {}).get(str(index0)))
    except Exception:
        return 0.0


def scenario(index0):
    return SCENARIOS[index0]


def count():
    return len(SCENARIOS)


# --------------------------------------------------------------------------
# per-mission world shaping
# --------------------------------------------------------------------------
_GUARD_KEEP = {"quiet": 2, "guarded": 99, "host": 99}


def _is_boss(kind):
    d = UNITS.get(kind) or {}
    return bool(d.get("boss"))


def apply_scenario(sc, m):
    """Shape the generated map's starting armies for this mission.

    Runs BEFORE World() is built. Kept deliberately data-only: boss swap,
    guard-count clamp, player extras — never invented coordinates (the
    generator already proved those tiles walkable).
    """
    en = m.starts.get(ENEMY)
    pl = m.starts.get(PLAYER)
    if en:
        units = list(en.get("units") or [])
        # strip every existing boss (Ashen Vale ships a hollow-king by default)
        units = [u for u in units if not (isinstance(u, (tuple, list)) and _is_boss(u[0]))]
        # clamp the standing guard force FIRST — the mission boss must never be
        # cut by the guard cap (it used to be appended before this clamp)
        keep = _GUARD_KEEP.get(sc.get("guards", "guarded"), 99)
        if keep < len(units):
            units = units[:keep]
        boss = sc.get("boss")
        if boss:
            # seat the mission boss beside the Necropolis, where the default
            # king stood (that tile is cleared by mapgen's footprint pass)
            necro = next((b for b in en.get("buildings") or []
                          if b.get("type") == "necropolis"), None)
            bx = (necro["x"] + 3.5) if necro else m.w * 0.73
            by = (necro["y"] + 7.0) if necro else m.h * 0.21
            units.append((boss, bx, by))
        en["units"] = units
    if pl:
        # every mission starts with the buffed Hearth Guard (mapgen start:
        # hall, farm, six workers, two footmen, an archer) — mission 1 keeps
        # its extra breathing room, later missions lose one footman so the
        # ramp is felt.
        if sc.get("guards") == "host":
            footmen = [i for i, u in enumerate(pl.get("units") or []) if u[0] == "footman"]
            if footmen:
                pl["units"].pop(footmen[-1])
    return m


def apply_to_world(sc, w):
    """Post-World() tweaks: Necropolis hitpoints + boss wake schedule."""
    try:
        hp = int(sc.get("necro_hp") or 0)
        if hp > 0:
            for b in w.buildings_of(ENEMY):
                if b.bid == "necropolis":
                    b.max_hp = hp
                    b.hp = hp
    except Exception:
        pass
    if w.ai is not None:
        w.ai.boss_wake_time = float(sc.get("boss_wake", 560.0))
    return w
