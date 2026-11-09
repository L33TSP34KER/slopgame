# art-coherence-01 — do the assets actually work together?

Reviewed by mimo: `design/render-test.png` (1600×900 iso terrain render),
`design/render-test-enemy.png`, `design/icon-sheet.png` (34 icons @96/48),
`design/map-preview.png`, palette from `design/ASSET-CONTRACT.md`.

## Verdict

**Icons: excellent and coherent as a set.** One line weight, one warm palette
(gold `#d9a441`, cream, crimson, walnut ground), readable silhouettes at 48 px,
96 px versions consistent. This is the strongest asset family we have — the HUD
should lean on it hard.

**Terrain render: competent but tonally a different game.** Soft, outline-free,
dark-leaning, naturalistic greens; the icons are heavy-ink, bright, cartoony.
Side by side they read as two art directions. Not fatal — HUD icons sit on wood
panels — but in-world units/props must bridge the gap or the seam will show the
moment a Footman icon and a Footman sprite are on screen together.

## Concrete issues (highest impact first)

1. **Fog reads as a bug.** In `render-test.png` the dark area is a chain of
   huge overlapping opaque black *circles* slashing across the middle of the
   screen. Whatever it is (fog test, occlusion test), it does not read as fog:
   fog needs (a) a tile-aligned explored/visible boundary, (b) a soft 3–6 px
   gradient at the edge, (c) explored-but-invisible as a ~55 % dark veil, not
   solid black. If it's a WIP mask, fine — but it must not ship like this.
2. **Night grade is too dark.** The whole render sits low; grass reads near
   olive-black in the bottom half. Beta players screenshot at 100 % brightness
   on a laptop. Target: at night, terrain luminance floor ≈ 25 % of day, with
   torchlight pools carrying the eye. Day should be clearly *bright*.
3. **Grass checker is too regular.** The 2-tone diamond checker repeats in a
   perfect alternating lattice — at a glance the ground looks like a QA test
   pattern, not a vale. Add a second, lower-contrast variation layer (3–4
   variants chosen by hash of tile coords, clustered, not per-tile random) and
   keep the A/B delta ≤ 4 % luminance.
4. **Bridge the outline gap.** Two acceptable fixes, pick one and commit:
   - add a subtle dark edge (1–2 px, 35 % alpha ink `#161018`) to interactive
     props — trees, rocks, buildings, units — so they read like the icons; or
   - strip icons down toward the terrain (less ink, softer fills).
   The first is much cheaper and keeps the icon sheet's quality.
5. **Trees merge into a mass.** Forest clusters lose individual silhouettes at
   this darkness; give tree tops a slight rim from the top-left sun and 3
   tonal variants so a forest edge reads as trees, not a dark wall.
6. **Fonts:** `design/DESIGN.md` calls for serif display type in the HUD; the
   only font asset so far is `assets/fonts/fonts.css` (web). Native build needs
   a TTF path — tell me which file you load and I'll check licensing + the
   parchment/walnut contrast ratios in the HUD pass.

## What I'll check next (once units + HUD render)

- Unit sprite vs its command-card icon: same silhouette language, same palette
  family, same outline weight.
- Palette audit: sample the screenshot, confirm ember/gold/crimson vs
  bone/violet separation, no muddied mid-greys in combat areas.
- Readability test: can I name every entity at 25 % zoom in 2 seconds?
- HUD contrast ratios on walnut/parchment, tooltip legibility at 1600×900.
