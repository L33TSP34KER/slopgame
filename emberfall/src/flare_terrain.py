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
    """64x32 diamond crops: grass (+dry variant) and cobble/stone.

    Prefers the seam-blended Emberfall sheet (opaque core, edges blended
    toward the row mean): the original Flare diamonds carry a hard 1 px alpha
    edge, and where two tiles abut that edge composites to a translucent line
    around every cell — the dark lattice players report.
    """
    sheet = _load("emberfall_ground.png")
    if sheet is not None and sheet.get_size() == (1024, 256):
        def row(r: int):
            return [sheet.subsurface(pygame.Rect(c * 64, r * 32, 64, 32)).copy()
                    for c in range(16)]
        # rows: 0 grass, 1 grass_dry, 2 dirt, 3 dirt_road, 4 sand, 5 ash,
        # 6 stone, 7 moss — colours are baked into the sheet (see
        # design/notes/flare-tiles.md), so art can pick by biome directly.
        return {"grass": row(0), "grass_dry": row(1), "dirt": row(2),
                "dirt_road": row(3), "sand": row(4), "ash": row(5),
                "stone": row(6), "moss": row(7)}
    sheet = _load("grassland.png")
    out = {"grass": [], "stone": []}
    if sheet is None:
        return out
    for col in range(16):
        out["grass"].append(sheet.subsurface(pygame.Rect(col * 64, 96, 64, 32)).copy())
        out["stone"].append(sheet.subsurface(pygame.Rect(col * 64, 128 + 96, 64, 32)).copy())
    return out


def water_sources():
    """{'depth': 16 deep->shallow diamonds, 'shore': 16 water|sand edges}.

    Prefers the seam-blended emberfall_water.png (design/notes/flare-tiles.md
    §6): row 0 is a clean depth ramp with no per-tile outlines or foam dashes.
    The row this function used to return — grassland_water.png y=32 — is a
    SHORELINE row (cliffs, docks, dashes); tiled as open water it is part of
    the "water is a test pattern" report.  The legacy fallback now reads the
    atlas's only clean full-coverage water row (y=160) instead.
    """
    sheet = _load("emberfall_water.png")
    if sheet is not None and sheet.get_size() == (1024, 64):
        def row(r: int):
            return [sheet.subsurface(pygame.Rect(c * 64, r * 32, 64, 32)).copy()
                    for c in range(16)]
        return {"depth": row(0), "shore": row(1)}
    legacy = _load("grassland_water.png")
    out = []
    if legacy is not None and legacy.get_height() >= 192:
        for col in range(16):
            out.append(legacy.subsurface(pygame.Rect(col * 64, 160, 64, 32)).copy())
    return {"depth": out, "shore": []}


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
