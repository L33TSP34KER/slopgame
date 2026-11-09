#!/usr/bin/env python3
"""Flare asset extraction / isometric TMX renderer for EMBERFALL.

Headless: only numpy + Pillow, no pygame, no X server, no display.

Subcommands
-----------
render  Render any rectangular region of a Flare Tiled map (*.tmx) to a PNG.
        Used to visually verify that the isometric assembly is correct and to
        pick crop rectangles for multi-tile buildings.

extract Extract/compose individual building sprites from the Flare atlases
        (and from composed TMX regions) into transparent PNGs.

verify  Run the quality gates on everything in the output directory.

Isometric anchor convention (matches Tiled's default for isometric maps)
------------------------------------------------------------------------
For a map with tilewidth TW / tileheight TH, the diamond of tile (gx, gy)
has its bounding box at::

    left = (gx - gy) * TW / 2
    top  = (gx + gy) * TH / 2
    (bottom vertex = left + TW/2, top + TH)

A tile image of size (iw, ih) is drawn with its BOTTOM-CENTER at the tile's
diamond bottom vertex, i.e.::

    image_left = left + tileoffset_x
    image_top  = top + TH - ih + tileoffset_y

``<tileoffset>`` from the embedded tileset is applied verbatim in pixels
(positive y = down), which is what Tiled does.

Building sprite anchor convention (used by every file written by `extract`)
---------------------------------------------------------------------------
ANCHOR = bottom-center of the trimmed PNG.
The bottom-center pixel is the front (bottom) vertex of the building's ground
footprint diamond. In game, blit with::

    screen_x = footprint_front_vertex_x - sprite_w / 2
    screen_y = footprint_front_vertex_y - sprite_h

Usage
-----
    python3 tools/flare_buildings.py render \
        --map tiled/empyrean_campaign/black_oak_city.tmx \
        --rect 0,0,40,40 --out design/notes/flare-town.png
    python3 tools/flare_buildings.py extract --out-dir assets/flare/buildings
    python3 tools/flare_buildings.py verify --dir assets/flare/buildings
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

Image.MAX_IMAGE_PIXELS = None

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FLARE = os.path.join(REPO, "vendor", "flare-game")
TILED = os.path.join(FLARE, "tiled")

FLIP_H, FLIP_V, FLIP_D = 0x80000000, 0x40000000, 0x20000000
GID_MASK = 0x0FFFFFFF

# Every Flare Tiled map in this repo is isometric on the same 192x96 grid.
MAP_TILE_W = 192
MAP_TILE_H = 96

# Editor-only layers: never rendered by default (invisible marker overlays).
DEFAULT_SKIP = {"collision", "set_rules", "set_rules "}


# --------------------------------------------------------------------------- #
# TMX parsing
# --------------------------------------------------------------------------- #
class Tileset:
    def __init__(self, firstgid, name, tw, th, columns, tilecount, image, offset,
                 base_dir, image_w=0, image_h=0):
        self.firstgid = firstgid
        self.name = name
        self.tw = tw
        self.th = th
        self.columns = columns
        self.tilecount = tilecount
        self.image = image              # absolute path (or None for collection)
        self.offset = offset            # (dx, dy) pixels
        self.image_w = image_w
        self.image_h = image_h
        self._img = None                # lazily loaded full RGBA atlas
        self._cache = {}

    @property
    def lastgid(self):
        return self.firstgid + self.tilecount - 1

    def atlas(self):
        if self._img is None:
            if not self.image or not os.path.exists(self.image):
                raise FileNotFoundError("tileset image missing: %r" % (self.image,))
            self._img = Image.open(self.image).convert("RGBA")
        return self._img

    def tile(self, gid):
        """Return the RGBA image for a local tile id (flips already applied)."""
        local = gid - self.firstgid
        if local in self._cache:
            return self._cache[local]
        col = local % self.columns
        row = local // self.columns
        if self.columns <= 0:
            raise ValueError("tileset %r has no columns" % self.name)
        box = (col * self.tw, row * self.th, col * self.tw + self.tw,
               row * self.th + self.th)
        img = self.atlas().crop(box)
        self._cache[local] = img
        return img


class Layer:
    def __init__(self, name, width, height, data, visible=True):
        self.name = name
        self.width = width
        self.height = height
        self.data = data
        self.visible = visible

    def gid(self, x, y):
        return self.data[y * self.width + x]


class TmxMap:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.dir = os.path.dirname(self.path)
        tree = ET.parse(self.path)
        root = tree.getroot()
        if root.tag != "map":
            raise ValueError("%s: root element is <%s>, expected <map>" % (path, root.tag))
        self.orientation = root.get("orientation", "orthogonal")
        self.tw = int(root.get("tilewidth"))
        self.th = int(root.get("tileheight"))
        self.width = int(root.get("width"))
        self.height = int(root.get("height"))
        self.backgroundcolor = root.get("backgroundcolor", "#000000")
        self.tilesets = []
        self.layers = []
        self.objectgroups = []
        self.properties = {}
        for child in root:
            if child.tag == "tileset":
                self.tilesets.append(self._parse_tileset(child))
            elif child.tag == "layer":
                self.layers.append(self._parse_layer(child))
            elif child.tag == "objectgroup":
                self.objectgroups.append(child.get("name", ""))
            elif child.tag == "properties":
                for p in child.findall("property"):
                    self.properties[p.get("name")] = p.get("value", p.text or "")
        self.tilesets.sort(key=lambda ts: ts.firstgid)

    # -- parsing helpers ---------------------------------------------------- #
    def _parse_tileset(self, el):
        if el.get("source"):
            raise NotImplementedError(
                "external tileset references are not supported (%s)" % el.get("source"))
        firstgid = int(el.get("firstgid"))
        name = el.get("name", "")
        tw = int(el.get("tilewidth"))
        th = int(el.get("tileheight"))
        columns = int(el.get("columns", 0))
        tilecount = int(el.get("tilecount", 0))
        offset = (0, 0)
        to = el.find("tileoffset")
        if to is not None:
            offset = (int(to.get("x", 0)), int(to.get("y", 0)))
        image_el = el.find("image")
        image = None
        iw = ih = 0
        if image_el is not None:
            iw = int(image_el.get("width", 0))
            ih = int(image_el.get("height", 0))
            image = os.path.normpath(os.path.join(self.dir, image_el.get("source")))
        if not columns and image and iw:
            columns = iw // tw
        if not tilecount and image and iw and ih:
            tilecount = columns * (ih // th)
        return Tileset(firstgid, name, tw, th, columns, tilecount, image, offset,
                       self.dir, iw, ih)

    @staticmethod
    def _parse_csv(text):
        out = []
        for tok in text.replace("\n", ",").split(","):
            tok = tok.strip()
            if tok:
                out.append(int(tok))
        return out

    def _parse_layer(self, el):
        data_el = el.find("data")
        if data_el is None:
            raise ValueError("layer %r has no <data>" % el.get("name"))
        enc = data_el.get("encoding")
        if enc != "csv":
            raise NotImplementedError("layer %r encoding %r not supported"
                                      % (el.get("name"), enc))
        data = self._parse_csv(data_el.text or "")
        w = int(el.get("width", self.width))
        h = int(el.get("height", self.height))
        if len(data) != w * h:
            raise ValueError("layer %r: %d cells, expected %d" % (el.get("name"), len(data), w * h))
        visible = el.get("visible", "1") != "0"
        return Layer(el.get("name", ""), w, h, data, visible)

    # -- lookup ------------------------------------------------------------- #
    def tileset_for(self, gid):
        ts = None
        for cand in self.tilesets:
            if cand.firstgid <= gid <= cand.lastgid:
                ts = cand
        return ts

    def layer(self, name):
        for l in self.layers:
            if l.name == name:
                return l
        raise KeyError("no layer named %r in %s" % (name, self.path))


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def placement(m: TmxMap, gx, gy, iw, ih, offset):
    """Top-left pixel of the tile image for tile (gx, gy) on the canvas grid."""
    left = (gx - gy) * m.tw // 2 + offset[0]
    top = (gx + gy) * m.th // 2 + m.th - ih + offset[1]
    return left, top


def _apply_flips(img, flags):
    if flags & FLIP_D:
        img = img.transpose(Image.TRANSPOSE)
    if flags & FLIP_H:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    if flags & FLIP_V:
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    return img


def iter_cells(m: TmxMap, layers, rect):
    """Yield (layer, gx, gy, raw_gid) for nonzero cells inside rect."""
    rx, ry, rw, rh = rect
    rx = max(0, rx)
    ry = max(0, ry)
    rw = min(rw, m.width - rx)
    rh = min(rh, m.height - ry)
    for layer in layers:
        for gy in range(ry, ry + rh):
            base = gy * layer.width
            for gx in range(rx, rx + rw):
                raw = layer.data[base + gx]
                if raw & GID_MASK:
                    yield layer, gx, gy, raw


def compute_canvas(m: TmxMap, cells):
    """Union of diamond bboxes and tile-image bboxes (before trimming)."""
    min_l = min_t = 1 << 60
    max_r = max_b = -(1 << 60)
    for _layer, gx, gy, raw in cells:
        raw_id = raw & GID_MASK
        ts = m.tileset_for(raw_id)
        if ts is None:
            continue
        iw, ih = ts.tw, ts.th   # tile cell size (NOT the whole atlas image)
        l, t = placement(m, gx, gy, iw, ih, ts.offset)
        min_l = min(min_l, l)
        min_t = min(min_t, t)
        max_r = max(max_r, l + iw)
        max_b = max(max_b, t + ih)
        # diamond itself
        dl = (gx - gy) * m.tw // 2
        dt = (gx + gy) * m.th // 2
        min_l = min(min_l, dl)
        min_t = min(min_t, dt)
        max_r = max(max_r, dl + m.tw)
        max_b = max(max_b, dt + m.th)
    if min_l > max_r:
        return None
    return min_l, min_t, max_r, max_b


def render_map(m: TmxMap, rect, layer_names=None, skip=None, bg=None, scale=1,
               tileset_names=None):
    """Render a rectangular tile region to an RGBA PIL image.

    tileset_names: optional iterable of tileset names; only cells belonging to
    one of those tilesets are drawn (used to isolate buildings from props).
    """
    if layer_names is None:
        skip = set(DEFAULT_SKIP if skip is None else skip)
        layers = [l for l in m.layers if l.name not in skip and l.visible]
    else:
        wanted = list(layer_names)
        layers = [m.layer(n) for n in wanted]
    cells = list(iter_cells(m, layers, rect))
    if tileset_names:
        wanted_ts = set(tileset_names)
        cells = [c for c in cells
                 if (m.tileset_for(c[3] & GID_MASK) is not None
                     and m.tileset_for(c[3] & GID_MASK).name in wanted_ts)]
    bbox = compute_canvas(m, cells)
    if bbox is None:
        img = Image.new("RGBA", (max(1, rect[2] * m.tw), max(1, rect[3] * m.th)), (0, 0, 0, 0))
        return img
    min_l, min_t, max_r, max_b = bbox
    W = max_r - min_l
    H = max_b - min_t
    if W <= 0 or H <= 0:
        raise ValueError("empty render bounds")
    if W * H > 260_000_000:
        raise ValueError("render too large: %dx%d" % (W, H))
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if bg:
        canvas = Image.new("RGBA", (W, H), bg)
    for layer, gx, gy, raw in cells:
        flags = raw & 0xE0000000
        raw_id = raw & GID_MASK
        ts = m.tileset_for(raw_id)
        if ts is None:
            continue
        tile = ts.tile(raw_id)
        if flags:
            tile = _apply_flips(tile, flags)
        iw, ih = tile.size
        l, t = placement(m, gx, gy, iw, ih, ts.offset)
        # clip against the canvas rectangle (canvas space = map space - origin)
        cl = max(l, min_l)
        ct = max(t, min_t)
        cr = min(l + iw, max_r)
        cb = min(t + ih, max_b)
        if cl >= cr or ct >= cb:
            continue
        sub = tile.crop((cl - l, ct - t, cr - l, cb - t))
        box = (cl - min_l, ct - min_t, cr - min_l, cb - min_t)
        region = canvas.crop(box)
        merged = Image.alpha_composite(region, sub)
        canvas.paste(merged, box)
    if scale != 1:
        canvas = canvas.resize((W // scale, H // scale), Image.NEAREST)
    return canvas


def trim_alpha(img, pad=0):
    """Crop to the alpha bounding box. Returns (trimmed, bbox)."""
    a = np.array(img)[:, :, 3]
    ys, xs = np.nonzero(a > 0)
    if len(xs) == 0:
        return img, (0, 0, img.width, img.height)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(img.width, x1 + pad)
    y1 = min(img.height, y1 + pad)
    return img.crop((x0, y0, x1, y1)), (x0, y0, x1, y1)


def parse_rect(text):
    parts = [int(p) for p in text.split(",")]
    if len(parts) == 4:
        return tuple(parts)
    if len(parts) == 2:
        return (parts[0], parts[1], 1, 1)
    raise argparse.ArgumentTypeError("rect must be x,y,w,h (got %r)" % text)


# --------------------------------------------------------------------------- #
# Building catalogue
# --------------------------------------------------------------------------- #
# Atlasses the composer may draw from.
#   key -> (path relative to vendor/flare-game/tiled, columns, cell_w, cell_h)
ATLASES = {
    "structures": ("tilesheets/grassland_structures.png", 16, 192, 768),
    "snow_structures": ("tilesheets/snowplains_structures.png", 16, 192, 768),
    "grassland": ("tilesheets/grassland.png", 16, 192, 384),
    "grassland_2x2": ("tilesheets/grassland_2x2.png", 4, 384, 192),
    "rottentower": ("tilesheets/grassland_rottentower.png", 1, 1074, 1074),
    "snow_rottentower": ("tilesheets/snowplains_rottentower.png", 1, 1074, 1074),
    "ruins": ("tilesheets/ruins.png", 16, 192, 384),
    "dungeon": ("tilesheets/dungeon.png", 16, 192, 384),
    "dungeon_2x2": ("tilesheets/dungeon_2x2.png", 4, 384, 192),
}

# Every entry is one shipped sprite.
#   src "atlas"    -> crop a rectangle out of one tilesheet PNG
#   src "map"      -> render a tile rect of a TMX using only the given layers,
#                     then trim to alpha (multi-tile buildings assembled by the
#                     original Flare mappers)
#   src "compose"  -> place atlas cells on a virtual isometric grid
#                     (parts are painted in list order = back to front;
#                      "above": True stacks the part on the one before it)
BUILDINGS = [
    # ------------------------------- HUMAN -------------------------------- #
    dict(
        name="human_town_hall", kind="human", src="compose", footprint="3x3",
        post="human_town_hall",
        parts=[
            dict(a="structures", id=1, gx=1, gy=1),
            dict(a="structures", id=0, gx=0, gy=1),
            dict(a="structures", id=2, gx=2, gy=1),
            dict(a="structures", id=3, gx=2, gy=0),
        ],
        note="alternate cabin fragment set (structures ids 0-3): lodge with big gable + wing",
    ),
    dict(
        name="human_house_farm", kind="human", src="compose", footprint="2x2",
        post="human_house_farm",
        parts=[
            dict(a="structures", id=7, gx=2, gy=0),
            dict(a="structures", id=4, gx=0, gy=1),
            dict(a="structures", id=5, gx=1, gy=1),
            dict(a="structures", id=6, gx=2, gy=1),
        ],
        note="exact replica of the log cabin Flare places in black_oak_city/lochport",
    ),
    dict(
        name="human_barracks", kind="human", src="compose", footprint="2x2",
        parts=[
            dict(a="grassland", id=91, gx=0, gy=0),
            dict(a="grassland", id=88, gx=1, gy=0),
            dict(a="grassland", id=94, gx=2, gy=0),
            dict(a="grassland", id=59, gx=0, gy=1),
            dict(a="grassland", id=56, gx=1, gy=1),
            dict(a="grassland", id=80, gx=0, gy=2),
            dict(a="grassland", id=61, gx=2, gy=1),
        ],
        post="human_barracks",
        note="tents + rail palisade behind + spear rack w/ shield + crimson/gold standard = military camp",
    ),
    dict(
        name="human_workshop_lumber", kind="human", src="compose", footprint="3x2",
        parts=[
            dict(a="grassland", id=117, gx=0, gy=0),
            dict(a="grassland", id=118, gx=1, gy=0),
            dict(a="grassland", id=119, gx=2, gy=0),
            dict(a="grassland", id=84, gx=0, gy=2),
            dict(a="grassland", id=85, gx=1, gy=2),
            dict(a="grassland", id=121, gx=1, gy=1),
            dict(a="grassland", id=120, gx=0, gy=1),
            dict(a="grassland", id=92, gx=2, gy=2),
        ],
        post="human_workshop_lumber",
        note="tall timber stacks + log piles + saw frame + small crimson pennant = lumber mill",
    ),
    dict(
        name="human_blacksmith_smithy", kind="human", src="compose", footprint="2x2",
        post="human_blacksmith_smithy",
        parts=[
            dict(a="grassland", id=86, gx=0, gy=1),
            dict(a="grassland", id=87, gx=1, gy=1),
            dict(a="grassland", id=61, gx=2, gy=1),
            dict(a="grassland", id=80, gx=0, gy=2),
        ],
        note="shingle lean-to on posts + stone chimney + forge ember = reads as a building",
    ),
    dict(
        name="human_guard_tower", kind="human", src="compose", footprint="2x2",
        post="human_guard_tower", draw_width=104,
        parts=[
            dict(a="ruins", id=177, gx=1, gy=1),
            dict(a="ruins", id=177, gx=1, gy=1, above=True, overlap=120),
            dict(a="ruins", id=199, gx=1, gy=1, above=True, overlap=90),
        ],
        note="stacked stone column blocks + tapered crenellated cap (ruins.png)",
    ),
    dict(
        name="human_temple_altar", kind="human", src="compose", footprint="3x3",
        post="human_temple_altar",
        parts=[
            dict(a="ruins", id=177, gx=0, gy=1),
            dict(a="grassland_2x2", id=0, gx=1, gy=1),
            dict(a="ruins", id=128, gx=1, gy=1, dy=-60),
            dict(a="ruins", id=177, gx=2, gy=1),
        ],
        note="OPEN ARCH spanning two columns over the rune circle + standing ember flame (wide, low, no mass)",
    ),
    dict(
        name="human_keep", kind="human", src="compose", footprint="3x3",
        parts=[], post="human_keep",
        note="CASTLE: crenellated curtain wall + twin turrets + stacked keep, ember gate/windows, crimson+gold standards",
    ),
    # ---------------------------- UNDEAD/RUINED ---------------------------- #
    dict(
        name="undead_ruined_tower", kind="undead", src="atlas", post="undead_ruined_tower",
        footprint="3x3", atlas="tilesheets/grassland_rottentower.png",
        rect=(0, 0, 1074, 1074),
        note="Flare 'rottentower': ivy-covered stone tower, rotted plank roof",
    ),
    dict(
        name="undead_ruined_house", kind="undead", src="compose", footprint="3x3",
        post="undead_ruined_house",
        parts=[
            dict(a="structures", id=8, gx=0, gy=3),
            dict(a="structures", id=9, gx=1, gy=3),
            dict(a="structures", id=10, gx=2, gy=3),
            dict(a="structures", id=14, gx=3, gy=0),
            dict(a="structures", id=13, gx=3, gy=1),
            dict(a="structures", id=12, gx=3, gy=2),
            dict(a="structures", id=11, gx=3, gy=3),
        ],
        note="round collapsed stone shell with planks + floor hole (ydrakka_pass cluster)",
    ),
    dict(
        name="undead_crypt", kind="undead", src="compose", footprint="3x2",
        post="undead_crypt",
        parts=[
            dict(a="ruins", id=336, gx=0, gy=1),
            dict(a="ruins", id=306, gx=1, gy=1),
            dict(a="ruins", id=340, gx=2, gy=1),
            dict(a="ruins", id=246, gx=1, gy=2),
        ],
        note="stone sarcophagus between iron grave fences + bone pile",
    ),
    dict(
        name="undead_ziggurat_ruin", kind="undead", src="compose", footprint="2x2",
        parts=[], post="undead_ziggurat_ruin",
        note="3-tier stepped pyramid (430->286->162 wide) + shrine with violet flame, violet seams, bone rim",
    ),
    dict(
        name="undead_necropolis_ruin", kind="undead", src="compose", footprint="3x3",
        parts=[], post="undead_necropolis_ruin",
        note="WIN CONDITION: tall tomb+spire (~950px) with violet flame, bone spikes/skulls, headstones + iron fence, violet+sickly-green glow",
    ),
    dict(
        name="undead_bone_ritual", kind="undead", src="compose", footprint="2x2",
        post="undead_bone_ritual",
        parts=[
            dict(a="ruins", id=269, gx=1, gy=1),
            dict(a="ruins", id=128, gx=0, gy=1),
            dict(a="ruins", id=270, gx=2, gy=1),
            dict(a="ruins", id=247, gx=1, gy=2),
            dict(a="ruins", id=249, gx=0, gy=2),
        ],
        note="glowing skull-orb altar flanked by monuments + bones",
    ),
]


def load_buildings(path=None):
    """Optional JSON catalogue override (default: the list above)."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "flare_buildings_catalog.json")
    if path and os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return BUILDINGS


