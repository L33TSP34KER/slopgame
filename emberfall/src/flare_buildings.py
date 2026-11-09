"""Compose professional Flare building crops into game buildings."""
from __future__ import annotations
import os, math
import pygame
from .defs import *
from .art import shade, mix, INK, GOLD

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIR = os.path.join(ROOT, "assets", "flare", "buildings")

LAYERS = {
    "townhall": [("human_town_hall", 1.0, 0.0, 0.0, None)],
    "keep": [("human_keep", 1.0, 0.0, 0.0, None)],
    "farm": [("human_house_farm", 1.0, 0.0, 0.0, None)],
    "barracks": [("human_barracks", 1.0, 0.0, 0.0, None)],
    "mill": [("human_workshop_lumber", 1.0, 0.0, 0.0, None),
             ("human_house_farm", 0.34, -0.22, 0.06, None)],
    "blacksmith": [("human_house_farm", 0.64, 0.0, 0.05, None),
                   ("human_blacksmith_smithy", 0.70, 0.16, -0.04, None)],
    "sanctum": [("human_temple_altar", 1.0, 0.0, 0.0, None)],
    "tower": [("human_guard_tower", 1.0, 0.0, 0.0, None)],
    "altar": [("human_temple_altar", 0.82, 0.0, 0.0, None)],
    "necropolis": [("undead_necropolis_ruin", 1.0, 0.0, 0.0, None)],
    "ziggurat": [("undead_ziggurat_ruin", 1.0, 0.0, 0.0, None)],
    "crypt": [("undead_crypt", 1.0, 0.0, 0.0, None)],
    "slaughterhouse": [("undead_ruined_tower", 1.0, 0.0, 0.0, None),
                       ("undead_bone_ritual", 0.35, 0.25, 0.05, (0.8, 0.7, 0.9))],
    "temple": [("undead_bone_ritual", 1.0, 0.0, 0.0, None),
               ("undead_crypt", 0.5, -0.05, 0.12, (0.8, 0.7, 1.0))],
    "bonetower": [("human_guard_tower", 1.0, 0.0, 0.0, (0.62, 0.54, 0.82))],
    "altarhollow": [("undead_bone_ritual", 1.0, 0.0, 0.0, (0.85, 0.75, 1.0))],
}
TARGET_W = {"townhall": 250, "keep": 270, "farm": 145, "barracks": 205, "mill": 195,
            "blacksmith": 195, "sanctum": 195, "tower": 95, "altar": 120,
            "necropolis": 380, "ziggurat": 135, "crypt": 195, "slaughterhouse": 205,
            "temple": 195, "bonetower": 95, "altarhollow": 190}
BANNER = {PLAYER: (172, 58, 48), ENEMY: (110, 74, 150), NEUTRAL: (140, 120, 80)}


def _tint(surf, mul):
    out = surf.copy()
    out.fill((int(mul[0] * 255), int(mul[1] * 255), int(mul[2] * 255), 255),
             special_flags=pygame.BLEND_RGBA_MULT)
    return out


