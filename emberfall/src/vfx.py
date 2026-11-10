"""Emberfall VFX — procedural combat & ability effects (council p-a4a11c33).

Human directive that opened this lane: "is the gamea triple A? i dont think so".
This is the VFX half of the answer: hero abilities (Q/W/E/R) cast with real
spell FX, every weapon hit lands with impact feedback, and the boss wake is a
presentation beat instead of a text line.

Pure presentation layer.  Nothing in here reads or writes gameplay state
except polling `hero.shield_t` for the Aegis dome lifetime; no stats, no
timing, no behaviour changes.

Integration contract (kept small on purpose so no other module knows internals):

    vfx.spawn_ember_lance(hero, target)     # world.cmd_cast — Q
    vfx.spawn_aegis(hero)                   # world.cmd_cast — W
    vfx.spawn_consecrate(x, y, radius)      # world.cmd_cast — E
    vfx.spawn_daybreak(hero, x, y, radius)  # world.cmd_cast — R
    vfx.hit(target, source, dtype)          # world.damage  — spark feedback
    vfx.spawn_poof(x, y, h, team)           # world.kill    — death ash
    vfx.spawn_boss_wake(boss)               # ai.check_boss — violet shockwave
    vfx.spawn_dust(x, y, rad)               # app.place_building
    vfx.update(dt)                          # app.Game.update (after world)
    vfx.draw(screen, renderer, camera, t)   # app.Game.draw (world -> UI)
    vfx.reset()                             # start_mission / to_title

Screen mapping replicates render.py's math from public attributes only
(render.py is another lane's file and is never touched):

    screen = renderer.w2s(x, y, h) - (camera.x - SCREEN_W/2, camera.y - SCREEN_H/2)

Effects are drawn as an overlay AFTER the world layer — that is intentional,
spell VFX read on top in RTS convention.  Line/polygon work is added with
BLEND_RGB_ADD (true additive, so fading just adds less light instead of
painting grey); glow sprites are cached SRCALPHA surfaces blitted with a
per-surface alpha ramp.  Every surface is built once and cached: no file I/O,
no new asset files, no per-frame large-surface allocation.
"""
from __future__ import annotations

import math
import random

import pygame

from .core import clamp
from .defs import SCREEN_W, SCREEN_H, TILE_W, TILE_H, ELEV, PLAYER, ENEMY

# ---------------------------------------------------------------- budget/caps
MAX_SPARKS = 128        # hit sparks are constant-fire: hard pool, oldest drops
MAX_MOTES = 110
MAX_POPS = 72
MAX_LANCES = 8
MAX_PILLARS = 4

HALF_W = TILE_W // 2            # 32 px per world unit on the iso x-axis
HALF_H = TILE_H // 2            # 16 px per world unit on the iso y-axis
# a world-space circle of radius r projects to an ellipse with these half axes
RING_HW = HALF_W * math.sqrt(2.0)   # ~45.3 px per world unit
RING_HH = HALF_H * math.sqrt(2.0)   # ~22.6 px per world unit

# ---------------------------------------------------------------- palette
FIRE = (255, 142, 52)        # Ember Lance body
FIRE_HI = (255, 228, 176)    # lance core / impact flash
PHYS = (255, 226, 176)       # white-orange physical hit
VIOLET = (168, 116, 255)     # enemy hits + boss wake
VIOLET_HI = (226, 202, 255)
GOLD = (255, 206, 124)       # Aegis / Consecrate / Daybreak
GOLD_HI = (255, 247, 224)
DUST = (196, 174, 142)       # placement puff / death ash
PIL_GOLD = (255, 226, 158)    # Daybreak light pillars

# ---------------------------------------------------------------- state
_lance = []          # in-flight Ember Lances
_sparks = []         # impact streaks (pooled, capped)
_motes = []          # rising light motes
_pops = []           # flashes / ground glows / expanding rings (timed)
_pillars = []        # Daybreak light pillars
_lance_pending = set()   # uid whose damage delivery is owned by a flying lance
_clock = 0.0
_aegis_t0 = -1e9
_rng = random.Random(0x5EED)


def reset():
    """Forget every live effect — called on mission start and on to_title so
    effects can never leak from one mission into the next."""
    global _clock, _aegis_t0
    _lance.clear()
    _sparks.clear()
    _motes.clear()
    _pops.clear()
    _pillars.clear()
    _lance_pending.clear()
    _clock = 0.0
    _aegis_t0 = -1e9


