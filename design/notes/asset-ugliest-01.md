# asset-ugliest-01 — the five worst things at 1:1

Source: real-X screenshot `design/notes/shots/xwin-1920-1080-clicked.png`
(1920x1080 screen, 1600x900 window, native scale — no resampling), plus the
1366x768 capture. Ranked by how much each one says "unfinished".

1. **Three near-identical brown-roof cabins** (screen ≈ 600–1270 x 250–540):
   town hall, lodge and longhouse are the same wood-and-shingle language at the
   same value; nothing tells you which is your economy, your tech, your army.
   Needs: distinct roof colour/height per role (hall = banners + stone base,
   barracks = weapon rack + smoke, mill = log pile) — this is also your
   townhall/barracks silhouette split question: **yes, it matters most.**
2. **Guard tower = bare stacked stone column** (≈ 695–775 x 130–350): no
   crenellations, no batter, reads as a chimney/totem. It is the tallest
   human object on screen for the wrong reason.
3. **Terrain tiling shows through**: the mid-screen dirt band (≈ 1050–1400 x
   200–600) and grass checker still read as a diamond lattice with a hard
   diagonal road edge; top-right water (≈ 1740–1900 x 130–330) still draws
   per-tile outlines. One more variation layer + edge-blend would hide it.
4. **Unit blob legibility** (≈ 790–1080 x 450–640): 12+ Flare units are dark
   and small at 1:1; silhouettes merge into one brown mass. Cheapest wins:
   +6 % brightness on unit sprites, a 1px lighter top-left rim (we agreed this
   in art-coherence-02 and it never landed for units), and a stronger ground
   contact shadow to separate feet from grass.
5. **The unexplored slab bottom-left** (≈ 160–560 x 560–790): a flat
   grey-brown region with a straight diagonal boundary. Fog needs the tile
   mask + feathered edge we specified; a straight cut looks like a missing
   texture. Runner-up: the grey tent at top-centre (≈ 850–935) reads as a blob.
