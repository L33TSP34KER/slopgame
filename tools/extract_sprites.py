#!/usr/bin/env python3
"""Extract the individual sprites out of assets/source-sheet.svg.

The design sheet is a machine generated SVG (Illustrator style) that contains
every character / prop of the game, plus its labels.  Each sprite lives in one
top level <g> which we can recognise by the first path it contains.

For every sprite we emit a standalone SVG that keeps the *original* coordinates
and only narrows the viewBox to a padded bounding box of the sprite.  Curves are
approximated by their control points, which yields a slightly generous box -- the
asset pipeline trims the transparent padding away when it rasterises to PNG.
"""

import os
import re
import xml.etree.ElementTree as ET

SVG_NS = "http://www.w3.org/2000/svg"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SOURCE = os.path.join(ROOT, "assets", "source-sheet.svg")
OUT_DIR = os.path.join(ROOT, "assets", "sprites")

# (output name, signature of the first path's `d` attribute, extra margin in sheet units)
SPRITES = [
    ("player",  "M1913.755 329.182", 0),
    ("enemy_a", "M2838.632 348.224", 0),
    ("enemy_b", "M3297.943 356.435", 0),
    ("gun",     "M1861.778 776.935", 0),
    ("bow",     "M2080.07 778.381",  0),
    ("sword",   "M2292.374 771.507", 0),
    ("money",   "M2412.598 753.071", 0),
    ("xp",      "M2595.106 963.563", 0),
]

NUM = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")


def tag_of(el):
    return el.tag.split("}", 1)[-1]


def first_path_d(el):
    for child in el.iter():
        if tag_of(child) == "path" and child.get("d"):
            return child.get("d")
    return None


def bbox_of(el):
    """Conservative bounding box: every coordinate pair found in the subtree."""
    xs, ys = [], []
    for node in el.iter():
        stroke = 0.0
        try:
            stroke = float(node.get("stroke-width", 0.0))
        except (TypeError, ValueError):
            stroke = 0.0
        pad = stroke / 2.0

        coords = []
        if node.get("d"):
            coords = [float(n) for n in NUM.findall(node.get("d"))]
        elif tag_of(node) in ("rect", "image"):
            try:
                x, y = float(node.get("x", 0)), float(node.get("y", 0))
                w, h = float(node.get("width", 0)), float(node.get("height", 0))
                coords = [x, y, x + w, y + h]
            except (TypeError, ValueError):
                coords = []
        if not coords:
            continue
        # path data is a flat stream: x y x y ...
        for i in range(0, len(coords) - 1, 2):
            xs.append(coords[i] - pad)
            ys.append(coords[i + 1] - pad)
        if len(coords) % 2 == 1:  # odd trailing number: horizontal/vertical run
            xs.append(coords[-1] - pad)

    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def fmt(v):
    return ("%.3f" % v).rstrip("0").rstrip(".")


def write_sprite(name, element, margin_ratio=0.04):
    box = bbox_of(element)
    if box is None:
        raise SystemExit("no geometry found for sprite %r" % name)
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    mx, my = w * margin_ratio, h * margin_ratio
    x0, y0, w, h = x0 - mx, y0 - my, w + 2 * mx, h + 2 * my

    ET.register_namespace("", SVG_NS)
    svg = ET.Element(
        "{%s}svg" % SVG_NS,
        {
            "viewBox": " ".join(fmt(v) for v in (x0, y0, w, h)),
            "width": fmt(w),
            "height": fmt(h),
        },
    )
    svg.append(element)

    path = os.path.join(OUT_DIR, name + ".svg")
    ET.ElementTree(svg).write(path, encoding="utf-8", xml_declaration=True)
    return path, (x0, y0, w, h)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tree = ET.parse(SOURCE)
    root = tree.getroot()
    # every sprite is a direct child of the single top level <g>
    wrapper = [c for c in root if tag_of(c) == "g"][0]
    children = list(wrapper)

    # deep copy so that appending into a fresh tree is safe
    import copy

    by_signature = {}
    for child in children:
        d = first_path_d(child)
        if d:
            by_signature.setdefault(d.strip(), child)

    for name, signature, margin in SPRITES:
        match = None
        for d, el in by_signature.items():
            if d.startswith(signature):
                match = el
                break
        if match is None:
            raise SystemExit("sprite %r not found (signature %r)" % (name, signature))
        path, box = write_sprite(name, copy.deepcopy(match), 0.04)
        print("%-8s -> %s  viewBox=%s" % (name, os.path.relpath(path, ROOT),
                                          " ".join("%.2f" % v for v in box)))


if __name__ == "__main__":
    main()
