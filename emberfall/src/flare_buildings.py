"""Compose professional Flare building crops into game buildings."""
from __future__ import annotations
import os
import pygame
from .defs import *
from .art import shade, mix, INK, GOLD

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIR = os.path.join(ROOT, "assets", "flare", "buildings")

LAYERS = {
    "townhall": [("human_town_hall", 1.0, 0.0, 0.0, None)],
    "keep": [("human_keep", 1.0, 0.0, 0.0, None),
             ("human_town_hall", 0.58, 0.08, 0.16, None)],
    "farm": [("human_house_farm", 1.0, 0.0, 0.0, None)],
    "barracks": [("human_barracks", 1.0, 0.0, 0.0, None),
                 ("human_town_hall", 0.52, -0.16, 0.12, None)],
    "mill": [("human_workshop_lumber", 1.0, 0.0, 0.0, None),
             ("human_house_farm", 0.34, -0.22, 0.06, None)],
    "blacksmith": [("human_blacksmith_smithy", 1.0, 0.0, 0.0, None),
                   ("human_house_farm", 0.38, 0.18, -0.05, None)],
    "sanctum": [("human_temple_altar", 1.0, 0.0, 0.0, None)],
    "tower": [("human_guard_tower", 1.0, 0.0, 0.0, None)],
    "altar": [("human_temple_altar", 0.82, 0.0, 0.0, None)],
    "necropolis": [("undead_ruined_house", 1.0, 0.0, 0.0, None),
                   ("undead_necropolis_ruin", 0.55, -0.18, 0.12, (0.8, 0.72, 1.0))],
    "ziggurat": [("undead_ziggurat_ruin", 1.0, 0.0, 0.0, None)],
    "crypt": [("undead_crypt", 1.0, 0.0, 0.0, None)],
    "slaughterhouse": [("undead_ruined_tower", 1.0, 0.0, 0.0, None),
                       ("undead_bone_ritual", 0.35, 0.25, 0.05, (0.8, 0.7, 0.9))],
    "temple": [("undead_bone_ritual", 1.0, 0.0, 0.0, None),
               ("undead_crypt", 0.5, -0.05, 0.12, (0.8, 0.7, 1.0))],
    "bonetower": [("human_guard_tower", 1.0, 0.0, 0.0, (0.62, 0.54, 0.82))],
    "altarhollow": [("undead_bone_ritual", 1.0, 0.0, 0.0, (0.85, 0.75, 1.0))],
}
TARGET_W = {"townhall": 280, "keep": 320, "farm": 165, "barracks": 235, "mill": 215,
            "blacksmith": 215, "sanctum": 215, "tower": 110, "altar": 135,
            "necropolis": 420, "ziggurat": 150, "crypt": 215, "slaughterhouse": 225,
            "temple": 215, "bonetower": 110, "altarhollow": 210}
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