# --------------------------------------------------------------------------- #
# Subcommands
# --------------------------------------------------------------------------- #
def resolve_map_path(text):
    """Resolve a --map argument: absolute, repo-relative, flare-relative or tiled-relative."""
    if os.path.isabs(text):
        return text
    for base in (REPO, FLARE, TILED):
        cand = os.path.join(base, text)
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError("map not found: %s (tried under %s, %s, %s)"
                            % (text, REPO, FLARE, TILED))


def cmd_render(args):
    m = TmxMap(resolve_map_path(args.map))
    layers = args.layers.split(",") if args.layers else None
    tilesets = args.tilesets.split(",") if args.tilesets else None
    bg = None
    if args.bg:
        bg = hex_to_rgba(args.bg)
    img = render_map(m, args.rect, layer_names=layers, bg=bg, scale=args.scale,
                     tileset_names=tilesets)
    out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    img.save(out)
    print("rendered %s rect=%s layers=%s tilesets=%s -> %s (%dx%d)" % (
        os.path.relpath(m.path, REPO), args.rect,
        layers or "all-but-editor", tilesets or "all", out, img.width, img.height))
    return 0


def hex_to_rgba(text):
    text = text.lstrip("#")
    if len(text) == 6:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), 255)
    if len(text) == 8:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16),
                int(text[6:8], 16))
    raise argparse.ArgumentTypeError("bad colour %r" % text)


_ATLAS_CACHE = {}


def _atlas(key):
    if key not in _ATLAS_CACHE:
        rel, cols, tw, th = ATLASES[key]
        path = os.path.join(TILED, rel)
        img = Image.open(path).convert("RGBA")
        _ATLAS_CACHE[key] = dict(path=path, cols=cols, tw=tw, th=th, img=img)
    return _ATLAS_CACHE[key]


def content_bbox(img):
    a = np.array(img)[:, :, 3]
    ys, xs = np.nonzero(a > 0)
    if len(xs) == 0:
        return (0, 0, img.width, img.height)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _part_image(p):
    """Fetch + optionally crop/flip/scale/recolor one atlas cell."""
    a = _atlas(p["a"])
    cid = int(p["id"])
    col, row = cid % a["cols"], cid // a["cols"]
    img = a["img"].crop((col * a["tw"], row * a["th"],
                         col * a["tw"] + a["tw"], row * a["th"] + a["th"]))
    if p.get("crop"):
        l, t, r, b = p["crop"]
        img = img.crop((l, t, r, b))
    if p.get("flip") == "h":
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    elif p.get("flip") == "v":
        img = img.transpose(Image.FLIP_TOP_BOTTOM)
    if p.get("scale") and abs(float(p["scale"]) - 1.0) > 1e-6:
        s = float(p["scale"])
        img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))),
                         Image.LANCZOS)
    arr = np.array(img).astype(np.float32)
    if p.get("key_black"):
        # Many Flare wall tiles paint their hidden back face pure black; drop it.
        near_black = arr[:, :, :3].max(axis=2) <= float(p.get("key_black", 6))
        arr[:, :, 3] = np.where(near_black, 0.0, arr[:, :, 3])
    if p.get("tint_mul"):
        m = p["tint_mul"]
        arr[:, :, 0] *= m[0]
        arr[:, :, 1] *= m[1]
        arr[:, :, 2] *= m[2]
    if p.get("tint_screen"):
        m = p["tint_screen"]
        for i in range(3):
            arr[:, :, i] = 255.0 - (255.0 - arr[:, :, i]) * (255.0 - m[i] * 255.0) / 255.0
    if p.get("dim"):
        arr[:, :, :3] *= float(p["dim"])
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def compose(spec):
    """Place atlas cells on a virtual isometric grid (Tiled anchor rules)."""
    placed = []
    descs = []
    last = None
    for p in spec["parts"]:
        a = _atlas(p["a"])
        img = _part_image(p)
        gx, gy = int(p["gx"]), int(p["gy"])
        left = (gx - gy) * MAP_TILE_W // 2 + int(p.get("dx", 0))
        top = (gx + gy) * MAP_TILE_H // 2 + MAP_TILE_H - a["th"] + int(p.get("dy", 0))
        cb = content_bbox(img)
        if p.get("above") and last is not None:
            # stack: bottom of this part's content sits on top of the last one
            prev_content_top = last["t"] + last["cb"][1]
            top = prev_content_top + int(p.get("overlap", 16)) - cb[3]
        placed.append(dict(img=img, l=left, t=top, cb=cb))
        note = p.get("desc")
        if note:
            descs.append(note)
        else:
            descs.append("%s#%d@g(%d,%d)" % (p["a"], int(p["id"]), gx, gy))
        last = placed[-1]
    if not placed:
        # fully procedural sprite: the post-processor paints it from scratch
        return Image.new("RGBA", (8, 8), (0, 0, 0, 0)), "procedural"
    min_l = min(e["l"] for e in placed)
    min_t = min(e["t"] for e in placed)
    max_r = max(e["l"] + e["img"].width for e in placed)
    max_b = max(e["t"] + e["img"].height for e in placed)
    canvas = Image.new("RGBA", (max_r - min_l, max_b - min_t), (0, 0, 0, 0))
    for e in placed:
        box = (e["l"] - min_l, e["t"] - min_t)
        canvas.alpha_composite(e["img"], box)
    return canvas, " + ".join(descs)


