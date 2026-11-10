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


def _mirror_pt(v, size):
    """Mirror a continuous coordinate across a `size`-tile axis.

    The tile the point stands in becomes its mirrored tile (t -> size-1-t)
    and the in-tile fraction flips (f -> 1-f); a point exactly on a tile
    corner (f == 0) stays an integer so int(v) is still the mirrored tile.
    """
    t = math.floor(v)
    f = v - t
    return float(size - 1 - t) + (1.0 - f if f else 0.0)


def _flood(m, start):
    """8-dir can_step flood from start — the same rules pocket sealing uses."""
    from collections import deque
    from .pathfind import can_step
    W, H = m.w, m.h
    seen = bytearray(W * H)
    if not (0 <= start[0] < W and 0 <= start[1] < H):
        return seen
    seen[start[1] * W + start[0]] = 1
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if not m.inb(nx, ny):
                continue
            ni = ny * W + nx
            if seen[ni]:
                continue
            if can_step(m, x, y, nx, ny):
                seen[ni] = 1
                q.append((nx, ny))
    return seen


def _open_key_routes(m, spawn, route_targets):
    """Carve a way out of any key-point pocket on a scaled layout.

    The fixed 84x84 Ashen Vale layout keeps every mine, camp, start and route
    target connected on its own; a bigger map re-rolls the forest noise and
    can grow a closed tree ring around (for example) the south-east mine
    clearing — pocket-sealing would then delete the mine's whole clearing.
    Before validation floods, walk each key point's pocket across removable
    blocks (trees/rocks on passable ground, never mine cells or water) until
    it touches the reachable component, then clear that path. No-op when
    everything is already connected, which is the case on the default map.
    Returns the number of pockets that needed carving.
    """
    from collections import deque
    from .pathfind import walkable, nearest_walkable
    W, H = m.w, m.h
    mine_cells = set()
    for mm in m.mines:
        mine_cells |= {(mm["x"] + ox, mm["y"] + oy)
                       for oy in (-1, 0) for ox in (-1, 0)}
    points = [spawn]
    points += [t for t, _ in route_targets]
    points += [(mm["x"], mm["y"]) for mm in m.mines]
    points += [(c["x"], c["y"]) for c in m.camps]
    for side in m.starts.values():
        points += [(b["x"], b["y"]) for b in side["buildings"]]

    seen = _flood(m, spawn)
    carved = 0
    for pt in points:
        anchor = nearest_walkable(m, pt[0], pt[1], None, 6)
        if anchor is None or seen[anchor[1] * W + anchor[0]]:
            continue
        # 4-dir walk from the pocket; allowed to enter removable blocked tiles
        # to break out of the ring, never stepping where height forbids it
        parent = {anchor: None}
        q = deque([anchor])
        hit = None
        while q and hit is None:
            x, y = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (2 <= nx < W - 2 and 2 <= ny < H - 2):
                    continue
                if (nx, ny) in parent:
                    continue
                ni = ny * W + nx
                hi, hj = m.height[y * W + x], m.height[ni]
                if hi != hj and not (m.ramp[y * W + x] or m.ramp[ni]):
                    continue
                if seen[ni]:
                    parent[(nx, ny)] = (x, y)
                    hit = (nx, ny)
                    break
                removable = (m.blocked[ni] and m.terrain[ni] != WATER
                             and (nx, ny) not in mine_cells)
                if not walkable(m, nx, ny) and not removable:
                    continue
                parent[(nx, ny)] = (x, y)
                q.append((nx, ny))
        if hit is None:
            continue
        # clear the carved path (same tree teardown the camps use)
        cur = hit
        while cur is not None:
            cx, cy = cur
            ni = cy * W + cx
            if m.blocked[ni]:
                m.blocked[ni] = 0
                if (cx, cy) in m.wood:
                    for pr in m.tree_props.get((cx, cy), []):
                        pr["gone"] = True
                    m.wood.pop((cx, cy), None)
                    m.tree_props.pop((cx, cy), None)
            cur = parent[cur]
        carved += 1
        seen = _flood(m, spawn)
    return carved


