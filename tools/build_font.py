#!/usr/bin/env python3
"""Build the shared bitmap font atlas used by every platform renderer.

Why a bitmap atlas instead of native text APIs?
  The game logic lives in the shared library, and so does text layout: the
  library emits one GC_CMD_GLYPH per character.  A single atlas therefore gives
  *identical* typography on Linux, macOS, iOS and Android, and lets the renderers
  stay dumb (they only blit coloured quads).

The atlas is white-on-transparent, so a renderer can tint it with the colour
carried in the command.

Outputs
  assets/dist/font_atlas.png        the texture every platform bundles
  assets/dist/font_atlas.json       human/tool readable metrics (debug aid)
  core/src/generated/font_metrics.rs  metrics consumed by the shared library

Requires ImageMagick (`magick`).  Run via tools/build_assets.sh.
"""

import json
import os
import re
import subprocess
import sys

MAGICK = os.environ.get("MAGICK", "magick")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "assets", "dist")
BUILD = os.path.join(ROOT, "assets", ".fontbuild")
GEN_RS = os.path.join(ROOT, "core", "src", "generated", "font_metrics.rs")

FIRST_CHAR = 32
LAST_CHAR = 126
POINTSIZE = 64
# annotate origin: x = pen start, y = baseline (verified empirically)
ORIGIN = (100, 140)
CANVAS = 256
PAD = 2
ATLAS_W = 1024
FONT_CANDIDATES = [
    "DejaVu-Sans-Bold",
    "DejaVu-Sans",
    "Liberation-Sans-Bold",
    "Noto-Sans-Bold",
    "FreeSansBold",
]

METRICS_RE = re.compile(
    r"Metrics:.*?width:\s*(\d+);\s*height:\s*(\d+);\s*ascent:\s*(-?\d+);\s*"
    r"descent:\s*(-?\d+);.*?origin:\s*([-\d.]+),"
)


def run(args, capture=True):
    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
    )
    return proc.returncode, (proc.stdout or "")


def pick_font():
    for name in FONT_CANDIDATES:
        code, _ = run([MAGICK, "-font", name, "-pointsize", "16", "label:A", "null:"])
        if code == 0:
            return name
    raise SystemExit(
        "no usable font found; tried %s.\nInstall DejaVu fonts (e.g. ttf-dejavu)."
        % ", ".join(FONT_CANDIDATES)
    )


def render_glyph(font, ch):
    """Render one character and return (advance, ink box or None, metrics)."""
    out = os.path.join(BUILD, "g.png")
    _, log = run(
        [
            MAGICK, "-debug", "annotate",
            "-size", "%dx%d" % (CANVAS, CANVAS), "xc:none",
            "-font", font, "-pointsize", str(POINTSIZE),
            "-fill", "white",
            "-annotate", "+%d+%d" % ORIGIN, ch,
            out,
        ]
    )
    match = METRICS_RE.search(log)
    if not match:
        return None
    ascent, descent = int(match.group(3)), int(match.group(4))

    code, box = run([MAGICK, "identify", "-format", "%@", out])
    ink = None
    tile = None
    if code == 0:
        bm = re.match(r"(\d+)x(\d+)\+(\d+)\+(\d+)", box.strip())
        if bm:
            w, h, x, y = (int(v) for v in bm.groups())
            if w > 0 and h > 0 and x < CANVAS:
                ink = (x - ORIGIN[0], y - ORIGIN[1], w, h)
                # Pack the *trimmed ink*, not the whole canvas: the renderer gets
                # one tight tile per glyph and the metrics carry the placement.
                tile = os.path.join(BUILD, "tile_%d.png" % ord(ch))
                code, log = run([MAGICK, out, "-crop", "%dx%d+%d+%d" % (w, h, x, y),
                                 "+repage", "PNG32:" + tile])
                if code != 0:
                    raise SystemExit("failed to trim glyph U+%04X:\n%s" % (ord(ch), log))
    return {"advance": float(match.group(5)), "ink": ink,
            "ascent": ascent, "descent": descent, "png": tile}


def measure_label(font, text):
    """Ink width of a rendered label, in pointsize-64 pixels."""
    code, out = run([
        MAGICK, "-font", font, "-pointsize", str(POINTSIZE),
        "-fill", "white", "-background", "none", "label:" + text,
        "-format", "%w", "info:",
    ])
    if code != 0:
        raise SystemExit("failed to measure label %r" % text)
    return float(out.strip())


