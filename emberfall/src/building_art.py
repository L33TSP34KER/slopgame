"""Procedural isometric buildings, one silhouette per structure."""
from __future__ import annotations
import math, random
import pygame
from .defs import *
from .art import (SS, INK, PARCH, GOLD, EMBER, STEEL, BONE, VIOLET, BLOOD, MOSS,
                  hexc, shade, mix, new_sprite, finish, dpoly, dline, dcircle, dellipse)

HUMAN = dict(stone=(120, 113, 101), stone_d=(91, 85, 77), timber=(92, 65, 43),
             roof=(126, 57, 48), roof_d=(88, 38, 35), plaster=(198, 184, 150),
             gold=GOLD, banner=(172, 58, 48), accent=EMBER)
UNDEAD = dict(stone=(80, 71, 88), stone_d=(54, 48, 64), timber=(62, 52, 68),
              roof=(68, 46, 88), roof_d=(45, 29, 60), plaster=(120, 112, 126),
              gold=(150, 120, 190), banner=(96, 62, 130), accent=(170, 120, 235))
WOOD = (100, 72, 48)
WOOD_D = (72, 51, 34)


def _pal(team):
    return HUMAN if team == PLAYER else UNDEAD


def _proj(dx, dy, h=0):
    return ((dx - dy) * 32, (dx + dy) * 16 - h)