def _flip_map(m, variant, spawn, route_targets):
    """Mirror the finished, validated layout (variant: flipx/flipy/flipxy).

    Mirroring is a tile bijection, so adjacency and the pocket sealing done
    by the caller carry over by construction; a cheap connectivity sanity
    check runs on the mirrored result anyway. Returns the list of problems
    that check found (empty when everything is as it should be).
    """
    if variant == "flipx":
        fx, fy = True, False
    elif variant == "flipy":
        fx, fy = False, True
    elif variant == "flipxy":
        fx, fy = True, True
    else:
        raise ValueError(f"unknown map variant {variant!r}")
    from .defs import BUILDINGS
    from collections import deque
    from .pathfind import can_step, walkable, nearest_walkable
    W, H = m.w, m.h

    # ---- tile arrays (row-major i = y * W + x) -------------------------
    for name in ("terrain", "height", "blocked", "ramp", "ford", "road", "clear"):
        arr = getattr(m, name)
        if fx:
            for y in range(H):
                s = y * W
                arr[s:s + W] = arr[s:s + W][::-1]
        if fy:
            rows = bytearray(W * H)
            for y in range(H):
                rows[(H - 1 - y) * W:(H - y) * W] = arr[y * W:(y + 1) * W]
            arr[:] = rows
    # static-walk cache built by the validation above is now stale
    m._base_walk = None

    # ---- coordinate-bearing structures --------------------------------
    for p in m.props:
        if fx:
            p["x"] = _mirror_pt(p["x"], W)
        if fy:
            p["y"] = _mirror_pt(p["y"], H)

    def mir_key(key):
        x, y = key
        return ((W - 1 - x) if fx else x, (H - 1 - y) if fy else y)

    m.wood = {mir_key(k): v for k, v in m.wood.items()}
    m.tree_props = {mir_key(k): v for k, v in m.tree_props.items()}
    for mine in m.mines:
        # a mine occupies tiles (x-1..x, y-1..y), so its mirrored origin is
        # size - coord: 12 -> 72 maps cells {11,12} onto {71,72} exactly
        if fx:
            mine["x"] = W - mine["x"]
        if fy:
            mine["y"] = H - mine["y"]
    for camp in m.camps:
        cx, cy = camp["x"], camp["y"]
        ncx = (W - 1 - cx) if fx else cx
        ncy = (H - 1 - cy) if fy else cy
        for u in camp["units"]:
            ox, oy = u["x"] - cx, u["y"] - cy   # offsets mirror by negation
            if fx:
                u["x"] = ncx - ox
            if fy:
                u["y"] = ncy - oy
        camp["x"], camp["y"] = ncx, ncy
    for side in m.starts.values():
        for b in side["buildings"]:
            bw, bh = BUILDINGS[b["type"]]["size"]
            # footprint x..x+bw-1 mirrors to size-x-bw .. size-1-x, so the
            # mirrored hall lands exactly on its mirrored cleared footprint
            if fx:
                b["x"] = W - b["x"] - bw
            if fy:
                b["y"] = H - b["y"] - bh
        side["units"] = [(ut,
                          _mirror_pt(ux, W) if fx else ux,
                          _mirror_pt(uy, H) if fy else uy)
                         for (ut, ux, uy) in side["units"]]
        camx, camy = side["camera"]
        side["camera"] = ((W - 1 - camx) if fx else camx,
                          (H - 1 - camy) if fy else camy)

    # ---- cheap connectivity sanity check on the mirrored result --------
    problems = []
    sx0, sy0 = spawn
    start = ((W - 1 - sx0) if fx else sx0, (H - 1 - sy0) if fy else sy0)
    seen = bytearray(W * H)
    seen[start[1] * W + start[0]] = 1
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx2, ny2 = x + dx, y + dy
            if not m.inb(nx2, ny2):
                continue
            ni = ny2 * W + nx2
            if seen[ni]:
                continue
            if can_step(m, x, y, nx2, ny2):
                seen[ni] = 1
                q.append((nx2, ny2))
    for (tx, ty), label in route_targets:
        gx = (W - 1 - tx) if fx else tx
        gy = (H - 1 - ty) if fy else ty
        # raw targets may sit on a mine cell like they do on the stock map;
        # resolve to the walkable tile find_path would home in on (radius 6)
        hit = nearest_walkable(m, gx, gy, None, 6)
        if hit is None or not seen[hit[1] * W + hit[0]]:
            problems.append(f"post-{variant}: no path to mirrored {label}")
    for tag, side in m.starts.items():
        for (ut, ux, uy) in side["units"]:
            if not walkable(m, int(ux), int(uy)):
                problems.append(f"post-{variant}: start unit {ut} ({tag}) not walkable")
        for b in side["buildings"]:
            bw, bh = BUILDINGS[b["type"]]["size"]
            if not all(walkable(m, xx, yy)
                       for yy in range(b["y"], b["y"] + bh)
                       for xx in range(b["x"], b["x"] + bw)):
                problems.append(f"post-{variant}: {tag} {b['type']} footprint not walkable")
    return problems