# --------------------------------------------------------------------------- #
# Painterly procedural pieces (art-coherence-04 upgrade pass)
# ---------------------------------------------------------------------------
# Everything here paints INTO a compose() canvas using the same 2:1 isometric
# angle as the atlases, samples its textures from the real Flare tilesheets and
# keeps the alpha clean, so the results sit next to the source crops without
# looking vector-ish.
FACTION = {
    "human": dict(crimson=(168, 58, 58), crimson_dk=(112, 34, 36), gold=(217, 164, 65),
                  gold_dk=(150, 108, 40), ember=(240, 156, 70), wood=(96, 70, 44)),
    "undead": dict(bone=(216, 210, 189), bone_dk=(150, 144, 126),
                   violet=(112, 84, 148), violet_dk=(58, 42, 78),
                   sick=(158, 202, 96), sick_dk=(92, 130, 60)),
}

# kind -> (atlas key, tile id, optional fraction box of the content bbox)
# sampled for surface texture.  Only fully-painted tiles are used: wall blocks
# carry a pure-black "back face" paint which would show as flat blotches.
_TEX_SRC = {
    "stone": ("ruins", 5, None),          # cracked slab floor -> masonry
    "stone_light": ("ruins", 0, None),    # clean slab floor
    "stone_dark": ("ruins", 2, None),     # darker slab
    "wood": ("grassland", 117, None),     # stacked timber -> bark grain
    "wood_dark": ("grassland", 118, None),
    "shingle": ("structures", 7, (0.0, 0.0, 1.0, 0.62)),
    "iron": ("ruins", 338, None),         # iron fence -> dark metal
    "bone": ("dungeon", 162, None),       # bone pile
}
_TEX_CACHE = {}
# target mean luminance per surface so procedural stone sits in the same
# mid-tone range as the painted Flare blocks (raw slab samples are darker)
_TEX_TARGET = {"stone": 126, "stone_light": 138, "stone_dark": 106, "wood": 96,
               "wood_dark": 86, "shingle": 84, "iron": 92, "bone": 150}


def _tex_source(kind):
    if kind in _TEX_CACHE:
        return _TEX_CACHE[kind]
    key, gid, frac = _TEX_SRC.get(kind, _TEX_SRC["stone"])
    a = _atlas(key)
    col, row = gid % a["cols"], gid // a["cols"]
    cell = a["img"].crop((col * a["tw"], row * a["th"],
                          col * a["tw"] + a["tw"], row * a["th"] + a["th"]))
    bb = content_bbox(cell)
    if frac:
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        bb = (bb[0] + int(bw * frac[0]), bb[1] + int(bh * frac[1]),
              bb[0] + int(bw * frac[2]), bb[1] + int(bh * frac[3]))
    inner = cell.crop(bb)
    arr = np.array(inner).astype(np.float32)
    op = arr[:, :, 3] > 0
    if op.sum() < 64:
        arr[:, :, :3] = 120.0
        arr[:, :, 3] = 255.0
    else:
        # drop the pure-black "hidden back face" paint some wall tiles carry,
        # then fill every transparent texel with the mean opaque colour so the
        # crop can be stretched / tiled without holes or black blotches
        rgb = arr[:, :, :3]
        good = op & (rgb.max(axis=2) > 14)
        if good.sum() < 64:
            good = op
        mean = rgb[good].mean(axis=0)
        for i in range(3):
            ch = rgb[:, :, i]
            arr[:, :, i] = np.where(good, ch, mean[i])
        arr[:, :, 3] = 255.0
    target = _TEX_TARGET.get(kind)
    if target:
        m = arr[:, :, :3].mean()
        if m > 1.0:
            arr[:, :, :3] *= float(target) / m
    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    _TEX_CACHE[kind] = out
    return out


# masonry is generated (not sampled): the painted floor tiles carry a diamond
# tile outline which, tiled across a wall, reads as a lattice/glassy seam.
_NOISE_COL = {"stone": (126, 131, 117), "stone_light": (142, 146, 134),
              "stone_dark": (104, 108, 97)}