def _cull_push(lst, item, cap):
    lst.append(item)
    if len(lst) > cap:
        del lst[:len(lst) - cap]


# ---------------------------------------------------------------- cached art
_GLOW = {}        # (color, radius) -> SRCALPHA radial glow
_EGLOW = {}       # (color, radius) -> SRCALPHA iso ground ellipse glow
_GLOW_BASE = {}   # color -> 96x96 glow (scale source)
_EGLOW_BASE = {}  # color -> 96x48 ellipse (scale source)
_PILLAR = {}      # color -> (surface, w, h)
_BLOOM = None     # full-screen Daybreak bloom
_VIGN = None      # full-screen violet edge vignette (boss wake)


def _glow_base(color):
    """96x96 radial glow.  RGB is the flat colour on every pixel (only alpha
    falls off) so smoothscaling never drags transparent black into the edge."""
    s = _GLOW_BASE.get(color)
    if s is None:
        s = pygame.Surface((96, 96), pygame.SRCALPHA)
        c = 47.5
        for yy in range(96):
            dy = (yy - c) / c
            for xx in range(96):
                dx = (xx - c) / c
                r = math.sqrt(dx * dx + dy * dy)
                a = 0 if r >= 1.0 else int(255 * (1.0 - r) ** 2 * (2.0 - (1.0 - r)))
                s.set_at((xx, yy), (color[0], color[1], color[2], a))
        if len(_GLOW_BASE) > 32:
            _GLOW_BASE.clear()
        _GLOW_BASE[color] = s
    return s


def _glow(color, radius):
    """Radial glow sprite, built once per (color, radius) and cached."""
    radius = max(2, int(radius))
    key = (color, radius)
    s = _GLOW.get(key)
    if s is None:
        d = radius * 2
        s = pygame.transform.smoothscale(_glow_base(color), (d, d))
        if len(_GLOW) >= 96:
            _GLOW.clear()
        _GLOW[key] = s
    return s


def _eglow_base(color):
    """96x48 iso ellipse glow (2:1, the ground projection of a world circle)."""
    s = _EGLOW_BASE.get(color)
    if s is None:
        s = pygame.Surface((96, 48), pygame.SRCALPHA)
        cx, cy = 47.5, 23.5
        for yy in range(48):
            dy = (yy - cy) / cy
            for xx in range(96):
                dx = (xx - cx) / cx
                r = math.sqrt(dx * dx + dy * dy)
                a = 0 if r >= 1.0 else int(255 * (1.0 - r) ** 2 * (2.0 - (1.0 - r)))
                s.set_at((xx, yy), (color[0], color[1], color[2], a))
        _EGLOW_BASE[color] = s
    return s


def _eglow(color, radius):
    """Ground-pool glow sized to the world circle of `radius` tiles."""
    radius = float(radius)
    key = (color, round(radius, 2))
    s = _EGLOW.get(key)
    if s is None:
        w = max(10, int(RING_HW * radius) * 2 + 16)
        h = max(6, int(RING_HH * radius) * 2 + 10)
        s = pygame.transform.smoothscale(_eglow_base(color), (w, h))
        if len(_EGLOW) >= 48:
            _EGLOW.clear()
        _EGLOW[key] = s
    return s


def _pillar_sprite(color):
    """Vertical light column: bright at the foot, fading into a fine tip."""
    p = _PILLAR.get(color)
    if p is None:
        w, h = 26, 140
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        for yy in range(h):
            v = (yy + 1.0) / h               # 0 at tip, 1 at foot
            av = int(150 * v ** 1.6 + 90 * v)
            for xx in range(w):
                dx = (xx - (w - 1) / 2.0) / ((w - 1) / 2.0)
                ah = min(255, int(av * max(0.0, 1.0 - dx * dx) ** 1.3))
                if ah:
                    s.set_at((xx, yy), (color[0], color[1], color[2], ah))
        p = (s, w, h)
        _PILLAR[color] = p
    return p


