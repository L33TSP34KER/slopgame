#!/usr/bin/env python3
"""design/knight-model-sheet.png — REAL procedural model sheet, player knight.

Preserved from scratch under an explicit lane grant for this one path; the
referenced plan file design/notes/character-upgrade-plan.md did not exist, so
the design spec is derived from the in-game unit CFG (mounted knight, steel
plate, plume, red team accent) — not from any plan document.

Renders the mounted Emberhold knight with a small software renderer built for
this sheet: mesh primitives (tapered boxes, elliptical tubes, lathed balls,
extruded shield), orthographic camera with yaw/pitch, back-face culling,
painter's-algorithm depth sort, Lambert + rim + metal spec shading, then an
ink silhouette outline (mask dilation) at 2x supersample.

    SDL_VIDEODRIVER=dummy .venv/bin/python .vfx_scratch/knight_sheet.py [out.png]

No asset files are read or written; output goes wherever argv[1] says.
"""
from __future__ import annotations

import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "design", "knight-model-sheet.png")

# ---------------------------------------------------------------- materials
M = dict(
    steel=(196, 203, 214), steel_d=(116, 122, 136), steel_l=(233, 239, 247),
    gold=(226, 176, 84), gold_d=(163, 122, 52),
    cloth=(166, 52, 42), cloth_l=(204, 90, 60),
    leather=(94, 68, 48), leather_d=(64, 46, 34),
    horse=(110, 86, 63), horse_d=(82, 62, 46),
    plume=(200, 54, 42),
    dark=(40, 36, 42), ink=(22, 18, 22),
)
METAL = {"steel", "steel_d", "steel_l", "gold", "gold_d"}


# ---------------------------------------------------------------- vec helpers
def v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def v_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_norm(a):
    l = math.sqrt(v_dot(a, a)) or 1.0
    return (a[0] / l, a[1] / l, a[2] / l)


def v_mid(a, b):
    return ((a[0] + b[0]) * .5, (a[1] + b[1]) * .5, (a[2] + b[2]) * .5)


# ---------------------------------------------------------------- primitives
# A face is (verts, material, ref_center): the outward normal is resolved
# against (centroid - ref) so winding never matters (all parts are convex).
def _add(out, verts, mat, ref):
    out.append((verts, mat, ref))


def fbox(out, c, size, mat, taper=1.0):
    cx, cy, cz = c
    sx, sy, sz = size[0] * .5, size[1] * .5, size[2] * .5
    tx, tz = sx * taper, sz * taper
    b = [(cx - sx, cy - sy, cz - sz), (cx + sx, cy - sy, cz - sz),
         (cx + sx, cy - sy, cz + sz), (cx - sx, cy - sy, cz + sz)]
    t = [(cx - tx, cy + sy, cz - tz), (cx + tx, cy + sy, cz - tz),
         (cx + tx, cy + sy, cz + tz), (cx - tx, cy + sy, cz + tz)]
    _add(out, b, mat, c)
    _add(out, t, mat, c)
    for i in range(4):
        j = (i + 1) % 4
        _add(out, [b[i], b[j], t[j], t[i]], mat, c)


def box_oriented(out, c, u, v, w, su, sv, sw, mat):
    """Box with an arbitrary orthonormal frame — slung gear, blades, guards."""
    world = []
    for ia in (0, 1):
        for ib in (0, 1):
            for idd in (0, 1):
                a = -su if ia == 0 else su
                b = -sv if ib == 0 else sv
                d = -sw if idd == 0 else sw
                world.append(v_add(c, v_add(v_add(v_mul(u, a), v_mul(v, b)), v_mul(w, d))))
    idx = lambda ia, ib, idd: ia * 4 + ib * 2 + idd
    quads = [
        (idx(0, 0, 0), idx(0, 1, 0), idx(1, 1, 0), idx(1, 0, 0)),   # -w
        (idx(0, 0, 1), idx(1, 0, 1), idx(1, 1, 1), idx(0, 1, 1)),   # +w
        (idx(0, 0, 0), idx(1, 0, 0), idx(1, 0, 1), idx(0, 0, 1)),   # -v
        (idx(0, 1, 0), idx(0, 1, 1), idx(1, 1, 1), idx(1, 1, 0)),   # +v
        (idx(0, 0, 0), idx(0, 0, 1), idx(0, 1, 1), idx(0, 1, 0)),   # -u
        (idx(1, 0, 0), idx(1, 1, 0), idx(1, 1, 1), idx(1, 0, 1)),   # +u
    ]
    for q in quads:
        _add(out, [world[i] for i in q], mat, c)