def _stone_texture(kind, w, h, seed=0):
    base = np.array(_NOISE_COL[kind], dtype=np.float32)
    fine = np.array(Image.fromarray(rng_noise(w, h, seed + 11))
                    .filter(ImageFilter.GaussianBlur(0.7))).astype(np.float32)
    coarse = np.array(Image.fromarray(rng_noise(w, h, seed + 12))
                      .filter(ImageFilter.GaussianBlur(max(w, h) / 18.0))).astype(np.float32)
    blotch = np.array(Image.fromarray(rng_noise(w, h, seed + 13))
                      .filter(ImageFilter.GaussianBlur(max(w, h) / 7.0))).astype(np.float32)
    v = ((fine - 127.0) / 127.0 * 9.0 + (coarse - 127.0) / 127.0 * 14.0
         + (blotch - 127.0) / 127.0 * 10.0)
    rgb = base[None, None, :] + v[:, :, None]
    rgb[:, :, 2] += (coarse - 127.0) / 127.0 * 4.0     # slight cool/warm drift
    out = np.dstack([np.clip(rgb, 0, 255),
                     np.full((h, w), 255.0)]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def texture(kind, w, h, seed=0, grain=5.0, mottle=7.0):
    """Painterly surface texture, sized (w, h), RGBA opaque."""
    w, h = max(2, int(w)), max(2, int(h))
    if kind in _NOISE_COL:
        return _stone_texture(kind, w, h, seed)
    src = _tex_source(kind)
    sw, sh = src.size
    rng = random.Random(seed * 7919 + 13)
    # largest source window with the target aspect ratio (mirror-tiled below)
    ar = w / float(h)
    if sh * ar <= sw:
        tw, th = max(8, int(round(sh * ar))), sh
    else:
        tw, th = sw, max(8, int(round(sw / ar)))
    tw = min(tw, sw)
    th = min(th, sh)
    x0 = rng.randint(0, max(0, sw - tw))
    y0 = rng.randint(0, max(0, sh - th))
    tile = src.crop((x0, y0, x0 + tw, y0 + th))
    big = Image.new("RGBA", (max(w, tw * 2), max(h, th * 2)))
    for iy in range(0, big.height + th, th):
        for ix in range(0, big.width + tw, tw):
            p = tile
            if (ix // tw) % 2:
                p = p.transpose(Image.FLIP_LEFT_RIGHT)
            if (iy // th) % 2:
                p = p.transpose(Image.FLIP_TOP_BOTTOM)
            big.paste(p, (ix, iy))
    out = big.crop((0, 0, w, h)).resize((w, h), Image.LANCZOS)
    arr = np.array(out).astype(np.float32)
    if grain > 0:
        n = np.array(Image.fromarray(
            rng_noise(w, h, seed + 1)).filter(ImageFilter.GaussianBlur(0.6)))
        arr[:, :, :3] += (n[:, :, None] - 128.0) / 128.0 * grain
    if mottle > 0:
        n = np.array(Image.fromarray(
            rng_noise(w, h, seed + 2)).filter(ImageFilter.GaussianBlur(max(w, h) / 24.0)))
        arr[:, :, :3] += (n[:, :, None] - 128.0) / 128.0 * mottle
    arr[:, :, 3] = 255.0
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def rng_noise(w, h, seed):
    rng = np.random.default_rng(seed * 104729 + 7)
    return rng.integers(0, 256, size=(h, w), dtype=np.uint8)


def _poly_mask(size, polys, ss=3):
    """Antialiased 0..1 mask of one or more polygons (supersampled)."""
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(m)
    for pts in polys:
        d.polygon([(x * ss, y * ss) for x, y in pts], fill=255)
    m = m.resize((w, h), Image.LANCZOS)
    return np.array(m).astype(np.float32) / 255.0


def _line_mask(size, pts, width, ss=3):
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(m)
    d.line([(x * ss, y * ss) for x, y in pts], fill=255, width=max(1, int(width * ss)),
           joint="curve")
    m = m.resize((w, h), Image.LANCZOS)
    return np.array(m).astype(np.float32) / 255.0


def _blur(arr, r):
    if r <= 0:
        return arr
    im = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8), "L")
    return np.array(im.filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255.0


def _course_mask(w, h, spacing, slope, width=2):
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    c = -h - w
    while c < h + w:
        d.line([(0, c), (w, c + slope * w)], fill=255, width=width)
        c += spacing
    return np.array(m).astype(np.float32) / 255.0


def prism_layer(w, h, kind="stone", seed=0, shade=(0.75, 1.02, 1.24), grad=0.11,
                battlement=0, over=0, rim=True, courses=34, top_dim=1.0):
    """Isometric 2:1 prism.

    Returns (RGBA image, (ax, ay)) where (ax, ay) is the front (bottom) vertex
    of the prism's BASE diamond, i.e. the sprite anchor convention.
    battlement > 0 : add a parapet cap of that pixel height with crenel slots.
    """
    w, h = max(6, int(w)), max(6, int(h))
    D = w // 2
    pad = 4
    W, H = w + 2 * pad, h + D + 2 * pad
    ax, ay = pad + w // 2, pad + h + D
    # top diamond corners
    tB = (pad + w / 2.0, pad)                       # back
    tR = (pad + w, pad + D / 2.0)                   # right
    tF = (pad + w / 2.0, pad + D)                   # front
    tL = (pad, pad + D / 2.0)                       # left
    # bottom diamond corners
    bF = (pad + w / 2.0, pad + h + D)
    bL = (pad, pad + h + D / 2.0)
    bR = (pad + w, pad + h + D / 2.0)

    m_left = _poly_mask((W, H), [[tL, tF, bF, bL]])
    m_right = _poly_mask((W, H), [[tF, tR, bR, bF]])
    m_top = _poly_mask((W, H), [[tB, tR, tF, tL]])

    yy = np.arange(H, dtype=np.float32)[:, None]
    tlin = np.clip((yy - pad) / float(max(1, h + D)), 0.0, 1.0)
    sh = np.ones((H, W), dtype=np.float32)
    sh = sh * (1.0 - grad * tlin)
    sh = sh * (1.0 + (shade[2] * top_dim - 1.0) * m_top)
    sh = sh * (1.0 + (shade[0] - 1.0) * m_left)
    sh = sh * (1.0 + (shade[1] - 1.0) * m_right)

    tex = np.array(texture(kind, W, H, seed=seed)).astype(np.float32)
    rgb = tex[:, :, :3] * sh[:, :, None]

    if courses:
        # stone courses: joints follow each face's iso direction
        for slope, fmask in ((0.5, m_left), (-0.5, m_right)):
            j = _blur(_course_mask(W, H, courses, slope, 2) * fmask, 0.9)
            hl = _blur(_course_mask(W, H, courses + 4, slope, 1) * fmask, 1.4)
            rgb *= (1.0 - 0.15 * j)[:, :, None]
            rgb += (hl * 7.0)[:, :, None]

    if rim:
        e_top = _blur(_line_mask((W, H), [tL, tB, tR], 2), 0.9)
        e_front = _blur(_line_mask((W, H), [tL, tF, tR], 2), 0.9)
        e_base = _blur(_line_mask((W, H), [bL, bF, bR], 3), 1.4)
        edge = _line_mask((W, H), [tF, bF], 2)
        rgb += (e_top * 26.0 - e_front * 10.0 - e_base * 26.0)[:, :, None]
        rgb += (edge * 14.0)[:, :, None]

    alpha = np.clip(m_left + m_right + m_top, 0.0, 1.0) * 255.0
    img = np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)
    out = Image.fromarray(img, "RGBA")

    if battlement:
        out = _add_parapet(out, w, h, int(battlement), kind, seed + 3, over=over)
        # _add_parapet keeps the same anchor (it only grows upward/outward)
    return out, (ax, ay)


def _add_parapet(base_img, w, h, mh, kind, seed, over=4):
    """Cap the prism with a parapet ring cut by crenel slots (battlements)."""
    W2 = w + 2 * over
    cap, (cx, cy) = prism_layer(W2, mh, kind=kind, seed=seed + 91,
                                shade=(0.74, 0.98, 1.20), grad=0.10, rim=True)
    cap = _cut_crenels(cap, W2, mh)
    pad = 4
    D = w // 2
    D2 = W2 // 2
    # align the cap's base diamond centre with the prism's top diamond centre
    dx = (w - W2) / 2.0
    dy = D / 2.0 - mh - D2 / 2.0
    out = base_img.copy()
    paste(out, cap, (cx, cy), cx + dx, cy + dy)
    return out


def _cut_crenels(cap, w2, mh):
    """Remove vertical slots from the two visible (front) parapet faces."""
    pad = 4
    D2 = w2 // 2
    tL = (pad, pad + D2 / 2.0)
    tF = (pad + w2 / 2.0, pad + D2)
    tR = (pad + w2, pad + D2 / 2.0)
    W, H = cap.size
    slots = []
    sw = max(7.0, w2 * 0.035)
    depth = mh + 6
    for a, b in ((tL, tF), (tF, tR)):
        ex, ey = b[0] - a[0], b[1] - a[1]
        L = (ex * ex + ey * ey) ** 0.5
        n = max(1, int(L / (sw * 3.0)))
        for i in range(n):
            t0 = 0.16 + (i + 0.18) * (0.68 / max(1, n))
            t1 = t0 + (0.68 / max(1, n)) * 0.42
            p0 = (a[0] + ex * t0, a[1] + ey * t0)
            p1 = (a[0] + ex * t1, a[1] + ey * t1)
            slots.append([p0, p1, (p1[0], p1[1] + depth), (p0[0], p0[1] + depth)])
    m = _poly_mask((W, H), slots)
    arr = np.array(cap).astype(np.float32)
    arr[:, :, 3] *= (1.0 - np.clip(m, 0, 1))
    # darken the freshly cut stone edges a touch
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def paste(dst, layer, anchor, x, y):
    """Paste `layer` so its `anchor` pixel lands on integer (x, y) in dst."""
    ax, ay = int(round(anchor[0])), int(round(anchor[1]))
    x, y = int(round(x)), int(round(y))
    px, py = x - ax, y - ay
    W, H = dst.size
    lw, lh = layer.size
    sx0, sy0 = max(0, -px), max(0, -py)
    dx0, dy0 = max(0, px), max(0, py)
    cw = min(lw - sx0, W - dx0)
    ch = min(lh - sy0, H - dy0)
    if cw <= 0 or ch <= 0:
        return dst
    piece = layer.crop((sx0, sy0, sx0 + cw, sy0 + ch))
    box = (dx0, dy0, dx0 + cw, dy0 + ch)
    under = dst.crop(box)
    dst.alpha_composite(Image.alpha_composite(under, piece), (dx0, dy0))
    return dst


def grow_canvas(img, extra_top=0, extra_bottom=0, extra_left=0, extra_right=0):
    if not any((extra_top, extra_bottom, extra_left, extra_right)):
        return img, (extra_left, extra_top)
    W, H = img.size
    out = Image.new("RGBA", (W + extra_left + extra_right, H + extra_top + extra_bottom),
                    (0, 0, 0, 0))
    out.alpha_composite(img, (extra_left, extra_top))
    return out, (extra_left, extra_top)


_GROW_OFF = [0, 0]


def _grow(img, top=760, left=420, right=420, bottom=40):
    """Give a post-processor room; the final extract trims back to content."""
    out, off = grow_canvas(img, extra_top=top, extra_bottom=bottom,
                           extra_left=left, extra_right=right)
    _GROW_OFF[0], _GROW_OFF[1] = off
    return out


def add_glow(img, cx, cy, rx, ry, color, strength=0.7, blur=None, add_alpha=0.55):
    """Soft screen-blended light blob (also lifts alpha -> halo outside art)."""
    blur = max(4.0, min(rx, ry) * 0.55) if blur is None else blur
    W, H = img.size
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(blur))
    a = np.array(m).astype(np.float32) / 255.0 * strength
    arr = np.array(img).astype(np.float32)
    col = np.array(color, dtype=np.float32)
    contrib = col[None, None, :] * a[:, :, None]
    arr[:, :, :3] = 255.0 - (255.0 - arr[:, :, :3]) * (255.0 - contrib) / 255.0
    arr[:, :, 3] = np.clip(arr[:, :, 3] + a * 255.0 * add_alpha, 0, 255)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def _shade_overlay(img, mask01, mul=1.0, add=0.0, blur=1.0):
    m = _blur(mask01, blur)[:, :, None]
    arr = np.array(img).astype(np.float32)
    arr[:, :, :3] = arr[:, :, :3] * (1.0 + (mul - 1.0) * m) + add * m
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def draw_banner(img, x, y, height, width=None, seed=0, kind="human", flip=False,
                pole=True, scale_cloth=1.0):
    """Banner on a pole; (x, y) = foot of the pole (ground contact point)."""
    pal = FACTION[kind]
    rng = random.Random(seed + 5)
    height = int(height)
    pole_w = max(3, int(height * 0.035))
    width = int(width or height * 0.42)
    need_top = int(y - height - 12)
    if need_top < 0:
        img, off = grow_canvas(img, extra_top=need_top * -1 + 8)
        y += -need_top + 8
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    # pole
    if pole:
        d.rectangle([x - pole_w // 2, y - height, x + pole_w // 2, y],
                    fill=(66, 48, 32, 255))
        d.rectangle([x - pole_w // 2, y - height, x - pole_w // 2 + max(1, pole_w // 3), y],
                    fill=(126, 96, 60, 255))
        # gold finial
        r = max(3, pole_w)
        d.ellipse([x - r, y - height - r * 1.6, x + r, y - height + r * 0.4],
                  fill=pal["gold"])
        d.ellipse([x - r * 0.5, y - height - r * 1.4, x, y - height - r * 0.6],
                  fill=(255, 232, 170, 255))
    # cloth: hangs from the crossbar near the top
    top = y - height + int(height * 0.06)
    cw = int(width * scale_cloth)
    ch = int(height * 0.52)
    sgn = -1 if flip else 1
    x0 = x + sgn * (pole_w // 2 - 1)
    wave = int(cw * 0.10)
    pts = [(x0, top),
           (x0 + sgn * cw, top + int(ch * 0.10)),
           (x0 + sgn * (cw - wave), top + int(ch * 0.62)),
           (x0 + sgn * int(cw * 0.86), top + ch),
           (x0 + sgn * int(cw * 0.30), top + int(ch * 0.90)),
           (x0, top + int(ch * 0.86))]
    d.polygon(pts, fill=pal["crimson"] + (255,))
    # gold trim: bottom hem + outer edge
    hem = [(x0 + sgn * int(cw * 0.86), top + ch),
           (x0 + sgn * int(cw * 0.30), top + int(ch * 0.90)),
           (x0, top + int(ch * 0.86)),
           (x0, top + int(ch * 0.70)),
           (x0 + sgn * int(cw * 0.26), top + int(ch * 0.75)),
           (x0 + sgn * int(cw * 0.80), top + int(ch * 0.83))]
    d.polygon(hem, fill=pal["gold"] + (255,))
    d.line([(x0 + sgn * cw, top + int(ch * 0.10)),
            (x0 + sgn * (cw - wave), top + int(ch * 0.62))],
           fill=pal["gold"] + (255,), width=max(2, int(ch * 0.05)))
    # emblem
    ex = x0 + sgn * int(cw * 0.45)
    ey = top + int(ch * 0.42)
    er = max(3, int(cw * 0.16))
    d.polygon([(ex, ey - er), (ex + sgn * er, ey), (ex, ey + er), (ex - sgn * er, ey)],
              fill=pal["gold"] + (255,))
    # fabric shading + grain
    garr = np.array(lay).astype(np.float32)
    ga = garr[:, :, 3] / 255.0
    ys = np.arange(img.height, dtype=np.float32)[:, None]
    t = np.clip((ys - float(y - height)) / float(max(1, height)), 0.0, 1.0)
    garr[:, :, :3] *= ((1.0 - 0.30 * t) *
                       np.ones((1, img.width), dtype=np.float32))[:, :, None]
    garr[:, :, :3] += (rng_noise(img.width, img.height, seed + 3)[:, :, None].astype(np.float32) - 128.0) * 0.10 * ga[:, :, None]
    lay = Image.fromarray(np.clip(garr, 0, 255).astype(np.uint8), "RGBA")
    img.alpha_composite(lay)
    return img


def _tongue(cx, base_y, w, h, lean=0.0, wexp=0.62):
    """Teardrop flame outline: rounded base, pointed tip."""
    pts_l, pts_r = [], []
    n = 14
    for i in range(n + 1):
        v = i / float(n)
        wid = w * max(0.0, (1.0 - v ** wexp))
        cxx = cx + lean * (v ** 2) * h
        pts_l.append((cxx - wid / 2.0, base_y - v * h))
        pts_r.append((cxx + wid / 2.0, base_y - v * h))
    return pts_l + pts_r[::-1]


def draw_flame(img, x, y, size, palette="ember", seed=0, glow=0.7):
    """Standing flame; (x, y) = base centre. Drawn with soft painterly tongues."""
    rng = random.Random(seed + 17)
    if palette == "ember":
        cols = [(196, 74, 22), (232, 132, 44), (246, 186, 84), (255, 236, 178)]
        halo = (255, 168, 84)
    elif palette == "violet":
        cols = [(74, 44, 124), (112, 78, 176), (156, 122, 214), (226, 214, 252)]
        halo = (146, 104, 232)
    else:  # sick green
        cols = [(64, 108, 38), (116, 176, 66), (176, 220, 110), (238, 252, 206)]
        halo = (148, 232, 92)
    size = float(size)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    # outer body -> inner core: shrinking, rising, slightly leaning tongues
    for i, col in enumerate(cols):
        k = 1.0 - i * 0.20
        w = size * 0.62 * k
        h = size * (0.95 - i * 0.14)
        lean = rng.uniform(-0.10, 0.10)
        d.polygon(_tongue(x, y, w, h, lean=lean),
                  fill=col + (255 if i >= 2 else 236,))
    # side licks
    for j in range(3):
        lx = x + rng.choice((-1, 1)) * size * rng.uniform(0.18, 0.34)
        ly = y - size * rng.uniform(0.02, 0.16)
        d.polygon(_tongue(lx, ly, size * rng.uniform(0.14, 0.22),
                          size * rng.uniform(0.3, 0.5), lean=rng.uniform(-0.3, 0.3)),
                  fill=cols[1] + (215,))
    # detached sparks
    for j in range(4):
        sx = x + rng.uniform(-size * 0.3, size * 0.3)
        sy = y - size * rng.uniform(0.75, 1.15)
        r = size * rng.uniform(0.02, 0.045)
        d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=cols[3] + (200,))
    lay = lay.filter(ImageFilter.GaussianBlur(max(0.8, size * 0.016)))
    img.alpha_composite(lay)
    if glow:
        img = add_glow(img, x, y - size * 0.42, size * 0.7, size * 0.72,
                       halo, strength=glow, add_alpha=0.0)
    return img


def draw_arch(img, p0, p1, height, arch_h=None, fill=(14, 10, 16), glow_color=None,
              glow_strength=0.75, bars=0, sill=None, seed=0):
    """Arched opening on an isometric FACE.

    p0/p1 = the two ends of the face's bottom edge (screen px); `height` is the
    wall height in px (upwards). The opening is centred on that edge.
    """
    x0, y0 = p0
    x1, y1 = p1
    W, H = img.size
    ex, ey = x1 - x0, y1 - y0          # edge vector
    span = (ex * ex + ey * ey) ** 0.5
    if span < 8:
        return img
    u0, u1 = 0.26, 0.74                # opening extent along the edge
    v_top = 0.86
    ah = (arch_h if arch_h else height * 0.62)

    def P(u, v):
        # v measured upward from the base edge, in px
        return (x0 + ex * u, y0 + ey * u - v)

    # opening outline in (u, v) space, supersampled via polygon in screen space
    arc = []
    steps = 18
    for i in range(steps + 1):
        t = i / float(steps)          # 0..1 across the arch top
        uu = u0 + (u1 - u0) * t
        vv = ah + (height * v_top - ah) * (1.0 - (2 * t - 1.0) ** 2) ** 0.5
        arc.append(P(uu, vv))
    poly = [P(u0, 0.0)] + arc + [P(u1, 0.0)]
    m = _poly_mask((W, H), [poly])

    # dark interior with a vertical gradient
    arr = np.array(img).astype(np.float32)
    yy = np.arange(H, dtype=np.float32)[:, None]
    grad = np.clip(0.55 + 0.9 * (yy / max(1, H)), 0.0, 1.4)
    fillc = np.array(fill, dtype=np.float32)[None, None, :] * grad[:, :, None]
    mm = np.clip(m, 0, 1)[:, :, None]
    arr[:, :, :3] = arr[:, :, :3] * (1 - mm) + np.clip(fillc, 0, 255) * mm
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")

    # stone surround: brighten a band just outside the opening + keystone
    band = np.clip(_blur(m, 2.5) - m, 0, 1)
    img = _shade_overlay(img, band * 0.9, mul=1.30, add=10.0, blur=1.2)
    inner = np.clip(_blur(m, 1.2) - _blur(m, 3.0), 0, 1)
    img = _shade_overlay(img, inner * 0.8, mul=0.7, add=0.0, blur=1.0)

    if bars:
        bl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bl)
        for i in range(1, bars + 1):
            uu = u0 + (u1 - u0) * i / (bars + 1.0)
            a = P(uu, 0)
            b = P(uu, ah * 1.02)
            bd.line([a, b], fill=(46, 42, 48, 255), width=max(2, int(span * 0.018)))
            bd.line([(a[0] - 1, a[1]), (b[0] - 1, b[1])], fill=(96, 90, 98, 190),
                    width=1)
        bl = bl.filter(ImageFilter.GaussianBlur(0.6))
        img.alpha_composite(bl)

    if glow_color:
        cx = (P(u0, 0)[0] + P(u1, 0)[0]) / 2.0
        cy = (P(u0, 0)[1] + P(u1, 0)[1]) / 2.0 - ah * 0.55
        img = add_glow(img, cx, cy, span * (u1 - u0) * 0.75, ah * 0.85,
                       glow_color, strength=glow_strength, add_alpha=0.16)
    return img


def draw_window(img, p0, p1, height, u=0.5, wfrac=0.14, hfrac=0.18, vfrac=0.5,
                warm=(250, 190, 110), strength=0.9, seed=0):
    """Small lit window on an isometric face."""
    x0, y0 = p0
    x1, y1 = p1
    ex, ey = x1 - x0, y1 - y0
    ww = ((ex * ex + ey * ey) ** 0.5) * wfrac

    def P(du, v):
        return (x0 + ex * (u + du), y0 + ey * (u + du) - v)

    v0 = height * (vfrac - hfrac / 2.0)
    v1 = height * (vfrac + hfrac / 2.0)
    du = ww / 2.0 / max(1.0, ((ex * ex + ey * ey) ** 0.5))
    poly = [P(-du, v0), P(du, v0), P(du, v1), P(-du, v1)]
    W, H = img.size
    m = _poly_mask((W, H), [poly])
    arr = np.array(img).astype(np.float32)
    c = np.array(warm, dtype=np.float32)
    arr[:, :, :3] = arr[:, :, :3] * (1 - m[:, :, None] * 0.85) + \
        c[None, None, :] * m[:, :, None] * 0.85
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    cx = sum(p[0] for p in poly) / 4.0
    cy = sum(p[1] for p in poly) / 4.0
    return add_glow(img, cx, cy, ww * 2.0, ww * 2.0, warm, strength=strength,
                    add_alpha=0.10)


def bone_rim(img, strength=0.5, kind="undead"):
    """Warm bone-coloured rim light on the brightest pixels (undead identity)."""
    col = np.array(FACTION[kind]["bone"], dtype=np.float32)
    arr = np.array(img).astype(np.float32)
    lum = arr[:, :, :3].mean(axis=2)
    a = arr[:, :, 3] / 255.0
    hi = np.clip((lum - 150.0) / 90.0, 0, 1) * a * strength
    edge = np.clip(_blur(a, 1.6) - _blur(a, 3.4), 0, 1)
    hi = np.clip(hi + edge * strength * 0.55, 0, 1)
    arr[:, :, :3] = 255.0 - (255.0 - arr[:, :, :3]) * (255.0 - col[None, None, :] * hi[:, :, None]) / 255.0
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def draw_saw_frame(img, x, y, width, height, seed=0, log=True):
    """Open A-frame saw bench with a blade: (x, y) = front-centre ground point."""
    rng = random.Random(seed + 23)
    W, H = img.size
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    wood = (104, 74, 44)
    wood_hi = (150, 112, 68)
    wood_dk = (58, 40, 26)
    hw = width / 2.0
    leg_t = max(3, int(width * 0.055))
    top_y = y - height
    # ground log under the frame
    if log:
        d.rounded_rectangle([x - hw * 0.95, y - height * 0.16, x + hw * 0.95,
                             y - height * 0.02], radius=int(height * 0.06),
                            fill=(92, 64, 38, 255))
        d.rounded_rectangle([x - hw * 0.95, y - height * 0.155, x + hw * 0.95,
                             y - height * 0.115], radius=int(height * 0.03),
                            fill=(132, 98, 58, 255))
    # two A-frame legs (front pair + back pair)
    for dx, col in ((-hw * 0.78, wood_dk), (hw * 0.78, wood)):
        d.line([(x + dx, y), (x + dx * 0.34, top_y)], fill=col + (255,),
               width=leg_t)
    for dx in (-hw * 0.52, hw * 0.52):
        d.line([(x + dx, y - height * 0.06), (x + dx * 0.3, top_y - height * 0.03)],
               fill=wood + (255,), width=max(2, leg_t - 1))
    # top bar
    d.line([(x - hw * 0.62, top_y), (x + hw * 0.62, top_y - height * 0.05)],
           fill=wood_hi + (255,), width=leg_t + 1)
    # blade: long thin quad with teeth
    by = top_y + height * 0.16
    blade = [(x - hw * 0.86, by + height * 0.05), (x + hw * 0.9, by - height * 0.02),
             (x + hw * 0.9, by + height * 0.045), (x - hw * 0.86, by + height * 0.11)]
    d.polygon(blade, fill=(168, 170, 176, 255))
    d.line([blade[0], blade[1]], fill=(226, 228, 232, 255), width=2)
    # teeth
    n = 12
    for i in range(n):
        t0 = i / float(n)
        t1 = (i + 0.5) / float(n)
        ax = x - hw * 0.86 + (hw * 1.76) * t0
        bx = x - hw * 0.86 + (hw * 1.76) * t1
        ay = (by + height * 0.11) + ((-height * 0.065)) * t0
        by2 = (by + height * 0.11) + ((-height * 0.065)) * t1
        d.polygon([(ax, ay), (bx, by2), ((ax + bx) / 2, (ay + by2) / 2 + height * 0.035)],
                  fill=(206, 208, 214, 255))
    # handle
    d.ellipse([x + hw * 0.78, by - height * 0.10, x + hw * 1.02, by + height * 0.02],
              fill=(70, 48, 30, 255))
    lay = lay.filter(ImageFilter.GaussianBlur(0.5))
    img.alpha_composite(lay)
    return img


def draw_bone_spike(img, x, y, height, seed=0, lean=0.0, skull=True):
    """Bone spike driven into the ground; (x, y) = base point."""
    rng = random.Random(seed + 31)
    pal = FACTION["undead"]
    W, H = img.size
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    h = float(height)
    w0 = h * 0.10
    tipx = x + lean * h
    pts = [(x - w0, y), (x + w0, y),
           (tipx + w0 * 0.18, y - h * 0.62), (tipx, y - h)]
    d.polygon(pts, fill=pal["bone"] + (255,))
    d.polygon([(x + w0 * 0.1, y), (x + w0, y), (tipx + w0 * 0.16, y - h * 0.62),
               (tipx + w0 * 0.05, y - h * 0.9)],
              fill=pal["bone_dk"] + (255,))
    d.line([(x - w0 * 0.6, y - h * 0.05), (tipx, y - h * 0.94)],
           fill=(244, 240, 226, 255), width=max(1, int(w0 * 0.5)))
    if skull:
        r = h * 0.16
        sx, sy = tipx - lean * h * 0.06, y - h * 0.98
        d.ellipse([sx - r, sy - r, sx + r, sy + r * 0.9], fill=pal["bone"] + (255,))
        d.rounded_rectangle([sx - r * 0.55, sy + r * 0.3, sx + r * 0.55, sy + r * 1.0],
                            radius=int(r * 0.3), fill=pal["bone"] + (255,))
        for ex in (-r * 0.42, r * 0.42):
            d.ellipse([sx + ex - r * 0.26, sy - r * 0.2, sx + ex + r * 0.26, sy + r * 0.3],
                      fill=(36, 30, 34, 255))
        d.polygon([(sx, sy + r * 0.35), (sx - r * 0.12, sy + r * 0.6),
                   (sx + r * 0.12, sy + r * 0.6)], fill=(40, 34, 38, 255))
    lay = lay.filter(ImageFilter.GaussianBlur(0.5))
    img.alpha_composite(lay)
    return img


def warm_rim(img, strength=0.35, color=None):
    """Gold/ember rim light on the brightest pixels (human faction identity)."""
    col = np.array(color or FACTION["human"]["gold"], dtype=np.float32)
    arr = np.array(img).astype(np.float32)
    lum = arr[:, :, :3].mean(axis=2)
    a = arr[:, :, 3] / 255.0
    hi = np.clip((lum - 150.0) / 95.0, 0, 1) * a * strength
    edge = np.clip(_blur(a, 1.6) - _blur(a, 3.4), 0, 1)
    hi = np.clip(hi + edge * strength * 0.45, 0, 1)
    arr[:, :, :3] = 255.0 - (255.0 - arr[:, :, :3]) * (
        255.0 - col[None, None, :] * hi[:, :, None]) / 255.0
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def wash(img, color, strength=0.10, mode="screen"):
    arr = np.array(img).astype(np.float32)
    col = np.array(color, dtype=np.float32)[None, None, :]
    a = arr[:, :, 3:4] / 255.0
    if mode == "screen":
        blended = 255.0 - (255.0 - arr[:, :, :3]) * (255.0 - col) / 255.0
    else:
        blended = arr[:, :, :3] * col / 255.0
    arr[:, :, :3] = arr[:, :, :3] * (1 - strength * a) + blended * (strength * a)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


def paste_cell(img, atlas_key, gid, x, y, scale=1.0, flip=None, key_black=False,
               dim=None, tint_mul=None, anchor="bottom"):
    """Paste one atlas cell so its content bottom-centre lands on (x, y)."""
    layer = _part_image(dict(a=atlas_key, id=gid, scale=scale, flip=flip,
                             key_black=key_black, dim=dim, tint_mul=tint_mul))
    cb = content_bbox(layer)
    ax = cb[0] + (cb[2] - cb[0]) // 2
    ay = cb[3] if anchor == "bottom" else cb[1]
    return paste(img, layer, (ax, ay), x, y)


def gable_roof(w, ridge, kind="shingle", seed=0, bright=0.90):
    """Isometric gable roof: big slope faces front-right, gable end front-left.

    Returns (layer, anchor) with the anchor at the front vertex of the eave
    diamond (the same convention as prism_layer).
    """
    import math
    w = max(8, int(w))
    D = w // 2
    pad = 4
    W, H = w + 2 * pad, int(ridge) + D + 2 * pad
    ax, ay = pad + w // 2, pad + int(ridge) + D
    S = (pad + w / 2.0, ay)                      # front
    L = (pad, pad + int(ridge) + D / 2.0)        # left
    R = (pad + w, pad + int(ridge) + D / 2.0)    # right
    sw_a = ((S[0] + L[0]) / 2.0, (S[1] + L[1]) / 2.0 - ridge)   # ridge end (front-left)
    ne_a = ((S[0] + R[0]) / 2.0, (S[1] + R[1]) / 2.0 - ridge)   # ridge end (front-right)
    # visible faces: gable triangle over the front-left edge + slope over front-right
    m_slope = _poly_mask((W, H), [[S, R, ne_a, sw_a]])
    m_gable = _poly_mask((W, H), [[S, L, sw_a]])
    tex = np.array(texture(kind, W, H, seed=seed)).astype(np.float32)
    yy = np.arange(H, dtype=np.float32)[:, None]
    tlin = np.clip((yy - pad) / float(max(1, int(ridge) + D)), 0.0, 1.0)
    sh = (1.02 - 0.24 * tlin) * np.ones((1, W), dtype=np.float32)
    sh = sh * (1.0 + (bright - 1.0) * m_slope)
    sh = sh * (1.0 + (0.62 - 1.0) * m_gable)
    rgb = tex[:, :, :3] * sh[:, :, None]
    ridge_line = _blur(_line_mask((W, H), [sw_a, ne_a], 3), 1.0)
    eave = _blur(_line_mask((W, H), [S, R], 3), 1.2) + \
        _blur(_line_mask((W, H), [S, L], 3), 1.2)
    rgb += ridge_line[:, :, None] * 46.0
    rgb -= eave[:, :, None] * 34.0
    alpha = np.clip(m_slope + m_gable, 0, 1) * 255.0
    # thin board edge under the eaves
    out = np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)
    return Image.fromarray(out, "RGBA"), (ax, ay)


