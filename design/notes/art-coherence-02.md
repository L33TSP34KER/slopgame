# art-coherence-02 — unit + building sheets (first sprites)

Reviewed by mimo: `design/unit-sheet.png` (16 units), `design/building-sheet.png`
(16 buildings), against `design/icon-sheet.png` (34 icons) and `DESIGN.md`'s
art direction. Sheet labels overlapping sprites is a dev-sheet layout issue,
not a game issue — ignored below.

## Verdict

Structurally right: faction read is instant (warm steel/crimson/bone-violet),
silhouettes are mostly distinct, buildings are proper iso with base plates,
the Necropolis is a genuinely good objective silhouette. **But everything
in-world is ~20 % darker and less saturated than the icon sheet**, so the HUD
language and the battlefield language still look like two games. And four
sprites fail the "name it in one second" test.

## Blockers (do these before the next sheet ships)

1. **Lift in-world values to meet the icons.** Sample the icon sheet's cream
   `#f0e3c8`, gold `#d9a441`, crimson `#a83a3a` as the reference; units and
   buildings should reach similar *peak* brightness on their lit faces. Right
   now unit armour reads brown-grey where the icon reads steel-cream. Target:
   lit-face luminance within ~15 % of the matching icon's average, top-left sun.
2. **Silhouette failures:**
   - **Ballista** reads as a wooden wagon. It needs visible bow arms + string
     angled across the front, a bolt in the groove, and a taller rear axle —
     at 48 px it must say "bolt thrower", not "cart".
   - **Abomination** reads as a scarecrow: it's the same height/thickness as a
     footman. Give it a hunched 1.4× mass, hanging gut, stitched seams, one
     oversized arm.
   - **Hero (Aldric)** vs **Knight** are near-twins. Hero needs: 15 % taller,
     a cape, ember-glow on the blade/shoulder (the faction's one light source),
     and a distinct helm.
   - **Wolf vs elder-wolf** are the same sprite. Elder: 1.3× size, bone spikes,
     colder eyes, ragged mane.
3. **Size hierarchy is flat.** Order should read at a glance from the side:
   skeleton < worker/footman/archer < priest < knight < abomination/revenant
   < ballista (footprint wider than tall) < hollow-king (tallest thing on the
   map). Bake this into the scale table; a boss that is the same height as a
   knight is a wasted boss.
4. **Human buildings are one note.** Nine buildings, all dark maroon roof +
   grey wall. Each needs ONE identifying beacon so it can be told apart while
   panning: mill = stacked logs + saw wheel, blacksmith = chimney smoke + orange
   forge glow, sanctum = blue arcane light in the roof opening, farm = fenced
   field strip, tower = taller batter + banner, altar = ember column.
5. **Undead buildings converge.** Ziggurat/crypt/temple/bonetower are all
   "purple box + skull". Push the archetypes: ziggurat = stepped pyramid
   (yours already is — good), crypt = low wide mound with a skull archway,
   temple = twin spires + hanging ribs, bonetower = thin and tall (2.5× height
   of a ziggurat). Bonetower especially must read as "the thing that shoots".
6. **Verify the ink edge actually landed.** Promised 1–2 px 35 % ink on all
   interactive props — on these sheets the edges are soft/dark-on-dark. On
   dark terrain, dark ink disappears; use a *slightly lighter* rim on the
   top-left and darker on the bottom-right (or ink at 50 % over a 1 px lighter
   under-stroke) so props separate from the ground.

## Already good — do not "fix"

- Faction colour logic, warm humans vs cold undead.
- Necropolis scale and skull motif; altar flame reading; keep/townhall base
  plates and window glow.
- Icon sheet (still the strongest family; it is the reference, not the target
  of changes).

## Checks I will run in QA once they're in-scene

- 100 % zoom readability test: name every visible entity in 2 s.
- Icon ↔ sprite pairing test: put `icon-footman.png` next to the footman
  sprite — same family? (currently: no — item 1 fixes it).
- Contrast against both grass and ash-plateau ground; no unit should vanish
  into its own terrain.
- Selection ring / health bar legibility over busy forest tiles.