def tube(out, path, radii, mat, seg=8, cap=True):
    """Elliptical tube along a polyline — barrels, limbs, necks, tails.

    radii: [(rx, ry), ...] per path point (rx spans the horizontal frame
    axis, ry the other).  Ref centre per face is the local path point, so the
    outward normal resolves correctly even on bent paths."""
    n = len(path)
    if not isinstance(radii[0], (tuple, list)):
        radii = [(r, r) for r in radii]
    rings, axes = [], []
    for i, p in enumerate(path):
        if i == 0:
            t = v_sub(path[1], path[0])
        elif i == n - 1:
            t = v_sub(path[-1], path[-2])
        else:
            t = v_sub(path[i + 1], path[i - 1])
        t = v_norm(t)
        u = v_cross((0.0, 1.0, 0.0), t)
        if v_dot(u, u) < 1e-6:
            u = v_cross((0.0, 0.0, 1.0), t)
        u = v_norm(u)
        w = v_norm(v_cross(t, u))
        rx, ry = radii[i]
        ring = []
        for k in range(seg):
            a = math.tau * k / seg
            ring.append(v_add(p, v_add(v_mul(u, rx * math.cos(a)), v_mul(w, ry * math.sin(a)))))
        rings.append(ring)
        axes.append((u, w))
    for i in range(n - 1):
        ref = v_mid(path[i], path[i + 1])
        for k in range(seg):
            k2 = (k + 1) % seg
            _add(out, [rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]], mat, ref)
    if cap:
        _add(out, rings[0], mat, v_mid(path[0], path[1]) if n > 1 else path[0])
        _add(out, rings[-1], mat, v_mid(path[-1], path[-2]) if n > 1 else path[-1])


def ball(out, c, r, mat, seg=10, rings=6, squash=(1.0, 1.0, 1.0)):
    cx, cy, cz = c
    rx, ry, rz = (r * squash[0], r * squash[1], r * squash[2])
    grid = []
    for i in range(rings + 1):
        ph = math.pi * i / rings          # 0 = top pole
        y = math.cos(ph)
        rr = math.sin(ph)
        row = []
        for j in range(seg):
            th = math.tau * j / seg
            row.append((cx + rx * rr * math.cos(th),
                        cy + ry * y,
                        cz + rz * rr * math.sin(th)))
        grid.append(row)
    for i in range(rings):
        for j in range(seg):
            j2 = (j + 1) % seg
            quad = [grid[i][j], grid[i][j2], grid[i + 1][j2], grid[i + 1][j]]
            if i == 0:
                _add(out, [quad[0], quad[1], quad[2]], mat, c)
            elif i == rings - 1:
                _add(out, [quad[0], quad[2], quad[3]], mat, c)
            else:
                _add(out, quad, mat, c)


def extrude(out, outline, c, u, v, w, thick, mat):
    """Extruded 2D outline in the (u,v) plane — heater shield, cape plates."""
    front, back = [], []
    for (a, b) in outline:
        base = v_add(c, v_add(v_mul(u, a), v_mul(v, b)))
        front.append(v_add(base, v_mul(w, thick)))
        back.append(v_sub(base, v_mul(w, thick)))
    _add(out, front, mat, c)
    _add(out, back[::-1], mat, c)
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        _add(out, [front[i], front[j], back[j], back[i]], mat, c)


# ---------------------------------------------------------------- camera
class Cam:
    def __init__(self, az, el):
        a, e = math.radians(az), math.radians(el)
        self.ca, self.sa = math.cos(a), math.sin(a)
        self.ce, self.se = math.cos(e), math.sin(e)

    def rot(self, p):
        x, y, z = p
        x1 = x * self.ca + z * self.sa
        z1 = -x * self.sa + z * self.ca
        y2 = y * self.ce - z1 * self.se
        z2 = y * self.se + z1 * self.ce
        return (x1, y2, z2)


