"""Grid A* with cliff/ramp rules, path smoothing and nearest-walkable helpers."""
from __future__ import annotations
import math
from .core import MinHeap

DIRS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]


def inb(m, x, y):
    return 0 <= x < m.w and 0 <= y < m.h


def walkable(m, x, y, extra=None):
    if not inb(m, x, y):
        return False
    i = y * m.w + x
    if m.terrain[i] == 3 or m.blocked[i]:
        return False
    if x < 2 or y < 2 or x >= m.w - 2 or y >= m.h - 2:
        return False
    if extra is not None and (x, y) in extra:
        return False
    return True


def can_step(m, ax, ay, bx, by, extra=None):
    if not walkable(m, bx, by, extra):
        return False
    if abs(ax - bx) + abs(ay - by) > 1:
        # no diagonal corner cutting
        if not walkable(m, bx, ay, extra) or not walkable(m, ax, by, extra):
            return False
    i, j = ay * m.w + ax, by * m.w + bx
    if m.height[i] == m.height[j]:
        return True
    return bool(m.ramp[i] or m.ramp[j])


def _octile(ax, ay, bx, by):
    dx, dy = abs(bx - ax), abs(by - ay)
    return (dx + dy) + (1.4142 - 2) * min(dx, dy)


def _base_walk(m):
    """Static passability cache (terrain, trees/mines, map border)."""
    bw = getattr(m, "_base_walk", None)
    if bw is not None and len(bw) == m.w * m.h:
        return bw
    W, H = m.w, m.h
    bw = bytearray(W * H)
    terr = m.terrain
    blocked = m.blocked
    for y in range(2, H - 2):
        row = y * W
        for x in range(2, W - 2):
            i = row + x
            if terr[i] != 3 and not blocked[i]:
                bw[i] = 1
    m._base_walk = bw
    return bw


def find_path(m, start, goal, extra=None, max_nodes=6000):
    """Array-based A* tuned for the 84x84 Ashen Vale grid.

    Cell checks are inlined and the heuristic reuses base passability so the
    common siege/chase case stays in the low-millisecond range.
    """
    if extra is None:
        extra = set()
    W, H = m.w, m.h
    base = _base_walk(m)
    sx, sy = int(start[0]), int(start[1])
    gx, gy = int(goal[0]), int(goal[1])
    def ok(x, y):
        if x < 2 or y < 2 or x >= W - 2 or y >= H - 2:
            return False
        i = y * W + x
        return bool(base[i]) and (x, y) not in extra
    if not ok(sx, sy):
        found = nearest_walkable(m, sx, sy, extra, 4)
        if not found:
            return None
        sx, sy = found
    if not ok(gx, gy):
        found = nearest_walkable(m, gx, gy, extra, 6)
        if not found:
            return None
        gx, gy = found
    if (sx, sy) == (gx, gy):
        return [(sx + 0.5, sy + 0.5)]
    N = W * H
    start_i = sy * W + sx
    goal_i = gy * W + gx
    INF = 1e9
    gscore = [INF] * N
    came = [-1] * N
    gscore[start_i] = 0.0
    height = m.height
    ramp = m.ramp
    # (x, y, cost, dx, dy)
    moves = ((-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
             (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142))
    heap = []
    import heapq as _hq
    _hq.heappush(heap, (_octile(sx, sy, gx, gy), 0, start_i))
    counter = 0
    nodes = 0
    ex = set(extra)
    while heap:
        f, _, ci = _hq.heappop(heap)
        if ci == goal_i:
            path = []
            cur = ci
            while cur != start_i and cur != -1:
                path.append((cur % W, cur // W))
                cur = came[cur]
            path.append((sx, sy))
            path.reverse()
            # strip collinear points (cheap, no LOS scan)
            out = []
            for p in path:
                if len(out) >= 2:
                    ax, ay = out[-2]
                    bx, by = out[-1]
                    if (p[0] - bx) == (bx - ax) and (p[1] - by) == (by - ay):
                        out[-1] = p
                        continue
                out.append(p)
            return [(x + 0.5, y + 0.5) for x, y in out]
        nodes += 1
        if nodes > max_nodes:
            break
        cg = gscore[ci]
        cx = ci % W
        cy = ci // W
        for dx, dy, cost in moves:
            nx = cx + dx
            ny = cy + dy
            if nx < 2 or ny < 2 or nx >= W - 2 or ny >= H - 2:
                continue
            ni = ny * W + nx
            if not base[ni] or (nx, ny) in ex:
                continue
            if dx and dy:
                if not base[cy * W + nx] or not base[ny * W + cx]:
                    continue
                if (nx, cy) in ex or (cx, ny) in ex:
                    continue
            if height[ci] != height[ni] and not (ramp[ci] or ramp[ni]):
                continue
            ng = cg + cost
            if ng < gscore[ni]:
                gscore[ni] = ng
                came[ni] = ci
                counter += 1
                _hq.heappush(heap, (ng + _octile(nx, ny, gx, gy), counter, ni))
    return None


def nearest_walkable(m, x, y, extra=None, radius=6, prefer=None):
    if walkable(m, x, y, extra):
        return (x, y)
    best = None
    bestd = 1e9
    px = prefer[0] if prefer else x
    py = prefer[1] if prefer else y
    for r in range(1, radius + 1):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                nx, ny = x + dx, y + dy
                if walkable(m, nx, ny, extra) and can_step(m, px, py, nx, ny, extra):
                    d = dx * dx + dy * dy
                    if d < bestd:
                        bestd = d
                        best = (nx, ny)
        if best:
            return best
    return best


def line_clear(m, ax, ay, bx, by, extra=None):
    """True if a straight walk between two tile-space points crosses no wall."""
    steps = int(max(abs(bx - ax), abs(by - ay)) * 3) + 1
    px, py = int(ax), int(ay)
    for i in range(1, steps + 1):
        t = i / steps
        x = int(round(ax + (bx - ax) * t))
        y = int(round(ay + (by - ay) * t))
        if (x, y) == (px, py):
            continue
        if not can_step(m, px, py, x, y, extra):
            return False
        px, py = x, y
    return True


def smooth_path(m, path, extra=None):
    if not path or len(path) <= 2:
        return [(x + 0.5, y + 0.5) for x, y in path]
    pts = [(x + 0.5, y + 0.5) for x, y in path]
    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1:
            if line_clear(m, pts[i][0], pts[i][1], pts[j][0], pts[j][1], extra):
                break
            j -= 1
        out.append(pts[j])
        i = j
    return out