def span_arch(img, pL, pR, rise, thick, kind="stone", seed=0, joints=9,
              bright=1.14, dark=0.66):
    """Free-standing stone arch between two springing points (screen px)."""
    import math
    W, H = img.size

    def arc(p0, p1, hgt, n=30):
        pts = []
        for i in range(n + 1):
            t = i / float(n)
            x = p0[0] + (p1[0] - p0[0]) * t
            y = p0[1] + (p1[1] - p0[1]) * t - hgt * math.sin(math.pi * t)
            pts.append((x, y))
        return pts

    outer = arc(pL, pR, rise)
    inL = (pL[0] + (pR[0] - pL[0]) * 0.11, pL[1] + (pR[1] - pL[1]) * 0.11 + thick * 0.55)
    inR = (pL[0] + (pR[0] - pL[0]) * 0.89, pL[1] + (pR[1] - pL[1]) * 0.89 + thick * 0.55)
    inner = arc(inL, inR, max(6.0, rise - thick))
    band = outer + inner[::-1]
    mask = _poly_mask((W, H), [band])
    tex = np.array(texture(kind, W, H, seed=seed + 5)).astype(np.float32)
    ys = [p[1] for p in band]
    y0, y1 = min(ys), max(ys)
    yy = np.arange(H, dtype=np.float32)[:, None]
    tlin = np.clip((yy - y0) / max(1.0, (y1 - y0)), 0.0, 1.0)
    sh = (bright - (bright - dark) * tlin) * np.ones((1, W), dtype=np.float32)
    rgb = tex[:, :, :3] * sh[:, :, None]
    top_line = _blur(_line_mask((W, H), outer, 3), 1.0)
    under_line = _blur(_line_mask((W, H), inner, 4), 1.2)
    rgb += top_line[:, :, None] * 40.0
    rgb -= under_line[:, :, None] * 30.0
    # voussoir joints
    jm = np.zeros((H, W), dtype=np.float32)
    for i in range(1, joints):
        a = outer[int(round(i * (len(outer) - 1) / float(joints)))]
        b = inner[int(round(i * (len(inner) - 1) / float(joints)))]
        jm = np.maximum(jm, _line_mask((W, H), [a, b], 2))
    jm = _blur(jm, 0.8)
    rgb -= jm[:, :, None] * 30.0
    a = mask * 255.0
    lay = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a]).astype(np.uint8), "RGBA")
    img.alpha_composite(lay)
    return img