KEY = v_norm((-0.52, 0.66, 0.55))     # view-space key: upper-left, front
HALF = v_norm(v_add(KEY, (0.0, 0.0, 1.0)))
FILL = v_norm((0.55, -0.2, 0.45))


def shade(mat, n):
    base = M[mat]
    lam = max(0.0, v_dot(n, KEY))
    fil = max(0.0, v_dot(n, FILL))
    rim = (1.0 - min(1.0, max(0.0, n[2]))) ** 2.7
    sky = 0.06 * max(0.0, n[1])
    lum = 0.27 + 0.86 * lam + 0.17 * fil + sky
    r = base[0] * lum + 250 * rim * 0.19
    g = base[1] * lum + 242 * rim * 0.17
    b = base[2] * lum + 230 * rim * 0.14
    if mat in METAL:
        s = max(0.0, v_dot(n, HALF)) ** 26
        s *= 150.0 if mat != "gold" and mat != "gold_d" else 110.0
        r += s
        g += s
        b += s * 0.94
    return (min(255, int(r)), min(255, int(g)), min(255, int(b)))


def build_knight(head="A", only=None):
    """The mounted player knight.  Forward = +Z; az=0 is a front view."""
    f = []
    H = M
    # ---------------------------------------------------------- horse
    tube(f, [(0, 1.04, -0.92), (0, 1.07, -0.30), (0, 1.05, 0.34), (0, 1.00, 0.62)],
         [(0.30, 0.30), (0.34, 0.33), (0.33, 0.32), (0.26, 0.27)], "horse", seg=12)
    # neck + head + muzzle
    tube(f, [(0, 1.10, 0.58), (0, 1.34, 0.80), (0, 1.56, 0.96)],
         [(0.20, 0.19), (0.16, 0.16), (0.125, 0.13)], "horse", seg=10)
    tube(f, [(0, 1.60, 1.00), (0, 1.55, 1.20), (0, 1.44, 1.40)],
         [(0.115, 0.13), (0.095, 0.11), (0.07, 0.085)], "horse", seg=8)
    for sx in (-1, 1):
        tube(f, [(sx * 0.06, 1.66, 1.02), (sx * 0.075, 1.82, 0.97)],
             [(0.032, 0.032), (0.008, 0.008)], "horse_d", seg=6)
    # mane
    tube(f, [(0, 1.24, 0.66), (0, 1.46, 0.84), (0, 1.66, 0.99)],
         [(0.055, 0.03), (0.05, 0.03), (0.04, 0.02)], "horse_d", seg=6)
    # legs: near-side slightly forward for a live stance
    legs = [(-0.19, 0.54, 0.10), (0.19, 0.44, -0.04),
            (-0.185, -0.68, -0.10), (0.185, -0.76, 0.06)]
    for (lx, lz, dxf) in legs:
        knee = (lx * 1.05, 0.56, lz + dxf * 0.6)
        fet = (lx * 1.05, 0.14, lz + dxf)
        tube(f, [(lx, 0.95, lz), knee], [(0.115, 0.115), (0.07, 0.075)], "horse", seg=8)
        tube(f, [knee, fet], [(0.06, 0.065), (0.04, 0.045)], "horse_d", seg=7)
        fbox(f, (fet[0], 0.055, fet[2] + 0.015), (0.10, 0.10, 0.14), "dark")
    # tail
    tube(f, [(0, 1.16, -0.95), (0, 0.92, -1.14), (0, 0.62, -1.20)],
         [(0.085, 0.085), (0.06, 0.06), (0.02, 0.02)], "horse_d", seg=7)
    # saddle + caparison
    fbox(f, (0, 1.40, -0.06), (0.30, 0.10, 0.46), "leather", taper=1.08)
    fbox(f, (0, 1.44, -0.30), (0.20, 0.09, 0.12), "leather_d")
    for sx in (-1, 1):
        fbox(f, (sx * 0.335, 1.06, -0.04), (0.03, 0.52, 0.66), "cloth")
        fbox(f, (sx * 0.335, 0.82, -0.04), (0.035, 0.05, 0.66), "gold_d")
    # chest strap
    tube(f, [(0, 1.16, 0.44), (0, 1.24, 0.56)], [(0.04, 0.30), (0.04, 0.30)],
         "gold_d", seg=6)

    # ---------------------------------------------------------- rider
    pelvis_y = 1.56
    fbox(f, (0, pelvis_y, 0.0), (0.28, 0.17, 0.21), "steel_d")
    # cuirass (tapered up), fauld, waist cloth
    fbox(f, (0, 1.84, 0.0), (0.34, 0.44, 0.24), "steel", taper=1.16)
    fbox(f, (0, 1.63, 0.0), (0.35, 0.12, 0.25), "steel_d", taper=0.94)
    fbox(f, (0, 1.50, 0.115), (0.25, 0.17, 0.02), "cloth")
    fbox(f, (0, 1.50, -0.115), (0.25, 0.17, 0.02), "cloth")
    # gorget
    tube(f, [(0, 2.02, 0.0), (0, 2.11, 0.0)], [(0.075, 0.07), (0.07, 0.065)],
         "steel_d", seg=8)
    # pauldrons
    for sx in (-1, 1):
        ball(f, (sx * 0.235, 2.02, 0.0), 0.13, "steel", squash=(1.0, 0.82, 1.0))
    # legs
    for sx in (-1, 1):
        knee = (sx * 0.27, 1.22, 0.30)
        tube(f, [(sx * 0.16, 1.56, 0.02), knee],
             [(0.115, 0.115), (0.09, 0.09)], "steel_d", seg=8)
        tube(f, [knee, (sx * 0.30, 0.95, 0.24)],
             [(0.08, 0.085), (0.06, 0.065)], "steel", seg=8)
        fbox(f, (sx * 0.30, 0.89, 0.30), (0.10, 0.07, 0.22), "steel_d")
    # sword arm (right, +X): raised blade
    tube(f, [(0.26, 1.99, 0.02), (0.335, 1.76, 0.14)],
         [(0.085, 0.085), (0.075, 0.075)], "steel", seg=8)
    tube(f, [(0.335, 1.76, 0.14), (0.305, 1.97, 0.28)],
         [(0.07, 0.07), (0.06, 0.06)], "steel_d", seg=8)
    ball(f, (0.305, 1.99, 0.30), 0.068, "steel")
    # shield arm (left), relaxed
    tube(f, [(-0.26, 1.99, 0.02), (-0.31, 1.74, 0.10)],
         [(0.085, 0.085), (0.075, 0.075)], "steel", seg=8)
    tube(f, [(-0.31, 1.74, 0.10), (-0.28, 1.50, 0.18)],
         [(0.07, 0.07), (0.058, 0.058)], "steel_d", seg=8)
    ball(f, (-0.28, 1.48, 0.19), 0.065, "steel")

    # sword in the right hand
    grip0, grip1 = (0.305, 1.92, 0.30), (0.31, 2.10, 0.305)
    tube(f, [grip0, grip1], [(0.026, 0.026), (0.026, 0.026)], "leather", seg=7)
    ball(f, (0.305, 1.90, 0.30), 0.042, "gold")
    u_blade = v_norm((0.06, 1.0, 0.10))
    v_blade = (1.0, 0.0, 0.0)
    w_blade = v_norm(v_cross(u_blade, v_blade))
    box_oriented(f, (0.31, 2.62, 0.35), u_blade, v_blade, w_blade,
                 0.50, 0.028, 0.011, "steel_l")
    box_oriented(f, (0.31, 2.13, 0.31), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0),
                 0.13, 0.022, 0.022, "gold")

    # shield slung across the back
    su = v_norm((0.34, 1.0, 0.0))
    sw = (0.0, 0.0, -1.0)
    sv = v_norm(v_cross(sw, su))
    sc = (-0.02, 1.80, -0.205)
    outline = [(-0.24, 0.36), (0.24, 0.36), (0.27, 0.05), (0.0, -0.40), (-0.27, 0.05)]
    extrude(f, outline, sc, su, sv, sw, 0.035, "cloth")
    # emblem boss
    box_oriented(f, v_add(sc, v_mul(sw, 0.046)), su, sv, sw, 0.10, 0.10, 0.012, "gold")
    box_oriented(f, v_add(sc, v_mul(sw, 0.050)), v_norm(v_add(su, sv)),
                 v_norm(v_sub(su, sv)), sw, 0.12, 0.045, 0.010, "gold_d")

    # head variants (also returned alone for the helm detail panels)
    hf = []
    if head == "A":
        ball(hf, (0, 2.24, 0.0), 0.145, "steel", squash=(1.0, 1.06, 1.02))
        # great helm brow + slit
        fbox(hf, (0, 2.245, 0.135), (0.20, 0.045, 0.06), "steel_d", taper=0.9)
        fbox(hf, (0, 2.205, 0.155), (0.15, 0.028, 0.03), "dark")
        fbox(hf, (0, 2.10, -0.09), (0.16, 0.10, 0.08), "steel_d")
        # plume crest flowing back over the neck
        plume = [((0, 2.375, 0.03), 0.055), ((0, 2.37, -0.06), 0.05),
                 ((0, 2.32, -0.15), 0.045), ((0, 2.24, -0.22), 0.036),
                 ((0, 2.15, -0.26), 0.024)]
        tube(hf, [p for p, _ in plume], [r for _, r in plume], "plume", seg=7)
    else:  # head B: barbute + shoulder mantle
        ball(hf, (0, 2.23, 0.0), 0.148, "steel_d", squash=(1.0, 1.05, 1.0))
        fbox(hf, (0, 2.20, 0.138), (0.045, 0.15, 0.05), "dark")
        fbox(hf, (0, 2.265, 0.142), (0.17, 0.03, 0.05), "dark")
        fbox(hf, (0, 2.10, -0.085), (0.15, 0.09, 0.07), "steel")
        # mantle draped over pauldrons and upper back
        fbox(hf, (0, 2.00, -0.01), (0.52, 0.20, 0.38), "cloth", taper=0.72)
        fbox(hf, (0, 1.90, -0.01), (0.50, 0.05, 0.36), "cloth_l")
    if only == "head":
        return hf
    f.extend(hf)
    return f


