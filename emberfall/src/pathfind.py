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


def find_path(m, start, goal, extra=None, max_nodes=9000):
    sx, sy = int(start[0]), int(start[1])
    gx, gy = int(goal[0]), int(goal[1])
    if not walkable(m, sx, sy, extra):
        found = nearest_walkable(m, sx, sy, extra, 4)
        if not found:
            return None
        sx, sy = found
    if not walkable(m, gx, gy, extra):
        found = nearest_walkable(m, gx, gy, extra, 6)
        if not found:
            return None
        gx, gy = found
    W = m.w
    openh = MinHeap()
    gscore = {}
    came = {}
    start_i = sy * W + sx
    goal_i = gy * W + gx
    gscore[start_i] = 0.0
    openh.push(_octile(sx, sy, gx, gy), (sx, sy))
    nodes = 0
    while len(openh):
        cx, cy = openh.pop()
        ci = cy * W + cx
        if ci == goal_i:
            path = [(cx, cy)]
            while ci in came:
                ci = came[ci]
                path.append((ci % W, ci // W))
            path.reverse()
            return smooth_path(m, path, extra)
        nodes += 1
        if nodes > max_nodes:
            break
        g0 = gscore[ci]
        for dx, dy, cost in DIRS:
            nx, ny = cx + dx, cy + dy
            if not can_step(m, cx, cy, nx, ny, extra):
                continue
            ni = ny * W + nx
            ng = g0 + cost
            if ng < gscore.get(ni, 1e9):
                gscore[ni] = ng
                came[ni] = ci
                openh.push(ng + _octile(nx, ny, gx, gy), (nx, ny))
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