def _bloom_surface():
    """Full-screen Daybreak bloom: bright core, clear edges (alpha capped)."""
    global _BLOOM
    if _BLOOM is None:
        base = pygame.Surface((96, 54), pygame.SRCALPHA)
        cx, cy = 47.5, 26.5
        for yy in range(54):
            dy = (yy - cy) / cy
            for xx in range(96):
                dx = (xx - cx) / cx
                r = math.sqrt(dx * dx * 0.88 + dy * dy * 1.18)
                a = 0 if r >= 1.3 else int(170 * (1.0 - r / 1.3) ** 1.7)
                base.set_at((xx, yy), (GOLD_HI[0], GOLD_HI[1], GOLD_HI[2], a))
        _BLOOM = pygame.transform.smoothscale(base, (SCREEN_W, SCREEN_H))
    return _BLOOM


def _vignette_surface():
    """Full-screen violet edge pulse: dark-bright rim, centre left playable."""
    global _VIGN
    if _VIGN is None:
        base = pygame.Surface((96, 54), pygame.SRCALPHA)
        cx, cy = 47.5, 26.5
        for yy in range(54):
            dy = (yy - cy) / cy
            for xx in range(96):
                dx = (xx - cx) / cx
                r = math.sqrt(dx * dx * 0.88 + dy * dy * 1.18)
                if r <= 0.46:
                    a = 0
                else:
                    t = min(1.0, (r - 0.46) / 0.82)
                    a = int(150 * t * t)
                base.set_at((xx, yy), (VIOLET[0], VIOLET[1], VIOLET[2], a))
        _VIGN = pygame.transform.smoothscale(base, (SCREEN_W, SCREEN_H))
    return _VIGN


# ---------------------------------------------------------------- projection
def _proj(renderer, cam, x, y, h=0.0):
    """render.py w2s minus the camera viewport offset — same pixels, no import."""
    px, py = renderer.w2s(x, y, h)
    return px - cam.x + (SCREEN_W // 2), py - cam.y + (SCREEN_H // 2)


def _screen_delta(dx, dy, dz):
    """Screen offset for a world delta (core.sx/sy differential, no re-proj)."""
    return (dx - dy) * HALF_W, (dx + dy) * HALF_H - dz * ELEV


def _ground_h(renderer, x, y):
    m = getattr(renderer, "map", None)
    if m is None:
        return 0
    return m.height_at(int(x), int(y))


def _on_screen(px, py, margin=420):
    return -margin <= px <= SCREEN_W + margin and -margin <= py <= SCREEN_H + margin


# ---------------------------------------------------------------- spawns
def spawn_ember_lance(hero, target):
    """Q: a fast fire spear from the hero to the target (world.cmd_cast).

    Gameplay still lands its damage instantly, exactly as before; this is the
    presentation — the flight owns the impact, so world.damage's spark is
    suppressed for this one target until the lance lands (see `hit`)."""
    if hero is None or target is None or len(_lance) >= MAX_LANCES:
        return
    bx = by = 0.0
    if getattr(target, "is_building", False):
        bx, by = target.bw / 2, target.bh / 2
    tx, ty = target.x + bx, target.y + by
    d = math.hypot(hero.x - tx, hero.y - ty)
    uid = getattr(target, "uid", None)
    if uid is not None:
        _lance_pending.add(uid)
    _lance.append(dict(
        sx=hero.x, sy=hero.y, sz=hero.height + 1.9,
        tx=tx, ty=ty, tz=getattr(target, "height", 0) + 1.3,
        x=hero.x, y=hero.y, z=hero.height + 1.9,
        tgt=target, uid=uid, t=0.0,
        dur=max(0.12, min(0.42, d / 22.0)),   # ~22 tiles/s: reads as a lance
        trail=[]))


def spawn_aegis(hero):
    """W: golden shell pulse + the dome that lives as long as shield_t."""
    if hero is None:
        return
    global _aegis_t0
    _aegis_t0 = _clock
    x, y = hero.x, hero.y
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=0.0, dur=0.46,
                           color=GOLD, r0=0.3, r1=1.95, w=4), MAX_POPS)
    _cull_push(_pops, dict(kind="flash", x=x, y=y, zoff=1.4, t=0.0, dur=0.3,
                           color=GOLD_HI, r=82, peak=245), MAX_POPS)
    _spawn_motes(x, y, 0.4, 9, GOLD, life=0.9, power=1.0)