# ---------------------------------------------------------------- renderer
def render_figure(faces, az, el, box_px, ss=2, shadow=True, bg=None):
    """Project + paint one figure into a surface of box_px (w, h)."""
    W, H = box_px
    cam = Cam(az, el)
    tw, th = W * ss, H * ss
    surf = pygame.Surface((tw, th), pygame.SRCALPHA)
    # project everything at unit scale first to fit the box
    proj = []
    xs, ys = [], []
    for (verts, mat, ref) in faces:
        p3 = [cam.rot(v) for v in verts]
        proj.append((p3, mat, ref))
        for (x, y, z) in p3:
            xs.append(x)
            ys.append(-y)          # screen y grows downward
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    pad = 6 * ss
    scale = min((tw - 2 * pad) / max(1e-6, maxx - minx),
                (th - 2 * pad) / max(1e-6, maxy - miny))
    ox = (tw - (maxx - minx) * scale) / 2 - minx * scale
    oy = (th - (maxy - miny) * scale) / 2 - miny * scale

    def scr(p):
        return (p[0] * scale + ox, -p[1] * scale + oy)

    # ground shadow (separate layer so the ink outline wraps only the figure)
    shadow_surf = None
    if shadow:
        shadow_surf = pygame.Surface((tw, th), pygame.SRCALPHA)
        for k, (rad, a) in enumerate(((1.05, 70), (0.8, 46), (0.55, 34))):
            pts = []
            for i in range(26):
                ang = math.tau * i / 26
                pts.append(scr(cam.rot((math.cos(ang) * rad * 1.25, 0.0,
                                        math.sin(ang) * rad * 0.85))))
            pygame.draw.polygon(shadow_surf, (8, 7, 9, a), pts)

    # faces: cull, shade, depth sort (far first)
    draw_list = []
    for (p3, mat, ref) in proj:
        c = [0.0, 0.0, 0.0]
        for p in p3:
            c[0] += p[0]
            c[1] += p[1]
            c[2] += p[2]
        n = 1.0 / len(p3)
        cen = (c[0] * n, c[1] * n, c[2] * n)
        # world-space normal via Newell, resolved outward against ref
        nx = ny = nz = 0.0
        for i in range(len(p3)):
            a, b = p3[i], p3[(i + 1) % len(p3)]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        nrm = v_norm((nx, ny, nz))
        rf = cam.rot(ref)
        vref = v_sub(cen, rf)
        if v_dot(nrm, vref) < 0:
            nrm = v_mul(nrm, -1.0)
        if nrm[2] <= 0.02:
            continue
        zc = sum(p[2] for p in p3) * n
        draw_list.append((zc, [scr(p) for p in p3], shade(mat, nrm)))
    draw_list.sort(key=lambda d: d[0])
    for _, pts, col in draw_list:
        pygame.draw.polygon(surf, col, [(int(x), int(y)) for x, y in pts])

    # ink silhouette outline from the alpha mask
    mask = pygame.mask.from_surface(surf)
    ink = mask.to_surface(setcolor=(24, 20, 26, 255), unsetcolor=(0, 0, 0, 0))
    out = pygame.Surface((tw, th), pygame.SRCALPHA)
    k = max(1, int(2 * ss))
    for dx, dy in ((k, 0), (-k, 0), (0, k), (0, -k), (k, k), (k, -k), (-k, k), (-k, -k)):
        out.blit(ink, (dx, dy))
    out.blit(surf, (0, 0))
    if shadow_surf is not None:
        composed = pygame.Surface((tw, th), pygame.SRCALPHA)
        composed.blit(shadow_surf, (0, 0))
        composed.blit(out, (0, 0))
        out = composed
    return pygame.transform.smoothscale(out, (W, H))


