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
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

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
            dict(a="grassland", id=59, gx=0, gy=1),
            dict(a="grassland", id=56, gx=1, gy=1),
            dict(a="grassland", id=80, gx=0, gy=2),
            dict(a="grassland", id=61, gx=2, gy=1),
        ],
        note="two canvas/fur field tents + barrel + supply crate = encampment",
    ),
    dict(
        name="human_workshop_lumber", kind="human", src="compose", footprint="3x2",
        parts=[
            dict(a="grassland", id=84, gx=0, gy=2),
            dict(a="grassland", id=85, gx=1, gy=2),
            dict(a="grassland", id=121, gx=1, gy=1),
            dict(a="grassland", id=120, gx=0, gy=1),
            dict(a="grassland", id=92, gx=2, gy=2),
        ],
        note="log piles + axe-in-stump + cutting stump + rail fence (lumber yard)",
    ),
    dict(
        name="human_blacksmith_smithy", kind="human", src="compose", footprint="2x2",
        parts=[
            dict(a="grassland", id=86, gx=0, gy=1),
            dict(a="grassland", id=87, gx=1, gy=1),
            dict(a="grassland", id=61, gx=2, gy=1),
            dict(a="grassland", id=80, gx=0, gy=2),
        ],
        note="forge fire + anvil on stump + crate + barrel (work yard, not a shell)",
    ),
    dict(
        name="human_guard_tower", kind="human", src="compose", footprint="2x2",
        parts=[
            dict(a="ruins", id=177, gx=1, gy=1),
            dict(a="ruins", id=177, gx=1, gy=1, above=True, overlap=120),
            dict(a="ruins", id=199, gx=1, gy=1, above=True, overlap=90),
        ],
        note="stacked stone column blocks + tapered crenellated cap (ruins.png)",
    ),
    dict(
        name="human_temple_altar", kind="human", src="compose", footprint="3x3",
        parts=[
            dict(a="ruins", id=177, gx=0, gy=1),
            dict(a="grassland_2x2", id=0, gx=1, gy=1),
            dict(a="ruins", id=128, gx=1, gy=1, dy=-60),
            dict(a="ruins", id=177, gx=2, gy=1),
        ],
        note="carved stone rune circle + stepped monument + flanking columns",
    ),
    dict(
        name="human_keep", kind="human", src="compose", footprint="3x3",
        parts=[
            dict(a="ruins", id=177, gx=2, gy=0),
            dict(a="ruins", id=177, gx=0, gy=1),
            dict(a="ruins", id=177, gx=1, gy=1),
            dict(a="ruins", id=177, gx=2, gy=1),
            dict(a="ruins", id=199, gx=1, gy=1, above=True, overlap=150),
        ],
        note="four stone column blocks in the Flare house footprint + capped central tower",
    ),
    # ---------------------------- UNDEAD/RUINED ---------------------------- #
    dict(
        name="undead_ruined_tower", kind="undead", src="atlas",
        footprint="3x3", atlas="tilesheets/grassland_rottentower.png",
        rect=(0, 0, 1074, 1074),
        note="Flare 'rottentower': ivy-covered stone tower, rotted plank roof",
    ),
    dict(
        name="undead_ruined_house", kind="undead", src="compose", footprint="3x3",
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
        parts=[
            dict(a="ruins", id=201, gx=0, gy=1),
            dict(a="ruins", id=201, gx=2, gy=0),
            dict(a="ruins", id=201, gx=2, gy=1),
            dict(a="ruins", id=201, gx=1, gy=1),
            dict(a="ruins", id=199, gx=1, gy=1, above=True, overlap=140),
            dict(a="ruins", id=128, gx=1, gy=1, above=True, overlap=90),
        ],
        note="wide stepped base of tapered blocks + raised stepped core (ruins.png)",
    ),
    dict(
        name="undead_necropolis_ruin", kind="undead", src="compose", footprint="3x3",
        parts=[
            dict(a="ruins", id=336, gx=1, gy=1),
            dict(a="ruins", id=340, gx=2, gy=1),
            dict(a="grassland", id=124, gx=1, gy=2),
            dict(a="grassland", id=125, gx=2, gy=2),
            dict(a="grassland", id=126, gx=3, gy=2),
            dict(a="grassland", id=122, gx=2, gy=3),
        ],
        note="iron grave fence behind headstones, stone cross and wooden cross",
    ),
    dict(
        name="undead_bone_ritual", kind="undead", src="compose", footprint="2x2",
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


def compose(spec):
    """Place atlas cells on a virtual isometric grid (Tiled anchor rules)."""
    placed = []
    descs = []
    last = None
    for p in spec["parts"]:
        a = _atlas(p["a"])
        cid = int(p["id"])
        col, row = cid % a["cols"], cid // a["cols"]
        img = a["img"].crop((col * a["tw"], row * a["th"],
                             col * a["tw"] + a["tw"], row * a["th"] + a["th"]))
        gx, gy = int(p["gx"]), int(p["gy"])
        left = (gx - gy) * MAP_TILE_W // 2 + int(p.get("dx", 0))
        top = (gx + gy) * MAP_TILE_H // 2 + MAP_TILE_H - a["th"] + int(p.get("dy", 0))
        cb = content_bbox(img)
        if p.get("above") and last is not None:
            # stack: bottom of this part's content sits on top of the last one
            prev_content_top = last["t"] + last["cb"][1]
            top = prev_content_top + int(p.get("overlap", 16)) - cb[3]
        placed.append(dict(img=img, l=left, t=top, cb=cb))
        descs.append("%s#%d@g(%d,%d)" % (p["a"], cid, gx, gy))
        last = placed[-1]
    min_l = min(e["l"] for e in placed)
    min_t = min(e["t"] for e in placed)
    max_r = max(e["l"] + e["img"].width for e in placed)
    max_b = max(e["t"] + e["img"].height for e in placed)
    canvas = Image.new("RGBA", (max_r - min_l, max_b - min_t), (0, 0, 0, 0))
    for e in placed:
        box = (e["l"] - min_l, e["t"] - min_t)
        canvas.alpha_composite(e["img"], box)
    return canvas, " + ".join(descs)


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
    rows = []
    for spec in specs:
        if spec.get("skip"):
            continue
        img, src_desc = build_part(spec)
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
            note=spec.get("note", "")))
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


def write_catalog_markdown(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    lines = [
        "# Flare building sprites - catalog",
        "",
        "Generated by `python3 tools/flare_buildings.py extract --markdown design/notes/flare-buildings.md`.",
        "Anchor convention for every sprite below: **bottom-center** of the PNG = front (bottom)",
        "vertex of the building's ground footprint diamond.",
        "",
        "| name | file | px | anchor (px) | source atlas/TMX + crop | footprint (tiles) | RTS silhouette @48px |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append("| %s | `%s` | %dx%d | (%d, %d) | %s | %s | %s |" % (
            r["name"], r["file"], r["w"], r["h"], r["w"] // 2, r["h"],
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
    e.add_argument("--markdown", default=None, help="also write a markdown catalog table")
    e.add_argument("--json", default=None, help="also write machine readable rows")
    e.set_defaults(fn=cmd_extract)

    v = sub.add_parser("verify", help="quality gates on extracted sprites")
    v.add_argument("--dir", required=True)
    v.add_argument("--min-count", type=int, default=14)
    v.add_argument("--min-height", type=int, default=64)
    v.set_defaults(fn=cmd_verify)

    l = sub.add_parser("list", help="list catalogue entries")
    l.add_argument("--catalog", default=None)
    l.set_defaults(fn=cmd_list)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
