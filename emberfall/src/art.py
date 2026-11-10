"""Procedural art: isometric terrain, props, buildings, unit rigs, UI icons/fonts.

Everything is generated once at load (supersampled for smooth edges) and cached,
so the game ships with no external art dependency while keeping one coherent look.
"""
from __future__ import annotations
import math, os, random
import pygame
from .core import clamp, lerp, Rng, angle_diff, hash2
from .defs import *

SS = 2
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(ROOT, "assets")

# ---------------------------------------------------------------- colours

def hexc(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def shade(c, f):
    return (clamp(int(c[0] * f), 0, 255), clamp(int(c[1] * f), 0, 255), clamp(int(c[2] * f), 0, 255))


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def with_a(c, a):
    return (c[0], c[1], c[2], clamp(int(a), 0, 255))


# ---- cinematic tone (saturation lift + pivot contrast) -----------------------
# Applied ONCE per generated tile (and to the row averages those tiles report),
# never per frame: pygame has no per-channel LUT op, so a frame-time curve
# would mean a Python loop over 1.4M pixels.  Doing it where the art is baked
# gives a real S-style curve for free at runtime, and because every variant of
# a terrain runs the SAME function, vertex-converged rims still map to exactly
# one colour per row — the lattice metric cannot move from this pass.
TONE_K = 1.13        # contrast gain around TONE_PIVOT
TONE_S = 1.22        # saturation lift
TONE_PIVOT = 104.0


def tone_col(c, k=TONE_K, s=TONE_S, piv=TONE_PIVOT):
    """Saturation lift then pivot contrast for a single colour."""
    r, g, b = float(c[0]), float(c[1]), float(c[2])
    gy = 0.299 * r + 0.587 * g + 0.114 * b
    r = gy + (r - gy) * s
    g = gy + (g - gy) * s
    b = gy + (b - gy) * s
    return (clamp(int(piv + (r - piv) * k), 0, 255),
            clamp(int(piv + (g - piv) * k), 0, 255),
            clamp(int(piv + (b - piv) * k), 0, 255))


def tone_surface(img, k=TONE_K, s=TONE_S, piv=TONE_PIVOT):
    """Same curve, every pixel of one tile surface (~2k px, bake time only).

    Built from tobytes/frombytes so the loop is a plain byte walk: 80-90 tiles
    cost well under a second once at load instead of anything per tick.
    """
    w, h = img.get_size()
    if w <= 0 or h <= 0:
        return img
    raw = pygame.image.tobytes(img, "RGBA")
    lut = [clamp(int(piv + (i - piv) * k), 0, 255) for i in range(256)]
    out = bytearray(raw)
    i = 0
    n = len(raw)
    while i < n:
        r = raw[i]; g = raw[i + 1]; b = raw[i + 2]
        if raw[i + 3]:
            gy = 0.299 * r + 0.587 * g + 0.114 * b
            rr = gy + (r - gy) * s
            gg = gy + (g - gy) * s
            bb = gy + (b - gy) * s
            out[i] = lut[0 if rr < 0 else (255 if rr > 255 else int(rr))]
            out[i + 1] = lut[0 if gg < 0 else (255 if gg > 255 else int(gg))]
            out[i + 2] = lut[0 if bb < 0 else (255 if bb > 255 else int(bb))]
        i += 4
    return pygame.image.frombytes(bytes(out), (w, h), "RGBA")


INK = (24, 20, 26)
PARCH = hexc(PALETTE["parchment"])
GOLD = hexc(PALETTE["gold"])
EMBER = hexc(PALETTE["ember"])
STEEL = hexc(PALETTE["steel"])
BONE = hexc(PALETTE["bone"])
VIOLET = hexc(PALETTE["violet"])
BLOOD = hexc(PALETTE["blood"])
MOSS = hexc(PALETTE["moss"])

# per-terrain base colours
TERRAIN_COL = {
    0: (62, 88, 54), 1: (112, 87, 62), 2: (86, 82, 76),
    3: (37, 86, 98), 4: (168, 149, 105), 5: (70, 65, 72),
    6: (84, 30, 38), 7: (50, 73, 45),
}

# ---------------------------------------------------------------- drawing helpers

def _p(pts, ss=SS):
    return [(x * ss, y * ss) for x, y in pts]


def dpoly(s, color, pts, width=0, ss=SS):
    pygame.draw.polygon(s, color, _p(pts, ss), max(0, int(width * ss)))


def dline(s, color, a, b, width=1, ss=SS):
    pygame.draw.line(s, color, (a[0] * ss, a[1] * ss), (b[0] * ss, b[1] * ss), max(1, int(width * ss)))


def dcircle(s, color, c, r, width=0, ss=SS):
    pygame.draw.circle(s, color, (int(c[0] * ss), int(c[1] * ss)), max(1, int(r * ss)), max(0, int(width * ss)))


def dellipse(s, color, rect, width=0, ss=SS):
    r = pygame.Rect(int(rect[0] * ss), int(rect[1] * ss), int(rect[2] * ss), int(rect[3] * ss))
    pygame.draw.ellipse(s, color, r, max(0, int(width * ss)))


def new_sprite(w, h, ss=SS):
    return pygame.Surface((int(w * ss), int(h * ss)), pygame.SRCALPHA)


def finish(surf, w, h):
    return pygame.transform.smoothscale(surf, (int(w), int(h)))


def gradient_v(size, top, bottom):
    w, h = size
    s = pygame.Surface((1, h), pygame.SRCALPHA)
    for y in range(h):
        t = y / max(1, h - 1)
        s.set_at((0, y), (*mix(top, bottom, t), 255))
    return pygame.transform.scale(s, (w, h))


def radial_glow(radius, color, strength=255, falloff=2.0):
    d = radius * 2
    s = pygame.Surface((d, d), pygame.SRCALPHA)
    for r in range(radius, 0, -2):
        t = r / radius
        a = int(strength * ((1 - t) ** falloff))
        c = tuple(int(v * (a / 255.0) * 0.85) for v in color)
        pygame.draw.circle(s, (*c, 255), (radius, radius), r)
    return s


def soft_shadow(w, h, alpha=70):
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (10, 9, 12, alpha), (0, 0, w, h))
    return s


# ---------------------------------------------------------------- art manager

