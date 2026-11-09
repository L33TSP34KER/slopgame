"""Flare ground, water and tree sprites."""
from __future__ import annotations
import os
import pygame
from .art import SS, INK, shade, mix, new_sprite
from .defs import TILE_W, TILE_H

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FLARE = os.path.join(ROOT, "assets", "flare", "raw", "tiles")


def _load(name):
    p = os.path.join(FLARE, name)
    return pygame.image.load(p).convert_alpha() if os.path.exists(p) else None


def floor_sources():
    """64x32 diamond crops: 16 grass + 16 cobble."""
    sheet = _load("grassland.png")
    out = {"grass": [], "stone": []}
    if sheet is None:
        return out
    for col in range(16):
        out["grass"].append(sheet.subsurface(pygame.Rect(col * 64, 96, 64, 32)).copy())
        out["stone"].append(sheet.subsurface(pygame.Rect(col * 64, 128 + 96, 64, 32)).copy())
    return out


def water_sources():
    sheet = _load("grassland_water.png")
    out = []
    if sheet is None:
        return out
    for col in range(16):
        out.append(sheet.subsurface(pygame.Rect(col * 64, 32, 64, 32)).copy())
    return out


def tree_sources():
    sheet = _load("grassland_trees.png")
    out = []
    if sheet is None:
        return out
    for row in range(2):
        for col in range(8):
            cell = sheet.subsurface(pygame.Rect(col * 128, row * 256, 128, 256)).copy()
            bb = cell.get_bounding_rect(min_alpha=8)
            if bb.w < 8 or bb.h < 8:
                continue
            img = cell.subsurface(bb).copy()
            out.append((img, bb.centerx, bb.bottom))
    return out


TINTS = {
    0: None,                       # grass
    1: (0.98, 0.78, 0.55),         # dirt
    2: None,                       # rock -> stone bases
    3: None,                       # water (handled separately)
    4: (1.22, 1.08, 0.76),         # sand
    5: (0.56, 0.48, 0.62),         # ash (desaturated cold)
    6: (0.66, 0.34, 0.36),         # blood
    7: (0.78, 0.92, 0.72),         # moss
}
BASE_KIND = {0: "grass", 1: "grass", 2: "stone", 4: "grass", 5: "grass", 6: "grass", 7: "grass"}
LIGHT = {0: 1.28, 1: 1.14, 2: 1.12, 4: 1.22, 5: 1.02, 6: 0.98, 7: 1.16}


def tint(surf, mul, light=1.0):
    out = surf.copy()
    m = mul or (1.0, 1.0, 1.0)
    c = (min(255, int(255 * m[0] * light)), min(255, int(255 * m[1] * light)),
         min(255, int(255 * m[2] * light)), 255)
    out.fill(c, special_flags=pygame.BLEND_RGBA_MULT)
    return out


PROP_CELLS = {
    "bush": [(6, 0), (6, 1), (6, 4), (6, 5)],
    "grass": [(6, 2), (6, 3), (6, 12), (6, 13), (6, 14), (6, 15)],
    "flowers": [(6, 6), (6, 7)],
    "rock": [(7, 0), (7, 1), (7, 2), (7, 3)],
    "bone": [(7, 10), (7, 11), (7, 12), (7, 13)],
    "stone": [(7, 1), (7, 2)],
    "stump": [(7, 8), (7, 9)],
    "statue": [(7, 14), (7, 15)],
    "crate": [(5, 0), (5, 1), (5, 2), (5, 3), (5, 4), (5, 5)],
}


def prop_sources():
    sheet = _load("grassland.png")
    out = {}
    if sheet is None:
        return out
    for kind, cells in PROP_CELLS.items():
        arr = []
        for (r, c) in cells:
            cell = sheet.subsurface(pygame.Rect(c * 64, r * 128, 64, 128)).copy()
            bb = cell.get_bounding_rect(min_alpha=8)
            if bb.w < 4 or bb.h < 4:
                continue
            img = cell.subsurface(bb).copy()
            arr.append((img, bb.centerx, bb.bottom))
        out[kind] = arr
    return out
