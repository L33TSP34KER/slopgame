# ASSET CONTRACT — Emberfall (for mimo)

Deliver into the repo at the exact paths below. Missing files are tolerated by
the game (it falls back), so ship incrementally — a few files early is worth
more than a perfect pack late. Loudness: SFX peak ≤ -6 dBFS, music bed ≤ -18
dBFS RMS. OGG Vorbis for music, OGG or WAV for SFX. No copyrighted samples.

## SFX (mono, 44.1 kHz, < 1.2 s unless noted)

`assets/audio/sfx/click.ogg` — UI click, soft wooden tick
`select.ogg` — unit selected, parchment/armour tap
`command.ogg` — order acknowledged, muted drum + metal
`error.ogg` — can't do that, low wooden knock (no harsh beep)
`sword.ogg` — blade hit flesh/metal, 2–3 variants via pitch in engine
`bow.ogg` — bow release + distant thud
`magic.ogg` — arcane whoosh, airy
`holy.ogg` — warm bell shimmer (heal / level-up bed)
`build.ogg` — hammer on wood, short
`build-done.ogg` — structure completes, rising chime
`gold.ogg` — coins into purse, bright
`chop.ogg` — axe bites wood, 2 variants
`death.ogg` — short body fall, no gore
`level-up.ogg` — hero fanfare, 1.5 s
`alert.ogg` — under attack: low horn + drum, 1.5 s
`horn.ogg` — wave incoming, distant war horn, 2.5 s
`explosion.ogg` — siege impact, 1 s
`roar.ogg` — Hollow King, 2 s
`victory.ogg` — 4 s stinger
`defeat.ogg` — 4 s stinger

## Music (stereo, 44.1 kHz, seamless loops)

`assets/audio/music/menu.ogg` — 60–90 s, brooding ember/cello/choir pad, low
`assets/audio/music/battle.ogg` — 90–120 s, sparse war drums + strings, builds
`assets/audio/music/night.ogg` — 60–90 s, quiet vale ambience, optional

## Art (optional, only if it clearly beats procedural and matches the palette)

- `assets/art/logo.png` — 1024×512 transparent, wordmark "EMBERFALL" + subtitle
  "The Hollow Crown", parchment/brass, readable on dark ground.
- `assets/art/title-bg.png` — 1920×1080, moody vale silhouette + embers.
- `assets/art/loading.png` — 1920×1080, same world.
- UI icons (SVG preferred, 64×64, single-family line/fill):
  `assets/icons/icon-<id>.svg` for unit/building/ability ids:
  worker footman archer knight priest ballista townhall farm barracks mill
  blacksmith sanctum tower altar keep gold lumber food
  ember-lance aegis consecrate daybreak
- Keep palette: ember #ff8a3d, gold #d9a441, crimson #a83a3a, steel #cfd6df,
  moss #4b6b3f, slate #6d6a63, bone #d8d2bd, violet #5a4470, ink #161018.

Do not edit files under `game/`. Report on the bus
(`python3 bus.py send --from mimo --to deepseek ...`) with what landed.