class BuildingArt:
    def __init__(self):
        self.src = {}
        self.cache = {}
        if not os.path.isdir(DIR):
            return
        for fn in os.listdir(DIR):
            if fn.endswith(".png"):
                try:
                    self.src[fn[:-4]] = pygame.image.load(os.path.join(DIR, fn)).convert_alpha()
                except Exception:
                    pass

    def can(self, bid):
        return bid in LAYERS and any(n in self.src for n, *_ in LAYERS[bid])

    def sprite(self, bid, team, stage):
        key = (bid, team, stage)
        if key in self.cache:
            return self.cache[key]
        layers = LAYERS.get(bid, [])
        target = TARGET_W.get(bid, 220)
        # estimate height from first layer
        first = next((self.src[n] for n, *_ in layers if n in self.src), None)
        if first is None:
            return None
        ar = first.get_height() / max(1, first.get_width())
        tw = target
        th = int(tw * ar)
        W = int(tw * 1.65) + 80
        H = th + 150
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        cx = W / 2
        base_y = H - 24
        # ground contact shadow
        pygame.draw.ellipse(s, (10, 9, 12, 95), (cx - tw * 0.44, base_y - 18, tw * 0.88, 34))
        for name, sc, dx, dy, tint in layers:
            img = self.src.get(name)
            if img is None:
                continue
            bb = img.get_bounding_rect(min_alpha=8)
            if bb.w < 4 or bb.h < 4:
                bb = img.get_rect()
            img = img.subsurface(bb).copy()
            w = int(tw * sc)
            h = int(img.get_height() * w / max(1, img.get_width()))
            img = pygame.transform.smoothscale(img, (max(1, w), max(1, h)))
            if tint:
                img = _tint(img, tint)
            px = int(cx - w / 2 + dx * tw)
            py = int(base_y - h + dy * th)
            if stage < 4:
                frac = (0.30, 0.50, 0.72, 0.88)[stage]
                cut = max(8, int(h * frac))
                piece = img.subsurface((0, h - cut, w, cut))
                s.blit(piece, (px, base_y - cut + dy * th))
            else:
                s.blit(img, (px, py))
        self._fx(s, bid, cx, base_y, tw, th, team)
        # team banner
        if stage >= 3:
            bx = cx - tw * 0.40
            by = base_y - th * 0.55
            col = BANNER.get(team, BANNER[PLAYER])
            pygame.draw.line(s, (64, 50, 34), (bx, base_y - 4), (bx, by), 3)
            pts = [(bx, by), (bx + 24, by + 5), (bx + 20, by + 22), (bx, by + 18)]
            pygame.draw.polygon(s, (24, 20, 24), pts)
            inner = [(bx + 1, by + 2), (bx + 21, by + 6), (bx + 18, by + 19), (bx + 1, by + 16)]
            pygame.draw.polygon(s, col, inner)
            pygame.draw.circle(s, GOLD, (int(bx + 9), int(by + 10)), 2)
        if stage < 4:
            # scaffolding
            for i in range(4):
                x = cx - tw * 0.42 + i * tw * 0.28
                pygame.draw.line(s, (120, 92, 58), (x, base_y), (x, base_y - th * 0.7), 2)
                if i < 3:
                    pygame.draw.line(s, (96, 72, 46), (x, base_y - th * 0.35), (x + tw * 0.28, base_y - th * 0.35), 1)
        self.cache[key] = (s, W / 2, base_y)
        return self.cache[key]

    def _fx(self, s, bid, cx, base_y, tw, th, team):
        """Small painted effects that make each building read at a glance."""
        def glow(x, y, rad, col, strength=90):
            g = pygame.Surface((rad * 2, rad * 2), pygame.SRCALPHA)
            for r in range(rad, 0, -2):
                a = int(strength * (r / rad))
                pygame.draw.circle(g, (*col, a), (rad, rad), r)
            s.blit(g, (int(x - rad), int(y - rad)))
        def flame(x, y, h, col=(255, 150, 60)):
            pygame.draw.polygon(s, (40, 26, 18), [(x - 7, y), (x + 7, y), (x + 4, y - h * 0.55), (x, y - h), (x - 5, y - h * 0.5)])
            pygame.draw.polygon(s, col, [(x - 4, y), (x + 4, y), (x + 2, y - h * 0.5), (x, y - h * 0.85), (x - 3, y - h * 0.45)])
            pygame.draw.circle(s, (255, 226, 150), (int(x), int(y - h * 0.25)), 2)
        def motes(x, y, n, col):
            for i in range(n):
                pygame.draw.circle(s, col, (int(x + (i % 4) * 9 - 12), int(y - (i // 2) * 8)), 1 + (i % 2))
        if bid == "blacksmith":
            glow(cx + tw * 0.16, base_y - th * 0.16, 30, (130, 60, 24), 80)
            flame(cx + tw * 0.17, base_y - th * 0.12, 26)
            for i in range(3):
                pygame.draw.circle(s, (90, 84, 80, 90), (int(cx + tw * 0.28 + i * 8), int(base_y - th * 0.55 - i * 12)), 5 + i * 2)
        elif bid == "altar":
            glow(cx, base_y - th * 0.45, 34, (150, 100, 36), 85)
            flame(cx, base_y - th * 0.30, 38, (255, 190, 90))
            pygame.draw.line(s, (238, 232, 210), (cx, base_y - th * 0.30), (cx, base_y - th * 0.66), 3)
            pygame.draw.line(s, (201, 162, 39), (cx - 9, base_y - th * 0.46), (cx + 9, base_y - th * 0.46), 3)
        elif bid == "sanctum":
            glow(cx, base_y - th * 0.45, 34, (70, 64, 36), 50)
            glow(cx, base_y - th * 0.62, 20, (120, 110, 70), 80)
            pygame.draw.circle(s, (245, 230, 170), (int(cx), int(base_y - th * 0.62)), 4)
            pygame.draw.circle(s, (255, 250, 220), (int(cx), int(base_y - th * 0.62)), 2)
            motes(cx, base_y - th * 0.55, 8, (255, 210, 130))
        elif bid == "temple":
            glow(cx, base_y - th * 0.42, 58, (54, 26, 80), 100)
            motes(cx, base_y - th * 0.52, 9, (170, 120, 230))
        elif bid == "necropolis":
            glow(cx, base_y - th * 0.22, 70, (66, 34, 100), 70)
            # ground rune ring
            for i in range(8):
                a = i / 8 * 6.283
                pygame.draw.circle(s, (150, 100, 220), (int(cx + math.cos(a) * tw * 0.35), int(base_y - 8 + math.sin(a) * 10)), 2)
            for ox in (-0.24, 0.24):
                flame(cx + tw * ox, base_y - th * 0.12, 30, (120, 210, 130))
        elif bid == "altarhollow":
            glow(cx, base_y - th * 0.40, 38, (90, 44, 120), 75)
            motes(cx, base_y - th * 0.50, 8, (190, 150, 240))
        elif bid == "tower":
            flame(cx + tw * 0.28, base_y - th * 0.70, 20)
        elif bid == "keep":
            glow(cx - tw * 0.30, base_y - th * 0.30, 34, (100, 60, 20), 60)
        elif bid == "farm":
            # planted rows turn a cabin into a working farm
            for row in range(3):
                yy = base_y - 4 + row * 7
                for c in range(6):
                    xx = cx - tw * 0.42 + c * (tw * 0.17)
                    pygame.draw.line(s, (74, 98, 44), (xx, yy), (xx + 8, yy), 2)
                    pygame.draw.circle(s, (188, 162, 74), (int(xx + 4), int(yy - 3)), 2)
            pygame.draw.ellipse(s, (110, 86, 42), (cx + tw * 0.30, base_y - 10, 22, 10))
        elif bid == "barracks":
            # training yard: weapon rack + dummy, distinct from the town hall
            for i in range(4):
                pygame.draw.line(s, (60, 46, 32), (cx - tw * 0.34 + i * 7, base_y - 8), (cx - tw * 0.34 + i * 7, base_y - 34), 2)
            dx = cx + tw * 0.38
            pygame.draw.line(s, (70, 54, 36), (dx, base_y - 4), (dx, base_y - 30), 3)
            pygame.draw.line(s, (70, 54, 36), (dx - 8, base_y - 22), (dx + 8, base_y - 22), 2)
            pygame.draw.circle(s, (150, 138, 112), (int(dx), int(base_y - 31)), 4)
