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
        self.glow = {}
        self._gen_tiles()
        self._load_fonts()
        self._load_icons()

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
        # downloaded display fonts win if present
        for name, fname in (("display", "Cinzel-Bold.ttf"), ("display_regular", "Cinzel-Regular.ttf"),
                            ("serif", "EBGaramond-Regular.ttf"), ("serif_bold", "EBGaramond-Bold.ttf")):
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
        f = self.font(size, face)
        img = f.render(str(text), True, color)
        if not shadow:
            return img
        out = pygame.Surface((img.get_width() + 2, img.get_height() + 2), pygame.SRCALPHA)
        sh = f.render(str(text), True, (0, 0, 0, 160))
        out.blit(sh, (1, 1))
        out.blit(img, (0, 0))
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
                key = fn[5:-4]
                try:
                    self.icons[key] = pygame.image.load(os.path.join(d, fn)).convert_alpha()
                except Exception:
                    pass

    def icon(self, key, size=64):
        img = self.icons.get(key)
        if img is None:
            s = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.rect(s, (52, 45, 38), (0, 0, size, size), border_radius=6)
            pygame.draw.rect(s, (120, 104, 80), (0, 0, size, size), 2, border_radius=6)
            gl = self.font(max(12, size // 3), "display").render((key or "?")[0].upper(), True, PARCH)
            s.blit(gl, ((size - gl.get_width()) // 2, (size - gl.get_height()) // 2))
            return s
        return pygame.transform.smoothscale(img, (size, size))

    # ---- water/tile generation
    def _gen_tiles(self):
        for terr in range(8):
            for v in range(10):
                self.tiles[(terr, v)] = self._make_tile(terr, v)

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
        if key not in self.buildings:
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
        img = self.unit(rig, 0, "idle", 0, team)
        w, h = img.get_size()
        s = pygame.Surface((size, size), pygame.SRCALPHA)
        # warm portrait backdrop
        for y in range(size):
            t = y / size
            pygame.draw.line(s, (*mix((44, 36, 34), (22, 19, 22), t), 255), (0, y), (size, y))
        pygame.draw.circle(s, (36, 45, 38), (size // 2, size // 2 - 4), size // 3)
        pygame.draw.circle(s, (58, 70, 54), (size // 2, size // 2 - 4), size // 3, 2)
        scale = min(size / w, size / h) * 1.16
        im = pygame.transform.smoothscale(img, (max(1, int(w * scale)), max(1, int(h * scale))))
        s.blit(im, ((size - im.get_width()) // 2, size - im.get_height() + 4))
        self.portraits[key] = s
        return s

    def glow_sprite(self, color, radius=100, strength=160):
        key = (color, radius, strength)
        if key not in self.glow:
            self.glow[key] = radial_glow(radius, color, strength, 2.2)
        return self.glow[key]