def ink_outline(img, width=2, ink=(20, 18, 22), amount=0.40, inside=0.55):
    """Dark silhouette edge so props separate from terrain (art direction)."""
    arr = np.array(img).astype(np.float32)
    a = arr[:, :, 3]
    m = Image.fromarray(((a > 40) * 255).astype(np.uint8), "L")
    dil = m.filter(ImageFilter.MaxFilter(2 * width + 1))
    ero = m.filter(ImageFilter.MinFilter(2 * width + 1))
    d = np.array(dil).astype(np.float32)
    e = np.array(ero).astype(np.float32)
    ring = np.clip(d - a, 0, 255) / 255.0
    band = np.clip(a - e, 0, 255) / 255.0
    inkc = np.array(ink, dtype=np.float32)
    arr[:, :, :3] = (arr[:, :, :3] * (1 - (band * inside)[:, :, None])
                     + inkc[None, None, :] * (band * inside)[:, :, None])
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    ring_rgba = np.zeros((a.shape[0], a.shape[1], 4), dtype=np.float32)
    ring_rgba[:, :, :3] = inkc[None, None, :]
    ring_rgba[:, :, 3] = ring * 255.0 * amount
    base.alpha_composite(Image.fromarray(
        np.clip(ring_rgba, 0, 255).astype(np.uint8), "RGBA"))
    return base


POSTS = {}


def post(name):
    def deco(fn):
        POSTS[name] = fn
        return fn
    return deco


def apply_post(img, spec):
    name = spec.get("post")
    if not name:
        return img, ""
    fn = POSTS.get(name)
    if fn is None:
        raise KeyError("no post handler %r" % name)
    res = fn(img, spec)
    if isinstance(res, tuple):
        out, desc = res
    else:
        out, desc = res, name
    return out, desc


def anchor_of(img):
    """(cx, bottom_y) of the content bbox == anchor convention point."""
    bb = content_bbox(img)
    return bb[0] + (bb[2] - bb[0]) // 2, bb[3]


def part_geometry(spec):
    """Compose-space placement of every part: [(left, top, cb), ...], origin."""
    placed = []
    last = None
    for p in spec["parts"]:
        a = _atlas(p["a"])
        img = _part_image(p)
        gx, gy = int(p["gx"]), int(p["gy"])
        left = (gx - gy) * MAP_TILE_W // 2 + int(p.get("dx", 0))
        top = (gx + gy) * MAP_TILE_H // 2 + MAP_TILE_H - a["th"] + int(p.get("dy", 0))
        cb = content_bbox(img)
        if p.get("above") and last is not None:
            prev_content_top = last[1] + last[2][1]
            top = prev_content_top + int(p.get("overlap", 16)) - cb[3]
        placed.append((left, top, cb))
        last = placed[-1]
    if not placed:
        return [], (0, 0)
    min_l = min(e[0] for e in placed)
    min_t = min(e[1] for e in placed)
    return placed, (min_l, min_t)


def part_anchor(spec, img, index, where="bottom"):
    """Position of part `index` in FINAL (trimmed) image coordinates."""
    placed, (min_l, min_t) = part_geometry(spec)
    l, t, cb = placed[index]
    bb = content_bbox(img)
    x = l - min_l + cb[0] + (cb[2] - cb[0]) // 2 + _GROW_OFF[0]
    y = (t - min_t + (cb[3] if where == "bottom" else cb[1])) + _GROW_OFF[1]
    return x, y


