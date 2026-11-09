"""Core utilities: seeded RNG, noise, isometric math, heaps, formatting."""
from __future__ import annotations
import math, random, heapq
from .defs import TILE_W, TILE_H, ELEV

TAU = math.pi * 2


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(t):
    return t * t * (3 - 2 * t)


def dist(ax, ay, bx, by):
    return math.hypot(bx - ax, by - ay)


def dist2(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    return dx * dx + dy * dy


def angle_diff(a, b):
    return ((b - a + math.pi) % TAU + TAU) % TAU - math.pi


def angle_lerp(a, b, t):
    return a + angle_diff(a, b) * t


def approach(a, b, step):
    return min(a + step, b) if a < b else max(a - step, b)


class Rng:
    def __init__(self, seed=1337):
        self.r = random.Random(seed)
        self.seed = seed

    def __call__(self):
        return self.r.random()

    def random(self):
        return self.r.random()

    def uniform(self, a, b):
        return self.r.uniform(a, b)

    def randint(self, a, b):
        return self.r.randint(a, b)

    def randrange(self, a, b=None):
        return self.r.randrange(a) if b is None else self.r.randrange(a, b)

    def choice(self, seq):
        return self.r.choice(seq)

    def chance(self, p):
        return self.r.random() < p

    def shuffle(self, seq):
        self.r.shuffle(seq)

    def fork(self, n):
        return Rng(self.r.randrange(1 << 30) + n)


def hash2(x, y, seed=0):
    h = (int(x) * 374761393 + int(y) * 668265263 + int(seed) * 1442695040) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return (h & 0xFFFFFFFF) / 4294967296.0


def noise2(x, y, seed=0):
    xi, yi = math.floor(x), math.floor(y)
    xf, yf = x - xi, y - yi
    u, v = smoothstep(xf), smoothstep(yf)
    a = hash2(xi, yi, seed); b = hash2(xi + 1, yi, seed)
    c = hash2(xi, yi + 1, seed); d = hash2(xi + 1, yi + 1, seed)
    return lerp(lerp(a, b, u), lerp(c, d, u), v)


def fbm(x, y, seed=0, octaves=4, gain=0.5):
    amp, freq, total, norm = 1.0, 1.0, 0.0, 0.0
    for i in range(octaves):
        total += amp * noise2(x * freq, y * freq, seed + i * 31)
        norm += amp
        amp *= gain
        freq *= 2
    return total / norm


# ---------------- isometric projection ----------------

def sx(x, y):
    return (x - y) * (TILE_W / 2)


def sy(x, y, h=0):
    return (x + y) * (TILE_H / 2) - h * ELEV


def tile_from_screen(px, py, h=0):
    yy = (py + h * ELEV) / (TILE_H / 2)
    xx = px / (TILE_W / 2)
    return ((xx + yy) / 2, (yy - xx) / 2)


# ---------------- spatial hash ----------------

class SpatialHash:
    def __init__(self, cell=4):
        self.cell = cell
        self.map = {}

    def clear(self):
        self.map.clear()

    def insert(self, obj, x, y, r=0):
        c = self.cell
        x0, x1 = int((x - r) // c), int((x + r) // c)
        y0, y1 = int((y - r) // c), int((y + r) // c)
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                self.map.setdefault((cx, cy), []).append(obj)

    def query(self, x, y, r, out=None):
        out = [] if out is None else out
        seen = set()
        c = self.cell
        x0, x1 = int((x - r) // c), int((x + r) // c)
        y0, y1 = int((y - r) // c), int((y + r) // c)
        for cy in range(y0, y1 + 1):
            for cx in range(x0, x1 + 1):
                for o in self.map.get((cx, cy), ()):
                    if id(o) not in seen:
                        seen.add(id(o))
                        out.append(o)
        return out


# ---------------- A* helpers ----------------

class MinHeap:
    def __init__(self):
        self.a = []
        self.counter = 0

    def __len__(self):
        return len(self.a)

    def push(self, f, node):
        self.counter += 1
        heapq.heappush(self.a, (f, self.counter, node))

    def pop(self):
        return heapq.heappop(self.a)[2]


def point_seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return dist(px, py, ax, ay)
    t = clamp(((px - ax) * dx + (py - ay) * dy) / l2, 0, 1)
    return dist(px, py, ax + t * dx, ay + t * dy)


def fmt_time(sec):
    s = max(0, int(sec))
    return f"{s // 60}:{s % 60:02d}"


def fmt(n):
    return f"{int(round(n)):,}"


def seed_from(text):
    h = 2166136261
    for ch in text:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h
