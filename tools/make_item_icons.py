#!/usr/bin/env python3
"""Item icons for the Emberhold purveyor.

The icon set is authored as SVG (like every other icon in assets/icons) and
rasterised to 64x64 PNG for the engine.  Geometry is kept on the same 64x64
grid, with the same 2 px ink outline, a soft ground shadow and the engine's
palette, so items sit next to abilities and buildings without a seam.

    ./tools/make_item_icons.py          # writes svg + png
"""
from __future__ import annotations
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ICONS = os.path.join(ROOT, "assets", "icons")
PNGS = os.path.join(ICONS, "png")

DEFS = """  <defs>
    <linearGradient id="gd" x1="0" y1="0" x2="0.7" y2="1">
      <stop offset="0" stop-color="#f2cd78"/><stop offset="1" stop-color="#a8752c"/>
    </linearGradient>
    <linearGradient id="em" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="#ffd08a"/><stop offset="0.45" stop-color="#ff8a3d"/>
      <stop offset="1" stop-color="#a83a3a"/>
    </linearGradient>
    <linearGradient id="st" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0" stop-color="#eef3f8"/><stop offset="0.55" stop-color="#b9c3ce"/>
      <stop offset="1" stop-color="#6f7883"/>
    </linearGradient>
    <linearGradient id="cr" x1="0" y1="0" x2="0.5" y2="1">
      <stop offset="0" stop-color="#cf5a45"/><stop offset="1" stop-color="#6d241f"/>
    </linearGradient>
    <linearGradient id="le" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0" stop-color="#9a6c42"/><stop offset="1" stop-color="#4d3321"/>
    </linearGradient>
    <linearGradient id="vi" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0" stop-color="#c9a6ea"/><stop offset="1" stop-color="#4e3566"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#ffb066" stop-opacity="0.75"/>
      <stop offset="1" stop-color="#ff8a3d" stop-opacity="0"/>
    </radialGradient>
  </defs>
"""

SHADOW = ('    <ellipse cx="32" cy="56" rx="19" ry="4" fill="#161018" opacity="0.30" stroke="none"/>\n')


def svg(label: str, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" '
            f'role="img" aria-label="{label}">\n{DEFS}'
            '  <g stroke="#161018" stroke-width="2" stroke-linejoin="round" stroke-linecap="round">\n'
            + SHADOW + body + "  </g>\n</svg>\n")