def draw_post(img, x, y_ground, y_top, w=13, seed=0, tone=(94, 68, 42)):
    """Simple vertical timber post with lit left edge."""
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rectangle([x - w // 2, y_top, x + w // 2, y_ground], fill=tone + (255,))
    d.rectangle([x - w // 2, y_top, x - w // 2 + max(1, w // 3), y_ground],
                fill=(min(255, tone[0] + 44), min(255, tone[1] + 38),
                      min(255, tone[2] + 30), 255))
    d.rectangle([x + w // 2 - max(1, w // 4), y_top, x + w // 2, y_ground],
                fill=(max(0, tone[0] - 34), max(0, tone[1] - 28),
                      max(0, tone[2] - 22), 255))
    img.alpha_composite(lay)
    return img


def draw_weapon_rack(img, x, y, width, height, seed=0):
    """Rack of spears + shield: reads 'barracks' next to the tents."""
    rng = random.Random(seed + 41)
    W, H = img.size
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    wood = (88, 62, 38)
    hw = width / 2.0
    leg = max(3, int(width * 0.05))
    # frame: two uprights + two cross rails
    d.line([(x - hw, y), (x - hw, y - height)], fill=wood + (255,), width=leg)
    d.line([(x + hw, y), (x + hw, y - height * 0.94)], fill=wood + (255,), width=leg)
    for f in (0.30, 0.78):
        yy = y - height * f
        d.line([(x - hw, yy), (x + hw, yy - height * 0.03)],
               fill=(118, 86, 52, 255), width=max(2, leg - 1))
    # spears leaning in the rack
    for i in range(4):
        u = (i + 0.5) / 4.0
        bx = x - hw * 0.82 + hw * 1.64 * u
        lean = rng.uniform(-0.16, 0.16)
        tx = bx + lean * height
        ty = y - height * rng.uniform(1.12, 1.34)
        d.line([(bx, y - height * 0.05), (tx, ty)], fill=(70, 52, 34, 255),
               width=max(2, int(leg * 0.7)))
        # iron head
        d.polygon([(tx, ty - height * 0.10), (tx + 5, ty + 4), (tx - 5, ty + 4)],
                  fill=(176, 180, 188, 255))
    # round shield on the left upright, crimson + gold boss
    r = height * 0.30
    sx, sy = x - hw * 0.72, y - height * 0.52
    d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(126, 40, 42, 255))
    d.ellipse([sx - r, sy - r, sx + r, sy + r], outline=(217, 164, 65, 255),
              width=max(2, int(r * 0.16)))
    d.ellipse([sx - r * 0.3, sy - r * 0.3, sx + r * 0.3, sy + r * 0.3],
              fill=(217, 164, 65, 255))
    img.alpha_composite(lay)
    return img


@post("human_barracks")
def post_barracks(img, spec):
    img = _grow(img, top=620, left=460, right=460, bottom=60)
    cx, by = anchor_of(img)
    img = draw_weapon_rack(img, cx - 118, by - 26, 168, 118, seed=3)
    img = draw_banner(img, cx + 150, by - 58, 300, width=104, seed=2)
    img = add_glow(img, cx - 6, by - 26, 66, 34, (250, 170, 96), strength=0.30,
                   add_alpha=0.0)
    return img, "rail palisade corner + spear rack + crimson/gold standard"


@post("human_blacksmith_smithy")
def post_smithy(img, spec):
    img = _grow(img, top=640, left=320, right=320, bottom=60)
    cx, by = anchor_of(img)
    # real log shed corner (shingle roof + walls) set back behind forge+anvil
    img = paste_cell(img, "structures", 1, cx - 4, by - 116, scale=0.86)
    # forge ember light under the eaves
    img = add_glow(img, cx - 74, by - 46, 74, 46, (250, 150, 66), strength=0.42,
                   add_alpha=0.10)
    img = warm_rim(img, 0.30, color=(240, 176, 96))
    return img, "log shed w/ shingle roof behind forge + ember light (reads as a building)"


@post("human_workshop_lumber")
def post_lumber(img, spec):
    img = _grow(img, top=520, left=460, right=460, bottom=60)
    cx, by = anchor_of(img)
    img = draw_saw_frame(img, cx + 96, by - 26, 216, 132, seed=6)
    img = draw_banner(img, cx - 178, by - 92, 205, width=74, seed=7, scale_cloth=0.85)
    img = add_glow(img, cx + 96, by - 70, 70, 40, (255, 196, 110), strength=0.22,
                   add_alpha=0.0)
    return img, "tall timber stacks + saw frame + small crimson pennant"


@post("human_keep")
def post_keep(img, spec):
    img = _grow(img, top=900, left=460, right=460, bottom=60)
    cx, by = anchor_of(img)
    by -= 30
    pal = FACTION["human"]
    # ---- curtain wall ------------------------------------------------------
    bw, bh = 476, 176
    D = bw // 2
    base, (ax, ay) = prism_layer(bw, bh, kind="stone", seed=21, battlement=30,
                                 shade=(0.74, 0.98, 1.20), top_dim=0.70)
    img = paste(img, base, (ax, ay), cx, by)
    img = draw_arch(img, (cx, by), (cx + D, by - D // 2), bh, arch_h=bh * 0.80,
                    fill=(16, 10, 12), glow_color=(246, 156, 74),
                    glow_strength=0.34, bars=3)
    img = draw_window(img, (cx - D, by - D // 2), (cx, by), bh, u=0.34,
                      warm=(250, 186, 108), strength=0.34)
    img = draw_window(img, (cx - D, by - D // 2), (cx, by), bh, u=0.66,
                      warm=(250, 186, 108), strength=0.7)
    # ---- flanking turrets --------------------------------------------------
    for sx, seed in ((-1, 23), (1, 24)):
        tw_, th_ = 132, 214
        t, (tx, ty) = prism_layer(tw_, th_, kind="stone", seed=seed, battlement=22,
                                  shade=(0.74, 0.98, 1.20))
        fx = cx + sx * (D - 6)
        fy = by - (D - 6) / 2.0 + (tw_ // 2) / 2.0
        img = paste(img, t, (tx, ty), fx, fy)
    # ---- keep block --------------------------------------------------------
    sw_, sh_ = 306, 196
    stage_top = by - bh - D // 2            # centre of wall's top diamond
    sa = stage_top + sw_ // 4               # stage front vertex
    st, (stx, sty) = prism_layer(sw_, sh_, kind="stone", seed=25, battlement=28,
                                 shade=(0.74, 0.98, 1.20))
    img = paste(img, st, (stx, sty), cx, sa)
    img = draw_window(img, (cx - sw_ // 2, sa - sw_ // 4), (cx, sa), sh_, u=0.42,
                      vfrac=0.55, warm=(250, 186, 108), strength=0.34)
    img = draw_window(img, (cx, sa - sw_ // 4), (cx + sw_ // 2, sa), sh_, u=0.55,
                      vfrac=0.5, warm=(250, 186, 108), strength=0.34)
    # ---- top block ---------------------------------------------------------
    kw, kh = 186, 152
    stage2_top = sa - sh_ - sw_ // 4
    ka = stage2_top + kw // 4
    kt, (ktx, kty) = prism_layer(kw, kh, kind="stone", seed=26, battlement=24,
                                 shade=(0.74, 0.98, 1.20))
    img = paste(img, kt, (ktx, kty), cx, ka)
    top_centre = ka - kh - kw // 4
    # ---- crimson & gold standard on the roof ------------------------------
    img = draw_banner(img, cx + 46, top_centre + 18, 268, width=98, seed=11)
    img = draw_banner(img, cx - 96, top_centre + 34, 176, width=60, seed=12,
                      scale_cloth=0.8)
    img = add_glow(img, cx, by - bh * 0.4, 150, 96, (255, 176, 96), strength=0.16,
                   add_alpha=0.0)
    return img, ("crenellated curtain wall + flanking turrets + stacked keep "
                 "with ember windows + crimson/gold standards")


@post("human_temple_altar")
def post_temple(img, spec):
    img = _grow(img, top=700, left=460, right=460, bottom=60)
    cx, by = anchor_of(img)
    # column tops (part 0 = left column, part 3 = right column)
    lx, ly = part_anchor(spec, img, 0, "top")
    rx, ry = part_anchor(spec, img, 3, "top")
    lx += 12
    rx -= 12
    rise = max(150, int((rx - lx) * 0.50))
    img = span_arch(img, (lx, ly + 58), (rx, ry + 58), rise, 54, seed=3,
                    bright=1.12, dark=0.82)
    # standing flame on the stepped monument (part 2)
    mx, my = part_anchor(spec, img, 2, "top")
    img = draw_flame(img, mx, my + 16, 94, palette="ember", seed=5, glow=0.55)
    # gold keystone + ember spill on the rune circle
    gx, gy = part_anchor(spec, img, 1, "bottom")
    img = add_glow(img, gx, gy - 34, 150, 64, (246, 176, 96), strength=0.34,
                   add_alpha=0.0)
    return img, "open stone arch + standing ember flame on stepped monument"


@post("undead_ziggurat_ruin")
def post_ziggurat(img, spec):
    img = _grow(img, top=760, left=460, right=460, bottom=60)
    cx, by = anchor_of(img)
    by -= 30
    tiers = [(430, 112), (286, 96), (162, 86)]
    y = by
    tops = []
    for i, (w, h) in enumerate(tiers):
        lay, (ax, ay) = prism_layer(w, h, kind="stone_light" if i == 1 else "stone",
                                    seed=31 + i, shade=(0.74, 0.98, 1.20))
        img = paste(img, lay, (ax, ay), cx, y)
        top_c = y - h - w // 4
        tops.append(top_c)
        img = add_glow(img, cx, top_c + 6, w * 0.36, 30, (118, 84, 168),
                       strength=0.26, add_alpha=0.06)
        if i + 1 < len(tiers):
            y = top_c + tiers[i + 1][0] // 4
    # shrine + violet flame on the summit
    cell = _part_image(dict(a="ruins", id=128))
    cb = content_bbox(cell)
    mh = cb[3] - cb[1]
    sx, sy = cx, tops[-1] + 14
    img = paste_cell(img, "ruins", 128, sx, sy)
    img = draw_flame(img, sx, sy - mh - 4, 96, palette="violet", seed=9, glow=0.8)
    img = add_glow(img, sx, sy - mh * 0.6, 120, 150, (128, 92, 186), strength=0.42,
                   add_alpha=0.07)
    # rubble grounding either side of the bottom tier
    img = paste_cell(img, "ruins", 162, cx - 178, by - 78, scale=0.9)
    img = paste_cell(img, "ruins", 161, cx + 176, by - 76, scale=0.85)
    img = wash(img, FACTION["undead"]["violet"], 0.06)
    img = bone_rim(img, 0.40)
    return img, "3 stepped tiers (wide->narrow) + shrine with violet flame | violet seams | bone rim"


@post("undead_necropolis_ruin")
def post_necropolis(img, spec):
    img = _grow(img, top=1150, left=460, right=460, bottom=60)
    cx, by = anchor_of(img)
    by -= 30
    pal = FACTION["undead"]
    # ---- iron fence ring at the back (painted first: the tomb covers its feet)
    img = paste_cell(img, "ruins", 340, cx, by - 288, scale=1.05)
    img = paste_cell(img, "ruins", 344, cx - 150, by - 213, scale=1.05)
    img = paste_cell(img, "ruins", 346, cx + 150, by - 213, scale=1.05, flip="h")
    # ---- tomb house --------------------------------------------------------
    bw, bh = 470, 192
    D = bw // 2
    base, (ax, ay) = prism_layer(bw, bh, kind="stone_dark", seed=41, battlement=28,
                                 shade=(0.74, 0.98, 1.20), top_dim=0.74)
    img = paste(img, base, (ax, ay), cx, by)
    img = draw_arch(img, (cx, by), (cx + D, by - D // 2), bh, arch_h=bh * 0.82,
                    fill=(11, 6, 18), glow_color=(146, 100, 226),
                    glow_strength=0.42, bars=4)
    img = draw_window(img, (cx - D, by - D // 2), (cx, by), bh, u=0.52,
                      warm=(150, 214, 108), strength=0.34)
    # ---- spire -------------------------------------------------------------
    sw_, sh_ = 236, 430
    wall_top = by - bh - D // 2
    sa = wall_top + sw_ // 4
    spr, (stx, sty) = prism_layer(sw_, sh_, kind="stone", seed=42, battlement=32,
                                  shade=(0.74, 0.98, 1.20))
    img = paste(img, spr, (stx, sty), cx, sa)
    img = draw_window(img, (cx, sa - sw_ // 4), (cx + sw_ // 2, sa), sh_, u=0.5,
                      wfrac=0.30, hfrac=0.30, vfrac=0.55,
                      warm=(168, 128, 236), strength=0.62)
    img = draw_window(img, (cx - sw_ // 2, sa - sw_ // 4), (cx, sa), sh_, u=0.5,
                      vfrac=0.62, warm=(150, 214, 108), strength=0.34)
    # ---- cap ---------------------------------------------------------------
    kw, kh = 140, 128
    spire_top = sa - sh_ - sw_ // 4
    ka = spire_top + kw // 4
    kt, (ktx, kty) = prism_layer(kw, kh, kind="stone_dark", seed=44, battlement=22,
                                 shade=(0.74, 0.98, 1.20))
    img = paste(img, kt, (ktx, kty), cx, ka)
    cap_top = ka - kh - kw // 4
    # ---- violet flame + bone spikes on top --------------------------------
    img = draw_flame(img, cx, cap_top + 10, 104, palette="violet", seed=13, glow=0.9)
    for dx, lean in ((-58, -0.06), (56, 0.05), (0, 0.0)):
        img = draw_bone_spike(img, cx + dx, cap_top + 26, 96 if dx else 120,
                              lean=lean, seed=17 + dx)
    img = add_glow(img, cx, sa - sh_ * 0.5, 210, 250, (122, 88, 184), strength=0.45,
                   add_alpha=0.07)
    # ---- grounding: headstones, cross, skull stakes, bone piles ------------
    def ground(dx, inset=8):
        return cx + dx, by - abs(dx) * 0.5 - inset
    img = paste_cell(img, "grassland", 124, *ground(-176), scale=1.05)
    img = paste_cell(img, "grassland", 125, *ground(150), scale=0.95)
    img = paste_cell(img, "grassland", 126, *ground(-108), scale=1.0)
    img = paste_cell(img, "dungeon", 162, *ground(46), scale=1.1)
    img = paste_cell(img, "dungeon", 134, *ground(-232), scale=1.25)
    img = paste_cell(img, "dungeon", 134, *ground(224), scale=1.1)
    img = paste_cell(img, "dungeon", 160, *ground(-40, 4), scale=1.0)
    # ---- glows -------------------------------------------------------------
    img = add_glow(img, cx, by - 120, 230, 150, (132, 96, 196), strength=0.28,
                   add_alpha=0.16)
    img = add_glow(img, cx - 250, by - 90, 120, 70, (150, 214, 108), strength=0.20,
                   add_alpha=0.10)
    img = wash(img, pal["violet"], 0.06)
    img = bone_rim(img, 0.45)
    return img, ("tall tomb spire + crenellated cap with violet flame, bone spikes, "
                 "headstones + iron fence ring | violet + sickly-green glow")


@post("human_town_hall")
def post_town_hall(img, spec):
    img = _grow(img, top=320, left=180, right=180, bottom=40)
    cx, by = anchor_of(img)
    img = draw_banner(img, cx + 36, by - 372, 150, width=56, seed=21,
                      scale_cloth=0.8)
    img = add_glow(img, cx + 46, by - 148, 46, 34, (255, 190, 112), strength=0.42,
                   add_alpha=0.10)
    img = warm_rim(img, 0.34)
    return img, "roof pennant + warm window light (crimson/gold)"


@post("human_house_farm")
def post_farm(img, spec):
    img = _grow(img, top=300, left=160, right=160, bottom=40)
    cx, by = anchor_of(img)
    img = draw_banner(img, cx - 54, by - 330, 132, width=48, seed=22,
                      scale_cloth=0.8)
    img = add_glow(img, cx + 92, by - 128, 40, 30, (255, 190, 112), strength=0.40,
                   add_alpha=0.10)
    img = warm_rim(img, 0.32)
    return img, "roof pennant + warm window light (crimson/gold)"


@post("human_guard_tower")
def post_guard_tower(img, spec):
    img = _grow(img, top=260, left=140, right=140, bottom=30)
    cx, by = anchor_of(img)
    img = draw_banner(img, cx + 30, by - 548, 150, width=52, seed=23,
                      scale_cloth=0.8)
    img = add_glow(img, cx, by - 300, 44, 30, (255, 190, 112), strength=0.34,
                   add_alpha=0.08)
    img = warm_rim(img, 0.30)
    return img, "banner + ember slit high on the tower (crimson/gold)"


@post("undead_crypt")
def post_crypt(img, spec):
    img = _grow(img, top=180, left=160, right=160, bottom=30)
    cx, by = anchor_of(img)
    img = add_glow(img, cx - 10, by - 150, 96, 74, (124, 90, 190), strength=0.42,
                   add_alpha=0.12)
    img = add_glow(img, cx + 96, by - 70, 70, 46, (150, 214, 108), strength=0.26,
                   add_alpha=0.07)
    img = wash(img, FACTION["undead"]["violet"], 0.06)
    img = bone_rim(img, 0.45)
    return img, "violet edge glow + sickly-green seam + bone rim (undead)"


@post("undead_bone_ritual")
def post_bone_ritual(img, spec):
    img = _grow(img, top=160, left=140, right=140, bottom=30)
    cx, by = anchor_of(img)
    img = add_glow(img, cx - 30, by - 170, 88, 66, (126, 92, 190), strength=0.34,
                   add_alpha=0.10)
    img = wash(img, FACTION["undead"]["violet"], 0.07)
    img = bone_rim(img, 0.42)
    return img, "violet aura around the sick-green orb + bone rim (undead)"


@post("undead_ruined_house")
def post_ruined_house(img, spec):
    img = _grow(img, top=180, left=160, right=160, bottom=30)
    cx, by = anchor_of(img)
    img = add_glow(img, cx + 40, by - 120, 92, 64, (128, 94, 194), strength=0.44,
                   add_alpha=0.14)
    img = add_glow(img, cx - 60, by - 60, 70, 40, (150, 214, 108), strength=0.22,
                   add_alpha=0.06)
    img = wash(img, FACTION["undead"]["violet"], 0.07)
    img = bone_rim(img, 0.45)
    return img, "violet pit glow + bone rim (undead)"


@post("undead_ruined_tower")
def post_ruined_tower(img, spec):
    img = _grow(img, top=200, left=180, right=180, bottom=30)
    cx, by = anchor_of(img)
    img = add_glow(img, cx - 150, by - 300, 84, 96, (132, 96, 198), strength=0.46,
                   add_alpha=0.14)
    img = add_glow(img, cx + 150, by - 120, 74, 50, (150, 214, 108), strength=0.24,
                   add_alpha=0.06)
    img = wash(img, FACTION["undead"]["violet"], 0.07)
    img = bone_rim(img, 0.45)
    return img, "violet light behind the barred door + bone rim (undead)"


def build_part(spec):
    """Build one source part -> (RGBA image, description)."""
    if spec["src"] == "compose":
        return compose(spec)
    if spec["src"] == "atlas":
        apath = os.path.join(TILED, spec["atlas"])
        img = Image.open(apath).convert("RGBA")
        l, t, r, b = spec["rect"]
        return img.crop((l, t, r, b)), "%s [%d,%d,%d,%d]" % (
            os.path.relpath(apath, FLARE), l, t, r, b)
    if spec["src"] == "map":
        mpath = os.path.join(TILED, spec["map"])
        m = TmxMap(mpath)
        rect = tuple(spec["rect"])
        img = render_map(m, rect, layer_names=spec.get("layers"),
                         tileset_names=spec.get("tilesets"))
        img, bbox = trim_alpha(img)
        return img, "%s rect=%s layers=%s trim=%s" % (
            os.path.relpath(mpath, FLARE), rect,
            ",".join(spec.get("layers", ["all-but-editor"])), bbox)
    raise ValueError("unknown src %r" % spec["src"])


def cmd_extract(args):
    specs = load_buildings(args.catalog)
    out_dir = args.out_dir if os.path.isabs(args.out_dir) else os.path.join(REPO, args.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    only = set(args.only.split(",")) if getattr(args, "only", None) else None
    rows = []
    for spec in specs:
        if spec.get("skip"):
            continue
        if only and spec["name"] not in only:
            continue
        img, src_desc = build_part(spec)
        img, post_desc = apply_post(img, spec)
        if post_desc:
            src_desc = src_desc + " + " + post_desc
        img = ink_outline(img, width=2, amount=args.ink)
        if args.trim:
            img, _bbox = trim_alpha(img)
        img = img.convert("RGBA")
        out_name = spec["name"] + ".png"
        out_path = os.path.join(out_dir, out_name)
        img.save(out_path)
        rows.append(dict(
            name=spec["name"], kind=spec.get("kind", ""), file=out_name,
            w=img.width, h=img.height,
            anchor="bottom-center (%d, %d)" % (img.width // 2, img.height),
            source=src_desc, footprint=spec.get("footprint", ""),
            note=spec.get("note", ""),
            draw=draw_width(spec.get("footprint", ""), spec)))
        print("wrote %-34s %4dx%-4d  %s" % (out_name, img.width, img.height, src_desc))
    if args.markdown:
        md = args.markdown if os.path.isabs(args.markdown) else os.path.join(REPO, args.markdown)
        write_catalog_markdown(md, rows)
        print("catalog -> %s" % md)
    if args.json:
        jp = args.json if os.path.isabs(args.json) else os.path.join(REPO, args.json)
        with open(jp, "w") as fh:
            json.dump(rows, fh, indent=2)
        print("json -> %s" % jp)
    return 0


def draw_width(footprint, spec=None):
    """Recommended draw width in px at 1x for a 64x32 iso tile grid.

    The ground diamond of a WxH tile footprint is (W+H)*32 px wide; we add 8 px
    of slop so eaves/props may overhang the diamond slightly.  Spec may override
    with ``draw_width`` (used for the tall/thin guard tower).
    """
    if spec and spec.get("draw_width"):
        return int(spec["draw_width"])
    m = re.match(r"^(\d+)x(\d+)$", footprint or "")
    if not m:
        return 168
    w, h = int(m.group(1)), int(m.group(2))
    return (w + h) * 32 + 8


def write_catalog_markdown(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lines = [
        "# Flare building sprites - catalog",
        "",
        "Generated by `python3 tools/flare_buildings.py extract --markdown design/notes/flare-buildings.md`.",
        "Anchor convention for every sprite below: **bottom-center** of the PNG = front (bottom)",
        "vertex of the building's ground footprint diamond.",
        "",
        "`draw_width_px` = recommended on-screen width at 1x for a 64x32 iso grid (ground",
        "diamond width `(W+H)*32` plus 8 px of overhang slop); a 2x2 should land in 128-140 px,",
        "a 3x3 in 192-210 px. Height follows the sprite's own aspect ratio, so tall sprites",
        "(guard tower, necropolis) draw taller, never wider than their footprint.",
        "",
        "| name | file | px | anchor (px) | draw_width_px | source atlas/TMX + crop | footprint (tiles) | RTS silhouette @48px |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append("| %s | `%s` | %dx%d | (%d, %d) | %d | %s | %s | %s |" % (
            r["name"], r["file"], r["w"], r["h"], r["w"] // 2, r["h"], r["draw"],
            r["source"], r["footprint"], r["note"]))
    lines.append("")
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


def cmd_verify(args):
    d = args.dir if os.path.isabs(args.dir) else os.path.join(REPO, args.dir)
    ok = True
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(".png"))
    if len(files) < args.min_count:
        print("FAIL: only %d pngs in %s (need >= %d)" % (len(files), d, args.min_count))
        ok = False
    for f in files:
        p = os.path.join(d, f)
        problems = []
        im = Image.open(p)
        if im.mode != "RGBA":
            problems.append("mode=%s" % im.mode)
        arr = np.array(im.convert("RGBA"))
        if arr.size == 0:
            problems.append("empty")
            print("FAIL %-34s %s" % (f, problems)); ok = False; continue
        alpha = arr[:, :, 3]
        h, w = alpha.shape
        if w < 16 or h < args.min_height:
            problems.append("size %dx%d (min height %d)" % (w, h, args.min_height))
        if alpha.min() == 255:
            problems.append("no transparency (solid rectangle)")
        # edges transparent
        edges = np.concatenate([alpha[0, :], alpha[-1, :], alpha[:, 0], alpha[:, -1]])
        if (edges > 8).mean() > 0.25:
            problems.append("edges not transparent (%.0f%% opaque)" % (100 * (edges > 8).mean()))
        ys, xs = np.nonzero(alpha > 0)
        if len(xs) == 0:
            problems.append("no visible pixels")
        else:
            bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
            if bw < 16 or bh < args.min_height:
                problems.append("content bbox %dx%d too small" % (bw, bh))
            fill = len(xs) / float(bw * bh)
            if fill < 0.02:
                problems.append("content bbox has only %.1f%% fill (stray pixels?)" % (100 * fill))
            if bh < 0.5 * h or bw < 0.5 * w:
                problems.append("content bbox %dx%d much smaller than canvas %dx%d"
                                % (bw, bh, w, h))
        status = "ok   " if not problems else "FAIL "
        if problems:
            ok = False
        print("%s %-34s %4dx%-4d %s" % (status, f, w, h, "; ".join(problems)))
    print("verify: %d files, %s" % (len(files), "PASS" if ok else "FAIL"))
    return 0 if ok else 1


def _checker(w, h, cell=10, a=(48, 48, 54), b=(64, 64, 72)):
    im = Image.new("RGB", (w, h), a)
    d = ImageDraw.Draw(im)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if ((x // cell) + (y // cell)) % 2:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=b)
    return im


def cmd_montage(args):
    d = args.dir if os.path.isabs(args.dir) else os.path.join(REPO, args.dir)
    out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(".png"))
    if args.names:
        want = set(args.names.split(","))
        files = [f for f in files if f[:-4] in want]
    cols = args.cols
    cw, ch = args.cell_w, args.cell_h
    lab = 30
    pad = 14
    font = ImageFont.load_default(size=17)
    rows = (len(files) + cols - 1) // cols
    W = cols * (cw + pad) + pad
    H = rows * (ch + lab + pad) + pad + 34
    canvas = Image.new("RGB", (W, H), (24, 24, 28))
    dd = ImageDraw.Draw(canvas)
    dd.text((pad, 8), "EMBERFALL flare buildings - alpha checker, sorted by name, "
                      "red tick = bottom-centre anchor", font=font, fill=(180, 180, 190))
    for i, f in enumerate(files):
        im = Image.open(os.path.join(d, f)).convert("RGBA")
        iw, ih = im.size
        s = min((cw - 20) / float(iw), (ch - 20) / float(ih), 1.0)
        tw, th = max(1, int(iw * s)), max(1, int(ih * s))
        im2 = im.resize((tw, th), Image.LANCZOS)
        r, c = i // cols, i % cols
        x0 = pad + c * (cw + pad)
        y0 = pad + 34 + r * (ch + lab + pad)
        chk = _checker(cw, ch)
        canvas.paste(chk, (x0, y0))
        px = x0 + (cw - tw) // 2
        py = y0 + (ch - th) // 2
        canvas.paste(im2, (px, py), im2)
        # anchor marker: bottom-centre of the sprite
        dd.line([(px + tw // 2, y0 + ch - 6), (px + tw // 2, y0 + ch)], fill=(235, 70, 70),
                width=2)
        dd.text((x0 + 4, y0 + ch + 4), "%s  %dx%d" % (f, iw, ih), font=font,
                fill=(235, 220, 150))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    canvas.save(out)
    print("montage -> %s (%dx%d, %d sprites)" % (out, W, H, len(files)))
    return 0


def cmd_test48(args):
    d = args.dir if os.path.isabs(args.dir) else os.path.join(REPO, args.dir)
    out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
    four = ["human_keep", "human_temple_altar", "undead_ziggurat_ruin",
            "undead_necropolis_ruin"]
    font = ImageFont.load_default(size=15)
    zoom = args.zoom
    pad = 12
    cellw, cellh = 48 * zoom + pad * 2, 48 * zoom + 70
    W = pad + len(four) * (cellw + pad) + 60
    # section 1: the four silhouettes at exactly 48 px wide, plus a zoom
    H = 30 + cellh + 26
    # section 2: every sprite at 48 px wide
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(".png"))
    rowh = 48 * zoom + 44
    H2 = 30 + 3 * rowh
    canvas = Image.new("RGB", (max(W, pad + 10 * (48 + pad) + pad), H + H2), (24, 24, 28))
    dd = ImageDraw.Draw(canvas)
    dd.text((pad, 6), "48 px naming test - top: keep / temple / ziggurat / necropolis "
                      "at exactly 48 px wide (+ %dx zoom); below: every sprite at 48 px"
            % zoom, font=font, fill=(190, 190, 200))
    # section 1
    y = 30
    for i, name in enumerate(four):
        p = os.path.join(d, name + ".png")
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGBA")
        s = 48.0 / im.width
        small = im.resize((48, max(1, int(im.height * s))), Image.LANCZOS)
        x = pad + i * (cellw + pad)
        chk = _checker(48, small.height, cell=6, a=(44, 44, 50), b=(58, 58, 66))
        canvas.paste(chk, (x + pad, y))
        canvas.paste(small, (x + pad, y), small)
        big = small.resize((48 * zoom, small.height * zoom), Image.NEAREST)
        chk2 = _checker(big.width, big.height, cell=12)
        canvas.paste(chk2, (x + pad + 48 + 16, y))
        canvas.paste(big, (x + pad + 48 + 16, y), big)
        dd.text((x + pad, y + big.height + 6), "%s @48w" % name, font=font,
                fill=(235, 220, 150))
    # section 2: every sprite
    y = 30 + cellh + 30
    dd.text((pad, y - 20), "all sprites @48 px wide", font=font, fill=(170, 170, 180))
    for i, f in enumerate(files):
        im = Image.open(os.path.join(d, f)).convert("RGBA")
        s = 48.0 / im.width
        small = im.resize((48, max(1, int(im.height * s))), Image.LANCZOS)
        c, r = i % 10, i // 10
        x = pad + c * (48 * zoom + pad)
        yy = y + r * rowh
        big = small.resize((48 * zoom, small.height * zoom), Image.NEAREST)
        chk = _checker(big.width, big.height, cell=12)
        canvas.paste(chk, (x, yy))
        canvas.paste(big, (x, yy), big)
        dd.text((x, yy + big.height + 4), f[:-4][:16], font=font, fill=(200, 200, 210))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    canvas.save(out)
    print("48px test -> %s (%dx%d)" % (out, canvas.width, canvas.height))
    return 0


def cmd_list(args):
    specs = load_buildings(args.catalog)
    for s in specs:
        print("%-34s %-8s src=%-6s fp=%s" % (
            s["name"], s.get("kind", "?"), s.get("src", "composite"),
            s.get("footprint", "?")))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="flare_buildings.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a rect of a TMX map to PNG")
    r.add_argument("--map", required=True, help="path to .tmx (relative to vendor/flare-game/tiled/ or absolute)")
    r.add_argument("--rect", required=True, type=parse_rect, help="x,y,w,h in tile coords")
    r.add_argument("--out", required=True)
    r.add_argument("--layers", default=None, help="comma separated layer names (default: all except editor-only)")
    r.add_argument("--bg", default=None, help="background colour hex, default transparent")
    r.add_argument("--scale", type=int, default=1)
    r.set_defaults(fn=cmd_render)

    e = sub.add_parser("extract", help="extract building sprites")
    e.add_argument("--out-dir", required=True)
    e.add_argument("--catalog", default=None, help="JSON catalogue (default: tools/flare_buildings_catalog.json)")
    e.add_argument("--trim", type=int, default=1, help="1 = trim to alpha bbox (default)")
    e.add_argument("--only", default=None, help="comma separated sprite names to extract")
    e.add_argument("--ink", type=float, default=0.40, help="silhouette edge ink 0..1")
    e.add_argument("--markdown", default=None, help="also write a markdown catalog table")
    e.add_argument("--json", default=None, help="also write machine readable rows")
    e.set_defaults(fn=cmd_extract)

    v = sub.add_parser("verify", help="quality gates on extracted sprites")
    v.add_argument("--dir", required=True)
    v.add_argument("--min-count", type=int, default=14)
    v.add_argument("--min-height", type=int, default=64)
    v.set_defaults(fn=cmd_verify)

    m = sub.add_parser("montage", help="alpha-checker contact sheet of all sprites")
    m.add_argument("--dir", required=True)
    m.add_argument("--out", required=True)
    m.add_argument("--cols", type=int, default=4)
    m.add_argument("--cell-w", type=int, default=470)
    m.add_argument("--cell-h", type=int, default=430)
    m.add_argument("--names", default=None, help="comma separated subset")
    m.set_defaults(fn=cmd_montage)

    t = sub.add_parser("test48", help="48 px naming test strip")
    t.add_argument("--dir", required=True)
    t.add_argument("--out", required=True)
    t.add_argument("--zoom", type=int, default=4)
    t.set_defaults(fn=cmd_test48)

    l = sub.add_parser("list", help="list catalogue entries")
    l.add_argument("--catalog", default=None)
    l.set_defaults(fn=cmd_list)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