def spawn_consecrate(x, y, radius=3.6):
    """E: ground nova — expanding gold rings, rising motes, pooled light."""
    radius = float(radius or 3.6)
    _cull_push(_pops, dict(kind="scorch", x=x, y=y, t=0.0, dur=1.2,
                           color=GOLD, rad=radius, peak=150), MAX_POPS)
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=0.0, dur=0.5,
                           color=GOLD, r0=0.35, r1=radius, w=5), MAX_POPS)
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=-0.13, dur=0.5,
                           color=GOLD_HI, r0=0.2, r1=radius * 0.72, w=2), MAX_POPS)
    _cull_push(_pops, dict(kind="flash", x=x, y=y, zoff=0.5, t=0.0, dur=0.26,
                           color=GOLD_HI, r=76, peak=225), MAX_POPS)
    _spawn_motes(x, y, 0.25, 15, GOLD, life=1.15, power=radius / 3.4)


def spawn_daybreak(hero, x, y, radius=5.0):
    """R: screen-wide climax — bounded bloom, pillar ring, ground nova."""
    radius = float(radius or 5.0)
    _cull_push(_pops, dict(kind="bloom", t=0.0, dur=0.5, peak=196), MAX_POPS)
    _cull_push(_pops, dict(kind="flash", x=x, y=y, zoff=0.7, t=0.0, dur=0.34,
                           color=GOLD_HI, r=170, peak=255), MAX_POPS)
    _cull_push(_pops, dict(kind="scorch", x=x, y=y, t=0.0, dur=1.35,
                           color=GOLD, rad=radius, peak=160), MAX_POPS)
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=0.0, dur=0.55,
                           color=GOLD, r0=0.6, r1=radius, w=6), MAX_POPS)
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=-0.1, dur=0.6,
                           color=GOLD_HI, r0=0.4, r1=radius * 0.68, w=3), MAX_POPS)
    _spawn_motes(x, y, 0.3, 18, GOLD_HI, life=1.2, power=1.5)
    if len(_pillars) >= MAX_PILLARS:
        _pillars.pop(0)
    _pillars.append(dict(x=x, y=y, rad=radius * 0.88, color=PIL_GOLD,
                         t=0.0, dur=1.15, h=192.0, n=12,
                         ang=[i * math.tau / 12 + 0.26 for i in range(12)]))


def spawn_boss_wake(boss):
    """ai.check_boss: violet shockwave, rising motes, screen-edge vignette."""
    if boss is None:
        return
    x = y = 0.0
    if getattr(boss, "is_building", False):
        x, y = boss.x + boss.bw / 2, boss.y + boss.bh / 2
    else:
        x, y = boss.x, boss.y
    _cull_push(_pops, dict(kind="vign", t=0.0, dur=0.9, peak=150), MAX_POPS)
    _cull_push(_pops, dict(kind="flash", x=x, y=y, zoff=1.6, t=0.0, dur=0.4,
                           color=VIOLET_HI, r=132, peak=235), MAX_POPS)
    _cull_push(_pops, dict(kind="scorch", x=x, y=y, t=0.0, dur=1.4,
                           color=VIOLET, rad=11.0, peak=95), MAX_POPS)
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=0.0, dur=1.25,
                           color=VIOLET, r0=0.8, r1=12.5, w=6), MAX_POPS)
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=-0.14, dur=1.0,
                           color=VIOLET_HI, r0=0.5, r1=8.0, w=3), MAX_POPS)
    _spawn_motes(x, y, 0.5, 26, VIOLET, life=1.5, power=1.8)


def spawn_dust(x, y, rad=2.0):
    """app.place_building: the ground puffs where a structure is sited."""
    rad = float(rad or 2.0)
    _cull_push(_pops, dict(kind="scorch", x=x, y=y, t=0.0, dur=0.62,
                           color=DUST, rad=rad, peak=118), MAX_POPS)
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=0.0, dur=0.45,
                           color=DUST, r0=0.25, r1=rad, w=3), MAX_POPS)
    _spawn_motes(x, y, 0.25, 8, DUST, life=0.7, power=0.9)