# --------------------------------------------------------------------- pieces
ITEMS = {
    # ---- components
    "it-blade": ("Ashwood Blade", """
    <path d="M47 9 L54 16 L30 40 L23 33 Z" fill="url(#st)"/>
    <path d="M47 9 L54 16 L48 17 L46 15 Z" fill="#eef3f8" stroke="none"/>
    <path d="M23 33 L17 39 M28 38 L22 44" stroke="none"/>
    <rect x="19" y="35" width="10" height="4" rx="1" transform="rotate(-45 24 37)" fill="url(#gd)"/>
    <rect x="13" y="41" width="11" height="4.5" rx="2" transform="rotate(-45 18 43)" fill="url(#le)"/>
    <circle cx="11" cy="51" r="3.4" fill="url(#gd)"/>
    <path d="M36 20 L40 24" stroke="#8f9aa5" stroke-width="1.4"/>
"""),
    "it-buckler": ("Iron Buckler", """
    <circle cx="32" cy="32" r="21" fill="url(#st)"/>
    <circle cx="32" cy="32" r="21" fill="none" stroke-width="2.6"/>
    <circle cx="32" cy="32" r="15.5" fill="none" stroke="#7e8a95" stroke-width="1.6"/>
    <circle cx="32" cy="32" r="7.5" fill="url(#gd)"/>
    <circle cx="32" cy="32" r="3" fill="#f2cd78" stroke="none"/>
    <path d="M32 12 V20 M32 44 V52 M12 32 H20 M44 32 H52" stroke="#b9c3ce" stroke-width="1.6"/>
    <path d="M19 19 L24 24 M45 19 L40 24 M19 45 L24 40 M45 45 L40 40" stroke="#6f7883" stroke-width="1.4"/>
"""),
    "it-tonic": ("Ember Tonic", """
    <path d="M26 10 H38 V16 L43 24 V48 C43 52 39 54 32 54 C25 54 21 52 21 48 V24 L26 16 Z" fill="#3a2b21"/>
    <path d="M23.5 32 H40.5 V48 C40.5 51 37.5 52.5 32 52.5 C26.5 52.5 23.5 51 23.5 48 Z" fill="url(#em)"/>
    <path d="M23.5 34 C27 31 37 31 40.5 34 L40.5 40 C36 37 28 37 23.5 40 Z" fill="#ffd08a" opacity="0.55" stroke="none"/>
    <rect x="25" y="7" width="14" height="6" rx="2.5" fill="url(#le)"/>
    <circle cx="35" cy="45" r="2" fill="#3a2b21" opacity="0.7" stroke="none"/>
    <circle cx="29" cy="48" r="1.6" fill="#3a2b21" opacity="0.6" stroke="none"/>
"""),
    "it-focus": ("Kindled Focus", """
    <circle cx="32" cy="34" r="17" fill="none" stroke="url(#gd)" stroke-width="3.4"/>
    <circle cx="32" cy="34" r="17" fill="none" stroke="#161018" stroke-width="1" opacity="0.5"/>
    <path d="M32 12 L40 30 L32 46 L24 30 Z" fill="url(#vi)"/>
    <path d="M32 16 L36 30 L32 41 L28 30 Z" fill="#e6d2ff" opacity="0.55" stroke="none"/>
    <path d="M32 46 L32 56" stroke="url(#gd)" stroke-width="3"/>
    <circle cx="32" cy="34" r="22" fill="url(#glow)" stroke="none"/>
"""),
    "it-greaves": ("Trail Greaves", """
    <path d="M22 12 H34 V34 L44 46 V54 H20 V34 Z" fill="url(#le)"/>
    <path d="M22 12 H34 V20 H22 Z" fill="#b98a5c"/>
    <path d="M23 32 L43 32 L45 40 L23 40 Z" fill="#5c3d27"/>
    <path d="M20 46 H44 V54 H20 Z" fill="#3a2a1c"/>
    <path d="M20 54 H46" stroke="#161018" stroke-width="3"/>
    <path d="M28 14 V30 M31 14 V30" stroke="#d8b48a" stroke-width="1.3"/>
    <path d="M25 42 H38" stroke="#d9a441" stroke-width="1.6"/>
    <circle cx="25" cy="20" r="1.8" fill="#d9a441"/>
    <circle cx="31" cy="24" r="1.8" fill="#d9a441"/>
"""),
    "it-whet": ("Whetstone", """
    <path d="M12 40 L36 24 L52 32 L28 49 Z" fill="url(#st)"/>
    <path d="M12 40 L28 49 L28 54 L12 45 Z" fill="#6f7883"/>
    <path d="M28 49 L52 32 L52 37 L28 54 Z" fill="#8f9aa5"/>
    <path d="M17 39 L34 28" stroke="#eef3f8" stroke-width="1.4"/>
    <path d="M36 12 L38 19 L45 21 L38 23 L36 30 L34 23 L27 21 L34 19 Z" fill="#ffd08a" stroke="none"/>
    <path d="M48 14 L49.5 18 L53 19.5 L49.5 21 L48 25 L46.5 21 L43 19.5 L46.5 18 Z" fill="#ff8a3d" stroke="none"/>
    <circle cx="42" cy="34" r="10" fill="url(#glow)" stroke="none"/>
"""),
    # ---- forged
    "it-warbrand": ("Ember Warbrand", """
    <path d="M44 7 L55 18 L32 41 L21 30 Z" fill="url(#st)"/>
    <path d="M44 7 L55 18 L45 18 L44 12 Z" fill="#fff6e2" stroke="none"/>
    <path d="M47 12 L52 17 L34 35 L29 30 Z" fill="url(#em)" opacity="0.55" stroke="none"/>
    <rect x="16" y="30" width="14" height="4.5" rx="1.5" transform="rotate(-45 23 32)" fill="url(#gd)"/>
    <rect x="9" y="37" width="12" height="5" rx="2" transform="rotate(-45 15 39)" fill="url(#le)"/>
    <circle cx="8" cy="49" r="4" fill="url(#gd)"/>
    <path d="M40 24 C44 20 48 22 47 27 C52 26 54 31 50 34 C54 38 50 43 45 41"
          fill="none" stroke="#ff8a3d" stroke-width="1.6" opacity="0.8"/>
    <circle cx="34" cy="28" r="14" fill="url(#glow)" stroke="none"/>
"""),
    "it-bulwark": ("Ashen Bulwark", """
    <path d="M32 7 L53 13 C53 33 46 47 32 57 C18 47 11 33 11 13 Z" fill="url(#st)"/>
    <path d="M32 10 L50 15 C50 32 44 44 32 53 C20 44 14 32 14 15 Z" fill="#8b949e"/>
    <path d="M32 15 C39 21 41 32 32 45 C23 32 25 21 32 15 Z" fill="url(#em)"/>
    <path d="M32 20 C35 25 36 31 32 38 C28 31 29 25 32 20 Z" fill="#ffe0b0" opacity="0.7" stroke="none"/>
    <path d="M17 22 H47" stroke="#d9a441" stroke-width="2"/>
    <path d="M20 44 C26 49 38 49 44 44" fill="none" stroke="#d9a441" stroke-width="2"/>
    <circle cx="32" cy="30" r="16" fill="url(#glow)" stroke="none"/>
"""),
    "it-cinder": ("Cinder Plate", """
    <path d="M18 14 L28 9 L32 15 L36 9 L46 14 L50 26 L44 30 L44 47 C44 51 38 53 32 53 C26 53 20 51 20 47 L20 30 L14 26 Z" fill="url(#st)"/>
    <path d="M24 20 H40 L38 27 H26 Z" fill="#6f7883"/>
    <path d="M26 30 H38 L36 44 H28 Z" fill="url(#em)"/>
    <path d="M32 33 L34 39 L30 39 Z" fill="#ffe0b0" stroke="none"/>
    <path d="M28 9 L32 15 L36 9" fill="none" stroke="#d9a441" stroke-width="2"/>
    <circle cx="20" cy="22" r="2.4" fill="url(#gd)"/><circle cx="44" cy="22" r="2.4" fill="url(#gd)"/>
    <circle cx="32" cy="36" r="14" fill="url(#glow)" stroke="none"/>
"""),
    "it-pyre": ("Pyre Heart", """
    <path d="M32 48 C18 38 12 30 15 21 C18 13 27 12 32 20 C37 12 46 13 49 21 C52 30 46 38 32 48 Z" fill="url(#em)"/>
    <path d="M32 42 C22 35 18 29 20 23 C22 18 28 18 32 24 C36 18 42 18 44 23 C46 29 42 35 32 42 Z" fill="#ffe0b0" opacity="0.55" stroke="none"/>
    <path d="M32 52 V57" stroke="#8f9aa5" stroke-width="2"/>
    <path d="M24 14 L22 7 M40 14 L42 7 M32 10 V4" stroke="#ff8a3d" stroke-width="2" opacity="0.9"/>
    <circle cx="32" cy="30" r="20" fill="url(#glow)" stroke="none"/>
"""),
    "it-windstep": ("Windstep Boots", """
    <path d="M20 20 H32 V36 L44 46 V54 H18 V36 Z" fill="url(#le)"/>
    <path d="M20 20 H32 V26 H20 Z" fill="#b98a5c"/>
    <path d="M18 46 H44 V54 H18 Z" fill="#3a2a1c"/>
    <path d="M18 54 H46" stroke="#161018" stroke-width="3"/>
    <path d="M34 14 C40 16 42 21 39 26 C36 30 40 34 42 36" fill="none" stroke="#dfe9ef" stroke-width="2" opacity="0.9"/>
    <path d="M42 20 C47 22 48 26 46 30" fill="none" stroke="#dfe9ef" stroke-width="1.6" opacity="0.7"/>
    <path d="M26 30 L36 34" stroke="#d9a441" stroke-width="1.6"/>
"""),
    "it-ashenstep": ("Ashen Step", """
    <path d="M16 34 C22 30 26 24 32 24 C38 24 44 30 46 36 C40 40 36 46 30 46 C24 46 20 40 16 34 Z" fill="url(#vi)"/>
    <path d="M20 35 C25 32 27 27 32 27 C37 27 41 32 43 36 C38 39 35 43 30 43 C25 43 23 39 20 35 Z" fill="#2a1d3c"/>
    <path d="M30 30 L33 36 L30 42 L27 36 Z" fill="#ffd08a" stroke="none"/>
    <path d="M32 8 L32 20 M20 14 L26 22 M44 14 L38 22" stroke="#b58ad2" stroke-width="2" opacity="0.85"/>
    <circle cx="22" cy="46" r="2" fill="#cfc4dd" stroke="none"/>
    <circle cx="40" cy="48" r="1.6" fill="#cfc4dd" stroke="none"/>
    <circle cx="32" cy="34" r="20" fill="url(#glow)" stroke="none"/>
"""),
    "it-flask": ("Ember Flask", """
    <path d="M26 8 H38 V15 C44 18 47 23 47 31 C47 43 41 53 32 56 C23 53 17 43 17 31 C17 23 20 18 26 15 Z" fill="#3a2b21"/>
    <path d="M20 33 C20 43 25 50 32 52 C39 50 44 43 44 33 C44 27 41 23 36 21 C34 25 30 25 28 21 C23 23 20 27 20 33 Z" fill="url(#em)"/>
    <path d="M23 34 C26 30 38 30 41 34" fill="none" stroke="#ffd08a" stroke-width="1.5" opacity="0.7"/>
    <rect x="24" y="5" width="16" height="6" rx="2.5" fill="url(#le)"/>
    <path d="M17 34 C16 40 18 44 20 46 M47 34 C48 40 46 44 44 46" fill="none" stroke="#8f9aa5" stroke-width="1.6"/>
    <circle cx="32" cy="36" r="16" fill="url(#glow)" stroke="none"/>
"""),
    # ---- masterwork
    "it-regalia": ("Marshal's Regalia", """
    <path d="M14 16 L24 10 L28 18 L36 18 L40 10 L50 16 L52 28 L45 31 L45 48 C45 52 39 55 32 55 C25 55 19 52 19 48 L19 31 L12 28 Z" fill="url(#gd)"/>
    <path d="M19 20 L26 16 L28 22 H36 L38 16 L45 20 L46 27 H18 Z" fill="url(#cr)"/>
    <path d="M27 31 H37 L35 46 H29 Z" fill="url(#em)"/>
    <path d="M32 7 L33.5 11 L38 12 L34.5 14.5 L35 19 L32 16.5 L29 19 L29.5 14.5 L26 12 L30.5 11 Z" fill="#f2cd78"/>
    <path d="M15 30 C13 36 15 41 18 43 M49 30 C51 36 49 41 46 43" fill="none" stroke="#f2cd78" stroke-width="1.6"/>
    <circle cx="32" cy="34" r="18" fill="url(#glow)" stroke="none"/>
"""),
    "it-warsong": ("Warsong Talisman", """
    <path d="M14 20 C20 14 30 14 36 19 C42 24 48 26 52 24 L49 30 C43 33 36 31 31 27 C26 23 20 23 16 27 Z" fill="#3a2b21"/>
    <path d="M16 22 C22 18 29 19 35 23 C40 27 45 28 49 27 L46 31 C41 33 35 31 30 27 C25 23 20 24 17 27 Z" fill="url(#em)"/>
    <path d="M51 25 L56 23 L55 28 Z" fill="url(#gd)"/>
    <path d="M32 31 L32 40" stroke="#d9a441" stroke-width="2"/>
    <circle cx="32" cy="46" r="7" fill="url(#gd)"/>
    <path d="M32 42 L34 46 L32 50 L30 46 Z" fill="#6d241f" stroke="none"/>
    <circle cx="32" cy="46" r="14" fill="url(#glow)" stroke="none"/>
"""),
    # ---- shop entry (command card / top bar)
    "it-bag": ("Purveyor's Satchel", """
    <path d="M14 24 C14 21 17 19 20 19 H44 C47 19 50 21 50 24 L52 49 C52 52 49 54 46 54 H18 C15 54 12 52 12 49 Z" fill="url(#le)"/>
    <path d="M22 19 C22 11 42 11 42 19" fill="none" stroke="#3a2a1c" stroke-width="3"/>
    <rect x="24" y="30" width="16" height="12" rx="2" fill="url(#gd)"/>
    <path d="M32 30 V42" stroke="#6d241f" stroke-width="1.6"/>
    <circle cx="32" cy="36" r="2.6" fill="#f2cd78"/>
    <path d="M14 27 H50" stroke="#3a2a1c" stroke-width="2"/>
    <path d="M18 46 H24 M40 46 H46" stroke="#b98a5c" stroke-width="1.4"/>
"""),
}


def main() -> int:
    try:
        import cairosvg
    except ImportError:
        print("cairosvg missing: install it into the venv (pip install cairosvg)", file=sys.stderr)
        return 2
    os.makedirs(PNGS, exist_ok=True)
    for key, (label, body) in ITEMS.items():
        src = svg(label, body)
        # art.py reads the icon key from the filename as fn[5:-4], i.e. the
        # engine contract is assets/icons/icon-<key>.png
        fn = "icon-" + key
        with open(os.path.join(ICONS, fn + ".svg"), "w", encoding="utf-8") as f:
            f.write(src)
        cairosvg.svg2png(bytestring=src.encode(), write_to=os.path.join(PNGS, fn + ".png"),
                         output_width=64, output_height=64)
        print("wrote", fn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