def shelf_pack(items):
    """items: list of dicts with 'w'/'h'.  Simple shelf packer, returns
    (placed, atlas_h) where placed entries gained 'x'/'y'."""
    order = sorted(items, key=lambda it: (-it["h"], it["w"]))
    x = PAD
    y = PAD
    shelf_h = 0
    for it in order:
        if it["w"] == 0 or it["h"] == 0:
            it["x"] = it["y"] = 0
            continue
        if x + it["w"] + PAD > ATLAS_W:
            x = PAD
            y += shelf_h + PAD
            shelf_h = 0
        it["x"] = x
        it["y"] = y
        x += it["w"] + PAD
        shelf_h = max(shelf_h, it["h"])
    atlas_h = y + shelf_h + PAD
    return items, atlas_h


def compose_atlas(glyphs, atlas_h, out_path):
    # `-flatten` honours per-image page offsets *and* keeps the canvas size and
    # the alpha channel, which `-layers merge` does not.
    args = [MAGICK, "-size", "%dx%d" % (ATLAS_W, atlas_h), "xc:none"]
    for g in glyphs:
        if g["w"] == 0 or g["h"] == 0:
            continue
        args += ["(", g["png"], "-page", "+%d+%d" % (g["x"], g["y"]), ")"]
    args += ["-background", "none", "-flatten", "PNG32:" + out_path]
    code, log = run(args)
    if code != 0:
        raise SystemExit("atlas composition failed:\n" + log)

    code, out = run([MAGICK, "identify", "-format", "%wx%h %[channels]", out_path])
    got_w, got_h = (int(v) for v in out.split()[0].split("x"))
    if (got_w, got_h) != (ATLAS_W, atlas_h):
        raise SystemExit("atlas has unexpected size %dx%d (wanted %dx%d)"
                         % (got_w, got_h, ATLAS_W, atlas_h))
    if "a" not in out.split()[1]:
        raise SystemExit("atlas lost its alpha channel: %r" % out)


def write_rust(font, glyphs, atlas_h, ascent, descent, line_height):
    os.makedirs(os.path.dirname(GEN_RS), exist_ok=True)
    rows = []
    for g in glyphs:
        rows.append(
            "    (0x%02X, %d, %d, %d, %d, %d, %d, %s),"
            % (g["cp"], g["x"], g["y"], g["w"], g["h"],
               g["dx"], g["dy"], fmt_f32(g["advance"]))
        )
    body = "\n".join(rows)
    src = f"""// @generated by tools/build_font.py -- DO NOT EDIT BY HAND.
#![allow(dead_code)]
//
// Metrics for the shared bitmap font atlas (assets/dist/font_atlas.png).
// All distances are in "em units at pointsize {POINTSIZE}"; the shared library
// scales them by (requested_size / EM_SIZE).
//
// Tuple layout: (codepoint, atlas_x, atlas_y, w, h, offset_x, offset_y, advance)
//   offset_x / offset_y place the glyph's top-left corner relative to the pen
//   position on the baseline; offset_y is negative because the coordinate system
//   is y-down and glyph ink sits above the baseline.
//
// Source font: {font}

pub const ATLAS_W: u32 = {ATLAS_W};
pub const ATLAS_H: u32 = {atlas_h};
pub const EM_SIZE: f32 = {fmt_f32(POINTSIZE)};
pub const ASCENT: f32 = {fmt_f32(ascent)};
pub const DESCENT: f32 = {fmt_f32(descent)};
pub const LINE_HEIGHT: f32 = {fmt_f32(line_height)};
pub const FIRST_CHAR: u32 = {FIRST_CHAR};
pub const GLYPH_COUNT: usize = {len(glyphs)};

#[rustfmt::skip]
pub static GLYPHS: [(u32, u16, u16, u16, u16, i16, i16, f32); GLYPH_COUNT] = [
{body}
];
"""
    with open(GEN_RS, "w", encoding="utf-8") as fh:
        fh.write(src)


def fmt_f32(v):
    """Always emits a Rust float literal (never a bare integer)."""
    s = "%.4f" % v
    s = s.rstrip("0")
    if s.endswith("."):
        s += "0"
    return s or "0.0"


