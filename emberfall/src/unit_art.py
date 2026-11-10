"""Procedural unit sprites: 4 facing buckets, animated walk/attack/cast/death.

One shared rig language: heavy ink outline, two-tone fills, top-left rim light,
team accent on cloth. Silhouette first, detail second.
"""
from __future__ import annotations
import math, random
import pygame
from .defs import *
from .art import (SS, INK, PARCH, GOLD, EMBER, STEEL, BONE, VIOLET, BLOOD, MOSS,
                  hexc, shade, mix, new_sprite, finish, dpoly, dline, dcircle, dellipse)

TAU = math.pi * 2
ACCENT = {PLAYER: (172, 58, 48), ENEMY: (96, 62, 130), NEUTRAL: (120, 100, 70)}
ACCENT_L = {PLAYER: (232, 128, 74), ENEMY: (168, 128, 208), NEUTRAL: (186, 162, 112)}
SKIN = (208, 172, 136)
SKIN_D = (166, 128, 96)
BONE_L = (222, 214, 192)
BONE_D = (154, 146, 126)

CFG = {
    "worker": dict(kind="human", s=0.98, armor=(122, 92, 62), armor2=(92, 68, 46),
                   cloth=(150, 112, 72), helmet="cap", weapon="pick", shield=False, cape=False),
    "footman": dict(kind="human", s=1.04, armor=(176, 182, 190), armor2=(126, 132, 142),
                    cloth=None, helmet="steel", weapon="sword", shield=True, cape=False, plume=True),
    "archer": dict(kind="human", s=0.98, armor=(92, 112, 74), armor2=(66, 82, 54),
                   cloth=(74, 92, 62), helmet="hood", weapon="bow", shield=False, cape=True),
    "knight": dict(kind="mounted", s=1.04, armor=(184, 190, 198), armor2=(128, 134, 144),
                   cloth=None, helmet="steel", weapon="sword", shield=True, plume=True, horse=(104, 82, 62)),
    "priest": dict(kind="human", s=0.98, armor=(214, 198, 168), armor2=(166, 150, 124),
                   cloth=(196, 178, 150), helmet="hood", weapon="staff", shield=False, cape=True, robe=True, glow=(255, 186, 104)),
    "ballista": dict(kind="machine", s=1.0),
    "hero": dict(kind="human", s=1.1, armor=(206, 176, 108), armor2=(150, 118, 62),
                 cloth=None, helmet="steel", weapon="sword", shield=True, cape=True, plume=True, glow=(255, 150, 70)),
    "ghoul": dict(kind="human", s=0.94, armor=(126, 138, 116), armor2=(92, 104, 86),
                  cloth=(74, 82, 70), helmet="none", weapon="claw", shield=False, hunched=True, undead=True),
    "fiend": dict(kind="fiend", s=1.0),
    "necromancer": dict(kind="human", s=0.98, armor=(70, 56, 88), armor2=(48, 38, 62),
                        cloth=(54, 42, 70), helmet="skull", weapon="staff", shield=False, cape=True, robe=True, undead=True, glow=(140, 220, 130)),
    "abomination": dict(kind="human", s=1.36, armor=(150, 128, 112), armor2=(112, 92, 82),
                        cloth=(96, 78, 70), helmet="none", weapon="hook", shield=False, hunched=True, undead=True, big=True),
    "revenant": dict(kind="wraith", s=1.02),
    "skeleton": dict(kind="human", s=0.9, armor=None, armor2=None, cloth=None,
                     helmet="skull", weapon="sword", shield=False, undead=True, bone=True),
    "wolf": dict(kind="wolf", s=1.0),
    "elder-wolf": dict(kind="wolf", s=1.28),
    "hollow-king": dict(kind="human", s=1.66, armor=(76, 62, 88), armor2=(50, 40, 62),
                        cloth=(58, 42, 74), helmet="crown", weapon="greatsword", shield=False,
                        cape=True, undead=True, big=True, boss=True, glow=(160, 110, 240)),
    # campaign bosses: procedural fallback identity (the Flare sheet wins when
    # present) — colour and size ladder them from warden to the King himself
    "boss-grave-warden": dict(kind="human", s=1.18, armor=(96, 84, 70), armor2=(70, 60, 50),
                              cloth=(72, 62, 52), helmet="skull", weapon="greatsword",
                              shield=False, cape=True, undead=True, big=True, boss=True, glow=(208, 172, 108)),
    "boss-crypt-herald": dict(kind="human", s=1.28, armor=(78, 96, 84), armor2=(56, 72, 62),
                              cloth=(48, 66, 56), helmet="skull", weapon="greatsword",
                              shield=False, cape=True, undead=True, big=True, boss=True, glow=(120, 220, 150)),
    "boss-bone-tyrant": dict(kind="human", s=1.40, armor=(206, 200, 178), armor2=(150, 144, 126),
                             cloth=(110, 102, 86), helmet="crown", weapon="greatsword",
                             shield=False, cape=True, undead=True, big=True, boss=True, glow=(226, 220, 196)),
    "boss-ash-lich": dict(kind="human", s=1.34, armor=(74, 56, 104), armor2=(52, 40, 76),
                          cloth=(46, 36, 66), helmet="crown", weapon="greatsword",
                          shield=False, cape=True, undead=True, big=True, boss=True, glow=(154, 92, 226)),
    "boss-slaughter-king": dict(kind="human", s=1.52, armor=(126, 64, 58), armor2=(94, 48, 44),
                                cloth=(72, 38, 36), helmet="skull", weapon="greatsword",
                                shield=False, cape=True, undead=True, big=True, boss=True, glow=(226, 88, 74)),
    "boss-frost-sovereign": dict(kind="human", s=1.46, armor=(86, 118, 148), armor2=(62, 88, 112),
                                 cloth=(52, 72, 94), helmet="crown", weapon="greatsword",
                                 shield=False, cape=True, undead=True, big=True, boss=True, glow=(126, 196, 246)),
    "boss-hollow-champion": dict(kind="human", s=1.64, armor=(96, 62, 130), armor2=(66, 44, 92),
                                 cloth=(58, 40, 80), helmet="crown", weapon="greatsword",
                                 shield=False, cape=True, undead=True, big=True, boss=True, glow=(178, 126, 252)),
    "skeleton_king": dict(kind="human", s=1.5, armor=None, armor2=None, cloth=None,
                          helmet="crown", weapon="greatsword", shield=False, undead=True, bone=True, cape=True),
}

FRAMES = dict(idle=2, walk=4, attack=4, cast=3, gather=3, death=5, ride=4)


def _capsule(s, a, b, w, col, outline=INK):
    dline(s, outline, a, b, w + 2.2)
    dline(s, col, a, b, w)
    dcircle(s, outline, a, (w + 2.2) / 2)
    dcircle(s, col, a, w / 2)
    dcircle(s, outline, b, (w + 2.2) / 2)
    dcircle(s, col, b, w / 2)


