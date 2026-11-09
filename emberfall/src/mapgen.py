"""Handcrafted Ashen Vale map: river, fords, cliffs, forests, mines, camps."""
from __future__ import annotations
import math
from .defs import MAP_W, MAP_H, PLAYER, ENEMY, NEUTRAL
from .core import Rng, fbm, clamp
from .pathfind import find_path, walkable, nearest_walkable

GRASS, DIRT, ROCK, WATER, SAND, ASH, BLOOD, MOSS = range(8)
TERRAIN_NAMES = ["grass", "dirt", "rock", "water", "sand", "ash", "blood", "moss"]

# Layout anchors
PLAYER_HALL = (18, 66)       # top-left tile of 4x4
PLAYER_SPAWN = (24.0, 71.0)
ENEMY_BASE = (61.0, 18.0)
ENEMY_RAMP = (62, 26)        # 5 wide, y 26..29
MESA = (34, 29, 41, 35)
MESA_RAMP = (36, 36)         # 3 wide, y 36..37


class GameMap:
    def __init__(self, w=MAP_W, h=MAP_H):
        self.w, self.h = w, h
        n = w * h
        self.terrain = bytearray([GRASS]) * n
        self.height = bytearray([1]) * n
        self.blocked = bytearray(n)
        self.ramp = bytearray(n)
        self.ford = bytearray(n)
        self.road = bytearray(n)
        self.clear = bytearray(n)
        self.wood = {}
        self.props = []
        self.tree_props = {}
        self.mines = []
        self.camps = []
        self.starts = {}
        self.name = "Ashen Vale"

    # -- indexing -------------------------------------------------------
    def i(self, x, y):
        return int(y) * self.w + int(x)

    def inb(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def height_at(self, x, y):
        if not self.inb(x, y):
            return 3
        return self.height[self.i(x, y)]

    def terr(self, x, y):
        if not self.inb(x, y):
            return ROCK
        return self.terrain[self.i(x, y)]

    def is_water(self, x, y):
        return self.terr(x, y) == WATER

    def set_terr(self, x, y, t, force=False):
        if not self.inb(x, y):
            return
        i = self.i(x, y)
        if force or self.terrain[i] != WATER:
            self.terrain[i] = t

    def add_prop(self, kind, x, y, variant=0, scale=1.0, block=False, **kw):
        p = dict(kind=kind, x=float(x), y=float(y), variant=variant,
                 scale=scale, block=block, phase=(x * 7.13 + y * 3.7) % 6.283)
        p.update(kw)
        self.props.append(p)
        return p


def _river_y(x):
    return 41.0 + 5.2 * math.sin(x * 0.075) + 2.4 * math.sin(x * 0.21 + 1.9)


def _dist_to_rect(x, y, r):
    dx = max(r[0] - x, 0, x - r[2])
    dy = max(r[1] - y, 0, y - r[3])
    return math.hypot(dx, dy)


def generate_map(seed=20261109, difficulty="knight"):
    m = GameMap()
    rng = Rng(seed)
    W, H = m.w, m.h

    # ---- river with two fords ----------------------------------------
    fords = (23.0, 61.0)
    for x in range(W):
        cy = _river_y(x)
        width = 3.1 + 1.2 * fbm(x * 0.12, 3.3, seed)
        for y in range(H):
            d = abs(y - cy)
            near_ford = any(abs(x - fx) <= 2.6 for fx in fords)
            if d <= width and not near_ford:
                m.terrain[m.i(x, y)] = WATER
                m.height[m.i(x, y)] = 0
            elif d <= width + 1.8:
                m.terrain[m.i(x, y)] = SAND
                if near_ford:
                    m.ford[m.i(x, y)] = 1

    # ---- heights / cliffs -------------------------------------------
    # highland ring around the battlefield
    for y in range(H):
        for x in range(W):
            i = m.i(x, y)
            if x < 4 or y < 4 or x > W - 5 or y > H - 5:
                m.height[i] = 3 if (x < 2 or y < 2 or x > W - 3 or y > H - 3) else 2
                if m.terrain[i] != WATER:
                    m.terrain[i] = ROCK
            elif x < 8 or y < 8 or x > W - 9 or y > H - 9:
                if m.terrain[i] != WATER:
                    m.height[i] = 2
                    m.terrain[i] = ROCK
    # enemy plateau (north-east)
    for y in range(6, 26):
        for x in range(56, 79):
            i = m.i(x, y)
            if m.terrain[i] != WATER:
                m.height[i] = 2
                if m.terrain[i] == GRASS:
                    m.terrain[i] = ASH if x > 56 and y < 24 else MOSS
    # central mesa
    for y in range(MESA[1], MESA[3] + 1):
        for x in range(MESA[0], MESA[2] + 1):
            i = m.i(x, y)
            if m.terrain[i] != WATER:
                m.height[i] = 2
                m.terrain[i] = ROCK if (x in (MESA[0], MESA[2]) or y in (MESA[1], MESA[3])) else GRASS
    # south-east ridge for silhouette
    for y in range(66, 78):
        for x in range(60, 79):
            if (x - 60) + (77 - y) < 8:
                i = m.i(x, y)
                if m.terrain[i] != WATER:
                    m.height[i] = 2
                    m.terrain[i] = ROCK

    # ramps: enemy plateau approach
    ex, ey = ENEMY_RAMP
    for y in range(ey, ey + 4):
        for x in range(ex, ex + 5):
            i = m.i(x, y)
            m.height[i] = 1
            m.terrain[i] = DIRT
            m.ramp[i] = 1
            m.clear[i] = 1
    m.ramp[m.i(ex, 25)] = 1
    m.ramp[m.i(ex + 2, 25)] = 1
    m.ramp[m.i(ex + 4, 25)] = 1
    # eastern goat path: a narrow, unbuildable flank onto the plateau
    for y in range(24, 30):
        for x in range(73, 76):
            i = m.i(x, y)
            m.height[i] = 1
            m.terrain[i] = DIRT
            m.ramp[i] = 1
            m.clear[i] = 1
    for x in range(73, 76):
        m.ramp[m.i(x, 24)] = 1
    # mesa ramp (south side)
    mx, my = MESA_RAMP
    for y in range(my, my + 2):
        for x in range(mx, mx + 3):
            i = m.i(x, y)
            m.height[i] = 1
            m.terrain[i] = DIRT
            m.ramp[i] = 1
            m.clear[i] = 1
    for x in range(mx, mx + 3):
        m.ramp[m.i(x, MESA[3])] = 1

    # ---- terrain texture patches -------------------------------------
    for y in range(W):
        for x in range(W):
            i = m.i(x, y)
            if m.terrain[i] in (WATER, SAND, ROCK) or m.height[i] >= 2:
                continue
            n = fbm(x * 0.09, y * 0.09, seed + 5, 4)
            if n > 0.62:
                m.terrain[i] = DIRT
            elif n < 0.36:
                m.terrain[i] = MOSS
            elif m.terrain[i] == SAND:
                m.terrain[i] = SAND

    # ---- roads (dirt tracks that read the routes) --------------------
    routes = [
        [(24, 76), (23, 66), (23, 54), (23, 47), (26, 42), (30, 38),
         (30, 30), (36, 26), (46, 26), (56, 28), (61, 30), (64, 28), (64, 24), (62, 21)],
        [(28, 72), (40, 66), (52, 60), (60, 52), (61, 44), (61, 38), (64, 32), (64, 28)],
    ]
    for route in routes:
        for k in range(len(route) - 1):
            ax, ay = route[k]
            bx, by = route[k + 1]
            steps = int(max(abs(bx - ax), abs(by - ay)) * 3) + 1
            for s in range(steps + 1):
                t = s / steps
                x = ax + (bx - ax) * t
                y = ay + (by - ay) * t
                for oy in (-1, 0, 1):
                    for ox in (-1, 0, 1):
                        if abs(ox) + abs(oy) > 1:
                            continue
                        tx, ty = int(x) + ox, int(y) + oy
                        if m.inb(tx, ty):
                            m.road[m.i(tx, ty)] = 1
                            m.clear[m.i(tx, ty)] = 1
                            if m.terrain[m.i(tx, ty)] in (GRASS, MOSS, DIRT):
                                m.terrain[m.i(tx, ty)] = DIRT
                            if m.height[m.i(tx, ty)] == 2 and (tx, ty) not in ((64, 24),):
                                pass

    # ---- mines -------------------------------------------------------
    def add_mine(x, y, gold, owner=NEUTRAL):
        mine = dict(x=x, y=y, gold=gold, max_gold=gold, owner=owner,
                    workers=[], neutral=owner == NEUTRAL)
        m.mines.append(mine)
        for oy in (-1, 0):
            for ox in (-1, 0):
                i = m.i(x + ox, y + oy)
                m.blocked[i] = 1
                m.clear[i] = 1
        for oy in range(-3, 3):
            for ox in range(-3, 3):
                if m.inb(x + ox, y + oy):
                    m.clear[m.i(x + ox, y + oy)] = 1
        m.add_prop("mine", x - 0.5, y - 0.5, gold=gold, owner=owner)
        return mine

    add_mine(12, 62, 12000, PLAYER)      # home mine
    add_mine(74, 8, 20000, ENEMY)       # enemy reserve
    add_mine(13, 30, 10000, NEUTRAL)    # west ford
    add_mine(37, 32, 11000, NEUTRAL)    # mesa
    add_mine(70, 58, 10000, NEUTRAL)    # south-east
    add_mine(44, 54, 10000, NEUTRAL)    # south-central expansion

    # ---- clearings ---------------------------------------------------
    def clear_area(cx, cy, r):
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                if not m.inb(x, y):
                    continue
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    m.clear[m.i(x, y)] = 1

    clear_area(20, 68, 11)
    clear_area(23, 74, 6)
    clear_area(61, 18, 15)
    clear_area(64, 30, 5)
    clear_area(74, 28, 4)
    clear_area(74, 8, 3)
    clear_area(44, 54, 4)
    for mine in m.mines:
        clear_area(mine["x"], mine["y"], 4)

    # player hall footprint
    for y in range(PLAYER_HALL[1] - 1, PLAYER_HALL[1] + 5):
        for x in range(PLAYER_HALL[0] - 1, PLAYER_HALL[0] + 5):
            if m.inb(x, y):
                m.clear[m.i(x, y)] = 1
                m.set_terr(x, y, DIRT if m.terr(x, y) != WATER else WATER)

    # ---- forests -----------------------------------------------------
    zones = [
        (3, 46, 20, 80, 0.62), (6, 72, 48, 81, 0.5), (4, 6, 28, 30, 0.55),
        (66, 38, 80, 74, 0.58), (30, 5, 54, 22, 0.42), (22, 50, 34, 64, 0.18),
        (46, 48, 58, 62, 0.16), (10, 34, 20, 46, 0.2),
    ]
    for (x0, y0, x1, y1, density) in zones:
        for y in range(y0, min(y1, H - 1) + 1):
            for x in range(x0, min(x1, W - 1) + 1):
                i = m.i(x, y)
                if m.clear[i] or m.blocked[i] or m.terrain[i] in (WATER, SAND, ROCK):
                    continue
                if m.height[i] > 1:
                    continue
                if rng() < density * (0.55 + 0.9 * fbm(x * 0.2, y * 0.2, seed + 11)):
                    kind = "pine" if (y < 40 or x < 30) and rng() < 0.62 else "tree"
                    if rng() < 0.12:
                        kind = "dead"
                    scale = rng.uniform(0.82, 1.18)
                    p = m.add_prop(kind, x + rng.uniform(0.15, 0.85), y + rng.uniform(0.1, 0.8),
                                   variant=rng.randrange(4), scale=scale, block=True,
                                   sway=rng.uniform(0.7, 1.4), wood=100)
                    m.blocked[i] = 1
                    m.wood[(x, y)] = 100
                    m.tree_props.setdefault((x, y), []).append(p)
                    if rng() < 0.35:
                        m.add_prop("bush" if kind != "dead" else "stump",
                                   x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                                   variant=rng.randrange(3), scale=rng.uniform(0.7, 1.0),
                                   block=False, sway=1.1)
                    if rng() < 0.25:
                        m.add_prop("grass", x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                                   variant=rng.randrange(3), scale=rng.uniform(0.8, 1.2), block=False)

    # ---- enemy base ground dress ------------------------------------
    for y in range(9, 25):
        for x in range(56, 75):
            i = m.i(x, y)
            if m.blocked[i] or m.terrain[i] == WATER:
                continue
            if rng() < 0.1:
                m.set_terr(x, y, ASH)
            if rng() < 0.035:
                m.add_prop("bone", x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                           variant=rng.randrange(3), scale=rng.uniform(0.6, 1.0), block=False)
            elif rng() < 0.03:
                m.add_prop("rock", x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                           variant=rng.randrange(3), scale=rng.uniform(0.5, 0.9), block=True)

    # ---- decorative scatter (non-blocking) ---------------------------
    for y in range(3, H - 3):
        for x in range(3, W - 3):
            i = m.i(x, y)
            if m.blocked[i] or m.terrain[i] in (WATER, ROCK) or m.road[i]:
                continue
            r = rng()
            if r < 0.028:
                m.add_prop("bush", x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                           variant=rng.randrange(3), scale=rng.uniform(0.6, 1.0), sway=1.0)
            elif r < 0.085:
                m.add_prop("grass", x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                           variant=rng.randrange(3), scale=rng.uniform(0.7, 1.2))
            elif r < 0.105:
                m.add_prop("flowers", x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                           variant=rng.randrange(3), scale=rng.uniform(0.7, 1.1))
            elif r < 0.115:
                m.add_prop("rock", x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                           variant=rng.randrange(3), scale=rng.uniform(0.45, 0.8))
            elif r < 0.12:
                m.add_prop("bone", x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                           variant=rng.randrange(3), scale=rng.uniform(0.6, 0.9))

    # ruins: two old watch-stones + a broken arch
    for (x, y, kind, sc) in [(31, 45, "ruin", 1.0), (65, 48, "ruin", 0.9), (47, 37, "arch", 1.0)]:
        if m.inb(x, y):
            m.clear[m.i(x, y)] = 1
            m.add_prop(kind, x + 0.5, y + 0.5, scale=sc, block=True)
            m.blocked[m.i(x, y)] = 1

    # border highland dressing (impassable, pure silhouette)
    for y in range(2, H - 2):
        for x in range(2, W - 2):
            i = m.i(x, y)
            if m.height[i] < 2 or m.terrain[i] == WATER:
                continue
            if m.clear[i]:
                continue
            if rng() < 0.11:
                m.add_prop("pine" if rng() < 0.7 else "rock",
                           x + rng.uniform(0.1, 0.9), y + rng.uniform(0.1, 0.9),
                           variant=rng.randrange(4), scale=rng.uniform(0.8, 1.25),
                           block=False, sway=rng.uniform(0.6, 1.2))

    # campfires at home + enemy gate
    m.add_prop("fire", 22.5, 69.0, scale=1.0, block=False, glow=True)
    m.add_prop("fire", 58.0, 21.0, scale=1.0, block=False, glow=True)
    m.add_prop("fire", 63.0, 30.0, scale=0.7, block=False, glow=True)
    for fx in fords:
        for k in range(-2, 3):
            yy = _river_y(fx) + k * 1.2
            m.add_prop("stone", fx + 0.5 + (k % 2) * 0.3, yy,
                       variant=(k + 3) % 3, scale=0.8, block=False)
    # goat-path marker
    m.add_prop("fire", 74.0, 29.0, scale=0.55, block=False, glow=True)

    # ---- camps / creeps ---------------------------------------------
    def camp(cx, cy, units, name):
        camp = dict(x=cx, y=cy, units=[], name=name, cleared=False, bounty=0)
        for (ut, ox, oy) in units:
            ux, uy = cx + ox, cy + oy
            camp["units"].append(dict(type=ut, x=ux, y=uy))
        m.camps.append(camp)
        clear_area(cx, cy, 3)
        m.add_prop("fire", cx + 0.5, cy + 0.5, scale=0.55, block=False, glow=True)
        m.add_prop("bone", cx + 0.2, cy + 0.9, variant=0, scale=0.8)
        return camp

    camp(39, 32, [("goblin-brute", 0, 0), ("goblin", 1, 1), ("goblin", -1, 1), ("goblin", 1, -1)],
         "Mesa Warren")
    camp(74, 63, [("goblin", 0, 0), ("goblin", 2, 0), ("goblin", 1, -2)], "Thornwood Warren")
    camp(13, 27, [("goblin", 0, 0), ("goblin", -2, 1)], "Westford Warren")
    camp(48, 58, [("goblin", 0, 0), ("goblin", -2, 0)], "Crossroads Warren")

    # ---- starts ------------------------------------------------------
    player_buildings = [dict(type="townhall", x=PLAYER_HALL[0], y=PLAYER_HALL[1])]
    player_units = [
        ("hero", 24.5, 71.5), ("worker", 22.0, 72.5), ("worker", 23.5, 73.0),
        ("worker", 25.5, 73.0), ("worker", 26.5, 72.0),
        ("footman", 21.0, 70.0), ("footman", 27.0, 70.5),
    ]
    enemy_buildings = [
        dict(type="necropolis", x=58, y=12),
        dict(type="ziggurat", x=54, y=8), dict(type="ziggurat", x=64, y=8),
        dict(type="crypt", x=54, y=18), dict(type="slaughterhouse", x=65, y=18),
        dict(type="temple", x=68, y=10), dict(type="altarhollow", x=60, y=20),
        dict(type="bonetower", x=54, y=23), dict(type="bonetower", x=67, y=23),
    ]
    enemy_units = [
        ("hollow-king", 61.5, 19.0),
        ("ghoul", 57.5, 21.5), ("ghoul", 64.5, 21.5), ("ghoul", 58.5, 17.0),
        ("ghoul", 66.0, 16.0), ("fiend", 57.0, 19.5), ("fiend", 66.5, 12.5),
        ("necromancer", 63.0, 19.0), ("abomination", 62.0, 23.0),
    ]
    m.starts = {
        PLAYER: dict(buildings=player_buildings, units=player_units, camera=(24, 69)),
        ENEMY: dict(buildings=enemy_buildings, units=enemy_units, camera=(61, 18)),
    }

    # clear the exact footprints of start buildings above
    for side in (PLAYER, ENEMY):
        for b in m.starts[side]["buildings"]:
            from .defs import BUILDINGS
            bw, bh = BUILDINGS[b["type"]]["size"]
            for y in range(b["y"] - 1, b["y"] + bh + 1):
                for x in range(b["x"] - 1, b["x"] + bw + 1):
                    if m.inb(x, y):
                        m.clear[m.i(x, y)] = 1
                        if m.blocked[m.i(x, y)]:
                            m.blocked[m.i(x, y)] = 0
                            m.wood.pop((x, y), None)
                        if m.terrain[m.i(x, y)] == WATER:
                            # never allow a building footprint in the river
                            pass

    # remove trees/props that ended up inside cleared building footprints
    def drop_props_in(rect):
        x0, y0, x1, y1 = rect
        keep = []
        for p in m.props:
            if x0 <= int(p["x"]) <= x1 and y0 <= int(p["y"]) <= y1 and p["kind"] in (
                    "tree", "pine", "dead", "bush", "grass", "flowers", "stump", "rock", "bone"):
                if p.get("block"):
                    m.blocked[m.i(int(p["x"]), int(p["y"]))] = 0
                    m.wood.pop((int(p["x"]), int(p["y"])), None)
                continue
            keep.append(p)
        m.props = keep

    from .defs import BUILDINGS
    for side in (PLAYER, ENEMY):
        for b in m.starts[side]["buildings"]:
            bw, bh = BUILDINGS[b["type"]]["size"]
            drop_props_in((b["x"] - 1, b["y"] - 1, b["x"] + bw, b["y"] + bh))

    # unblock any start footprint tile that lost its tree
    for side in (PLAYER, ENEMY):
        for b in m.starts[side]["buildings"]:
            bw, bh = BUILDINGS[b["type"]]["size"]
            for y in range(b["y"], b["y"] + bh):
                for x in range(b["x"], b["x"] + bw):
                    if m.inb(x, y):
                        m.blocked[m.i(x, y)] = 0

    # ---- validate routes --------------------------------------------
    from .pathfind import find_path
    problems = []
    route = find_path(m, (24, 72), (61, 24))
    if not route:
        problems.append("no path player spawn -> enemy ramp")
    route2 = find_path(m, (24, 72), (39, 35))
    if not route2:
        problems.append("no path player spawn -> mesa camp")
    route3 = find_path(m, (24, 72), (13, 34))
    if not route3:
        problems.append("no path player spawn -> west mine")
    route4 = find_path(m, (24, 72), (70, 57))
    if not route4:
        problems.append("no path player spawn -> southeast mine")
    m.problems = problems
    m.seed = seed
    return m
