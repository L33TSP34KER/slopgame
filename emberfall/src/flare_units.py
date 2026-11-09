"""Flare art integration: compose professional 8-direction animated units.

Flare asset pack (CC-BY-SA 3.0, Clint Bellanger + contributors). Avatar layers
are composited with the engine's offset convention; enemies use packed sheets.
Frame defs use: frame=<animFrame>,<direction>,x,y,w,h,ox,oy
Iso directions used: 7=SE, 5=NE, 1=SW, 3=NW for our 4 facing buckets.
"""
from __future__ import annotations
import os, re
import pygame
from .defs import PLAYER, ENEMY, NEUTRAL

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FLARE = os.path.join(ROOT, "assets", "flare")
DIRS = (7, 5, 1, 3)          # facing bucket 0..3
SECT = dict(idle="stance", walk="run", attack="swing", cast="cast",
            death="die", gather="swing", ride="run")

# draw order: far layers first
BASE = ["default_feet", "default_legs", "default_chest", "default_hands", "head_short"]
AVATARS = {
    "worker": BASE + ["cloth_pants", "cloth_shirt", "cloth_sandals", "smith_hammer"],
    "footman": BASE + ["chain_greaves", "chain_cuirass", "chain_boots", "chain_gloves",
                       "chain_coif", "shield", "longsword"],
    "archer": BASE + ["leather_pants", "leather_armor", "leather_boots", "leather_gloves",
                      "leather_hood", "longbow"],
    "knight": BASE + ["plate_greaves", "plate_cuirass", "plate_boots", "plate_gauntlets",
                      "plate_helm", "shield", "greatsword"],
    "priest": BASE + ["mage_skirt", "mage_vest", "mage_boots", "mage_sleeves", "mage_hood", "staff"],
    "hero": BASE + ["plate_greaves", "plate_cuirass", "plate_boots", "plate_gauntlets",
                    "plate_helm", "shield", "longsword"],
}
ENEMIES = {
    "ghoul": ("zombie", 1.0),
    "fiend": ("antlion", 1.0),
    "necromancer": ("skeleton_mage", 1.0),
    "abomination": ("minotaur", 0.95),
    "revenant": ("stealth", 1.0),
    "skeleton": ("skeleton_weak", 0.92),
    "goblin": ("goblin", 0.95),
    "goblin-brute": ("goblin_elite", 1.05),
    "goblin-brute": ("goblin_elite", 1.05),
    "elder-wolf": ("goblin_elite", 1.05),
    "hollow-king": ("skeleton_knight_boss", 1.05),
}
RANGED = {"archer": "shoot", "priest": "shoot", "fiend": "shoot",
          "necromancer": "cast", "revenant": "cast", "hero": "swing"}
UNIT_SCALE = {
    "worker": 1.30, "footman": 1.36, "archer": 1.30, "knight": 1.50, "priest": 1.32,
    "hero": 1.70, "ghoul": 1.30, "fiend": 1.36, "necromancer": 1.30, "abomination": 1.56,
    "revenant": 1.43, "skeleton": 1.17, "goblin": 1.19, "goblin-brute": 1.43,
    "hollow-king": 1.76,
}
TINT = {
    "hero": (1.0, 0.9, 0.62),
}
TEAM_TINT = {
    PLAYER: (1.0, 0.50, 0.34),     # warm ember cloth
    ENEMY: (0.64, 0.62, 1.0),      # cold violet cloth
    NEUTRAL: (1.0, 1.0, 1.0),
}
TEAM_CLOTH = ("cloth_", "leather_", "mage_", "shield", "hood")


def parse_def(path):
    secs = {}
    cur = None
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"\[(\w+)\]", line)
        if m:
            cur = m.group(1)
            secs[cur] = dict(frames=4, rows={}, type="")
            continue
        if cur is None:
            continue
        if line.startswith("frames="):
            secs[cur]["frames"] = int(line.split("=")[1])
        elif line.startswith("type="):
            secs[cur]["type"] = line.split("=")[1]
        elif line.startswith("frame="):
            try:
                v = [int(x) for x in line[6:].split(",")]
            except ValueError:
                continue
            if len(v) >= 8:
                secs[cur]["rows"][(v[0], v[1])] = (v[2], v[3], v[4], v[5], v[6], v[7])
    return secs