class UnitSprite:
    def __init__(self, rig, facing, anim, frame, team):
        self.rig = rig
        self.cfg = CFG.get(rig, CFG["footman"])
        self.team = team
        self.facing = facing % 4
        self.anim = anim
        self.n = FRAMES.get(anim, 2)
        self.frame = int(frame) % self.n
        self.t = self.frame / max(1, self.n)
        k = self.cfg["kind"]
        if k == "mounted":
            self.W, self.H = 132, 150
        elif k == "machine":
            self.W, self.H = 112, 92
        elif k == "wolf":
            self.W, self.H = 108, 90
        elif k == "fiend":
            self.W, self.H = 116, 130
        elif k == "wraith":
            self.W, self.H = 104, 128
        elif self.cfg.get("big"):
            self.W, self.H = 150, 168
        else:
            self.W, self.H = 100, 112
        self.feet = self.H - 16
        self.cx = self.W / 2
        self.s = self.cfg.get("s", 1.0)
        self.side = 1 if self.facing in (0, 1) else -1
        self.back = self.facing in (1, 3)
        self.rng = random.Random(hash((rig, facing, anim, frame, team)) & 0xffff)

    def build(self):
        s = new_sprite(self.W, self.H)
        self.surf = s
        kind = self.cfg["kind"]
        if kind == "mounted":
            self._mounted()
        elif kind == "machine":
            self._machine()
        elif kind == "wolf":
            self._wolf()
        elif kind == "fiend":
            self._fiend()
        elif kind == "wraith":
            self._wraith()
        else:
            self._humanoid()
        if self.anim == "death" and not self.cfg.get("machine"):
            ang = (self.frame / 4) * 26
            rotated = pygame.transform.rotate(s, -ang * self.side)
            out = pygame.Surface((self.W + 30, self.H + 24), pygame.SRCALPHA)
            out.blit(rotated, ((out.get_width() - rotated.get_width()) / 2,
                                (out.get_height() - rotated.get_height()) / 2 + self.frame * 2))
            return finish(out, out.get_width() / SS, out.get_height() / SS), out.get_width() / SS / 2, self.feet + 4
        return finish(s, self.W, self.H), self.cx, self.feet

    # ---------------------------------------------------------------- common pieces
    def _aim(self):
        atk = self.anim == "attack"
        t = self.t
        if atk:
            if t < 0.5:
                return 0.3 - (t / 0.5) * 1.9
            return -1.6 + ((t - 0.5) / 0.5) * 2.9
        if self.anim == "cast":
            return -2.2
        if self.anim == "gather":
            return 0.5 + math.sin(t * TAU) * 0.9
        if self.anim in ("walk", "ride"):
            return 0.45 + math.sin(t * TAU) * 0.14
        return 0.45

    def _bob(self):
        t = self.t
        if self.anim in ("walk", "ride"):
            return abs(math.sin(t * TAU)) * 1.4
        if self.anim == "idle":
            return 0.6 + math.sin(t * TAU) * 0.6
        if self.anim == "attack":
            return math.sin(t * math.pi) * 1.0
        return 0.6

    def _draw_weapon(self, hand, ang, kind, scale, glow=None):
        s = self.surf
        L = 24 * scale
        d = (math.cos(ang), math.sin(ang))
        tip = (hand[0] + d[0] * L, hand[1] + d[1] * L)
        if kind in ("sword", "greatsword"):
            w = 3.4 if kind == "sword" else 5.0
            dline(s, INK, hand, tip, w + 2)
            dline(s, (196, 202, 210), hand, tip, w)
            dline(s, (238, 242, 248), (hand[0] + 1, hand[1] - 1), (tip[0] + 1, tip[1] - 1), max(1, w * 0.35))
            guard = (hand[0] + d[0] * 4, hand[1] + d[1] * 4)
            perp = (-d[1], d[0])
            dline(s, INK, (guard[0] - perp[0] * 6, guard[1] - perp[1] * 6), (guard[0] + perp[0] * 6, guard[1] + perp[1] * 6), 3.2)
            dline(s, GOLD, (guard[0] - perp[0] * 5, guard[1] - perp[1] * 5), (guard[0] + perp[0] * 5, guard[1] + perp[1] * 5), 1.8)
            if self.anim == "attack" and 0.45 < self.t < 0.9:
                for k in range(2):
                    a0 = ang - 0.55 + k * 0.22
                    p0 = (hand[0] + math.cos(a0) * 12, hand[1] + math.sin(a0) * 12)
                    p1 = (hand[0] + math.cos(a0) * 30, hand[1] + math.sin(a0) * 30)
                    dline(s, (255, 226, 160, 160), p0, p1, 1.4)
        elif kind in ("staff", "scythe"):
            dline(s, INK, (hand[0] - d[0] * 6, hand[1] - d[1] * 6), (hand[0] + d[0] * (L + 6), hand[1] + d[1] * (L + 6)), 4)
            dline(s, (118, 88, 60), (hand[0] - d[0] * 5, hand[1] - d[1] * 5), (hand[0] + d[0] * (L + 5), hand[1] + d[1] * (L + 5)), 2.4)
            tip2 = (hand[0] + d[0] * (L + 6), hand[1] + d[1] * (L + 6))
            gc = glow or (255, 180, 100)
            dcircle(s, INK, tip2, 6)
            dcircle(s, gc, tip2, 4.4)
            dcircle(s, (255, 244, 210), tip2, 2)
            for k in range(3):
                rr = 5 + k * 2
                dcircle(s, (*gc,), tip2, rr, 1)
        elif kind == "bow":
            cx, cy = hand[0] + d[0] * 7, hand[1] + d[1] * 7
            rect = pygame.Rect(int((cx - 12) * SS), int((cy - 17) * SS), int(24 * SS), int(34 * SS))
            pygame.draw.arc(s, INK, rect, -1.1, 1.1, int(4 * SS))
            pygame.draw.arc(s, (142, 102, 62), rect, -1.05, 1.05, int(2.4 * SS))
            top = (cx + math.cos(-1.1) * 12, cy + math.sin(-1.1) * 17)
            bot = (cx + math.cos(1.1) * 12, cy + math.sin(1.1) * 17)
            dline(s, (226, 220, 196), top, bot, 1)
        elif kind == "pick":
            dline(s, INK, hand, tip, 4)
            dline(s, (116, 84, 56), hand, tip, 2.4)
            head = [(tip[0] - 7, tip[1] - 2), (tip[0] + 8, tip[1] - 8), (tip[0] + 9, tip[1] - 4), (tip[0] - 6, tip[1] + 3)]
            dpoly(s, INK, head)
            dpoly(s, STEEL, [(tip[0] - 5, tip[1] - 1), (tip[0] + 7, tip[1] - 6), (tip[0] + 7, tip[1] - 3), (tip[0] - 4, tip[1] + 2)])
        elif kind == "claw":
            for k in range(3):
                a = ang + (k - 1) * 0.35
                p1 = (hand[0] + math.cos(a) * 12, hand[1] + math.sin(a) * 12)
                p2 = (hand[0] + math.cos(a - 0.3) * 19, hand[1] + math.sin(a - 0.3) * 19)
                dline(s, INK, hand, p1, 3.4)
                dline(s, BONE_L, hand, p1, 2)
                dline(s, BONE_L, p1, p2, 1.4)
        elif kind == "hook":
            dline(s, INK, hand, tip, 5)
            dline(s, (128, 110, 100), hand, tip, 3)
            pygame.draw.arc(s, INK, pygame.Rect(int((tip[0] - 10) * SS), int((tip[1] - 6) * SS), int(22 * SS), int(22 * SS)), 2.4, 5.4, int(3.4 * SS))
            pygame.draw.arc(s, (150, 138, 128), pygame.Rect(int((tip[0] - 9) * SS), int((tip[1] - 5) * SS), int(20 * SS), int(20 * SS)), 2.5, 5.3, int(1.8 * SS))

    def _shield(self, hand, team_col):
        s = self.surf
        x, y = hand
        w, h = 15 * self.s, 21 * self.s
        pts = [(x, y - h / 2), (x + w / 2, y - h / 4), (x + w / 2, y + h / 4), (x, y + h / 2), (x - w / 2, y + h / 4), (x - w / 2, y - h / 4)]
        dpoly(s, INK, pts)
        inner = [(x, y - h / 2 + 2), (x + w / 2 - 2, y - h / 4 + 1), (x + w / 2 - 2, y + h / 4 - 1), (x, y + h / 2 - 2), (x - w / 2 + 2, y + h / 4 - 1), (x - w / 2 + 2, y - h / 4 + 1)]
        dpoly(s, team_col, inner)
        dcircle(s, GOLD, (x, y), 2.4)
        dline(s, INK, (x, y - h / 2), (x, y + h / 2), 1)

    def _head(self, hx, hy, r, skin, helmet, team_col, glow=None, undead=False):
        s = self.surf
        # neck
        dline(s, INK, (hx, hy + r * 0.6), (hx, hy + r * 1.4), 4)
        dline(s, skin, (hx, hy + r * 0.6), (hx, hy + r * 1.4), 2.6)
        dcircle(s, INK, (hx, hy), r + 1.4)
        dcircle(s, skin, (hx, hy), r)
        if not self.back:
            if undead:
                dcircle(s, (26, 22, 26), (hx - r * 0.38, hy - r * 0.05), r * 0.16)
                dcircle(s, (26, 22, 26), (hx + r * 0.38, hy - r * 0.05), r * 0.16)
                if glow:
                    dcircle(s, glow, (hx - r * 0.38, hy - r * 0.05), r * 0.11)
                    dcircle(s, glow, (hx + r * 0.38, hy - r * 0.05), r * 0.11)
            else:
                dcircle(s, INK, (hx - r * 0.35, hy - 1), r * 0.12)
                dcircle(s, INK, (hx + r * 0.35, hy - 1), r * 0.12)
                dline(s, INK, (hx - r * 0.25, hy + r * 0.42), (hx + r * 0.25, hy + r * 0.42), 1)
        if helmet == "steel":
            dpoly(s, INK, [(hx - r - 1, hy - r * 0.5), (hx - r * 0.8, hy - r - 3), (hx + r * 0.8, hy - r - 3), (hx + r + 1, hy - r * 0.5), (hx + r * 0.8, hy + r * 0.1), (hx - r * 0.8, hy + r * 0.1)])
            dpoly(s, STEEL, [(hx - r, hy - r * 0.45), (hx - r * 0.75, hy - r - 1), (hx + r * 0.75, hy - r - 1), (hx + r, hy - r * 0.45), (hx + r * 0.7, hy - r * 0.05), (hx - r * 0.7, hy - r * 0.05)])
            dline(s, INK, (hx, hy - r), (hx, hy + r * 0.4), 1.4)
            dline(s, shade(STEEL, 1.25), (hx - r * 0.6, hy - r + 2), (hx - r * 0.2, hy - r + 2), 1)
        elif helmet == "cap":
            dcircle(s, INK, (hx, hy - r * 0.4), r * 0.95)
            dcircle(s, (118, 88, 58), (hx, hy - r * 0.42), r * 0.82)
            dline(s, (82, 60, 40), (hx - r * 0.8, hy - r * 0.2), (hx + r * 0.8, hy - r * 0.2), 1.4)
            dpoly(s, (118, 88, 58), [(hx - r * 0.9, hy - r * 0.3), (hx - r * 1.2, hy + r * 0.3), (hx - r * 0.6, hy + r * 0.15)])
        elif helmet == "hood":
            dpoly(s, INK, [(hx - r - 2, hy + r * 0.5), (hx - r - 1, hy - r * 0.8), (hx, hy - r - 4), (hx + r + 1, hy - r * 0.8), (hx + r + 2, hy + r * 0.5), (hx + r * 0.6, hy + r * 0.9), (hx - r * 0.6, hy + r * 0.9)])
            dpoly(s, self.cfg.get("cloth") or (86, 70, 50), [(hx - r, hy + r * 0.3), (hx - r * 0.8, hy - r * 0.7), (hx, hy - r - 2), (hx + r * 0.8, hy - r * 0.7), (hx + r, hy + r * 0.3), (hx + r * 0.55, hy + r * 0.7), (hx - r * 0.55, hy + r * 0.7)])
            dpoly(s, (26, 22, 24), [(hx - r * 0.7, hy - r * 0.05), (hx + r * 0.7, hy - r * 0.05), (hx + r * 0.5, hy + r * 0.6), (hx - r * 0.5, hy + r * 0.6)])
            if not self.back:
                dcircle(s, glow or (255, 190, 110), (hx - r * 0.25, hy + r * 0.15), 1.1)
                dcircle(s, glow or (255, 190, 110), (hx + r * 0.25, hy + r * 0.15), 1.1)
        elif helmet == "skull":
            dcircle(s, INK, (hx, hy), r + 1.2)
            dcircle(s, BONE_L, (hx, hy), r)
            dpoly(s, INK, [(hx - r * 0.6, hy), (hx - r * 0.15, hy), (hx - r * 0.15, hy - r * 0.45), (hx - r * 0.6, hy - r * 0.45)])
            dpoly(s, INK, [(hx + r * 0.15, hy), (hx + r * 0.6, hy), (hx + r * 0.6, hy - r * 0.45), (hx + r * 0.15, hy - r * 0.45)])
            if glow:
                dcircle(s, glow, (hx - r * 0.38, hy - r * 0.22), r * 0.18)
                dcircle(s, glow, (hx + r * 0.38, hy - r * 0.22), r * 0.18)
            dline(s, INK, (hx, hy + r * 0.1), (hx, hy + r * 0.5), 1)
            dline(s, INK, (hx - r * 0.5, hy + r * 0.55), (hx + r * 0.5, hy + r * 0.55), 1.2)
            # hood over skull
            dpoly(s, self.cfg.get("cloth") or (54, 44, 60), [(hx - r - 2, hy - r * 0.3), (hx - r * 0.6, hy - r - 3), (hx + r * 0.6, hy - r - 3), (hx + r + 2, hy - r * 0.3), (hx + r * 0.8, hy - r * 0.1), (hx - r * 0.8, hy - r * 0.1)])
        elif helmet == "crown":
            dpoly(s, INK, [(hx - r - 3, hy - r * 0.2), (hx - r - 2, hy - r - 7), (hx - r * 0.5, hy - r - 2), (hx, hy - r - 10), (hx + r * 0.5, hy - r - 2), (hx + r + 2, hy - r - 7), (hx + r + 3, hy - r * 0.2)])
            dpoly(s, GOLD, [(hx - r - 1, hy - r * 0.3), (hx - r - 1, hy - r - 5), (hx - r * 0.5, hy - r - 1), (hx, hy - r - 8), (hx + r * 0.5, hy - r - 1), (hx + r + 1, hy - r - 5), (hx + r + 1, hy - r * 0.3)])
            if undead:
                dcircle(s, glow or (170, 120, 235), (hx - r * 0.38, hy - 1), 1.8)
                dcircle(s, glow or (170, 120, 235), (hx + r * 0.38, hy - 1), 1.8)
        if helmet == "steel" and self.cfg.get("plume") and not self.back:
            for k in range(2):
                a = -1.9 + k * 0.25
                p1 = (hx + math.cos(a) * 4, hy - r + 1)
                p2 = (hx + math.cos(a) * 15, hy - r + 2 + math.sin(self.t * TAU) * 1.2)
                dline(s, INK, p1, p2, 3.4)
                dline(s, team_col, p1, p2, 2)

    # ---------------------------------------------------------------- humanoid
    def _humanoid(self):
        c = self.cfg
        s = self.s
        cx = self.cx
        side = self.side
        back = self.back
        feet = self.feet
        bob = self._bob()
        t = self.t
        sw = math.sin(t * TAU) if self.anim in ("walk", "ride") else 0.0
        crouch = 4 * s if self.anim == "gather" else 0
        lean = (math.sin(t * math.pi) * 2.2 - 1.2) if self.anim == "attack" else 0
        team_col = ACCENT[self.team]
        team_l = ACCENT_L[self.team]
        cloth = c.get("cloth") or team_col
        armor = c.get("armor") or (150, 150, 150)
        armor2 = c.get("armor2") or shade(armor, 0.7)
        skin = BONE_L if c.get("bone") or c.get("undead") else SKIN
        skin_d = BONE_D if c.get("bone") or c.get("undead") else SKIN_D
        # shadow
        dellipse(self.surf, (12, 10, 14, 80), (cx - 18 * s, feet - 4, 36 * s, 10))
        hip_y = feet - 22 * s - bob + crouch
        sh_y = feet - 44 * s - bob + crouch * 1.2
        head_y = feet - 55 * s - bob + crouch * 1.3
        if c.get("hunched"):
            sh_y += 3 * s
            head_y += 5 * s
            lean += 3 * s * self.side
        # ---- cape / robe back
        if c.get("cape") or back:
            flap = math.sin(t * TAU) * 2
            if back:
                pts = [(cx - 12 * s, sh_y + 2), (cx + 12 * s, sh_y + 2), (cx + 16 * s + flap, feet - 4), (cx - 16 * s + flap, feet - 4)]
                dpoly(self.surf, INK, pts)
                dpoly(self.surf, shade(cloth, 0.72), [(cx - 10 * s, sh_y + 4), (cx + 10 * s, sh_y + 4), (cx + 13 * s + flap, feet - 6), (cx - 13 * s + flap, feet - 6)])
                dline(self.surf, shade(cloth, 0.5), (cx, sh_y + 4), (cx + flap, feet - 6), 1)
            else:
                pts = [(cx - 11 * s, sh_y), (cx - 3 * s, sh_y), (cx - 7 * s + flap, feet - 8), (cx - 19 * s + flap, feet - 4)]
                dpoly(self.surf, INK, pts)
                dpoly(self.surf, shade(cloth, 0.8), [(cx - 10 * s, sh_y + 2), (cx - 4 * s, sh_y + 2), (cx - 8 * s + flap, feet - 9), (cx - 17 * s + flap, feet - 6)])
        # ---- legs / robe
        if c.get("robe"):
            hem = feet - 2 + math.sin(t * TAU) * 1 if self.anim in ("walk", "ride") else feet - 2
            pts = [(cx - 9 * s, hip_y + 2), (cx + 9 * s, hip_y + 2), (cx + 15 * s + sw * 2, hem), (cx - 15 * s - sw * 2, hem)]
            dpoly(self.surf, INK, pts)
            dpoly(self.surf, cloth, [(cx - 7 * s, hip_y + 3), (cx + 7 * s, hip_y + 3), (cx + 12 * s + sw * 2, hem - 1), (cx - 12 * s - sw * 2, hem - 1)])
            dpoly(self.surf, shade(cloth, 0.72), [(cx - 12 * s, hem - 1), (cx + 12 * s, hem - 1), (cx + 8 * s, hem + 2), (cx - 8 * s, hem + 2)])
            dline(self.surf, GOLD, (cx - 6 * s, hip_y + 6), (cx + 6 * s, hip_y + 6), 1.4)
        else:
            # far leg
            far = (cx - side * 4.5 * s, hip_y)
            farf = (cx - side * 7 * s - sw * 5 * s, feet - 1)
            _capsule(self.surf, far, farf, 5.6 * s, shade(cloth if c.get("cloth") else c.get("armor2") or armor2, 0.8))
            dellipse(self.surf, INK, (farf[0] - 5 * s, farf[1] - 4 * s, 11 * s, 7 * s))
            dellipse(self.surf, (66, 48, 34), (farf[0] - 4 * s, farf[1] - 3.4 * s, 9 * s, 5.5 * s))
            near = (cx + side * 4.5 * s, hip_y)
            nearf = (cx + side * 7 * s + sw * 5 * s, feet - 1)
            _capsule(self.surf, near, nearf, 6.0 * s, cloth if c.get("cloth") else armor2)
            dellipse(self.surf, INK, (nearf[0] - 5.4 * s, nearf[1] - 4.4 * s, 12 * s, 7.6 * s))
            dellipse(self.surf, (84, 60, 42), (nearf[0] - 4.5 * s, nearf[1] - 3.6 * s, 10 * s, 6 * s))
        # ---- torso
        torso_pts = [(cx - 8 * s + lean * 0.4, hip_y), (cx + 8 * s + lean * 0.4, hip_y),
                     (cx + 11 * s + lean, sh_y + 1), (cx - 11 * s + lean, sh_y + 1)]
        dpoly(self.surf, INK, torso_pts)
        dpoly(self.surf, armor, [(cx - 7 * s + lean * 0.4, hip_y - 1), (cx + 7 * s + lean * 0.4, hip_y - 1),
                                 (cx + 9.5 * s + lean, sh_y + 2), (cx - 9.5 * s + lean, sh_y + 2)])
        # chest highlight (sun top-left)
        dpoly(self.surf, shade(armor, 1.22), [(cx - 7 * s + lean * 0.4, hip_y - 4), (cx - 1 * s + lean * 0.4, hip_y - 4),
                                              (cx - 1.5 * s + lean, sh_y + 4), (cx - 8 * s + lean, sh_y + 4)])
        # tabard
        if c.get("cloth") or not c.get("undead"):
            tab = [(cx - 4.5 * s + lean * 0.4, hip_y - 2), (cx + 4.5 * s + lean * 0.4, hip_y - 2),
                   (cx + 5.5 * s + lean, sh_y + 5), (cx - 5.5 * s + lean, sh_y + 5)]
            dpoly(self.surf, INK, tab)
            dpoly(self.surf, team_col, [(cx - 3.4 * s + lean * 0.4, hip_y - 3), (cx + 3.4 * s + lean * 0.4, hip_y - 3),
                                        (cx + 4.2 * s + lean, sh_y + 6), (cx - 4.2 * s + lean, sh_y + 6)])
            if not back:
                dcircle(self.surf, GOLD, (cx + lean * 0.7, sh_y + 14 * s), 2.0)
        dline(self.surf, INK, (cx - 7 * s + lean * 0.4, hip_y - 2), (cx + 7 * s + lean * 0.4, hip_y - 2), 1.2)
        # belt
        dline(self.surf, (60, 46, 32), (cx - 7.5 * s + lean * 0.4, hip_y - 1.5), (cx + 7.5 * s + lean * 0.4, hip_y - 1.5), 2)
        # ---- shoulders / arms
        shoulder_near = (cx + side * 10 * s + lean, sh_y + 3)
        shoulder_far = (cx - side * 10 * s + lean, sh_y + 3)
        ang = self._aim()
        # weapon hand pose
        if self.anim == "attack":
            hand = (shoulder_near[0] + side * 9 * s, shoulder_near[1] - 2 + math.sin(self.t * math.pi) * -5)
        elif self.anim == "cast":
            hand = (shoulder_near[0] + side * 5 * s, shoulder_near[1] - 16 * s)
        elif self.anim == "gather":
            hand = (shoulder_near[0] + side * 8 * s, shoulder_near[1] + 8 * s)
        else:
            hand = (shoulder_near[0] + side * 7 * s, shoulder_near[1] + 13 * s + (math.sin(t * TAU) * 1 if self.anim in ("walk", "ride") else 0))
        elbow = ((shoulder_near[0] + hand[0]) / 2 + side * 2, (shoulder_near[1] + hand[1]) / 2)
        # far arm (shield side / off hand)
        shield_hand = (shoulder_far[0] - side * 4 * s, shoulder_far[1] + 15 * s)
        if c.get("shield"):
            _capsule(self.surf, shoulder_far, (shoulder_far[0] - side * 2, shoulder_far[1] + 9 * s), 4.6 * s, shade(armor2, 0.85))
        # near arm
        _capsule(self.surf, shoulder_near, elbow, 5.2 * s, armor2)
        _capsule(self.surf, elbow, hand, 4.4 * s, armor)
        dcircle(self.surf, INK, hand, 3.4 * s)
        dcircle(self.surf, skin_d, hand, 2.4 * s)
        # pauldrons
        for (sx0, sy0, cc) in ((shoulder_near, shoulder_near, armor), (shoulder_far, shoulder_far, shade(armor, 0.82))):
            dcircle(self.surf, INK, (sx0[0], sy0[1]), 6.2 * s)
            dcircle(self.surf, cc, (sx0[0], sy0[1]), 5.0 * s)
            dcircle(self.surf, shade(cc, 1.24), (sx0[0] - 1.4 * s, sy0[1] - 1.6 * s), 2.2 * s)
        # ---- head
        self._head(cx + lean * 1.2, head_y, 7.2 * s, skin, c.get("helmet", "none"), team_col,
                   c.get("glow"), c.get("undead", False))
        # ---- shield + weapon
        if c.get("shield"):
            self._shield(shield_hand, team_col)
        self._draw_weapon(hand, ang, c.get("weapon", "sword"), s, c.get("glow"))
        # undead aura wisps
        if c.get("undead") and not c.get("bone"):
            for k in range(3):
                a = t * TAU + k * 2.1
                x = cx + math.cos(a) * 15 * s
                y = feet - 8 - (k * 7 + math.sin(t * TAU + k) * 4) * s
                dcircle(self.surf, (*shade(c.get("glow") or (140, 180, 160), 1.0),), (x, y), 1.4 + 0.8 * s)

    # ---------------------------------------------------------------- mounted
    def _mounted(self):
        c = self.cfg
        s = self.s
        cx = self.cx
        side = self.side
        feet = self.feet
        t = self.t
        sw = math.sin(t * TAU) if self.anim in ("walk", "ride") else 0
        team_col = ACCENT[self.team]
        horse = c.get("horse", (104, 82, 62))
        # shadow
        dellipse(self.surf, (12, 10, 14, 90), (cx - 30 * s, feet - 4, 60 * s, 12))
        # horse legs
        for i, off in enumerate((-16, -8, 9, 17)):
            swing = math.sin(t * TAU + i * 1.6) * (5 if self.anim in ("walk", "ride") else 0)
            hx = cx + off * s
            top = (hx, feet - 30 * s)
            bot = (hx + swing, feet - 1)
            _capsule(self.surf, top, bot, 5 * s, shade(horse, 0.72 if i % 2 else 1.0))
            dellipse(self.surf, (42, 32, 24), (bot[0] - 4 * s, bot[1] - 3 * s, 9 * s, 5 * s))
        # body
        dellipse(self.surf, INK, (cx - 28 * s, feet - 48 * s, 56 * s, 30 * s))
        dellipse(self.surf, horse, (cx - 26 * s, feet - 47 * s, 52 * s, 27 * s))
        dellipse(self.surf, shade(horse, 1.2), (cx - 20 * s, feet - 45 * s, 30 * s, 12 * s))
        # barding
        dpoly(self.surf, INK, [(cx - 24 * s, feet - 40 * s), (cx + 20 * s, feet - 40 * s), (cx + 16 * s, feet - 22 * s), (cx - 20 * s, feet - 22 * s)])
        dpoly(self.surf, team_col, [(cx - 22 * s, feet - 38 * s), (cx + 18 * s, feet - 38 * s), (cx + 14 * s, feet - 24 * s), (cx - 18 * s, feet - 24 * s)])
        dpoly(self.surf, GOLD, [(cx - 6 * s, feet - 36 * s), (cx + 2 * s, feet - 36 * s), (cx - 2 * s, feet - 28 * s)])
        # neck + head
        neck_a = (cx + 20 * s, feet - 44 * s)
        neck_b = (cx + 30 * s, feet - 62 * s)
        _capsule(self.surf, neck_a, neck_b, 8 * s, horse)
        head_c = (cx + 36 * s, feet - 64 * s)
        dellipse(self.surf, INK, (head_c[0] - 12 * s, head_c[1] - 8 * s, 24 * s, 15 * s))
        dellipse(self.surf, horse, (head_c[0] - 10 * s, head_c[1] - 7 * s, 21 * s, 13 * s))
        # mane
        for i in range(3):
            dline(self.surf, INK, (cx + 24 * s, feet - 58 * s + i * 4 * s), (cx + 18 * s, feet - 62 * s + i * 4 * s), 3)
            dline(self.surf, (60, 44, 32), (cx + 24 * s, feet - 58 * s + i * 4 * s), (cx + 18 * s, feet - 62 * s + i * 4 * s), 1.6)
        # tail
        dline(self.surf, INK, (cx - 28 * s, feet - 42 * s), (cx - 40 * s, feet - 28 * s), 5)
        dline(self.surf, shade(horse, 0.7), (cx - 27 * s, feet - 42 * s), (cx - 39 * s, feet - 29 * s), 3)
        # saddle
        dpoly(self.surf, (62, 44, 32), [(cx - 10 * s, feet - 48 * s), (cx + 8 * s, feet - 48 * s), (cx + 6 * s, feet - 40 * s), (cx - 8 * s, feet - 40 * s)])
        # rider (reuse head/torso drawing, shifted)
        bob = abs(math.sin(t * TAU)) * 1.2 if self.anim in ("walk", "ride") else 0
        sh_y = feet - 66 * s - bob
        hip_y = feet - 48 * s - bob
        head_y = feet - 78 * s - bob
        lean = math.sin(t * math.pi) * 2.5 if self.anim == "attack" else 0
        armor = c.get("armor", STEEL)
        armor2 = c.get("armor2", shade(armor, 0.7))
        # far leg astride
        _capsule(self.surf, (cx - 3 * s, hip_y), (cx - 10 * s, feet - 34 * s), 5 * s, shade(armor2, 0.8))
        # torso
        dpoly(self.surf, INK, [(cx - 8 * s + lean * 0.4, hip_y), (cx + 8 * s + lean * 0.4, hip_y), (cx + 11 * s + lean, sh_y), (cx - 11 * s + lean, sh_y)])
        dpoly(self.surf, armor, [(cx - 7 * s + lean * 0.4, hip_y - 1), (cx + 7 * s + lean * 0.4, hip_y - 1), (cx + 9.5 * s + lean, sh_y + 1), (cx - 9.5 * s + lean, sh_y + 1)])
        dpoly(self.surf, shade(armor, 1.24), [(cx - 7 * s + lean * 0.4, hip_y - 3), (cx - 1 * s + lean * 0.4, hip_y - 3), (cx - 1.5 * s + lean, sh_y + 3), (cx - 8 * s + lean, sh_y + 3)])
        dpoly(self.surf, team_col, [(cx - 4 * s + lean * 0.4, hip_y - 2), (cx + 4 * s + lean * 0.4, hip_y - 2), (cx + 5 * s + lean, sh_y + 4), (cx - 5 * s + lean, sh_y + 4)])
        # near leg
        _capsule(self.surf, (cx + 3 * s, hip_y), (cx + 8 * s, feet - 34 * s), 5.4 * s, armor2)
        # arm + weapon
        shoulder = (cx + side * 10 * s + lean, sh_y + 3)
        hand = (shoulder[0] + side * 8 * s, shoulder[1] + 11 * s)
        _capsule(self.surf, shoulder, hand, 5 * s, armor2)
        # shield on far side
        self._shield((cx - side * 13 * s, sh_y + 14 * s), team_col)
        self._head(cx + lean * 1.2, head_y, 7.3 * s, SKIN, "steel", team_col, None, False)
        self._draw_weapon(hand, self._aim(), "sword", s)
        # plume
        for k in range(2):
            p1 = (cx + lean + math.cos(-1.9 + k * 0.3) * 5, head_y - 6 * s)
            p2 = (cx + lean + math.cos(-1.7 + k * 0.3) * 18, head_y - 12 * s)
            dline(self.surf, INK, p1, p2, 3)
            dline(self.surf, team_col, p1, p2, 1.8)

    # ---------------------------------------------------------------- wolf
    def _wolf(self):
        c = self.cfg
        s = self.s
        cx, feet = self.cx, self.feet
        t = self.t
        back = self.back
        fur = (112, 100, 80) if self.team == NEUTRAL else (120, 96, 96)
        if self.rig == "elder-wolf":
            fur = (140, 128, 104)
        fur_d = shade(fur, 0.7)
        dellipse(self.surf, (12, 10, 14, 80), (cx - 26 * s, feet - 4, 52 * s, 10))
        gait = math.sin(t * TAU)
        # legs
        for i, (ox, ph) in enumerate(((-18, math.pi), (-12, 0), (12, math.pi), (18, 0))):
            swing = math.sin(t * TAU + ph) * (5 if self.anim in ("walk", "ride") else 0)
            top = (cx + ox * s, feet - 22 * s)
            bot = (cx + ox * s + swing, feet - 1)
            _capsule(self.surf, top, bot, 4.6 * s, fur_d if i % 2 else fur)
            dellipse(self.surf, (44, 34, 26), (bot[0] - 4 * s, bot[1] - 3 * s, 8 * s, 4.6 * s))
        # body
        dellipse(self.surf, INK, (cx - 28 * s, feet - 38 * s, 52 * s, 22 * s))
        dellipse(self.surf, fur, (cx - 26 * s, feet - 37 * s, 48 * s, 19 * s))
        dellipse(self.surf, shade(fur, 1.16), (cx - 20 * s, feet - 34 * s, 28 * s, 9 * s))
        # tail
        dline(self.surf, INK, (cx - 27 * s, feet - 30 * s), (cx - 42 * s, feet - 38 * s - gait * 3), 6)
        dline(self.surf, fur_d, (cx - 27 * s, feet - 30 * s), (cx - 41 * s, feet - 38 * s - gait * 3), 3.4)
        # head
        hx = cx + 26 * s
        hy = feet - 36 * s
        if back:
            dellipse(self.surf, INK, (hx - 10 * s, hy - 8 * s, 20 * s, 16 * s))
            dellipse(self.surf, fur_d, (hx - 8 * s, hy - 7 * s, 17 * s, 13 * s))
            dline(self.surf, INK, (hx - 4 * s, hy - 7 * s), (hx - 9 * s, hy - 14 * s), 3)
            dline(self.surf, INK, (hx + 6 * s, hy - 7 * s), (hx + 1 * s, hy - 14 * s), 3)
        else:
            dpoly(self.surf, INK, [(hx - 10 * s, hy), (hx - 2 * s, hy - 10 * s), (hx + 12 * s, hy - 6 * s), (hx + 16 * s, hy), (hx + 10 * s, hy + 7 * s), (hx - 8 * s, hy + 6 * s)])
            dpoly(self.surf, fur, [(hx - 8 * s, hy), (hx - 1 * s, hy - 8 * s), (hx + 10 * s, hy - 4 * s), (hx + 13 * s, hy + 1 * s), (hx + 8 * s, hy + 5 * s), (hx - 6 * s, hy + 4 * s)])
            dcircle(self.surf, INK, (hx + 8 * s, hy), 2 * s)
            dcircle(self.surf, (255, 190, 90), (hx + 8 * s, hy - 0.5 * s), 1.1 * s)
            dline(self.surf, INK, (hx + 12 * s, hy + 4 * s), (hx + 16 * s, hy + 3 * s), 2)
            # ears
            dpoly(self.surf, INK, [(hx - 5 * s, hy - 7 * s), (hx - 2 * s, hy - 17 * s), (hx + 3 * s, hy - 8 * s)])
            dpoly(self.surf, fur_d, [(hx - 3 * s, hy - 8 * s), (hx - 1 * s, hy - 15 * s), (hx + 2 * s, hy - 8 * s)])
        # ribs highlight
        for k in range(3):
            dline(self.surf, shade(fur, 1.22), (cx - 16 * s + k * 7, feet - 33 * s), (cx - 12 * s + k * 7, feet - 26 * s), 1.2)

    # ---------------------------------------------------------------- fiend
    def _fiend(self):
        c = self.cfg
        s = self.s
        cx, feet = self.cx, self.feet
        carapace = (92, 70, 112)
        dark = shade(carapace, 0.65)
        bone = BONE_L
        dellipse(self.surf, (12, 10, 14, 80), (cx - 24 * s, feet - 4, 50 * s, 10))
        # spider legs
        for i in range(4):
            ph = i * 1.6
            swing = math.sin(self.t * TAU + ph) * (4 if self.anim in ("walk", "ride") else 0)
            side = 1 if i < 2 else -1
            base = (cx + side * 8 * s, feet - 26 * s)
            mid = (cx + side * (22 + i % 2 * 7) * s, feet - 30 * s + swing)
            foot = (cx + side * (30 + i % 2 * 6) * s + swing, feet - 1)
            _capsule(self.surf, base, mid, 3.6 * s, dark)
            _capsule(self.surf, mid, foot, 2.6 * s, dark)
        # abdomen
        dellipse(self.surf, INK, (cx - 18 * s, feet - 34 * s, 32 * s, 20 * s))
        dellipse(self.surf, carapace, (cx - 16 * s, feet - 33 * s, 28 * s, 17 * s))
        for k in range(3):
            dpoly(self.surf, bone, [(cx - 8 * s, feet - 33 * s - k * 2), (cx, feet - 43 * s - k * 3), (cx + 7 * s, feet - 33 * s - k * 2)])
        # torso
        sh_y = feet - 50 * s
        dpoly(self.surf, INK, [(cx - 9 * s, feet - 30 * s), (cx + 9 * s, feet - 30 * s), (cx + 11 * s, sh_y), (cx - 11 * s, sh_y)])
        dpoly(self.surf, mix(carapace, (150, 140, 160), 0.3), [(cx - 7 * s, feet - 31 * s), (cx + 7 * s, feet - 31 * s), (cx + 9 * s, sh_y + 1), (cx - 9 * s, sh_y + 1)])
        # arms
        for side2 in (-1, 1):
            sh = (cx + side2 * 9 * s, sh_y + 3)
            hand = (cx + side2 * 19 * s, sh_y + 14 * s)
            _capsule(self.surf, sh, hand, 3.4 * s, dark)
            for k in range(3):
                a = 0.4 + k * 0.3
                dline(self.surf, INK, hand, (hand[0] + side2 * math.cos(a) * 9, hand[1] + math.sin(a) * 9), 2.6)
                dline(self.surf, bone, hand, (hand[0] + side2 * math.cos(a) * 8, hand[1] + math.sin(a) * 8), 1.4)
        # head
        hx, hy = cx, sh_y - 8 * s
        dcircle(self.surf, INK, (hx, hy), 8 * s)
        dcircle(self.surf, shade(carapace, 1.1), (hx, hy), 6.8 * s)
        for ex in (-3, 0, 3):
            dcircle(self.surf, (180, 120, 240), (hx + ex * s, hy - 1), 1.3 * s)
        dpoly(self.surf, bone, [(hx - 6 * s, hy + 4 * s), (hx - 3 * s, hy + 10 * s), (hx + 3 * s, hy + 10 * s), (hx + 6 * s, hy + 4 * s)])
        dline(self.surf, (200, 60, 70), (hx, hy + 6 * s), (hx, hy + 9 * s), 1.4)

    # ---------------------------------------------------------------- wraith
    def _wraith(self):
        s = self.s
        cx, feet = self.cx, self.feet
        robe = (64, 96, 116)
        glow = (150, 220, 240)
        # floating haze
        for k in range(4):
            a = self.t * TAU + k * 1.6
            dellipse(self.surf, (*shade(robe, 1.2), 70), (cx - 18 * s + math.cos(a) * 6, feet - 6 - k * 4, 36 * s, 9 * s))
        dellipse(self.surf, (14, 20, 26, 90), (cx - 20 * s, feet - 6, 40 * s, 10))
        hem = feet - 2
        pts = [(cx - 12 * s, feet - 52 * s), (cx + 12 * s, feet - 52 * s), (cx + 18 * s, hem), (cx + 6 * s, hem - 8 * s), (cx, hem), (cx - 8 * s, hem - 7 * s), (cx - 18 * s, hem)]
        dpoly(self.surf, INK, pts)
        dpoly(self.surf, robe, [(cx - 10 * s, feet - 50 * s), (cx + 10 * s, feet - 50 * s), (cx + 15 * s, hem - 2), (cx + 4 * s, hem - 9 * s), (cx, hem - 2), (cx - 6 * s, hem - 9 * s), (cx - 15 * s, hem - 2)])
        for k in range(4):
            dline(self.surf, shade(robe, 0.7), (cx - 8 * s + k * 5 * s, feet - 46 * s), (cx - 11 * s + k * 6 * s, hem - 4), 1.2)
        # arms
        for side2 in (-1, 1):
            sh = (cx + side2 * 10 * s, feet - 48 * s)
            hand = (cx + side2 * 16 * s, feet - 34 * s)
            _capsule(self.surf, sh, hand, 3.2 * s, shade(robe, 1.2))
            dcircle(self.surf, BONE_L, hand, 2.6 * s)
        # skull head + icy crown
        hy = feet - 60 * s
        dcircle(self.surf, INK, (cx, hy), 9 * s)
        dcircle(self.surf, BONE_L, (cx, hy), 7.6 * s)
        dcircle(self.surf, (20, 20, 24), (cx - 3 * s, hy - 1 * s), 1.6 * s)
        dcircle(self.surf, (20, 20, 24), (cx + 3 * s, hy - 1 * s), 1.6 * s)
        dcircle(self.surf, glow, (cx - 3 * s, hy - 1 * s), 1.0 * s)
        dcircle(self.surf, glow, (cx + 3 * s, hy - 1 * s), 1.0 * s)
        dline(self.surf, INK, (cx - 4 * s, hy + 4 * s), (cx + 4 * s, hy + 4 * s), 1.2)
        for k in range(4):
            a = -1.9 + k * 0.5
            p1 = (cx + math.cos(a) * 5 * s, hy - 6 * s)
            p2 = (cx + math.cos(a) * 11 * s, hy - 15 * s)
            dline(self.surf, INK, p1, p2, 2.4)
            dline(self.surf, glow, p1, p2, 1.2)
        # staff
        hand = (cx + 17 * s, feet - 32 * s)
        _capsule(self.surf, (hand[0], hand[1] + 14 * s), hand, 2.4 * s, (120, 90, 70))
        dcircle(self.surf, (30, 40, 46), (hand[0], hand[1] - 3), 5.4 * s)
        dcircle(self.surf, glow, (hand[0], hand[1] - 3), 3.4 * s)
        dcircle(self.surf, (230, 250, 255), (hand[0], hand[1] - 3), 1.4 * s)

    # ---------------------------------------------------------------- machine
    def _machine(self):
        s = self.s
        cx, feet = self.cx, self.feet
        wood = (120, 88, 58)
        dark = (82, 58, 38)
        team_col = ACCENT[self.team]
        dellipse(self.surf, (12, 10, 14, 80), (cx - 30 * s, feet - 4, 60 * s, 11))
        # Attack used to render one static frame (the rig read "machines don't
        # animate"), so firing looked like standing still. The chassis now rocks
        # back through the swing, the bolt leaves on the second half with a
        # flash, and idle breathes through the bow limbs.
        atk = self.anim == "attack"
        t = self.t
        kick = math.sin(t * math.pi) * 3.0 if atk else 0.0
        released = atk and t >= 0.5
        # FRAMES["idle"] is 2, so sin(t*TAU) is 0 on both frames — step the
        # limb per frame instead so idle is not a frozen still.
        sway = ((0.06 if (self.frame % 2) else -0.06)
                if self.anim == "idle" else 0.0)
        cx = cx - kick
        # wheels
        for ox in (-22, 20):
            dcircle(self.surf, INK, (cx + ox * s, feet - 10 * s), 10 * s)
            dcircle(self.surf, wood, (cx + ox * s, feet - 10 * s), 8.4 * s)
            dcircle(self.surf, dark, (cx + ox * s, feet - 10 * s), 2.6 * s)
            for k in range(4):
                a = k * math.pi / 2 + self.t * (2 if self.anim in ("walk", "ride") else 0)
                dline(self.surf, dark, (cx + ox * s, feet - 10 * s), (cx + ox * s + math.cos(a) * 8, feet - 10 * s + math.sin(a) * 8), 1.2)
        # frame
        dpoly(self.surf, INK, [(cx - 30 * s, feet - 20 * s), (cx + 26 * s, feet - 20 * s), (cx + 20 * s, feet - 42 * s), (cx - 24 * s, feet - 42 * s)])
        dpoly(self.surf, wood, [(cx - 28 * s, feet - 21 * s), (cx + 24 * s, feet - 21 * s), (cx + 18 * s, feet - 40 * s), (cx - 22 * s, feet - 40 * s)])
        # bow arm
        dline(self.surf, INK, (cx - 26 * s, feet - 40 * s), (cx + 11 * s, feet - 58 * s), 5)
        dline(self.surf, dark, (cx - 25 * s, feet - 40 * s), (cx + 10 * s, feet - 56 * s), 2.6)
        # bow limbs + string
        pygame.draw.arc(self.surf, INK, pygame.Rect(int((cx + 6) * SS), int((feet - 74) * SS), int(26 * SS), int(38 * SS)), -1.2 + sway, 1.2 + sway, int(3.4 * SS))
        pygame.draw.arc(self.surf, wood, pygame.Rect(int((cx + 7) * SS), int((feet - 73) * SS), int(25 * SS), int(36 * SS)), -1.15 + sway, 1.15 + sway, int(2 * SS))
        dline(self.surf, (226, 220, 196), (cx + 13 * s, feet - 71 * s), (cx + 13 * s, feet - 37 * s), 1.2)
        # bolt — present until released, then flash + flight streak
        if not released:
            dline(self.surf, INK, (cx - 4 * s, feet - 48 * s), (cx + 34 * s, feet - 54 * s), 3.4)
            dline(self.surf, STEEL, (cx - 3 * s, feet - 48 * s), (cx + 33 * s, feet - 54 * s), 1.6)
            dpoly(self.surf, STEEL, [(cx + 33 * s, feet - 54 * s), (cx + 39 * s, feet - 55 * s), (cx + 34 * s, feet - 51 * s)])
        else:
            dline(self.surf, mix(STEEL, (255, 255, 255), 0.5),
                  (cx + 12 * s, feet - 52 * s), (cx + 54 * s, feet - 58 * s), 2.2)
            if t < 0.78:
                fr = max(0.0, 1.0 - (t - 0.5) / 0.28)
                dcircle(self.surf, (255, 216, 148), (cx + 36 * s, feet - 54 * s), (8.0 * fr + 2) * s)
                dcircle(self.surf, (255, 248, 220), (cx + 36 * s, feet - 54 * s), (3.6 * fr + 1) * s)
        # operator banner
        dline(self.surf, (70, 54, 36), (cx - 22 * s, feet - 40 * s), (cx - 22 * s, feet - 64 * s), 2)
        dpoly(self.surf, INK, [(cx - 22 * s, feet - 64 * s), (cx - 8 * s, feet - 61 * s), (cx - 22 * s, feet - 55 * s)])
        dpoly(self.surf, team_col, [(cx - 21 * s, feet - 63 * s), (cx - 10 * s, feet - 61 * s), (cx - 21 * s, feet - 56 * s)])


def make_unit_sprite(art, rig, facing, anim, frame, team):
    return UnitSprite(rig, facing, anim, frame, team).build()