def spawn_poof(x, y, h, team):
    """world.kill: a quiet ash puff so deaths land instead of just falling."""
    col = VIOLET if team == ENEMY else DUST
    _cull_push(_pops, dict(kind="scorch", x=x, y=y, t=0.0, dur=0.5,
                           color=col, rad=1.15, peak=105), MAX_POPS)
    _cull_push(_pops, dict(kind="flash", x=x, y=y, zoff=0.9, t=0.0, dur=0.16,
                           color=col, r=40, peak=170), MAX_POPS)
    _spawn_motes(x, y, 0.3, 7, col, life=0.8, power=0.8)


def hit(tgt, source=None, dtype="normal"):
    """world.damage: 0.2-0.35s spark/flash on every hit that lands HP damage.

    Colour-coded: physical = white-orange, hero ability magic = fire,
    anything the Hollow Host swings = violet.  Pooled at MAX_SPARKS."""
    if tgt is None or not getattr(tgt, "alive", True):
        return
    uid = getattr(tgt, "uid", None)
    if uid is not None and uid in _lance_pending:
        return                      # the flying lance delivers this impact
    team = getattr(source, "team", None)
    if isinstance(source, dict):
        team = source.get("team")
    if team == ENEMY:
        col = VIOLET
    elif dtype == "magic":
        col = FIRE
    else:
        col = PHYS
    bx, by = tgt.x, tgt.y
    if getattr(tgt, "is_building", False):
        bx += tgt.bw / 2
        by += tgt.bh / 2
    _spawn_sparks(bx, by, getattr(tgt, "height", 0) + 1.1,
                  _rng.randint(5, 9), col, power=3.4, g=13.0)
    _cull_push(_pops, dict(kind="flash", x=bx, y=by, zoff=1.1, t=0.0, dur=0.1,
                           color=col, r=17, peak=255), MAX_POPS)


def _spawn_sparks(x, y, z, n, color, power=2.7, g=13.0):
    for _ in range(n):
        a = _rng.uniform(0.0, math.tau)
        sp = _rng.uniform(0.4, 1.0) * power
        _sparks.append([x, y, z,
                        math.cos(a) * sp, math.sin(a) * sp * 0.7,
                        _rng.uniform(0.5, 1.4) * power, g,
                        _rng.uniform(0.2, 0.35), 0.0, color])
    if len(_sparks) > MAX_SPARKS:
        del _sparks[:len(_sparks) - MAX_SPARKS]


def _spawn_motes(x, y, zoff, n, color, life=1.1, power=1.0):
    """Rising motes: z is stored as an offset above the local ground, so they
    never sink when the terrain under them steps up or down."""
    for _ in range(n):
        a = _rng.uniform(0.0, math.tau)
        rr = _rng.uniform(0.1, 1.0) * power * 1.5
        _motes.append([x + math.cos(a) * rr, y + math.sin(a) * rr, zoff, 0.0,
                       _rng.uniform(-0.5, 0.5), _rng.uniform(-0.5, 0.5),
                       _rng.uniform(1.1, 2.4) * power,
                       life * _rng.uniform(0.7, 1.15), 0.0, color,
                       _rng.uniform(0.75, 1.45)])
    if len(_motes) > MAX_MOTES:
        del _motes[:len(_motes) - MAX_MOTES]


def _lance_impact(p):
    x, y = p["tx"], p["ty"]
    uid = p.get("uid")
    if uid is not None:
        _lance_pending.discard(uid)
    _cull_push(_pops, dict(kind="flash", x=x, y=y, zoff=1.3, t=0.0, dur=0.24,
                           color=FIRE_HI, r=86, peak=255), MAX_POPS)
    _cull_push(_pops, dict(kind="scorch", x=x, y=y - 0.2, t=0.0, dur=0.95,
                           color=FIRE, rad=2.1, peak=145), MAX_POPS)
    _cull_push(_pops, dict(kind="ring", x=x, y=y, t=0.0, dur=0.34,
                           color=FIRE, r0=0.15, r1=2.0, w=4), MAX_POPS)
    _cull_push(_pops, dict(kind="star", x=x, y=y, zoff=1.3, t=0.0, dur=0.3,
                           color=FIRE_HI), MAX_POPS)
    _spawn_sparks(x, y, p["tz"], 16, FIRE, power=5.2, g=11.0)
    # the spear's fire hangs in the air for a beat after it lands
    for q in p["trail"][::3]:
        _spawn_motes(q[0], q[1], 1.0, 1, FIRE, life=0.45, power=0.2)