def generate_map(seed=20261109, difficulty="knight", w=None, h=None, variant=None,
                 name=None):
    w = MAP_W if w is None else int(w)
    h = MAP_H if h is None else int(h)
    m = GameMap(w=w, h=h)
    if name is not None:
        m.name = name
    rng = Rng(seed)
    W, H = m.w, m.h

    # Every layout anchor below is authored on the 84x84 Ashen Vale grid and
    # mapped through X()/Y() so other sizes keep the same proportions:
    #   xscaled = round(x * w / 84), yscaled = round(y * h / 84).
    # At the default size kx == ky == 1.0 EXACTLY (84/84.0 in IEEE-754), so
    # round(x * 1.0) == x for every int literal and x * 1.0 == x for every
    # float: the default output is byte-identical to the fixed 84x84 layout.
    kx = W / 84.0
    ky = H / 84.0
    nx = 84.0 / W          # inverse factors: tile -> base space (noise inputs)
    ny = 84.0 / H

    def X(x):
        return round(x * kx)

    def Y(y):
        return round(y * ky)

    def river_y(x):
        # base curve is authored for 84 wide/high: normalize x, scale y
        return _river_y(x * nx) * ky

    hall_x, hall_y = X(PLAYER_HALL[0]), Y(PLAYER_HALL[1])

    # ---- river with two fords ----------------------------------------
    fords = tuple(fx * kx for fx in (23.0, 61.0))
    for x in range(W):
        cy = river_y(x)
        width = 3.1 + 1.2 * fbm((x * nx) * 0.12, 3.3, seed)
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
    pl_x0, pl_x1, pl_y0, pl_y1 = X(56), X(79), Y(6), Y(26)
    for y in range(pl_y0, pl_y1):
        for x in range(pl_x0, pl_x1):
            i = m.i(x, y)
            if m.terrain[i] != WATER:
                m.height[i] = 2
                if m.terrain[i] == GRASS:
                    m.terrain[i] = ASH if x > pl_x0 and y < Y(24) else MOSS
    # central mesa
    ms_x0, ms_y0, ms_x1, ms_y1 = X(MESA[0]), Y(MESA[1]), X(MESA[2]), Y(MESA[3])
    for y in range(ms_y0, ms_y1 + 1):
        for x in range(ms_x0, ms_x1 + 1):
            i = m.i(x, y)
            if m.terrain[i] != WATER:
                m.height[i] = 2
                m.terrain[i] = ROCK if (x in (ms_x0, ms_x1) or y in (ms_y0, ms_y1)) else GRASS
    # south-east ridge for silhouette
    rg_x0, rg_x1, rg_y0, rg_y1 = X(60), X(79), Y(66), Y(78)
    for y in range(rg_y0, rg_y1):
        for x in range(rg_x0, rg_x1):
            if (x - rg_x0) + (Y(77) - y) < X(8):
                i = m.i(x, y)
                if m.terrain[i] != WATER:
                    m.height[i] = 2
                    m.terrain[i] = ROCK

    # ramps: enemy plateau approach
    ex, ey = X(ENEMY_RAMP[0]), Y(ENEMY_RAMP[1])
    for y in range(ey, ey + 4):          # 4 rows deep: thickness stays in tiles
        for x in range(ex, ex + 5):      # 5 wide: thickness stays in tiles
            i = m.i(x, y)
            m.height[i] = 1
            m.terrain[i] = DIRT
            m.ramp[i] = 1
            m.clear[i] = 1
    # lip row sits on the plateau's last row (y25 == ey-1 on the default map)
    m.ramp[m.i(ex, ey - 1)] = 1
    m.ramp[m.i(ex + 2, ey - 1)] = 1
    m.ramp[m.i(ex + 4, ey - 1)] = 1
    # eastern goat path: a narrow, unbuildable flank onto the plateau
    gp_x0, gp_x1, gp_y0, gp_y1 = X(73), X(76), Y(24), Y(30)
    for y in range(gp_y0, gp_y1):
        for x in range(gp_x0, gp_x1):
            i = m.i(x, y)
            m.height[i] = 1
            m.terrain[i] = DIRT
            m.ramp[i] = 1
            m.clear[i] = 1
    for x in range(gp_x0, gp_x1):
        m.ramp[m.i(x, gp_y0)] = 1
    # mesa ramp (south side): starts right below the mesa's scaled south edge
    # so lip and plateau stay adjacent at every size (my == 36 at 84x84)
    mx, my = X(MESA_RAMP[0]), ms_y1 + 1
    for y in range(my, my + 2):
        for x in range(mx, mx + 3):
            i = m.i(x, y)
            m.height[i] = 1
            m.terrain[i] = DIRT
            m.ramp[i] = 1
            m.clear[i] = 1
    for x in range(mx, mx + 3):
        m.ramp[m.i(x, ms_y1)] = 1

    # ---- terrain texture patches -------------------------------------
    for y in range(H):
        for x in range(W):
            i = m.i(x, y)
            if m.terrain[i] in (WATER, SAND, ROCK) or m.height[i] >= 2:
                continue
            n = fbm((x * nx) * 0.09, (y * ny) * 0.09, seed + 5, 4)
            if n > 0.62:
                m.terrain[i] = DIRT
            elif n < 0.36:
                m.terrain[i] = MOSS
            elif m.terrain[i] == SAND:
                m.terrain[i] = SAND

    # ---- roads (dirt tracks that read the routes) --------------------
    routes = [
        [(X(24), Y(76)), (X(23), Y(66)), (X(23), Y(54)), (X(23), Y(47)),
         (X(26), Y(42)), (X(30), Y(38)), (X(30), Y(30)), (X(36), Y(26)),
         (X(46), Y(26)), (X(56), Y(28)), (X(61), Y(30)), (X(64), Y(28)),
         (X(64), Y(24)), (X(62), Y(21))],
        [(X(28), Y(72)), (X(40), Y(66)), (X(52), Y(60)), (X(60), Y(52)),
         (X(61), Y(44)), (X(61), Y(38)), (X(64), Y(32)), (X(64), Y(28))],
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
                            if m.height[m.i(tx, ty)] == 2 and (tx, ty) not in ((X(64), Y(24)),):
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

    add_mine(X(12), Y(62), 12000, PLAYER)      # home mine
    add_mine(X(74), Y(8), 20000, ENEMY)        # enemy reserve
    add_mine(X(13), Y(30), 10000, NEUTRAL)     # west ford
    add_mine(X(37), Y(32), 11000, NEUTRAL)     # mesa
    add_mine(X(70), Y(58), 10000, NEUTRAL)     # south-east
    add_mine(X(44), Y(54), 10000, NEUTRAL)     # south-central expansion

    # ---- clearings ---------------------------------------------------
    def clear_area(cx, cy, r):
        for y in range(int(cy - r), int(cy + r) + 1):
            for x in range(int(cx - r), int(cx + r) + 1):
                if not m.inb(x, y):
                    continue
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    m.clear[m.i(x, y)] = 1

    clear_area(X(20), Y(68), 11)
    clear_area(X(23), Y(74), 6)
    clear_area(X(61), Y(18), 15)
    clear_area(X(64), Y(30), 5)
    clear_area(X(74), Y(28), 4)
    clear_area(X(74), Y(8), 3)
    clear_area(X(44), Y(54), 4)
    for mine in m.mines:
        clear_area(mine["x"], mine["y"], 4)

    # player hall footprint
    for y in range(hall_y - 1, hall_y + 5):
        for x in range(hall_x - 1, hall_x + 5):
            if m.inb(x, y):
                m.clear[m.i(x, y)] = 1
                m.set_terr(x, y, DIRT if m.terr(x, y) != WATER else WATER)

    # ---- forests -----------------------------------------------------
    zones = [
        (X(3), Y(46), X(20), Y(80), 0.62), (X(6), Y(72), X(48), Y(81), 0.5),
        (X(4), Y(6), X(28), Y(30), 0.55), (X(66), Y(38), X(80), Y(74), 0.58),
        (X(30), Y(5), X(54), Y(22), 0.42), (X(22), Y(50), X(34), Y(64), 0.18),
        (X(46), Y(48), X(58), Y(62), 0.16), (X(10), Y(34), X(20), Y(46), 0.2),
    ]
    for (x0, y0, x1, y1, density) in zones:
        for y in range(y0, min(y1, H - 1) + 1):
            for x in range(x0, min(x1, W - 1) + 1):
                i = m.i(x, y)
                if m.clear[i] or m.blocked[i] or m.terrain[i] in (WATER, SAND, ROCK):
                    continue
                if m.height[i] > 1:
                    continue
                if rng() < density * (0.55 + 0.9 * fbm((x * nx) * 0.2, (y * ny) * 0.2, seed + 11)):
                    kind = "pine" if (y < Y(40) or x < X(30)) and rng() < 0.62 else "tree"
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
    for y in range(Y(9), Y(25)):
        for x in range(X(56), X(75)):
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
    for (x, y, kind, sc) in [(X(31), Y(45), "ruin", 1.0), (X(65), Y(48), "ruin", 0.9),
                             (X(47), Y(37), "arch", 1.0)]:
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
    m.add_prop("fire", 16.5 * kx, 72.6 * ky, scale=0.85, block=False, glow=True)
    m.add_prop("fire", 58.0 * kx, 21.0 * ky, scale=1.0, block=False, glow=True)
    m.add_prop("fire", 63.0 * kx, 30.0 * ky, scale=0.7, block=False, glow=True)
    for fx in fords:
        for k in range(-2, 3):
            yy = river_y(fx) + k * 1.2
            m.add_prop("stone", fx + 0.5 + (k % 2) * 0.3, yy,
                       variant=(k + 3) % 3, scale=0.8, block=False)
    # goat-path marker
    m.add_prop("fire", 74.0 * kx, 29.0 * ky, scale=0.55, block=False, glow=True)

    # ---- camps / creeps ---------------------------------------------
    def camp(cx, cy, units, name):
        camp = dict(x=cx, y=cy, units=[], name=name, cleared=False, bounty=0)
        for (ut, ox, oy) in units:
            ux, uy = cx + ox, cy + oy
            camp["units"].append(dict(type=ut, x=ux, y=uy))
        m.camps.append(camp)
        clear_area(cx, cy, 3)
        # open the camp clearing for real: clear_area only marks the map, so remove
        # blocking trees/rocks and their props as well (Thornwood sat in a tree shaft).
        for yy in range(int(cy) - 3, int(cy) + 4):
            for xx in range(int(cx) - 3, int(cx) + 4):
                if not m.inb(xx, yy):
                    continue
                i = m.i(xx, yy)
                if m.blocked[i] and (xx, yy) not in [(mm["x"], mm["y"]) for mm in []]:
                    if (xx, yy) in m.wood:
                        for pr in m.tree_props.get((xx, yy), []):
                            pr["gone"] = True
                        m.wood.pop((xx, yy), None)
                        m.tree_props.pop((xx, yy), None)
                    m.blocked[i] = 0
        m.add_prop("fire", cx + 0.5, cy + 0.5, scale=0.55, block=False, glow=True)
        m.add_prop("bone", cx + 0.2, cy + 0.9, variant=0, scale=0.8)
        return camp

    camp(X(39), Y(32), [("goblin-brute", 0, 0), ("goblin", 1, 1), ("goblin", -1, 1), ("goblin", 1, -1)],
         "Mesa Warren")
    camp(X(74), Y(63), [("goblin", 0, 0), ("goblin", 2, 0), ("goblin", 1, -2)], "Thornwood Warren")
    camp(X(13), Y(27), [("goblin", 0, 0), ("goblin", -2, 1)], "Westford Warren")
    camp(X(48), Y(58), [("goblin", 0, 0), ("goblin", -2, 0)], "Crossroads Warren")

    # ---- starts ------------------------------------------------------
    player_buildings = [dict(type="townhall", x=hall_x, y=hall_y),
                        dict(type="farm", x=X(13), y=Y(70))]
    player_units = [
        ("hero", 24.5 * kx, 71.5 * ky), ("worker", 22.0 * kx, 72.5 * ky),
        ("worker", 23.5 * kx, 73.0 * ky),
        ("worker", 25.5 * kx, 73.0 * ky), ("worker", 26.5 * kx, 72.0 * ky),
        ("worker", 20.5 * kx, 73.5 * ky), ("worker", 28.0 * kx, 72.5 * ky),
        ("footman", 21.0 * kx, 70.0 * ky), ("footman", 27.0 * kx, 70.5 * ky),
        ("archer", 29.0 * kx, 69.0 * ky),
    ]
    enemy_buildings = [
        dict(type="necropolis", x=X(58), y=Y(12)),
        dict(type="ziggurat", x=X(54), y=Y(8)), dict(type="ziggurat", x=X(64), y=Y(8)),
        dict(type="crypt", x=X(54), y=Y(18)), dict(type="slaughterhouse", x=X(65), y=Y(18)),
        dict(type="temple", x=X(68), y=Y(10)), dict(type="altarhollow", x=X(60), y=Y(20)),
        dict(type="bonetower", x=X(54), y=Y(23)), dict(type="bonetower", x=X(67), y=Y(23)),
    ]
    enemy_units = [
        ("hollow-king", 61.5 * kx, 19.0 * ky),
        ("ghoul", 57.5 * kx, 21.5 * ky), ("ghoul", 64.5 * kx, 21.5 * ky),
        ("fiend", 66.5 * kx, 12.5 * ky), ("necromancer", 63.0 * kx, 19.0 * ky),
        ("abomination", 62.0 * kx, 23.0 * ky),
    ]
    m.starts = {
        PLAYER: dict(buildings=player_buildings, units=player_units,
                     camera=(X(24), Y(69))),
        ENEMY: dict(buildings=enemy_buildings, units=enemy_units,
                    camera=(X(61), Y(18))),
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
    spawn = (X(24), Y(72))
    route_targets = [((X(61), Y(24)), "enemy ramp"),
                     ((X(39), Y(35)), "mesa camp"),
                     ((X(13), Y(34)), "west mine"),
                     ((X(70), Y(57)), "southeast mine")]
    # scaled layouts can wall a key point behind a tree ring; break it open
    # before validation so sealing only ever removes border silhouette
    _open_key_routes(m, spawn, route_targets)
    # bigger grids need a bigger A* budget than the 84x84 tuning (the default
    # budget still succeeds on the stock map, so its result cannot change)
    budget = max(6000, 4 * m.w * m.h)
    for target, label in route_targets:
        if not find_path(m, spawn, target, max_nodes=budget):
            problems.append(f"no path player spawn -> {label}")
    # Seal unreachable walkable pockets so the map has no dead rooms and the
    # audit can prove connectivity. Pockets are visually dressed with rocks.
    from collections import deque
    from .pathfind import can_step, walkable
    start = spawn
    seen = bytearray(m.w * m.h)
    q = deque([start])
    seen[start[1] * m.w + start[0]] = 1
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = x + dx, y + dy
            if not m.inb(nx, ny):
                continue
            ni = ny * m.w + nx
            if seen[ni]:
                continue
            if can_step(m, x, y, nx, ny):
                seen[ni] = 1
                q.append((nx, ny))
    sealed = 0
    for y in range(2, m.h - 2):
        for x in range(2, m.w - 2):
            i = y * m.w + x
            if seen[i] or not walkable(m, x, y):
                continue
            m.blocked[i] = 1
            sealed += 1
    if sealed:
        problems.append(f"sealed {sealed} unreachable pocket tiles")
    # ---- optional mirror variant (after validation) -------------------
    # Mirroring is a tile bijection, so adjacency — and therefore the sealing
    # above — carries over by construction; re-check it cheaply anyway.
    if variant is not None:
        problems.extend(_flip_map(m, variant, spawn, route_targets))
    m.problems = problems
    m.seed = seed
    return m