class B:
    def __init__(self, art, bid, team, stage):
        self.art, self.bid, self.team, self.stage = art, bid, team, stage
        self.d = BUILDINGS[bid]
        self.p = _pal(team)
        self.bw, self.bd = self.d["size"]
        self.hpx = self.d.get("height", 60)
        margin = 70
        self.W = (self.bw + self.bd) * 32 + margin * 2
        self.H = (self.bw + self.bd) * 16 + self.hpx + margin * 2 + 40
        self.s = new_sprite(self.W, self.H)
        self.cx = self.W / 2
        self.cy = self.H - margin
        self.prog = (1.0, 0.35, 0.62, 0.85, 1.0)[min(4, stage)]
        self.complete = stage >= 4
        self.rng = random.Random(hash(bid) % 99991 + team * 17)

    # ---- primitives -------------------------------------------------
    def prism(self, cx, cy, w, d, h, top, right, left, outline=True, base_h=0):
        """Iso prism; cx,cy = screen center of base top; returns corner dict."""
        A = (cx + (d / 2 - w / 2) * 32, cy - (w / 2 + d / 2) * 16)
        Bp = (cx + (w / 2 + d / 2) * 32, cy - (w / 2 - d / 2) * 16)
        C = (cx + (w / 2 - d / 2) * 32, cy + (w / 2 + d / 2) * 16)
        D = (cx - (w / 2 + d / 2) * 32, cy + (d / 2 - w / 2) * 16)
        top_pts = [(A[0], A[1] - h), (Bp[0], Bp[1] - h), (C[0], C[1] - h), (D[0], D[1] - h)]
        # front-right face (B-C) and front-left (C-D)
        dpoly(self.s, right, [(Bp[0], Bp[1] - h), (C[0], C[1] - h), (C[0], C[1]), (Bp[0], Bp[1])])
        dpoly(self.s, left, [(C[0], C[1] - h), (D[0], D[1] - h), (D[0], D[1]), (C[0], C[1])])
        dpoly(self.s, top, top_pts)
        if outline:
            for a, b in ((A, Bp), (Bp, C), (C, D), (D, A)):
                dline(self.s, INK, (a[0], a[1] - h), (b[0], b[1] - h), 1.2)
            dline(self.s, INK, (Bp[0], Bp[1] - h), (Bp[0], Bp[1]), 1.0)
            dline(self.s, INK, (C[0], C[1] - h), (C[0], C[1]), 1.2)
            dline(self.s, INK, (D[0], D[1] - h), (D[0], D[1]), 1.0)
        # wall shading
        dpoly(self.s, (0, 0, 0, 26), [(Bp[0], Bp[1] - h), (Bp[0], Bp[1]), (C[0], C[1]), (C[0], C[1] - h)])
        return dict(A=A, B=Bp, C=C, D=D, h=h, top=top_pts)

    def hip_roof(self, cx, cy, w, d, h, rh, col, dark, outline=True):
        A = (cx + (d / 2 - w / 2) * 32, cy - (w / 2 + d / 2) * 16)
        Bp = (cx + (w / 2 + d / 2) * 32, cy - (w / 2 - d / 2) * 16)
        C = (cx + (w / 2 - d / 2) * 32, cy + (w / 2 + d / 2) * 16)
        D = (cx - (w / 2 + d / 2) * 32, cy + (d / 2 - w / 2) * 16)
        # ridge along the longer iso axis
        if w >= d:
            r1 = ((A[0] + D[0]) / 2, (A[1] + D[1]) / 2 - h - rh)
            r2 = ((Bp[0] + C[0]) / 2, (Bp[1] + C[1]) / 2 - h - rh)
        else:
            r1 = ((A[0] + Bp[0]) / 2, (A[1] + Bp[1]) / 2 - h - rh)
            r2 = ((D[0] + C[0]) / 2, (D[1] + C[1]) / 2 - h - rh)
        dpoly(self.s, col, [(Bp[0], Bp[1] - h), (C[0], C[1] - h), r2, r1])
        dpoly(self.s, dark, [(D[0], D[1] - h), (C[0], C[1] - h), r2, r1])
        if outline:
            dline(self.s, INK, (Bp[0], Bp[1] - h), r1, 1.2)
            dline(self.s, INK, (C[0], C[1] - h), r1, 1.2)
            dline(self.s, INK, (C[0], C[1] - h), r2, 1.2)
            dline(self.s, INK, (D[0], D[1] - h), r2, 1.2)
            dline(self.s, INK, r1, r2, 1.4)
        # tile ridges
        for k in range(1, 4):
            t = k / 4
            dline(self.s, shade(col, 0.86), ((Bp[0] + (C[0] - Bp[0]) * t) * 0 + (C[0] - Bp[0]) * t + Bp[0], (C[1] - Bp[1]) * t + Bp[1] - h), r2, 1)
        return r1, r2

    def pyramid(self, cx, cy, w, d, h, rh, col, dark):
        A = (cx + (d / 2 - w / 2) * 32, cy - (w / 2 + d / 2) * 16)
        Bp = (cx + (w / 2 + d / 2) * 32, cy - (w / 2 - d / 2) * 16)
        C = (cx + (w / 2 - d / 2) * 32, cy + (w / 2 + d / 2) * 16)
        D = (cx - (w / 2 + d / 2) * 32, cy + (d / 2 - w / 2) * 16)
        apex = (cx, cy - h - rh)
        dpoly(self.s, col, [(Bp[0], Bp[1] - h), (C[0], C[1] - h), apex])
        dpoly(self.s, dark, [(C[0], C[1] - h), (D[0], D[1] - h), apex])
        dline(self.s, INK, (Bp[0], Bp[1] - h), apex, 1.2)
        dline(self.s, INK, (C[0], C[1] - h), apex, 1.2)
        dline(self.s, INK, (D[0], D[1] - h), apex, 1.2)
        return apex

    def window(self, x, y, w=8, h=11, glow=(255, 190, 100), arch=True):
        dpoly(self.s, INK, [(x - w / 2 - 1, y + h + 1), (x + w / 2 + 1, y + h + 1), (x + w / 2 + 1, y - h), (x - w / 2 - 1, y - h)])
        dpoly(self.s, glow, [(x - w / 2, y + h), (x + w / 2, y + h), (x + w / 2, y - h + 2), (x, y - h - 2), (x - w / 2, y - h + 2)])
        dline(self.s, shade(glow, 0.6), (x, y - h - 1), (x, y + h), 0.8)

    def door(self, x, y, w=16, h=24, col=(46, 34, 26), glow=None):
        dpoly(self.s, INK, [(x - w / 2 - 1, y + 1), (x + w / 2 + 1, y + 1), (x + w / 2 + 1, y - h), (x, y - h - 7), (x - w / 2 - 1, y - h)])
        dpoly(self.s, col, [(x - w / 2, y), (x + w / 2, y), (x + w / 2, y - h + 2), (x, y - h - 5), (x - w / 2, y - h + 2)])
        if glow:
            dline(self.s, glow, (x, y - 3), (x, y - h + 4), 1.2)

    def banner(self, x, y, col, h=26, w=13, flip=1):
        dline(self.s, (62, 48, 34), (x, y), (x, y - h - 8), 2)
        pts = [(x, y - h - 8), (x + w * flip, y - h - 4), (x + w * flip * 0.8, y - 8), (x, y - 10)]
        dpoly(self.s, col, pts)
        dpoly(self.s, shade(col, 0.72), [(x + w * flip * 0.8, y - 8), (x + w * flip, y - h - 4), (x + w * flip * 0.8, y - h + 2)])
        dline(self.s, INK, pts[0], pts[1], 1.0)
        dline(self.s, INK, pts[1], pts[2], 1.0)
        dcircle(self.s, GOLD, (x + w * flip * 0.45, y - h + 6), 2.2)

    def skull(self, x, y, r=9):
        dcircle(self.s, BONE, (x, y), r)
        dpoly(self.s, BONE, [(x - r * 0.55, y + r * 0.5), (x + r * 0.55, y + r * 0.5), (x + r * 0.3, y + r * 1.15), (x - r * 0.3, y + r * 1.15)])
        dcircle(self.s, INK, (x - r * 0.4, y - 1), r * 0.24)
        dcircle(self.s, INK, (x + r * 0.4, y - 1), r * 0.24)
        dline(self.s, INK, (x - r * 0.2, y + r * 0.55), (x + r * 0.2, y + r * 0.55), 1)

    def crystal(self, x, y, h, col=(156, 110, 224)):
        dpoly(self.s, INK, [(x - 5, y), (x, y - h - 2), (x + 6, y)])
        dpoly(self.s, col, [(x - 4, y - 1), (x, y - h), (x + 3, y - 1)])
        dline(self.s, shade(col, 1.3), (x - 1, y - 2), (x, y - h + 3), 1)

    def scaffold(self, cx, cy, w, d, h):
        for i in range(4):
            x = cx - (w + d) * 8 + i * (w + d) * 5.3
            dline(self.s, (126, 96, 60), (x, cy + 4), (x, cy - 34 - h * 0.35), 1.6)
            dline(self.s, (96, 72, 46), (x, cy - 18), (x + 22, cy - 18), 1.2)
        dellipse(self.s, (180, 160, 120, 40), (cx - (w + d) * 9, cy - 8, (w + d) * 18, 20))

    # ---- entry ------------------------------------------------------
    def build(self):
        d = self.d
        cx, cy = self.cx, self.cy
        # ground shadow
        dellipse(self.s, (10, 9, 12, 92), (cx - (self.bw + self.bd) * 13, cy - 16, (self.bw + self.bd) * 26, 34))
        fn = getattr(self, "b_" + self.bid.replace("-", "_"), None)
        if fn is None:
            fn = self.b_generic
        fn(cx, cy)
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, self.hpx * self.prog)
            # dust
            for _ in range(10):
                x = cx + self.rng.uniform(-(self.bw + self.bd) * 10, (self.bw + self.bd) * 10)
                y = cy - self.rng.uniform(0, 30)
                dcircle(self.s, (150, 140, 120, 90), (x, y), self.rng.uniform(1, 3))
        # clip to canvas
        return finish(self.s, self.W, self.H), self.W / 2 + 34, self.H - 70

    # ---- buildings --------------------------------------------------
    def b_generic(self, cx, cy):
        w, d = self.bw * 0.86, self.bd * 0.86
        h = self.hpx * self.prog * 0.5
        self.prism(cx, cy, w, d, h, self.p["stone"], self.p["stone"], self.p["stone_d"])
        if self.complete:
            self.hip_roof(cx, cy, w, d, h, 22, self.p["roof"], self.p["roof_d"])

    def b_townhall(self, cx, cy):
        p = self.p
        hh = 38 * self.prog
        # stone plinth
        self.prism(cx, cy, 4.0, 4.0, 7, shade(p["stone"], 1.06), p["stone"], p["stone_d"])
        # main hall
        self.prism(cx, cy, 3.2, 3.0, hh, shade(p["stone"], 1.12), p["stone"], p["stone_d"])
        if self.complete:
            self.hip_roof(cx, cy, 3.2, 3.0, hh, 26, p["roof"], p["roof_d"])
            # tower at back
            tx, ty = cx + 18, cy - 24
            self.prism(tx, ty, 1.15, 1.15, hh + 34, shade(p["stone"], 1.2), p["stone"], p["stone_d"])
            self.pyramid(tx, ty, 1.15, 1.15, hh + 34, 22, p["roof"], p["roof_d"])
            self.banner(tx, ty - (hh + 58), p["banner"], 30, 12)
            # door + windows on the front face
            self.door(cx + 2, cy + 26, 16, 26, (48, 35, 26), glow=(255, 180, 90))
            for i in (-1, 1):
                self.window(cx + i * 36, cy + 2, 7, 10)
                self.window(cx + i * 18, cy - 15, 6, 9)
            # banners either side
            self.banner(cx - 48, cy + 18, p["banner"], 24, 11, -1)
            self.banner(cx + 48, cy + 18, p["banner"], 24, 11, 1)
            # brazier
            self.crystal(cx - 60, cy + 28, 10, (255, 150, 60))
        self.scaffold(cx, cy, self.bw, self.bd, hh) if not self.complete else None

    def b_keep(self, cx, cy):
        p = self.p
        hh = 52 * self.prog
        self.prism(cx, cy, 4.2, 4.2, 8, shade(p["stone"], 1.06), p["stone"], p["stone_d"])
        self.prism(cx, cy, 3.3, 3.3, hh, shade(p["stone"], 1.15), p["stone"], p["stone_d"])
        if self.complete:
            self.hip_roof(cx, cy, 3.3, 3.3, hh, 30, p["roof"], p["roof_d"])
            for ox, oy, th in ((30, -30, hh + 40), (-34, -18, hh + 26)):
                self.prism(cx + ox, cy + oy, 1.1, 1.1, th, shade(p["stone"], 1.22), p["stone"], p["stone_d"])
                self.pyramid(cx + ox, cy + oy, 1.1, 1.1, th, 26, p["roof"], p["roof_d"])
                self.banner(cx + ox, cy + oy - (th + 30), p["banner"], 34, 13)
            self.door(cx, cy + 30, 20, 30, (44, 32, 24), glow=(255, 190, 100))
            for i in (-1, 0, 1):
                self.window(cx + i * 34, cy + 2, 7, 12)
                self.window(cx + i * 22, cy - 20, 6, 9)
            # crenellations
            for i in range(5):
                x = cx - 44 + i * 22
                dpoly(self.s, shade(p["stone"], 1.2), [(x - 6, cy - hh + 2), (x + 6, cy - hh + 2), (x + 6, cy - hh - 8), (x - 6, cy - hh - 8)])
            self.banner(cx - 58, cy + 22, p["banner"], 28, 12, -1)
            self.banner(cx + 58, cy + 22, p["banner"], 28, 12, 1)
            self.crystal(cx - 74, cy + 34, 12, (255, 150, 60))
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_farm(self, cx, cy):
        p = self.p
        hh = 24 * self.prog
        # field rows in the front half
        if self.complete:
            for i in range(3):
                y = cy + 12 + i * 7
                dpoly(self.s, (150, 124, 70), [(cx - 38 + i * 3, y), (cx - 2 + i * 3, y - 10), (cx - 2 + i * 3, y - 5), (cx - 38 + i * 3, y + 5)])
                dline(self.s, (96, 80, 46), (cx - 38 + i * 3, y + 5), (cx - 2 + i * 3, y - 5), 1)
                for k in range(4):
                    dline(self.s, (198, 170, 92), (cx - 34 + i * 3 + k * 8, y + 3 - k * 2), (cx - 34 + i * 3 + k * 8, y - 4 - k * 2), 1)
        self.prism(cx + 8, cy - 6, 1.7, 1.7, hh, shade(p["plaster"], 1.04), p["plaster"], shade(p["plaster"], 0.8))
        if self.complete:
            self.hip_roof(cx + 8, cy - 6, 1.7, 1.7, hh, 20, (150, 112, 60), (104, 76, 40))
            self.door(cx + 20, cy + 10, 10, 15)
            self.window(cx - 4, cy - 10, 5, 6, (255, 196, 110))
            # haystack
            dellipse(self.s, (188, 156, 82), (cx - 48, cy + 20, 22, 16))
            dellipse(self.s, (214, 182, 100), (cx - 45, cy + 18, 16, 11))
            # fence
            for i in range(5):
                dline(self.s, WOOD_D, (cx - 54 + i * 12, cy + 30), (cx - 54 + i * 12, cy + 18), 2)
            dline(self.s, WOOD, (cx - 54, cy + 23), (cx - 6, cy + 23), 1.4)

    def b_barracks(self, cx, cy):
        p = self.p
        hh = 30 * self.prog
        self.prism(cx, cy, 3.0, 2.3, hh, shade(p["timber"], 1.2), p["timber"], shade(p["timber"], 0.78))
        if self.complete:
            self.hip_roof(cx, cy, 3.0, 2.3, hh, 24, p["roof"], p["roof_d"])
            self.door(cx - 8, cy + 20, 16, 22, (50, 36, 26), glow=(255, 170, 90))
            for i in (-1, 1):
                self.window(cx + i * 30, cy + 2, 6, 8)
            self.banner(cx + 52, cy + 10, p["banner"], 26, 12)
            # training dummy + rack
            dline(self.s, WOOD_D, (cx - 62, cy + 24), (cx - 62, cy + 2), 3)
            dline(self.s, WOOD_D, (cx - 70, cy + 14), (cx - 54, cy + 14), 2)
            dcircle(self.s, (170, 160, 140), (cx - 62, cy + 2), 5)
            for i in range(3):
                dline(self.s, STEEL, (cx + 40 + i * 5, cy + 26), (cx + 48 + i * 5, cy + 6), 1.4)
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_mill(self, cx, cy):
        p = self.p
        hh = 26 * self.prog
        self.prism(cx, cy, 2.4, 2.0, hh, shade(p["timber"], 1.16), p["timber"], shade(p["timber"], 0.8))
        if self.complete:
            self.hip_roof(cx, cy, 2.4, 2.0, hh, 20, (112, 88, 52), (78, 60, 36))
            # saw blade
            dcircle(self.s, INK, (cx + 38, cy + 8), 17)
            dcircle(self.s, (176, 176, 168), (cx + 38, cy + 8), 15)
            for i in range(10):
                a = i / 10 * math.tau
                dline(self.s, (120, 120, 114), (cx + 38 + math.cos(a) * 12, cy + 8 + math.sin(a) * 12),
                      (cx + 38 + math.cos(a) * 17, cy + 8 + math.sin(a) * 17), 2)
            dcircle(self.s, INK, (cx + 38, cy + 8), 3)
            self.door(cx - 4, cy + 18, 12, 16)
            # log pile
            for i in range(5):
                x = cx - 44 + (i % 3) * 9
                y = cy + 18 + (i // 3) * 9
                dellipse(self.s, (126, 96, 62), (x - 7, y - 5, 15, 10))
                dellipse(self.s, (166, 132, 88), (x - 4, y - 2, 8, 5))
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_blacksmith(self, cx, cy):
        p = self.p
        hh = 28 * self.prog
        self.prism(cx, cy, 2.1, 1.9, hh, shade(p["stone"], 1.08), p["stone"], p["stone_d"])
        if self.complete:
            self.hip_roof(cx, cy, 2.1, 1.9, hh, 18, (84, 64, 52), (58, 42, 36))
            # chimney
            self.prism(cx + 26, cy - 16, 0.5, 0.5, hh + 34, (92, 84, 76), (92, 84, 76), (64, 58, 52))
            # forge glow
            dcircle(self.s, (255, 130, 50), (cx - 24, cy + 16), 11)
            dcircle(self.s, (255, 200, 110), (cx - 24, cy + 16), 6)
            dline(self.s, (60, 46, 34), (cx - 14, cy + 24), (cx + 10, cy + 12), 3)
            # anvil
            dpoly(self.s, (60, 58, 56), [(cx + 22, cy + 24), (cx + 40, cy + 20), (cx + 40, cy + 12), (cx + 22, cy + 16)])
            dline(self.s, STEEL, (cx + 28, cy + 16), (cx + 34, cy + 5), 3)
            self.window(cx - 2, cy - 12, 5, 6, (255, 160, 80))
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_sanctum(self, cx, cy):
        p = self.p
        hh = 46 * self.prog
        self.prism(cx, cy, 2.3, 2.3, hh, shade(p["stone"], 1.15), p["stone"], p["stone_d"])
        if self.complete:
            self.pyramid(cx, cy, 2.3, 2.3, hh, 26, (76, 96, 112), (50, 64, 80))
            for i in (-1, 1):
                self.window(cx + i * 24, cy + 6, 7, 13, (255, 196, 112))
            self.window(cx - 4, cy - 26, 8, 10, (255, 210, 130))
            self.banner(cx - 42, cy + 18, p["banner"], 24, 10, -1)
            for i in range(7):
                a = i / 7 * math.tau
                dcircle(self.s, (255, 190, 110), (cx + math.cos(a) * 44, cy - 20 + math.sin(a) * 18), 2)
            self.door(cx + 4, cy + 22, 12, 18, (42, 34, 30), glow=(255, 210, 140))
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_tower(self, cx, cy):
        p = self.p
        hh = 64 * self.prog
        self.prism(cx, cy, 1.35, 1.35, hh, shade(p["stone"], 1.12), p["stone"], p["stone_d"])
        if self.complete:
            # crenellations
            for i in range(4):
                x = cx - 24 + i * 16
                dpoly(self.s, shade(p["stone"], 1.2), [(x - 5, cy - hh + 2), (x + 5, cy - hh + 2), (x + 5, cy - hh - 9), (x - 5, cy - hh - 9)])
            self.window(cx, cy - 26, 4, 7, (255, 176, 92))
            self.window(cx - 10, cy + 2, 3, 5, (255, 176, 92))
            self.banner(cx + 18, cy - hh + 12, p["banner"], 22, 10)
            self.door(cx, cy + 14, 10, 14, (44, 34, 26))
            self.crystal(cx - 30, cy + 20, 9, (255, 150, 60))
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_altar(self, cx, cy):
        p = self.p
        hh = 18 * self.prog
        self.prism(cx, cy, 1.5, 1.5, 8, shade(p["stone"], 1.1), p["stone"], p["stone_d"])
        self.prism(cx, cy, 1.0, 1.0, hh, shade(p["stone"], 1.2), p["stone"], p["stone_d"])
        if self.complete:
            # brazier + sword
            dcircle(self.s, (255, 140, 56), (cx, cy - hh - 6), 12)
            dcircle(self.s, (255, 214, 130), (cx, cy - hh - 7), 6)
            dline(self.s, STEEL, (cx, cy - hh - 6), (cx, cy - hh - 34), 3)
            dline(self.s, GOLD, (cx - 8, cy - hh - 22), (cx + 8, cy - hh - 22), 3)
            dpoly(self.s, GOLD, [(cx - 4, cy - hh - 34), (cx, cy - hh - 42), (cx + 4, cy - hh - 34)])
            self.banner(cx - 30, cy + 12, p["banner"], 20, 9, -1)
            self.banner(cx + 30, cy + 12, p["banner"], 20, 9, 1)
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    # ---- undead -----------------------------------------------------
    def b_necropolis(self, cx, cy):
        p = self.p
        hh = 56 * self.prog
        self.prism(cx, cy, 5.0, 5.0, 10, (58, 50, 66), (72, 62, 82), (46, 39, 54))
        self.prism(cx, cy, 3.8, 3.8, hh, (64, 55, 74), (56, 48, 66), (38, 32, 48))
        if self.complete:
            # jagged crown spires
            for ox, oy, hsp in ((-46, -26, 54), (44, -18, 42), (0, -58, 70), (-16, -46, 30), (34, 8, 28)):
                bx, by = cx + ox, cy + oy
                self.prism(bx, by, 0.8, 0.8, hh + 12, (86, 74, 98), (76, 64, 88), (50, 42, 64))
                dpoly(self.s, BONE, [(bx - 20, by - hh - 12), (bx, by - hh - 12 - hsp), (bx + 22, by - hh - 12)])
                dpoly(self.s, shade(BONE, 0.72), [(bx, by - hh - 12 - hsp), (bx + 22, by - hh - 12), (bx + 6, by - hh - 12)])
            # skull gate
            self.skull(cx, cy - 10, 26)
            self.skull(cx - 52, cy + 8, 13)
            self.skull(cx + 52, cy + 8, 13)
            self.door(cx, cy + 40, 30, 34, (16, 12, 20), glow=(130, 90, 200))
            for i in (-1, 1):
                self.window(cx + i * 56, cy + 4, 10, 16, (150, 100, 230))
            for i in range(5):
                self.crystal(cx - 70 + i * 35, cy + 38, 16 + (i % 2) * 8, (150, 100, 235))
            # green braziers
            for ox in (-38, 38):
                dcircle(self.s, (110, 190, 120), (cx + ox, cy + 30), 9)
                dcircle(self.s, (180, 240, 160), (cx + ox, cy + 30), 4)
            # chains
            for i in range(3):
                dline(self.s, (40, 36, 44), (cx - 24 + i * 24, cy - hh + 4), (cx - 24 + i * 24, cy - 14), 1.4)
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_ziggurat(self, cx, cy):
        p = self.p
        hh = 20 * self.prog
        self.prism(cx, cy, 2.4, 2.4, hh, (74, 64, 84), (66, 56, 74), (44, 36, 54))
        self.prism(cx, cy, 1.8, 1.8, hh + 18, (86, 76, 96), (76, 66, 86), (50, 42, 62))
        self.prism(cx, cy, 1.1, 1.1, hh + 34, (94, 84, 104), (82, 72, 92), (56, 48, 68))
        if self.complete:
            self.skull(cx, cy - hh - 10, 12)
            for i in (-1, 1):
                self.crystal(cx + i * 30, cy + 16, 16)
                self.window(cx + i * 26, cy + 4, 5, 8, (160, 120, 235))
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_crypt(self, cx, cy):
        p = self.p
        hh = 28 * self.prog
        self.prism(cx, cy, 2.7, 2.2, hh, (78, 69, 86), (66, 58, 74), (46, 38, 54))
        if self.complete:
            self.hip_roof(cx, cy, 2.7, 2.2, hh, 20, p["roof"], p["roof_d"])
            self.door(cx, cy + 18, 18, 24, (18, 14, 22), glow=(120, 200, 120))
            self.skull(cx - 34, cy + 8, 9)
            self.skull(cx + 36, cy + 6, 8)
            for i in range(4):
                dline(self.s, BONE, (cx - 30 + i * 20, cy + 26), (cx - 24 + i * 20, cy + 18), 2)
            self.crystal(cx + 38, cy + 24, 12, (120, 200, 130))
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_slaughterhouse(self, cx, cy):
        p = self.p
        hh = 30 * self.prog
        self.prism(cx, cy, 2.9, 2.4, hh, (96, 70, 66), (84, 60, 58), (58, 40, 42))
        if self.complete:
            self.hip_roof(cx, cy, 2.9, 2.4, hh, 18, (86, 50, 48), (58, 32, 32))
            self.door(cx - 6, cy + 22, 18, 22, (28, 20, 22), glow=(190, 90, 70))
            # meat hooks
            for i in range(3):
                x = cx + 34 + i * 12
                dline(self.s, (140, 130, 120), (x, cy + 18), (x, cy + 2), 1.4)
                dline(self.s, (140, 130, 120), (x, cy + 2), (x - 4, cy + 2), 1.4)
                dellipse(self.s, (150, 60, 58), (x - 6, cy + 2, 10, 14))
            # chimney smoke
            self.prism(cx + 24, cy - 18, 0.5, 0.5, hh + 26, (74, 62, 60), (74, 62, 60), (50, 42, 42))
            for i in range(3):
                dcircle(self.s, (80, 72, 70, 100), (cx + 30 + i * 7, cy - hh - 38 - i * 8), 5 + i * 2)
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_temple(self, cx, cy):
        p = self.p
        hh = 40 * self.prog
        self.prism(cx, cy, 2.4, 2.4, hh, (70, 60, 82), (60, 50, 72), (40, 32, 50))
        if self.complete:
            for ox, oy, th in ((-26, -20, 26), (26, -20, 34), (0, -34, 44)):
                self.prism(cx + ox, cy + oy, 0.7, 0.7, hh + th, (84, 72, 98), (74, 62, 88), (48, 40, 62))
                dpoly(self.s, p["roof"], [(cx + ox - 12, cy + oy - hh - th), (cx + ox, cy + oy - hh - th - 26), (cx + ox + 12, cy + oy - hh - th)])
            self.door(cx, cy + 24, 18, 26, (16, 12, 20), glow=(150, 90, 220))
            for i in (-1, 1):
                self.window(cx + i * 30, cy + 2, 7, 12, (150, 100, 230))
            for i in (-1, 1):
                self.banner(cx + i * 42, cy + 18, p["banner"], 22, 9, i)
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_bonetower(self, cx, cy):
        p = self.p
        hh = 60 * self.prog
        self.prism(cx, cy, 1.2, 1.2, hh, (100, 88, 110), (88, 76, 98), (58, 50, 68))
        if self.complete:
            self.skull(cx, cy - hh + 6, 12)
            for i in range(4):
                dline(self.s, BONE, (cx - 10 + i * 6, cy - hh + 22), (cx - 14 + i * 7, cy - 18), 1.6)
            for i in range(5):
                dcircle(self.s, (150, 210, 235), (cx + math.sin(i * 2) * 20, cy - 24 - i * 8), 2)
            self.window(cx, cy - 18, 4, 7, (150, 220, 240))
            self.door(cx, cy + 12, 8, 12, (18, 16, 24), glow=(130, 200, 220))
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)

    def b_altarhollow(self, cx, cy):
        p = self.p
        hh = 16 * self.prog
        self.prism(cx, cy, 2.2, 2.2, 8, (60, 52, 70), (52, 44, 60), (36, 30, 44))
        if self.complete:
            # rib arch
            for i in (-1, 1):
                x = cx + i * 22
                for k in range(4):
                    dline(self.s, BONE, (x + i * k * 3, cy - 4), (x + i * (k * 2 + 8), cy - 12 - k * 9), 3)
                dline(self.s, BONE, (x, cy - 4), (x, cy - 40), 4)
            dline(self.s, BONE, (cx - 28, cy - 40), (cx + 28, cy - 40), 4)
            self.skull(cx, cy - 44, 10)
            # throne of bone
            for i in range(3):
                dline(self.s, shade(BONE, 0.8), (cx - 10 + i * 10, cy - 2), (cx - 14 + i * 12, cy - 30), 3)
            dcircle(self.s, (150, 90, 220), (cx, cy - 4), 10)
            dcircle(self.s, (210, 160, 250), (cx, cy - 6), 5)
            self.crystal(cx - 36, cy + 18, 14)
            self.crystal(cx + 36, cy + 18, 12)
        if not self.complete:
            self.scaffold(cx, cy, self.bw, self.bd, hh)


def make_building(art, bid, team, stage):
    b = B(art, bid, team, stage)
    return b.build()