# ---------------------------------------------------------------- update
def update(dt):
    global _clock
    if dt <= 0.0:
        return
    dt = min(dt, 0.1)
    _clock += dt

    for i in range(len(_lance) - 1, -1, -1):
        p = _lance[i]
        p["t"] += dt
        tgt = p["tgt"]
        if tgt is not None and getattr(tgt, "alive", False):
            if getattr(tgt, "is_building", False):
                p["tx"] = tgt.x + tgt.bw / 2
                p["ty"] = tgt.y + tgt.bh / 2
            else:
                p["tx"], p["ty"] = tgt.x, tgt.y
            p["tz"] = getattr(tgt, "height", p["tz"]) + 1.3
        f = p["t"] / p["dur"]
        p["x"] = p["sx"] + (p["tx"] - p["sx"]) * f
        p["y"] = p["sy"] + (p["ty"] - p["sy"]) * f
        p["z"] = p["sz"] + (p["tz"] - p["sz"]) * f
        tr = p["trail"]
        tr.append([p["x"], p["y"], p["z"], 0.0])
        for q in tr:
            q[3] += dt
        while tr and tr[0][3] > 0.34:
            tr.pop(0)
        if len(tr) > 26:
            del tr[:len(tr) - 26]
        if f >= 1.0:
            _lance.pop(i)
            _lance_impact(p)

    for i in range(len(_sparks) - 1, -1, -1):
        s = _sparks[i]
        s[8] += dt
        if s[8] >= s[7]:
            _sparks.pop(i)
            continue
        s[0] += s[3] * dt
        s[1] += s[4] * dt
        s[2] += s[5] * dt
        s[5] -= s[6] * dt

    for i in range(len(_motes) - 1, -1, -1):
        m = _motes[i]
        m[8] += dt
        if m[8] >= m[7]:
            _motes.pop(i)
            continue
        m[0] += m[4] * dt
        m[1] += m[5] * dt
        m[3] += m[6] * dt       # rise, kept as an offset above the ground

    for i in range(len(_pops) - 1, -1, -1):
        p = _pops[i]
        p["t"] += dt
        if p["t"] >= p["dur"]:
            _pops.pop(i)

    for i in range(len(_pillars) - 1, -1, -1):
        p = _pillars[i]
        p["t"] += dt
        if p["t"] >= p["dur"]:
            _pillars.pop(i)