# ---------------------------------------------------------------- sheet
PARCH = (232, 220, 192)
DIM = (150, 144, 132)
BOARD = (30, 31, 37)
PANEL = (38, 39, 47)
EDGE = (66, 64, 74)


def board(w, h):
    s = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        s.fill((int(28 + 8 * t), int(29 + 8 * t), int(35 + 9 * t)), (0, y, w, 1))
    return s


def panel(scr, rect, title=None, sub=None, fonts=None):
    x, y, w, h = rect
    pygame.draw.rect(scr, PANEL, rect, border_radius=10)
    pygame.draw.rect(scr, EDGE, rect, 2, border_radius=10)
    # ground line
    pygame.draw.line(scr, (58, 57, 66), (x + 18, y + h - 44), (x + w - 18, y + h - 44), 2)
    if title and fonts:
        scr.blit(fonts["sub"].render(title, True, PARCH), (x + 16, y + 10))
    if sub and fonts:
        scr.blit(fonts["small"].render(sub, True, DIM), (x + 16, y + h - 34))


def label(scr, f, text, pos, col=PARCH):
    scr.blit(f.render(text, True, col), pos)


def main():
    pygame.init()
    pygame.display.set_mode((64, 64))
    W, H = 2560, 1620
    scr = board(W, H)

    fonts = dict(
        title=pygame.font.Font(os.path.join(ROOT, "assets/fonts/Cinzel-Bold.ttf"), 46),
        sub=pygame.font.Font(os.path.join(ROOT, "assets/fonts/Cinzel-Bold.ttf"), 22),
        small=pygame.font.Font(os.path.join(ROOT, "assets/fonts/SourceSans3-SemiBold.ttf"), 19),
        tiny=pygame.font.Font(os.path.join(ROOT, "assets/fonts/SourceSans3-SemiBold.ttf"), 16),
    )

    # title block
    scr.blit(fonts["title"].render("EMBERFALL  ·  PLAYER KNIGHT", True, PARCH), (44, 34))
    scr.blit(fonts["small"].render(
        "model sheet — procedural 3D render · rear three-quarter focus · "
        "head variants A/B · turntable 0°–315° · mounted, plate of the Emberhold",
        True, DIM), (46, 92))
    # palette strip
    pal = [("plate", "steel"), ("shadow", "steel_d"), ("trim", "gold"),
           ("ember", "cloth"), ("reins", "leather"), ("destrier", "horse")]
    px = W - 44 - len(pal) * 168
    for i, (nm, key) in enumerate(pal):
        r = pygame.Rect(px + i * 168, 40, 40, 40)
        pygame.draw.rect(scr, M[key], r, border_radius=6)
        pygame.draw.rect(scr, EDGE, r, 1, border_radius=6)
        scr.blit(fonts["tiny"].render(f"{nm} {M[key][0]:02x}{M[key][1]:02x}{M[key][2]:02x}",
                                      True, DIM), (px + i * 168 + 48, 50))
        scr.blit(fonts["tiny"].render(key, True, (110, 106, 100)),
                 (px + i * 168 + 48, 70))

    facesA = build_knight("A")
    facesB = build_knight("B")

    # ---- hero panel: rear three-quarter, head A --------------------------
    hero_rect = (40, 140, 1180, 1060)
    panel(scr, hero_rect, "REAR THREE-QUARTER  ·  AZ 155°",
          "HEAD A — great helm + ember plume · mounted plate of the Emberhold", fonts)
    hsrc = render_figure(facesA, 155, 9, (716, 950), ss=2)
    scr.blit(hsrc, (hero_rect[0] + 26, hero_rect[1] + 52))
    # helm detail plates inside the hero panel's right gutter
    pygame.draw.line(scr, EDGE, (hero_rect[0] + 772, hero_rect[1] + 56),
                     (hero_rect[0] + 772, hero_rect[1] + hero_rect[3] - 56), 1)
    for j, (nm, hkey) in enumerate((("HELM A — GREAT HELM 3×", "A"),
                                    ("HELM B — BARBUTE 3×", "B"))):
        dx = hero_rect[0] + 800
        dy = hero_rect[1] + 70 + j * 470
        dr = (dx, dy, 340, 400)
        pygame.draw.rect(scr, (33, 34, 41), dr, border_radius=8)
        pygame.draw.rect(scr, EDGE, dr, 1, border_radius=8)
        faces_h = build_knight(hkey, only="head")
        detail = render_figure(faces_h, 155, 14, (316, 336), ss=3, shadow=False)
        scr.blit(detail, (dx + 12, dy + 34))
        scr.blit(fonts["small"].render(nm, True, PARCH), (dx + 12, dy + 8))
        scr.blit(fonts["tiny"].render(
            "barbute: T-visor" if hkey == "B" else "slit visor, ember crest",
            True, DIM), (dx + 12, dy + 366))

    # ---- right column ---------------------------------------------------
    p1 = (1250, 140, 630, 520)
    panel(scr, p1, "HEAD B — REAR 3/4", "barbute + shoulder mantle", fonts)
    scr.blit(render_figure(facesB, 155, 9, (570, 430), ss=2), (p1[0] + 30, p1[1] + 46))

    p2 = (1890, 140, 630, 520)
    panel(scr, p2, "HEAD B — FRONT 3/4  ·  AZ 45°", "T-visor barbute, mantle over pauldrons", fonts)
    scr.blit(render_figure(facesB, 45, 9, (570, 430), ss=2), (p2[0] + 30, p2[1] + 46))

    p3 = (1250, 680, 630, 520)
    panel(scr, p3, "HEAD A — FRONT 3/4  ·  AZ 45°", "sword guard, heater shield slung", fonts)
    scr.blit(render_figure(facesA, 45, 9, (570, 430), ss=2), (p3[0] + 30, p3[1] + 46))

    p4 = (1890, 680, 630, 520)
    panel(scr, p4, "GEAR — STRAIGHT REAR  ·  AZ 180°", "shield emplacement, scabbard side, plume fall", fonts)
    scr.blit(render_figure(facesA, 180, 9, (570, 430), ss=2), (p4[0] + 30, p4[1] + 46))

    # ---- turntable strip ------------------------------------------------
    strip_y, strip_h = 1230, 350
    angles = [(0, "0° front"), (45, "45° front 3/4"), (90, "90° side"),
              (135, "135° rear 3/4"), (180, "180° rear"), (315, "315° rear 3/4")]
    cell_w = (W - 80) // len(angles)
    for i, (az, nm) in enumerate(angles):
        r = (40 + i * cell_w, strip_y, cell_w - 12, strip_h)
        panel(scr, r, None, None, fonts)
        scr.blit(render_figure(facesA, az, 9, (cell_w - 44, strip_h - 62), ss=2),
                 (r[0] + 16, r[1] + 8))
        scr.blit(fonts["small"].render(nm, True, PARCH), (r[0] + 16, r[1] + strip_h - 36))
    scr.blit(fonts["tiny"].render(
        "procedural render — mesh primitives, painter's depth sort, Lambert + rim + spec, "
        "ink silhouette · no source art modified", True, (112, 108, 102)), (44, H - 30))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    pygame.image.save(scr, OUT)
    print("saved", OUT, scr.get_size(), flush=True)


if __name__ == "__main__":
    main()