def _tint(surf, mul):
    out = surf.copy()
    out.fill((min(255, int(255 * mul[0])), min(255, int(255 * mul[1])), min(255, int(255 * mul[2])), 255),
             special_flags=pygame.BLEND_RGBA_MULT)
    return out


class FlareUnits:
    def __init__(self):
        self.layers = {}
        self.ldefs = {}
        for name in set(sum(AVATARS.values(), [])):
            p = os.path.join(FLARE, "units", "layers", name + ".png")
            d = os.path.join(FLARE, "units", "defs", name + ".txt")
            if os.path.exists(p) and os.path.exists(d):
                self.layers[name] = pygame.image.load(p).convert_alpha()
                self.ldefs[name] = parse_def(d)
        self.enemies = {}
        self.edefs = {}
        for rid, (sheet, sc) in ENEMIES.items():
            p = os.path.join(FLARE, "enemies", sheet + ".png")
            d = os.path.join(FLARE, "enemies", "defs", sheet + ".txt")
            if os.path.exists(p) and os.path.exists(d):
                self.enemies[rid] = pygame.image.load(p).convert_alpha()
                self.edefs[rid] = parse_def(d)
        self.cache = {}
        self.anchors = {}
        self.ranged = dict(RANGED)

    # ------------------------------------------------------------------
    def can(self, rig):
        return rig in AVATARS or rig in self.enemies

    def _avatar_bounds(self):
        # static 128x128 canvas, anchor from feet layer
        return 128, 128, 64, 96

    def _enemy_bounds(self, rid):
        """Canvas + per-rig ground anchor from Flare ox/oy, not crop size."""
        if rid in self.anchors:
            return self.anchors[rid]
        img = self.enemies[rid]
        d = self.edefs[rid]
        left = top = 1e9
        right = bottom = -1e9
        for sec in d.values():
            for (af, dr), (x, y, w, h, ox, oy) in sec["rows"].items():
                left = min(left, -ox)
                right = max(right, w - ox)
                top = min(top, -oy)
                bottom = max(bottom, h - oy)
        pad = 10
        W = int(right - left + pad * 2)
        H = int(bottom - top + pad * 2)
        ax = -left + pad
        ay = -top + pad
        self.anchors[rid] = (W, H, ax, ay, img)
        return self.anchors[rid]

    def frame_count(self, rig, anim):
        """Native Flare frame count for this rig/state (run=8, die=6...)."""
        if not hasattr(self, "_frame_counts"):
            self._frame_counts = {}
        key = (rig, anim)
        hit = self._frame_counts.get(key)
        if hit is not None:
            return hit
        secname = self._section_for(None, anim,
                                    rig in ("archer", "priest", "fiend", "necromancer", "revenant"))
        n = 4
        if rig in AVATARS:
            for ln in AVATARS[rig]:
                d = self.ldefs.get(ln)
                if not d:
                    continue
                sec = d.get(secname) or d.get("stance")
                if sec:
                    n = max(n, int(sec.get("frames", 4)))
        elif rig in self.edefs:
            sec = self.edefs[rig].get(secname) or self.edefs[rig].get("stance")
            if sec:
                n = max(1, int(sec.get("frames", 4)))
        self._frame_counts[key] = n
        return n

    def sprite(self, rig, facing, anim, frame, team=PLAYER):
        key = (rig, facing % 4, anim, frame, team)
        if key in self.cache:
            return self.cache[key]
        d = DIRS[facing % 4]
        if rig in AVATARS:
            surf = self._compose_avatar(rig, d, anim, frame, team)
            ax, ay = 64, 96
        elif rig in self.enemies:
            surf, ax, ay = self._compose_enemy(rig, d, anim, frame, team)
        else:
            return None
        sc = UNIT_SCALE.get(rig, 0.85)
        w, h = surf.get_size()
        surf = pygame.transform.smoothscale(surf, (max(1, int(w * sc)), max(1, int(h * sc))))
        # Flare's painted units are very dark; lift them enough to read on the vale.
        surf.fill((34, 29, 24, 0), special_flags=pygame.BLEND_RGB_ADD)
        # top-left warm rim light: light edges separate the unit from dark ground
        try:
            mask = pygame.mask.from_surface(surf)
            rim_col = (238, 205, 150, 96) if team == PLAYER else (166, 148, 224, 88)
            rim = mask.to_surface(setcolor=rim_col, unsetcolor=(0, 0, 0, 0))
            out = pygame.Surface((surf.get_width() + 2, surf.get_height() + 2), pygame.SRCALPHA)
            out.blit(rim, (0, 0))
            out.blit(surf, (1, 1))
            surf = out
            ax += 1 / max(sc, 0.001)
            ay += 1 / max(sc, 0.001)
        except Exception:
            pass
        res = (surf, ax * sc, ay * sc)
        self.cache[key] = res
        return res

    def _section_for(self, defs, anim, ranged=False):
        if anim == "attack" and ranged:
            name = "shoot"
        elif anim == "idle":
            name = "stance"
        elif anim == "walk":
            name = "run"
        elif anim == "death":
            name = "die"
        elif anim == "gather":
            name = "swing"
        elif anim == "cast":
            name = "cast"
        else:
            name = SECT.get(anim, "stance")
        return name

    def _compose_avatar(self, rig, direction, anim, frame, team=PLAYER):
        W, H, ax, ay = self._avatar_bounds()
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        ranged = self.ranged.get(rig) in ("shoot",) or rig in ("archer", "priest")
        secname = self._section_for(None, anim, ranged)
        for ln in AVATARS[rig]:
            img = self.layers.get(ln)
            d = self.ldefs.get(ln)
            if img is None or d is None:
                continue
            sec = d.get(secname) or d.get("stance")
            if not sec:
                continue
            n = max(1, sec["frames"])
            idx = int(frame) % n
            if sec.get("type") == "back_forth" and n > 2:
                period = 2 * n - 2
                i = int(frame) % period
                idx = i if i < n else period - i
            rect = sec["rows"].get((idx, direction))
            if rect is None:
                rect = sec["rows"].get((0, direction))
            if rect is None:
                continue
            x, y, w, h, ox, oy = rect
            # verified Flare convention: top_left = feet_anchor - (ox, oy)
            dx = 64 - ox
            dy = 96 - oy
            if ln in ("plate_cuirass", "plate_helm", "plate_greaves", "plate_boots", "plate_gauntlets") and rig == "hero":
                part = img.subsurface(pygame.Rect(x, y, w, h)).copy()
                part = _tint(part, TINT["hero"])
                s.blit(part, (int(dx), int(dy)))
            elif ln.startswith(("chain_", "plate_")) and rig != "hero":
                part = img.subsurface(pygame.Rect(x, y, w, h)).copy()
                part = _tint(part, (0.78, 0.76, 0.72))
                s.blit(part, (int(dx), int(dy)))
            elif ln.startswith(TEAM_CLOTH):
                part = img.subsurface(pygame.Rect(x, y, w, h)).copy()
                part = _tint(part, TEAM_TINT.get(team, TEAM_TINT[NEUTRAL]))
                s.blit(part, (int(dx), int(dy)))
            else:
                s.blit(img, (int(dx), int(dy)), pygame.Rect(x, y, w, h))
        return s

    def _compose_enemy(self, rid, direction, anim, frame, team=ENEMY):
        W, H, ax, ay, img = self._enemy_bounds(rid)
        d = self.edefs[rid]
        sec = d.get(self._section_for(None, anim, rid in ("fiend", "necromancer", "revenant"))) or d.get("stance")
        n = max(1, sec["frames"])
        idx = int(frame) % n
        if sec.get("type") == "back_forth" and n > 2:
            period = 2 * n - 2
            i = int(frame) % period
            idx = i if i < n else period - i
        rect = sec["rows"].get((idx, direction)) or sec["rows"].get((0, direction))
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        if rect:
            x, y, w, h, ox, oy = rect
            s.blit(img, (ax - ox, ay - oy), pygame.Rect(x, y, w, h))
        if team == ENEMY:
            s.fill((212, 205, 255, 255), special_flags=pygame.BLEND_RGBA_MULT)
        return s, ax, ay