# ---------------------------------------------------------------- draw
def draw(screen, renderer, camera, world_time=0.0):
    if renderer is None or camera is None:
        return

    # --- ground pools (below rings, motes, everything else) -------------
    for p in _pops:
        if p["kind"] != "scorch":
            continue
        px, py = _proj(renderer, camera, p["x"], p["y"], _ground_h(renderer, p["x"], p["y"]))
        if not _on_screen(px, py, 700):
            continue
        e = clamp(p["t"] / p["dur"], 0.0, 1.0)
        if p["t"] < 0.0:
            continue
        a = int(p["peak"] * (1.0 - e) ** 1.5)
        if a <= 1:
            continue
        g = _eglow(p["color"], p["rad"])
        g.set_alpha(a)
        screen.blit(g, (int(px - g.get_width() // 2), int(py - g.get_height() // 2)))

    # --- expanding ground rings ----------------------------------------
    for p in _pops:
        if p["kind"] != "ring" or p["t"] < 0.0:
            continue
        px, py = _proj(renderer, camera, p["x"], p["y"], _ground_h(renderer, p["x"], p["y"]))
        if not _on_screen(px, py, 860):
            continue
        e = clamp(p["t"] / p["dur"], 0.0, 1.0)
        k = 1.0 - (1.0 - e) ** 2
        r = p["r0"] + (p["r1"] - p["r0"]) * k
        # saturated fade (never toward black): pygame-ce's ellipse/line take no
        # blend flag, so the tail must stay a *lit colour* or it reads muddy
        f = 0.36 + 0.64 * (1.0 - e) ** 0.9
        c = p["color"]
        col = (int(c[0] * f), int(c[1] * f), int(c[2] * f))
        hw = int(RING_HW * r)
        hh = int(RING_HH * r)
        if hw < 3 or hh < 2:
            continue
        # a world circle projects to an axis-aligned 2:1 ellipse on screen,
        # which is exactly what draw.ellipse inscribes in this rect
        rect = pygame.Rect(int(px) - hw, int(py) - hh, hw * 2, hh * 2)
        pygame.draw.ellipse(screen, col, rect, p["w"])
        if p["w"] >= 3 and hw > 8 and hh > 4:
            f2 = min(1.0, f * 1.4)
            col2 = (int(c[0] * f2), int(c[1] * f2), int(c[2] * f2))
            pygame.draw.ellipse(screen, col2,
                                pygame.Rect(int(px) - hw + 3, int(py) - hh + 2,
                                            (hw - 3) * 2, (hh - 2) * 2), 1)

    # --- rising motes ---------------------------------------------------
    for m in _motes:
        e = 1.0 - m[8] / m[7]
        if e <= 0.0:
            continue
        px, py = _proj(renderer, camera, m[0], m[1],
                       _ground_h(renderer, m[0], m[1]) + m[2] + m[3])
        if not _on_screen(px, py, 120):
            continue
        g = _glow(m[9], 14)
        g.set_alpha(int(215 * e * e))
        screen.blit(g, (int(px - 7), int(py - 7)))

    # --- impact streaks (shrinking, saturated fade; hot head stays additive) ---
    for s in _sparks:
        e = 1.0 - s[8] / s[7]
        px, py = _proj(renderer, camera, s[0], s[1], s[2])
        if not _on_screen(px, py, 90):
            continue
        hx, hy = _screen_delta(s[3] * 0.20 * e, s[4] * 0.20 * e, s[5] * 0.20 * e)
        c = s[9]
        f = 0.36 + 0.64 * e * e
        col = (int(c[0] * f), int(c[1] * f), int(c[2] * f))
        wdt = 3 if e > 0.65 else (2 if e > 0.35 else 1)
        pygame.draw.line(screen, col, (px, py), (px - hx, py - hy), wdt)
        if e > 0.5:
            f2 = e * e
            pygame.draw.circle(screen,
                               (int(c[0] * f2), int(c[1] * f2), int(c[2] * f2)),
                               (int(px), int(py)), 2, 0, pygame.BLEND_RGB_ADD)

    # --- Ember Lance flight ---------------------------------------------
    if _lance:
        trail_glow = _glow(FIRE, 17)
        head_glow = _glow(FIRE_HI, 27)
        for p in _lance:
            for q in p["trail"]:
                e = 1.0 - q[3] / 0.3
                px, py = _proj(renderer, camera, q[0], q[1], q[2])
                if not _on_screen(px, py, 90):
                    continue
                trail_glow.set_alpha(int(190 * e * e))
                screen.blit(trail_glow, (int(px - 17), int(py - 17)))
            px, py = _proj(renderer, camera, p["x"], p["y"], p["z"])
            if not _on_screen(px, py, 90):
                continue
            head_glow.set_alpha(255)
            screen.blit(head_glow, (int(px - 27), int(py - 27)))
            pygame.draw.circle(screen, (255, 250, 236), (int(px), int(py)), 3,
                               0, pygame.BLEND_RGB_ADD)
            pygame.draw.circle(screen, (255, 176, 84), (int(px), int(py)), 6,
                               2, pygame.BLEND_RGB_ADD)

    # --- lance starburst (additive spokes) --------------------------------
    for p in _pops:
        if p["kind"] != "star" or p["t"] < 0.0:
            continue
        e = p["t"] / p["dur"]
        if e >= 1.0:
            continue
        px, py = _proj(renderer, camera, p["x"], p["y"],
                       _ground_h(renderer, p["x"], p["y"]) + p["zoff"])
        if not _on_screen(px, py, 300):
            continue
        c = p["color"]
        fade = (1.0 - e) ** 1.3
        grow = 0.45 + 0.8 * e
        for i in range(8):
            a = i * (math.tau / 8.0) + 0.42
            dx = math.cos(a)
            dy = math.sin(a) * 0.58          # squashed to sit in the iso plane
            for j in range(1, 5):
                f = fade * (1.0 - (j - 1) * 0.17)
                if f <= 0.05:
                    continue
                dist = (8 + j * 11) * grow
                col = (int(c[0] * f), int(c[1] * f), int(c[2] * f))
                pygame.draw.circle(screen, col,
                                   (int(px + dx * dist), int(py + dy * dist)),
                                   3 if j == 1 else 2, 0, pygame.BLEND_RGB_ADD)

    # --- flashes ---------------------------------------------------------
    for p in _pops:
        if p["kind"] != "flash" or p["t"] < 0.0:
            continue
        e = clamp(p["t"] / p["dur"], 0.0, 1.0)
        px, py = _proj(renderer, camera, p["x"], p["y"],
                       _ground_h(renderer, p["x"], p["y"]) + p["zoff"])
        if not _on_screen(px, py, 400):
            continue
        a = int(p["peak"] * (1.0 - e) ** 1.6)
        if a <= 1:
            continue
        g = _glow(p["color"], p["r"])
        g.set_alpha(a)
        screen.blit(g, (int(px - g.get_width() // 2), int(py - g.get_height() // 2)))

    # --- Aegis dome (polls hero.shield_t, fades at either end) ----------
    world = getattr(renderer, "game", None)
    hero = getattr(world, "hero", None) if world is not None else None
    if hero is not None and getattr(hero, "alive", False) and hero.shield_t > 0:
        rise = clamp((_clock - _aegis_t0) / 0.28, 0.0, 1.0)
        fall = clamp(hero.shield_t / 1.1, 0.0, 1.0)
        pulse = 0.5 + 0.5 * math.sin((world_time or _clock) * 5.0)
        a = int(170 * rise * fall * (0.74 + 0.26 * pulse))
        px, py = _proj(renderer, camera, hero.x, hero.y, hero.height + 1.5)
        if _on_screen(px, py, 300):
            g = _glow(GOLD, 80)
            g.set_alpha(a)
            screen.blit(g, (int(px - 80), int(py - 80)))
            g2 = _glow(GOLD_HI, 40)
            g2.set_alpha(int(a * 0.55))
            screen.blit(g2, (int(px - 40), int(py - 40)))
            f = 0.42 + 0.58 * (a / 255.0)
            c = GOLD
            col = (int(c[0] * f), int(c[1] * f), int(c[2] * f))
            hw = int(RING_HW * 1.3)
            hh = int(RING_HH * 1.3)
            pygame.draw.ellipse(screen, col,
                                pygame.Rect(int(px) - hw, int(py) - hh,
                                            hw * 2, hh * 2), 3)

    # --- Daybreak pillars -------------------------------------------------
    for p in _pillars:
        base = p["t"] / p["dur"]
        if base >= 1.0:
            continue
        fade = int(248 * (1.0 - base) ** 1.4)
        if fade <= 2:
            continue
        px, py = _proj(renderer, camera, p["x"], p["y"], _ground_h(renderer, p["x"], p["y"]))
        if not _on_screen(px, py, 700):
            continue
        surf, pw, ph = _pillar_sprite(p["color"])
        surf.set_alpha(fade)
        angs = p["ang"]
        for i in range(p["n"]):
            pr = clamp((p["t"] - i * 0.05) / 0.5, 0.0, 1.0)
            if pr <= 0.0:
                continue
            k = 1.0 - (1.0 - pr) ** 2
            cur = max(8, int(p["h"] * k * (0.8 + 0.2 * math.sin(i * 2.3))))
            a = angs[i]
            ox, oy = _screen_delta(math.cos(a) * p["rad"],
                                   math.sin(a) * p["rad"], 0.0)
            ix, iy = px + ox, py + oy
            if not _on_screen(ix, iy, 220):
                continue
            ih = min(cur, ph)
            screen.blit(surf, (int(ix - pw / 2), int(iy - ih)),
                        (0, ph - ih, pw, ih))

    # --- screen-space climax layers (Daybreak bloom / boss vignette) -----
    for p in _pops:
        k = p["kind"]
        if k == "bloom":
            e = clamp(p["t"] / p["dur"], 0.0, 1.0)
            a = int(p["peak"] * (1.0 - e) ** 1.7)
            if a > 2:
                s = _bloom_surface()
                s.set_alpha(a)
                screen.blit(s, (0, 0))
        elif k == "vign":
            e = clamp(p["t"] / p["dur"], 0.0, 1.0)
            a = int(p["peak"] * (1.0 - e) ** 1.5)
            if a > 2:
                s = _vignette_surface()
                s.set_alpha(a)
                screen.blit(s, (0, 0))