def verify_atlas(font, glyphs, ascent, descent, sample):
    """Proof-read the metrics: rebuild a string *from the atlas* exactly the way
    the renderers will, and put it next to ImageMagick's own rendering."""
    by_cp = {g["cp"]: g for g in glyphs}
    baseline = ascent + PAD
    pen = PAD

    atlas_path = os.path.join(DIST, "font_atlas.png")
    layers = []
    for ch in sample:
        g = by_cp.get(ord(ch))
        if g is None:
            raise SystemExit("verify: character %r missing from the atlas" % ch)
        if g["w"] and g["h"]:
            crop = os.path.join(BUILD, "crop_%d_%d.png" % (g["x"], g["y"]))
            code, log = run([MAGICK, atlas_path, "-crop",
                             "%dx%d+%d+%d" % (g["w"], g["h"], g["x"], g["y"]),
                             "+repage", "PNG32:" + crop])
            if code != 0:
                raise SystemExit("verify: crop failed:\n" + log)
            layers.append((pen + g["dx"], baseline + g["dy"], crop))
        pen += int(round(g["advance"]))
    width = pen + PAD
    height = int(ascent + descent) + 2 * PAD

    args = [MAGICK, "-size", "%dx%d" % (width, height), "xc:#202028"]
    for (x, y, path) in layers:
        args += ["(", path, "-page", "+%d+%d" % (x, max(0, y)), ")"]
    args += ["-background", "none", "-flatten",
             os.path.join(BUILD, "verify_from_atlas.png")]
    code, log = run(args)
    if code != 0:
        raise SystemExit("verification render failed:\n" + log)

    code, log = run([
        MAGICK, "-background", "#202028", "-fill", "white",
        "-font", font, "-pointsize", str(POINTSIZE),
        "label:" + sample, os.path.join(BUILD, "verify_reference.png"),
    ])
    if code != 0:
        raise SystemExit("reference render failed:\n" + log)

    out = os.path.join(ROOT, "assets", "font_verify.png")
    run([MAGICK, os.path.join(BUILD, "verify_from_atlas.png"),
         os.path.join(BUILD, "verify_reference.png"),
         "-background", "#101014", "-gravity", "west", "-append", out])
    print("verification image -> %s (top: composed from atlas, bottom: reference)"
          % os.path.relpath(out, ROOT))


def main():
    verify_only = "--verify" in sys.argv
    os.makedirs(DIST, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)
    font = pick_font()
    print("font: %s" % font)

    glyphs = []
    ascent = descent = None
    blanks = []
    for cp in range(FIRST_CHAR, LAST_CHAR + 1):
        ch = chr(cp)
        info = render_glyph(font, ch)
        if info is None:
            # Whitespace and other inkless glyphs produce no metrics at all.
            blanks.append(cp)
            glyphs.append({"cp": cp, "char": ch, "advance": 0.3 * POINTSIZE,
                           "dx": 0, "dy": 0, "w": 0, "h": 0, "png": None})
            continue
        ascent = info["ascent"]
        descent = info["descent"]
        entry = {"cp": cp, "char": ch, "advance": info["advance"]}
        if info["ink"]:
            dx, dy, w, h = info["ink"]
        else:
            dx = dy = w = h = 0
        entry.update({"dx": dx, "dy": dy, "w": w, "h": h, "png": info["png"]})
        glyphs.append(entry)

    if ascent is None:
        raise SystemExit("font %r produced no metrics at all" % font)

    # Space needs a special case: measuring its ink is impossible, so derive the
    # advance from the difference between "a a" and "aa", which cancels the
    # bearings of 'a'.
    if 32 in blanks:
        space = next(g for g in glyphs if g["cp"] == 32)
        space["advance"] = measure_label(font, "a a") - measure_label(font, "aa")
        print("space advance: %.2f" % space["advance"])

    glyphs, atlas_h = shelf_pack(glyphs)
    # Keep the atlas height a multiple of 4 for tidy GPU uploads.
    atlas_h = (atlas_h + 3) & ~3
    compose_atlas(glyphs, atlas_h, os.path.join(DIST, "font_atlas.png"))

    ascent = float(ascent)
    descent = float(abs(descent))
    line_height = ascent + descent

    with open(os.path.join(DIST, "font_atlas.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "font": font, "pointsize": POINTSIZE, "atlas": [ATLAS_W, atlas_h],
            "ascent": ascent, "descent": descent, "line_height": line_height,
            "glyphs": [{k: g[k] for k in ("cp", "char", "x", "y", "w", "h",
                                          "dx", "dy", "advance")} for g in glyphs],
        }, fh, indent=1)

    write_rust(font, glyphs, atlas_h, ascent, descent, line_height)
    print("atlas: %dx%d -> %s" % (ATLAS_W, atlas_h, os.path.relpath(
        os.path.join(DIST, "font_atlas.png"), ROOT)))
    print("metrics -> %s" % os.path.relpath(GEN_RS, ROOT))

    verify_atlas(font, glyphs, ascent, descent, "SLIME ARENA 42 $ 100%")


if __name__ == "__main__":
    main()