class Art:
    def __init__(self):
        from .flare_units import FlareUnits
        self.flare = FlareUnits()
        self.fonts = {}
        self.icons = {}
        self.tiles = {}
        self.props = {}
        self.buildings = {}
        self.units = {}
        self.portraits = {}
        self.portrait_faces = {}
        for name in ("worker", "footman", "archer", "knight", "priest", "hero", "goblin"):
            fp = os.path.join(ASSETS, "flare", "portraits", name + ".png")
            if os.path.exists(fp):
                self.portrait_faces[name] = pygame.image.load(fp).convert_alpha()
        self.glow = {}
        self.rims = {}
        self._icon_cache = {}
        self._text_cache = {}
        self._gen_tiles()
        self._load_fonts()
        self._load_icons()
        self._prewarm_units()

    # ---- fonts
    def _load_fonts(self):
        self.font_paths = {
            "display": "/usr/share/fonts/gsfonts/C059-Bold.otf",
            "display_regular": "/usr/share/fonts/gsfonts/C059-Roman.otf",
            "serif": "/usr/share/fonts/TTF/DejaVuSerif.ttf",
            "serif_bold": "/usr/share/fonts/TTF/DejaVuSerif-Bold.ttf",
            "sans": "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "sans_bold": "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        }
        # bundled OFL fonts win if present (assets/fonts: Cinzel for display,
        # EB Garamond for body/serif, Source Sans 3 for HUD labels — instanced
        # from Google Fonts variable TTFs, licences shipped as OFL-*.txt).
        # Before this bundle existed the game fell back to DejaVu/C059, which
        # is the "ugly font" the human reported.
        for name, fname in (("display", "Cinzel-Bold.ttf"), ("display_regular", "Cinzel-Regular.ttf"),
                            ("serif", "EBGaramond-Regular.ttf"), ("serif_bold", "EBGaramond-Bold.ttf"),
                            ("sans", "SourceSans3-Regular.ttf"), ("sans_bold", "SourceSans3-SemiBold.ttf")):
            p = os.path.join(ASSETS, "fonts", fname)
            if os.path.exists(p):
                self.font_paths[name] = p

    def font(self, size, face="serif"):
        key = (face, int(size))
        f = self.fonts.get(key)
        if f is None:
            path = self.font_paths.get(face, self.font_paths["serif"])
            try:
                f = pygame.font.Font(path, int(size))
            except Exception:
                f = pygame.font.Font(None, int(size))
            self.fonts[key] = f
        return f

    def text(self, text, size, color=PARCH, face="serif", shadow=True):
        key = (str(text), int(size), tuple(color), face, bool(shadow))
        hit = self._text_cache.get(key)
        if hit is not None:
            return hit
        f = self.font(size, face)
        img = f.render(str(text), True, color)
        if not shadow:
            out = img
        else:
            out = pygame.Surface((img.get_width() + 2, img.get_height() + 2), pygame.SRCALPHA)
            sh = f.render(str(text), True, (0, 0, 0, 160))
            out.blit(sh, (1, 1))
            out.blit(img, (0, 0))
        if len(self._text_cache) > 800:
            self._text_cache.clear()
        self._text_cache[key] = out
        return out

    def text_wrap(self, text, size, width, color, face="serif", line_gap=2):
        f = self.font(size, face)
        words = str(text).split()
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if f.size(test)[0] <= width:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        surfs = [f.render(line, True, color) for line in lines]
        h = sum(s.get_height() + line_gap for s in surfs)
        out = pygame.Surface((width, max(1, h)), pygame.SRCALPHA)
        y = 0
        for s in surfs:
            out.blit(s, (0, y))
            y += s.get_height() + line_gap
        return out

    # ---- icons
    def _load_icons(self):
        d = os.path.join(ASSETS, "icons", "png")
        if not os.path.isdir(d):
            return
        for fn in os.listdir(d):
            if fn.endswith(".png"):
                if fn.startswith("icon-"):
                    key = fn[5:-4]
                elif fn.startswith("it-"):
                    key = fn[:-4]
                else:
                    key = fn[:-4]
                try:
                    self.icons[key] = pygame.image.load(os.path.join(d, fn)).convert_alpha()
                except Exception:
                    pass

    def icon(self, key, size=64):
        ck = (key, int(size))
        hit = self._icon_cache.get(ck)
        if hit is not None:
            return hit
        img = self.icons.get(key)
        if img is None:
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.rect(s, (52, 45, 38), (0, 0, size, size), border_radius=6)
            pygame.draw.rect(s, (120, 104, 80), (0, 0, size, size), 2, border_radius=6)
            gl = self.font(max(12, size // 3), "display").render((key or "?")[0].upper(), True, PARCH)
            s.blit(gl, ((size - gl.get_width()) // 2, (size - gl.get_height()) // 2))
            self._icon_cache[ck] = s
            return s
        out = pygame.transform.smoothscale(img, (size, size))
        self._icon_cache[ck] = out
        return out

    def unit_frame_count(self, rig, anim):
        return self.flare.frame_count(rig, anim) if getattr(self, "flare", None) else 4

    def _prewarm_units(self):
        """Cache the most common frames so first contact does not hitch."""
        if not getattr(self, "flare", None):
            return
        player = ("worker", "footman", "archer", "knight", "priest", "hero")
        enemies = ("ghoul", "fiend", "necromancer", "abomination", "revenant",
                   "skeleton", "goblin", "goblin-brute", "hollow-king")
        plan = (("idle", 4), ("walk", 8), ("attack", 4), ("cast", 4), ("death", 6))
        for rig in player + enemies:
            if not self.flare.can(rig):
                continue
            team = PLAYER if rig in player else ENEMY
            for facing in range(4):
                for anim, n in plan:
                    for f in range(n):
                        self.unit(rig, facing, anim, f, team)

    # ---- water/tile generation
    def _gen_tiles(self):
        from .flare_terrain import floor_sources, water_sources
        src = floor_sources()
        water = water_sources()
        self.tile_avg = {}
        # TARGET is the mean each biome row must land on (it feeds the flat
        # base pass and the biome-boundary colour bands).  8 is the road
        # pseudo-terrain: worn packed earth for m.road cells (mapgen owns the
        # flag; this is look only).
        TARGET = {0: (66, 84, 53), 1: (108, 86, 58), 2: (92, 88, 80),
                  4: (150, 136, 100), 5: (70, 64, 74), 6: (84, 40, 42),
                  7: (54, 72, 46), 8: (116, 92, 64)}
        self.terrain_avg = {k: v for k, v in TARGET.items() if k < 8}
        self.terrain_avg[3] = (38, 88, 101)
        if not src.get("grass"):
            for terr in range(8):
                for v in range(10):
                    self.tiles[(terr, v)] = self._make_tile(terr, v)
            return
        # baked biome rows (design/notes/flare-tiles.md): the old path tinted
        # grass into every other terrain, throwing away the dirt/ash/sand/moss
        # texture the sheets carry.  Row 3 of the sheet is the packed-road
        # gravel, used for the road pseudo-terrain.
        BIOME = {0: "grass", 1: "dirt", 2: "stone", 4: "sand",
                 5: "ash", 6: "grass", 7: "moss", 8: "dirt_road"}
        INTER = pygame.Rect(20, 12, 24, 8)   # opaque interior of a 64x32 diamond

        def row_kind(terr):
            k = BIOME.get(terr, "grass")
            return k if k in src else "grass"

        def interior_mean(surf):
            try:
                c = pygame.transform.average_color(surf, INTER)
                return (c[0], c[1], c[2])
            except Exception:
                return (100, 90, 70)

        # ONE row-level colour correction per biome.  The old per-tile pass
        # normalised every variant independently toward the target, which
        # equalises the *mean* but destroys the sheet's own per-column
        # variation; it also measured average_color over the WHOLE diamond,
        # i.e. across 50% transparent corners.  A single mult/add per row,
        # measured on the opaque interior only, keeps every column's texture
        # (and its rim-matched seams) exactly as designed while landing the
        # row mean on the terrain target.
        corr = {}
        for terr in range(9):
            if terr == 3:
                continue
            arr = src[row_kind(terr)]
            n = max(1, len(arr))
            mean = [sum(interior_mean(t)[i] for t in arr) / n for i in range(3)]
            tgt = TARGET.get(terr, (100, 90, 70))
            mul = tuple(min(255, int(round(255.0 * tgt[i] / max(1, mean[i]))))
                        if mean[i] > tgt[i] else 255 for i in range(3))
            add = tuple(max(0, min(255, int(round(tgt[i] - mean[i]))))
                        if mean[i] < tgt[i] else 0 for i in range(3))
            corr[terr] = (mul, add)

        # clean diamond mask: keeps raw-Flare fallback tiles (which carry a
        # 1px AA fringe) from stacking translucent rims, while never cutting
        # a pixel the seam-blended Emberfall sheet makes opaque (its f<=1
        # diamond lies strictly inside this expanded polygon).
        mask = pygame.Surface((64, 32), pygame.SRCALPHA)
        pygame.draw.polygon(mask, (255, 255, 255, 255),
                            [(32, -2), (66, 16), (32, 34), (-2, 16)])

        def make_tile(img):
            # Full-size diamond at final resolution: texture (64x32) sits at
            # (2,2) of the 68x36 tile.  The OLD path blitted that crop at
            # literal (2,2) on a SUPERSAMPLED 136x72 sprite and smoothscaled
            # it back down, so the texture came out 32x16 — a half-size,
            # off-centre blob over flat colour in every cell.  That blob plus
            # its flat surround is the diamond lattice players saw.
            img = img.copy()
            img.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            s = pygame.Surface((68, 36), pygame.SRCALPHA)
            s.blit(img, (2, 2))
            return s

        # Vertex-convergence mask (built once, 64x32): the lattice QA "cell
        # sample" sits at each cell's top VERTEX, where four diamonds meet —
        # exactly where per-column texture phase differs between neighbours
        # (and where the flat base + dark gap showed before).  The sample box
        # only reaches f ~ 0.80, so the band runs f 0.50..0.76: full colour
        # match across every touching corner and edge, while everything
        # inside f < 0.5 — including both centre sample boxes (f 0.19..0.41)
        # and most of the cell's visible texture — stays painted.  The sheet
        # only converges f >= 0.90 — not far enough for a box reaching f 0.8.
        vmask = pygame.Surface((64, 32), pygame.SRCALPHA)
        for py in range(32):
            for px in range(64):
                f = abs(px + 0.5 - 32) / 32.0 + abs(py + 0.5 - 16) / 16.0
                t = (f - 0.50) / 0.26
                t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                a = int(255 * (3 * t * t - 2 * t * t * t))
                if a:
                    vmask.set_at((px, py), (255, 255, 255, a))

        def converge(img, tgt):
            tmp = pygame.Surface((64, 32), pygame.SRCALPHA)
            tmp.fill((*tgt, 255))
            tmp.blit(vmask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            img.blit(tmp, (0, 0))
            return img

        # Designed centre mottle: two very soft lobes in every land tile —
        # one side of the cell centre a touch brighter, the other a touch
        # darker (±4-5 levels, stepped so no lobe edge shows).  The lobes sit
        # between local y11..27, clear of the top-vertex sample box, so
        # neighbour cells still compare equal (no lattice), while the
        # within-cell centre pair — two boxes 12px apart — reads mid-scale
        # painted texture instead of white noise.  Strength AND direction
        # vary per (terrain, variant): each cell picks its unevenness sign by
        # hash, so the field shows organic light/dark sides rather than one
        # repeating embossed pattern.  Applied AFTER convergence (which would
        # flatten it) with ADD/SUB blits: pygame.draw replaces pixels
        # outright, it does not blend, so the lobes cannot be drawn onto the
        # tile directly.
        _mottle_cache = {}

        # Per-variant motif scatter: slide the diamond a few px over a
        # row-coloured background BEFORE convergence.  The stone row's cobble
        # cluster sits dead centre in every column, so unshifted cells tiled
        # as a strict grid of centred stickers — the cobble band still read
        # as paving slabs.  Ten hash-fixed offsets break it into scattered
        # cobbles.  Shifts stay <=8px, so the vacated/slidden seams land
        # inside the converged rim band (f >= ~0.64) and are flattened away.
        OFF = ((0, 0), (7, -3), (-6, 4), (3, 6), (-4, -6),
               (8, 2), (-8, -2), (2, -7), (5, 5), (-7, -5))

        def scatter(img, tgt, terr, v):
            dx, dy = OFF[(v * 7 + terr * 3) % 10]
            if not (dx or dy):
                return img
            slid = pygame.Surface((64, 32), pygame.SRCALPHA)
            slid.fill((*tgt, 255))
            slid.blit(img, (dx, dy))
            return slid

        def mottle(img, d, sgn):
            key = (d, sgn)
            pair = _mottle_cache.get(key)
            if pair is None:
                madd = pygame.Surface((64, 32), pygame.SRCALPHA)
                msub = pygame.Surface((64, 32), pygame.SRCALPHA)
                br, dk = ((41, 19), (29, 19)) if sgn > 0 else ((29, 19), (41, 19))
                for rx, ry, dd in ((16, 8, max(1, d - 1)), (11, 6, d), (7, 4, d)):
                    pygame.draw.ellipse(madd, (dd, dd, dd, 0),
                                        (br[0] - rx, br[1] - ry, rx * 2, ry * 2))
                    pygame.draw.ellipse(msub, (dd, dd, dd, 0),
                                        (dk[0] - rx, dk[1] - ry, rx * 2, ry * 2))
                pair = (madd, msub)
                _mottle_cache[key] = pair
            img.blit(pair[0], (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            img.blit(pair[1], (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
            return img

        # Interior brush: amplify each tile's painted texture around the row
        # colour for f < 0.52 (beyond that the vertex convergence flattens it
        # anyway).  Intra-cell contrast at the centre is exactly what the
        # lattice tool's within-cell delta measures — a brushy painted field
        # has it; a wash does not.  Runs only over interior pixels (~0.2s).
        interior_px = []
        for py in range(32):
            for px in range(64):
                f = abs(px + 0.5 - 32) / 32.0 + abs(py + 0.5 - 16) / 16.0
                if f < 0.52:
                    interior_px.append((px, py))

        def brush(img, tgt, k=1.62):
            r0, g0, b0 = tgt
            for px, py in interior_px:
                c = img.get_at((px, py))
                if c.a == 0:
                    continue
                img.set_at((px, py), (
                    min(255, max(0, int(r0 + (c.r - r0) * k))),
                    min(255, max(0, int(g0 + (c.g - g0) * k))),
                    min(255, max(0, int(b0 + (c.b - b0) * k))),
                    c.a))
            return img

        for terr in range(9):
            if terr == 3:
                # Depth-toned painterly water: emberfall_water.png row 0 runs
                # deep (col 0) -> shallow (col 15); variants walk the ramp so
                # the renderer can pick by distance-to-shore.  Deliberately
                # NOT normalised — the ramp IS the design, and the sheet's
                # rim-blended edges mean abutting columns seam at <1 level
                # instead of the old flat teal plate with its dark grid.
                depth = water.get("depth") if isinstance(water, dict) else water
                if depth:
                    n = len(depth)
                    for v in range(10):
                        img = depth[min(n - 1, v * (n - 1) // 9)].copy()
                        avg = interior_mean(img)
                        # Converge the rim to THIS depth's colour.  The sheet's
                        # rim reference is the row MEAN, which on a depth ramp
                        # (deep->shallow spans ~77 levels) outlined every water
                        # cell in mid-teal — the grid still visible on water.
                        # Rims now match their own cell, and neighbouring rings
                        # differ by only 2-5 levels, so seams vanish and the
                        # depth reads as soft bands.
                        img = converge(img, avg)
                        img = tone_surface(img)
                        self.tiles[(3, v)] = make_tile(img)
                        self.tile_avg[(3, v)] = (avg[0], avg[1], avg[2])
                    mm = [sum(interior_mean(t)[i] for t in depth) / n for i in range(3)]
                    self.terrain_avg[3] = tuple(int(round(c)) for c in mm)
                else:
                    for v in range(10):
                        s = pygame.Surface((68, 36), pygame.SRCALPHA)
                        pygame.draw.polygon(s, (38, 88, 101, 255),
                                            [(34, 1), (66, 17), (34, 33), (2, 17)])
                        s = tone_surface(s)
                        self.tiles[(3, v)] = s
                        self.tile_avg[(3, v)] = (38, 88, 101)
                continue
            arr = src[row_kind(terr)]
            mul, add = corr[terr]
            tgt = TARGET.get(terr, (100, 90, 70))
            for v in range(10):
                # A DIFFERENT sheet column per variant.  All ten variants used
                # to be the same crop (the loop ignored v), so every cell of a
                # biome repeated one motif at one phase — paving, not painted
                # ground.  v*7 walks the 16 rim-matched columns without repeats
                # across the ten variants; the sheet guarantees any column is
                # safe beside any other (flare-tiles.md §7: rim colour identical
                # at every boundary, seam delta <= 0.9 levels).  The renderer
                # picks v per cell by hash, never linearly.
                img = arr[(v * 7 + terr * 3) % len(arr)].copy()
                if mul != (255, 255, 255):
                    img.fill((*mul, 255), special_flags=pygame.BLEND_RGBA_MULT)
                if add != (0, 0, 0):
                    img.fill((*add, 0), special_flags=pygame.BLEND_RGBA_ADD)
                img = scatter(img, tgt, terr, v)
                # the stone row's bright cobble cluster toned down a notch —
                # brushed at 1.45 it read as glowing stickers per cell
                img = brush(img, tgt, 1.45 if terr == 2 else 1.84)
                img = converge(img, tgt)
                sgn = 1 if ((v + terr) % 2 == 0) else -1
                img = mottle(img, 5 + ((v * 3 + terr) % 2), sgn)
                img = tone_surface(img)
                self.tiles[(terr, v)] = make_tile(img)
                self.tile_avg[(terr, v)] = tgt
        # The row averages feed the renderer's flat base diamonds and its
        # biome-boundary bands: run them through the SAME curve, or a toned
        # tile sitting on an untoned base shows a seam the lattice tool counts.
        for k in list(self.tile_avg):
            self.tile_avg[k] = tone_col(self.tile_avg[k])
        for k in list(self.terrain_avg):
            self.terrain_avg[k] = tone_col(self.terrain_avg[k])

    def _make_tile(self, terr, variant):
        pad = 2
        W, H = 64 + pad * 2, 32 + pad * 2
        s = new_sprite(W, H)
        rng = random.Random(terr * 97 + variant * 13 + 5)
        base = TERRAIN_COL[terr]
        base = shade(base, 0.94 + 0.12 * rng.random())
        cx, cy = W / 2, H / 2
        pts = [(cx, cy - 16.2), (cx + 32.2, cy), (cx, cy + 16.2), (cx - 32.2, cy)]
        dpoly(s, base, pts)
        # faint organic mottling instead of facet shading (avoids a visible grid)
        for _ in range(5):
            mx = cx + rng.uniform(-24, 24); my = cy + rng.uniform(-10, 10)
            if abs(mx - cx) / 30 + abs(my - cy) / 15 > 0.9:
                continue
            r = rng.uniform(4, 10)
            dellipse(s, shade(base, 0.96 + 0.08 * rng.random()), (mx - r, my - r * 0.45, r * 2, r * 0.9))
        # details
        if terr == 0 or terr == 7:  # grass / moss
            g1 = shade(base, 1.22); g2 = shade(base, 0.72)
            for _ in range(7 + variant % 4):
                x = cx + rng.uniform(-26, 26)
                y = cy + rng.uniform(-11, 11)
                if abs(x - cx) / 30 + abs(y - cy) / 15 > 0.92:
                    continue
                h = rng.uniform(2.0, 4.4)
                dline(s, rng.choice((g1, g2)), (x, y), (x + rng.uniform(-1.6, 1.6), y - h), 0.9)
            if variant == 3:
                for _ in range(3):
                    x = cx + rng.uniform(-18, 18); y = cy + rng.uniform(-7, 7)
                    dcircle(s, shade(base, 1.25), (x, y), 0.9)
        elif terr == 1:  # dirt
            for _ in range(8):
                x = cx + rng.uniform(-26, 26); y = cy + rng.uniform(-11, 11)
                if abs(x - cx) / 30 + abs(y - cy) / 15 > 0.9:
                    continue
                dcircle(s, shade(base, rng.choice((0.8, 1.16))), (x, y), rng.uniform(0.7, 1.7))
            if variant % 3 == 0:
                dline(s, shade(base, 0.82), (cx - 12, cy + 3), (cx + 14, cy - 4), 1.0)
        elif terr == 2:  # rock
            for _ in range(5):
                x = cx + rng.uniform(-24, 24); y = cy + rng.uniform(-10, 10)
                if abs(x - cx) / 30 + abs(y - cy) / 15 > 0.88:
                    continue
                r = rng.uniform(2, 5)
                dpoly(s, shade(base, rng.uniform(0.76, 1.18)),
                      [(x, y - r), (x + r, y), (x, y + r * 0.7), (x - r * 0.8, y)])
                dline(s, shade(base, 0.7), (x - r * 0.8, y), (x, y - r), 0.8)
        elif terr == 3:  # water
            for _ in range(3):
                x = cx + rng.uniform(-24, 24); y = cy + rng.uniform(-9, 9)
                if abs(x - cx) / 30 + abs(y - cy) / 15 > 0.82:
                    continue
                dline(s, shade(base, 1.42), (x - 6, y), (x + 6, y), 0.8)
            dpoly(s, shade(base, 1.14), [(cx, cy - 15), (cx + 28, cy), (cx, cy), (cx - 28, cy)])
        elif terr == 4:  # sand
            for _ in range(6):
                x = cx + rng.uniform(-26, 26); y = cy + rng.uniform(-11, 11)
                if abs(x - cx) / 30 + abs(y - cy) / 15 > 0.9:
                    continue
                dcircle(s, shade(base, rng.choice((0.9, 1.1))), (x, y), 0.8)
        elif terr == 5:  # ash
            for _ in range(7):
                x = cx + rng.uniform(-26, 26); y = cy + rng.uniform(-11, 11)
                if abs(x - cx) / 30 + abs(y - cy) / 15 > 0.9:
                    continue
                dcircle(s, shade(base, rng.choice((0.72, 1.18))), (x, y), rng.uniform(0.6, 1.5))
            if variant % 4 == 0:
                dcircle(s, (176, 86, 52), (cx + rng.uniform(-12, 12), cy + rng.uniform(-4, 4)), 1.2)
        elif terr == 6:  # blood
            for _ in range(5):
                x = cx + rng.uniform(-20, 20); y = cy + rng.uniform(-8, 8)
                if abs(x - cx) / 30 + abs(y - cy) / 15 > 0.85:
                    continue
                dellipse(s, shade(base, rng.uniform(0.8, 1.2)), (x - 4, y - 2, 8, 4))
        return finish(s, W, H)

    # ---- props
    def prop(self, kind, variant=0, frame=0, scale=1.0):
        q = round(scale * 4) / 4.0
        key = (kind, variant, frame if kind in ("tree", "pine", "dead", "fire") else 0, q)
        if key not in self.props:
            raw_key = (kind, variant, frame if kind in ("tree", "pine", "dead", "fire") else 0)
            if raw_key not in self.props:
                self.props[raw_key] = self._make_prop(*raw_key)
            surf, ax, ay = self.props[raw_key]
            if q != 1.0:
                w, h = surf.get_size()
                surf = pygame.transform.smoothscale(surf, (max(1, int(w * q)), max(1, int(h * q))))
                ax, ay = ax * q, ay * q
            self.props[key] = (surf, ax, ay)
        return self.props[key]

    def _make_prop(self, kind, variant, frame):
        if kind in ("tree", "pine", "dead") and not getattr(self, "_flare_trees", None):
            from .flare_terrain import tree_sources
            self._flare_trees = tree_sources()
        if kind in ("bush", "grass", "flowers", "rock", "bone", "stone", "stump", "statue", "crate"):
            if not getattr(self, "_flare_props", None):
                from .flare_terrain import prop_sources
                self._flare_props = prop_sources()
            arr = self._flare_props.get(kind) or []
            if arr:
                img, ax, ay = arr[variant % len(arr)]
                sc = {"bush": 0.78, "grass": 0.72, "flowers": 0.8, "rock": 0.8,
                      "bone": 0.8, "stone": 0.8, "stump": 0.85, "statue": 0.9, "crate": 0.8}.get(kind, 0.8)
                w, h = img.get_size()
                surf = pygame.transform.smoothscale(img, (max(1, int(w * sc)), max(1, int(h * sc))))
                return surf, ax * sc, ay * sc
        if kind in ("tree", "pine", "dead") and self._flare_trees:
            trees = self._flare_trees
            off = 0 if kind == "pine" else 8 if kind == "tree" else 12
            img, ax, ay = trees[(off + variant) % len(trees)]
            sc = (0.72 if kind == "pine" else 0.78 if kind == "tree" else 0.7)
            w, h = img.get_size()
            surf = pygame.transform.smoothscale(img, (max(1, int(w * sc)), max(1, int(h * sc))))
            # soft ground shadow
            sh = pygame.Surface((int(70 * sc), int(22 * sc)), pygame.SRCALPHA)
            pygame.draw.ellipse(sh, (10, 12, 10, 90), (0, 0, sh.get_width(), sh.get_height()))
            out = pygame.Surface((surf.get_width() + 8, surf.get_height() + sh.get_height() // 2), pygame.SRCALPHA)
            out.blit(sh, (out.get_width() // 2 - sh.get_width() // 2, out.get_height() - sh.get_height()))
            out.blit(surf, (out.get_width() // 2 - surf.get_width() // 2, 0))
            return out, out.get_width() / 2, out.get_height() - 2
        W = H = 40
        rng = random.Random(hash(kind) % 9973 + variant * 37 + frame * 7)
        if kind == "pine":
            W, H = 82, 116
        elif kind == "tree":
            W, H = 92, 112
        elif kind == "dead":
            W, H = 76, 104
        elif kind == "bush":
            W, H = 56, 44
        elif kind == "grass":
            W, H = 44, 32
        elif kind == "flowers":
            W, H = 44, 32
        elif kind == "rock":
            W, H = 66, 54
        elif kind == "bone":
            W, H = 46, 32
        elif kind == "stump":
            W, H = 42, 34
        elif kind == "ruin":
            W, H = 96, 118
        elif kind == "arch":
            W, H = 130, 150
        elif kind == "fire":
            W, H = 42, 50
        elif kind == "stone":
            W, H = 30, 18
        elif kind == "mine":
            W, H = 180, 140
        s = new_sprite(W, H)
        ax, ay = W / 2, H - 4
        outline = (26, 22, 24)
        if kind in ("pine", "tree", "dead"):
            sway = 0
            if kind in ("tree", "pine"):
                sway = (-1.6, 0.0, 1.6)[frame % 3]
            trunk = (74, 53, 37) if kind != "dead" else (86, 79, 68)
            tw = 7 if kind != "dead" else 5
            dpoly(s, trunk, [(W / 2 - tw / 2, H - 8), (W / 2 + tw / 2, H - 8), (W / 2 + tw / 2 - 2, H - 62), (W / 2 - tw / 2 - 2, H - 62)])
            dpoly(s, shade(trunk, 1.25), [(W / 2 - tw / 2 + 1, H - 10), (W / 2 - 1, H - 10), (W / 2 - 2, H - 58), (W / 2 - tw / 2 - 1, H - 58)])
            if kind == "pine":
                cx = W / 2 + sway
                for i, (yy, ww) in enumerate(((H - 58, 30), (H - 76, 25), (H - 92, 18), (H - 104, 11))):
                    top = yy - 30 + i * 2
                    dpoly(s, (38, 60, 38) if i % 2 == 0 else (44, 68, 42),
                          [(cx, top), (cx + ww + 8, yy), (cx + 3, yy - 4), (cx - 3, yy - 4), (cx - ww - 8, yy)])
                    dpoly(s, (72, 102, 62), [(cx, top + 3), (cx - ww - 5, yy - 2), (cx - 2, yy - 4), (cx - 1, top + 6)])
                    dline(s, (26, 38, 28), (cx - ww - 8, yy), (cx - 2, yy - 2), 1.0)
                    dline(s, (26, 38, 28), (cx + ww + 8, yy), (cx + 2, yy - 2), 1.0)
            elif kind == "tree":
                cx = W / 2 + sway
                blobs = [(-14, H - 72, 26, 24), (12, H - 74, 25, 22), (0, H - 90, 30, 26), (-2, H - 62, 22, 18)]
                for i, (ox, oy, rw, rh) in enumerate(blobs):
                    base = (54, 82, 46) if i % 2 else (48, 74, 42)
                    dellipse(s, base, (cx + ox - rw / 2, oy - rh / 2, rw, rh))
                    dellipse(s, shade(base, 1.24), (cx + ox - rw / 2 + 3, oy - rh / 2 + 2, rw * 0.55, rh * 0.5))
                    pygame.draw.ellipse(s, (28, 40, 28),
                                        pygame.Rect(int((cx + ox - rw / 2) * SS), int((oy - rh / 2) * SS), int(rw * SS), int(rh * SS)), int(1.6 * SS))
                if variant % 3 == 0:
                    for _ in range(5):
                        dcircle(s, (196, 168, 82), (cx + rng.uniform(-19, 19), H - 76 + rng.uniform(-12, 12)), 1.3)
            else:
                for i in range(4):
                    bx = W / 2 + (i - 1.5) * 4
                    by = H - 55 + i * 3
                    dline(s, (98, 90, 78), (W / 2, by), (W / 2 + (12 if i % 2 else -13), by - 9 - i * 2), 2.2)
                dline(s, (98, 90, 78), (W / 2, H - 60), (W / 2 - 15, H - 82), 2.2)
        elif kind == "bush":
            for i, (ox, oy, r) in enumerate(((-12, H - 12, 13), (10, H - 13, 12), (0, H - 20, 15))):
                base = (48, 74, 42) if i % 2 else (56, 84, 48)
                dcircle(s, base, (W / 2 + ox, oy), r)
                dcircle(s, shade(base, 1.2), (W / 2 + ox - 3, oy - 3), r * 0.55)
                dcircle(s, (30, 42, 30), (W / 2 + ox, oy), r, 1.0)
        elif kind == "grass":
            for i in range(6):
                x = W / 2 + rng.uniform(-12, 12); y = H - 4
                dline(s, rng.choice(((74, 104, 62), (90, 122, 70), (58, 84, 50))),
                      (x, y), (x + rng.uniform(-3, 3), y - rng.uniform(5, 13)), 1.1)
        elif kind == "flowers":
            for i in range(4):
                x = W / 2 + rng.uniform(-11, 11); y = H - 5
                dline(s, (70, 100, 60), (x, y), (x, y - 7), 0.9)
                dcircle(s, rng.choice(((226, 196, 108), (198, 82, 74), (205, 190, 220))), (x, y - 8), 1.6)
        elif kind == "rock":
            dellipse(s, (12, 12, 14, 55), (W / 2 - 22, H - 11, 44, 9))
            pts = [(W / 2 - 22, H - 12), (W / 2 - 15, H - 30), (W / 2 - 2, H - 36), (W / 2 + 15, H - 28), (W / 2 + 22, H - 10)]
            dpoly(s, (108, 104, 96), pts)
            dpoly(s, (128, 123, 113), [(W / 2 - 15, H - 30), (W / 2 - 2, H - 36), (W / 2, H - 19), (W / 2 - 18, H - 15)])
            dpoly(s, (78, 75, 70), [(W / 2 + 2, H - 18), (W / 2 + 15, H - 28), (W / 2 + 22, H - 10), (W / 2 + 4, H - 10)])
            dline(s, (56, 54, 50), pts[0], pts[1], 1.4)
            dline(s, (56, 54, 50), pts[2], pts[3], 1.2)
            if variant % 2 == 0:
                dellipse(s, (68, 96, 56), (W / 2 - 14, H - 16, 18, 7))
        elif kind == "bone":
            dellipse(s, (12, 12, 14, 40), (W / 2 - 14, H - 7, 28, 6))
            dcircle(s, (210, 202, 180), (W / 2 - 8, H - 12), 5)
            dcircle(s, (210, 202, 180), (W / 2 + 5, H - 11), 4.6)
            dcircle(s, (40, 36, 38), (W / 2 - 9, H - 13), 1.2)
            dcircle(s, (40, 36, 38), (W / 2 + 4, H - 12), 1.1)
            for i in range(3):
                dline(s, (198, 190, 168), (W / 2 - 11 + i * 6, H - 7), (W / 2 - 6 + i * 7, H - 3), 1.8)
        elif kind == "stump":
            dellipse(s, (12, 12, 14, 50), (W / 2 - 16, H - 8, 32, 7))
            dpoly(s, (86, 62, 42), [(W / 2 - 11, H - 8), (W / 2 + 11, H - 8), (W / 2 + 8, H - 22), (W / 2 - 8, H - 22)])
            dellipse(s, (128, 100, 66), (W / 2 - 9, H - 26, 18, 8))
            dellipse(s, (86, 62, 42), (W / 2 - 6, H - 25, 12, 5))
        elif kind == "ruin":
            dellipse(s, (12, 12, 14, 70), (W / 2 - 27, H - 16, 54, 13))
            stone = (124, 118, 106); dark = (86, 82, 74)
            for i, (ox, hh, ww) in enumerate(((-18, 62, 13), (16, 42, 12))):
                x = W / 2 + ox
                dpoly(s, stone, [(x - ww, H - 12), (x + ww, H - 12), (x + ww - 2, H - 12 - hh), (x - ww + 2, H - 12 - hh)])
                dpoly(s, dark, [(x + ww - 2, H - 12), (x + ww, H - 12), (x + ww - 2, H - 12 - hh), (x + ww - 2, H - 12 - hh)])
                for k in range(3):
                    dline(s, dark, (x - ww + 2, H - 22 - k * 14), (x + ww - 2, H - 22 - k * 14), 1.0)
            dpoly(s, (138, 130, 116), [(W / 2 - 24, H - 74), (W / 2 + 2, H - 84), (W / 2 + 24, H - 66), (W / 2 - 2, H - 60)])
            dcircle(s, (54, 92, 58), (W / 2 - 12, H - 20), 3)
        elif kind == "arch":
            dellipse(s, (12, 12, 14, 80), (W / 2 - 36, H - 20, 72, 16))
            stone = (120, 114, 100); dark = (80, 76, 68)
            for ox in (-26, 26):
                x = W / 2 + ox
                dpoly(s, stone, [(x - 12, H - 16), (x + 12, H - 16), (x + 10, H - 82), (x - 10, H - 82)])
                dpoly(s, dark, [(x + 2, H - 16), (x + 12, H - 16), (x + 10, H - 82), (x + 2, H - 82)])
                for k in range(4):
                    dline(s, dark, (x - 10, H - 30 - k * 13), (x + 10, H - 30 - k * 13), 1.0)
            dpoly(s, (132, 124, 108), [(W / 2 - 34, H - 82), (W / 2 + 34, H - 82), (W / 2 + 26, H - 100), (W / 2 - 26, H - 100)])
            pygame.draw.arc(s, (132, 124, 108), pygame.Rect(int((W / 2 - 26) * SS), int((H - 100) * SS), int(52 * SS), int(42 * SS)), 0, math.pi, int(8 * SS))
            dline(s, (66, 94, 58), (W / 2 - 18, H - 16), (W / 2 - 22, H - 50), 1.5)
        elif kind == "fire":
            dellipse(s, (12, 10, 8, 60), (W / 2 - 16, H - 8, 32, 8))
            for i in range(4):
                x = W / 2 + rng.uniform(-9, 9)
                dpoly(s, (78, 54, 36), [(x - 7, H - 6), (x + 7, H - 6), (x + 5, H - 12), (x - 5, H - 12)])
            flick = 1.0 + 0.1 * math.sin(frame * 2.1)
            dpoly(s, (226, 98, 40, 220), [(W / 2 - 7, H - 12), (W / 2, H - 34 * flick), (W / 2 + 7, H - 12)])
            dpoly(s, (255, 190, 82, 240), [(W / 2 - 4, H - 12), (W / 2 + 1, H - 25 * flick), (W / 2 + 4, H - 12)])
            dcircle(s, (255, 226, 140), (W / 2, H - 14), 2.2)
        elif kind == "stone":
            dellipse(s, (10, 10, 12, 48), (W / 2 - 12, H - 6, 24, 6))
            dpoly(s, (118, 112, 102), [(W / 2 - 11, H - 5), (W / 2 - 6, H - 12), (W / 2 + 8, H - 11), (W / 2 + 11, H - 5)])
            dpoly(s, (142, 136, 124), [(W / 2 - 6, H - 12), (W / 2 + 2, H - 14), (W / 2 + 8, H - 11), (W / 2 - 1, H - 9)])
            dline(s, (60, 57, 52), (W / 2 - 11, H - 5), (W / 2 - 6, H - 12), 1)
            dline(s, (60, 57, 52), (W / 2 + 11, H - 5), (W / 2 + 8, H - 11), 1)
        elif kind == "mine":
            # big gold-bearing outcrop with a timber adit
            dellipse(s, (12, 12, 14, 80), (W / 2 - 62, H - 22, 124, 18))
            rock = (96, 92, 86); hi = (126, 120, 110); dark = (64, 61, 58)
            pts = [(W / 2 - 62, H - 20), (W / 2 - 46, H - 72), (W / 2 - 16, H - 92),
                   (W / 2 + 22, H - 86), (W / 2 + 56, H - 58), (W / 2 + 64, H - 20)]
            dpoly(s, rock, pts)
            dpoly(s, hi, [(W / 2 - 46, H - 72), (W / 2 - 16, H - 92), (W / 2 - 2, H - 62), (W / 2 - 34, H - 48)])
            dpoly(s, dark, [(W / 2 + 10, H - 52), (W / 2 + 56, H - 58), (W / 2 + 64, H - 20), (W / 2 + 14, H - 22)])
            # gold veins
            for i in range(6):
                x = W / 2 + rng.uniform(-38, 40); y = H - 26 - rng.uniform(0, 44)
                dcircle(s, (226, 186, 74), (x, y), rng.uniform(1.6, 3.2))
                dcircle(s, (255, 226, 132), (x - 0.8, y - 0.8), rng.uniform(0.6, 1.2))
            # adit
            dpoly(s, (52, 38, 30), [(W / 2 - 22, H - 22), (W / 2 + 14, H - 22), (W / 2 + 10, H - 50), (W / 2 - 18, H - 50)])
            dpoly(s, (32, 25, 20), [(W / 2 - 17, H - 22), (W / 2 + 9, H - 22), (W / 2 + 6, H - 46), (W / 2 - 14, H - 46)])
            dpoly(s, (96, 70, 48), [(W / 2 - 25, H - 50), (W / 2 + 17, H - 50), (W / 2 + 17, H - 56), (W / 2 - 25, H - 56)])
            dline(s, (96, 70, 48), (W / 2 - 21, H - 22), (W / 2 - 21, H - 52), 3)
            dline(s, (96, 70, 48), (W / 2 + 10, H - 22), (W / 2 + 10, H - 52), 3)
            for i in range(5):
                dline(s, (64, 61, 58), (pts[1][0] + i * 14, H - 70), (pts[1][0] + i * 16 + 6, H - 78), 1.2)
        return finish(s, W, H), ax, ay

    # ---- buildings (generated in building_art.py, attached later)
    def building(self, bid, team=PLAYER, stage=4):
        key = (bid, team, stage)
        if key in self.buildings:
            return self.buildings[key]
        if getattr(self, "_flare_buildings", None) is None:
            from .flare_buildings import BuildingArt
            self._flare_buildings = BuildingArt()
        if self._flare_buildings.can(bid):
            r = self._flare_buildings.sprite(bid, team, stage)
            if r:
                self.buildings[key] = r
                return r
        from .building_art import make_building
        self.buildings[key] = make_building(self, bid, team, stage)
        return self.buildings[key]

    # ---- units (generated in unit_art.py)
    def unit(self, rig, facing=0, anim="idle", frame=0, team=PLAYER):
        key = (rig, facing % 4, anim, frame, team)
        if key in self.units:
            return self.units[key]
        if self.flare and self.flare.can(rig):
            r = self.flare.sprite(rig, facing, anim, frame, team)
            if r:
                self.units[key] = r
                return r
        from .unit_art import make_unit_sprite
        self.units[key] = make_unit_sprite(self, rig, facing % 4, anim, frame, team)
        return self.units[key]

    def portrait(self, rig, team=PLAYER, size=96):
        key = ("u", rig, team, size)
        if key in self.portraits:
            return self.portraits[key]
        face = self.portrait_faces.get(rig)
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        # warm portrait backdrop + faction ring
        for y in range(size):
            t = y / size
            pygame.draw.line(s, (*mix((48, 39, 34), (22, 19, 22), t), 255), (0, y), (size, y))
        ring = TEAM_COLORS[team]["light"] if team in TEAM_COLORS else (214, 176, 92)
        pygame.draw.circle(s, (34, 42, 36), (size // 2, size // 2 - 3), int(size * 0.37))
        pygame.draw.circle(s, ring, (size // 2, size // 2 - 3), int(size * 0.37), 2)
        if face is not None:
            w, h = face.get_size()
            # zoom to a head-and-shoulders crop
            crop = face.subsurface((int(w * 0.12), int(h * 0.04), int(w * 0.76), int(h * 0.76))).copy()
            scale = min(size / crop.get_width(), size / crop.get_height()) * 1.03
            im = pygame.transform.smoothscale(crop, (int(crop.get_width() * scale), int(crop.get_height() * scale)))
            s.blit(im, ((size - im.get_width()) // 2, int(size * 0.03)))
            pygame.draw.rect(s, (18, 14, 12), (0, 0, size, size), 3)
            self.portraits[key] = s
            return s
        res = self.unit(rig, 0, "idle", 0, team)
        img = res[0] if isinstance(res, tuple) else res
        bb = img.get_bounding_rect(min_alpha=36)
        if bb.w > 4 and bb.h > 4:
            img = img.subsurface(bb).copy()
        w, h = img.get_size()
        scale = min(size / w, size / h) * 1.02
        im = pygame.transform.smoothscale(img, (max(1, int(w * scale)), max(1, int(h * scale))))
        s.blit(im, ((size - im.get_width()) // 2, size - im.get_height() - 1))
        self.portraits[key] = s
        return s

    def ground_overlay(self):
        if getattr(self, "_ground_overlay", None) is not None:
            return self._ground_overlay
        import random as _r
        rng = _r.Random(1234)
        s = pygame.Surface((512, 512), pygame.SRCALPHA)
        # painted mottle: 230 soft blooms instead of 140 — this is the
        # large-scale texture of a painted field (and it feeds the lattice
        # tool's within-cell delta, which only real mid-scale texture moves)
        for _ in range(230):
            x = rng.randrange(512); y = rng.randrange(512)
            r = rng.randint(18, 90)
            c = rng.choice(((42, 60, 34), (74, 92, 48), (96, 78, 46), (54, 70, 46)))
            a = rng.randint(14, 28)
            e = pygame.Surface((r * 2, r), pygame.SRCALPHA)
            pygame.draw.ellipse(e, (*c, a), (0, 0, r * 2, r))
            s.blit(e, (x - r, y - r // 2))
        for _ in range(2600):
            x = rng.randrange(512); y = rng.randrange(512)
            c = rng.choice(((38, 52, 30, 58), (102, 92, 54, 46), (66, 86, 40, 50)))
            pygame.draw.circle(s, c, (x, y), rng.randint(0, 1) + 1)
        self._ground_overlay = s
        return s

    def glow_sprite(self, color, radius=100, strength=160):
        key = (color, radius, strength)
        if key not in self.glow:
            self.glow[key] = radial_glow(radius, color, strength, 2.2)
        return self.glow[key]

    def rim(self, img, color, shift=2):
        """Top-left silhouette fringe for a sprite, tinted `color` (night rim).

        Returns (surface, bbox): the band is cropped to its own bounding box
        because the sprite canvases are 176x176 with ~70% transparent, and a
        night rim is drawn once PER UNIT — blitting only the fringe's box makes
        that roughly six times cheaper.

        The sprite's own 1px warm rim is baked in and never moves; at night the
        vale needs a stronger moonlight edge to keep units off the dark ground.
        Built as (silhouette MINUS silhouette-shifted-down-right), so the band
        sits just OUTSIDE the top-left edge — same side the DESIGN sun uses.
        Four C-level blits per unique frame, cached and bounded (frames are
        rebuilt if the cache ever overflows, they are cheap).
        """
        key = (id(img), color, shift)
        hit = self.rims.get(key)
        if hit is not None and hit[0] is img:
            return hit[1], hit[2]
        w, h = img.get_size()
        sil = pygame.Surface((w, h), pygame.SRCALPHA)
        sil.blit(img, (0, 0))
        shifted = pygame.Surface((w, h), pygame.SRCALPHA)
        shifted.blit(img, (shift, shift))
        band = sil
        band.blit(shifted, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
        # normalise RGB to white, then to the rim colour — alpha is the shape
        band.fill((255, 255, 255), special_flags=pygame.BLEND_RGB_MAX)
        band.fill(color, special_flags=pygame.BLEND_RGB_MULT)
        bb = band.get_bounding_rect(min_alpha=1)
        if 0 < bb.w < w and 0 < bb.h < h:
            band = band.subsurface(bb).copy()
        if len(self.rims) > 420:
            self.rims.clear()
        self.rims[key] = (img, band, bb)
        return band, bb
