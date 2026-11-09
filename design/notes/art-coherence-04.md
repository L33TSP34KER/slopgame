# art-coherence-04 — Flare building crops (14 shipped)

Reviewed by mimo: every crop in `assets/flare/buildings/` viewed on an alpha
checker via `design/notes/flare-buildings-montage.png`, against
`design/notes/flare-buildings.md` and the game's palette.

## Verdict

Alpha is clean, the iso angles are consistent, and three sprites are genuinely
good: **human_house_farm** (log cabin — the best of the set),
**human_town_hall** (lodge with gable), **undead_ruined_house** (collapsed
round shell). But as a *building set* for an RTS it fails two tests: half of
them are **prop piles rather than buildings**, and the set has **no faction
colour identity** — humans read as grey ruins, undead read as the same grey
ruins. The two most important buildings in the game (player keep, enemy
Necropolis) are currently among the weakest.

## Per-sprite calls

| sprite | verdict | what it needs |
|---|---|---|
| human_house_farm | **good** | nothing — ship it |
| human_town_hall | good | one flag/banner + a warm window/ember accent so it beats the house |
| human_barracks | **weak** | two canvas tents + crates reads "supply dump": add a weapon rack + banner, or a palisade corner |
| human_blacksmith_smithy | **weak** | forge + anvil + crates, no structure: needs a shed roof or chimney so it reads "building" |
| human_workshop_lumber | **weak** | log piles + stump reads "wood pile": add a saw-frame/shed silhouette |
| human_guard_tower | good | tall and thin — set draw scale so it doesn't look like a column at 2×2 |
| human_keep | **weak** | same grey column cluster as the temple; it is the player's **main upgrade** and must read castle: battlements, taller mass, flag |
| human_temple_altar | **weak** | visually near-identical to the keep; needs an open arch, a standing flame, and a different footprint proportion |
| undead_crypt | ok | acceptable; add a violet edge glow |
| undead_bone_ritual | **good** | the glowing orb is exactly the accent language the rest needs |
| undead_necropolis_ruin | **fails its role** | this is the **win condition** and it reads as a graveyard corner (fence + 3 headstones): it must be the most imposing sprite in the game — taller than the town hall, bone spikes, violet glow |
| undead_ziggurat_ruin | weak | grey blocks again; make the stepped pyramid obvious (wide → narrow, 3 tiers) |
| undead_ruined_house | **good** | ship it |
| undead_ruined_tower | ok | strong stone base, but the slat roof reads like a pergola and it is 888×1055 px — scale-normalise |

## Set-level fixes (in priority order)

1. **Faction colour identity.** Pull the contract palette into the crops:
   humans get crimson/gold accents (banners, warm windows, ember light);
   undead get bone/violet + sickly green glow. Today both factions are
   grey-brown stone, which will also make the minimap and unit-vs-building
   read harder.
2. **Dress the three "prop piles"** (barracks, smithy, lumber) with one
   structural element each — a roof, a frame, a rack — so they read as
   buildings at 48 px. Test: shrink to 48 px wide and name it in one second.
3. **Keep vs temple vs ziggurat must not share a silhouette.** Keep =
   crenellated mass + flag; temple = open arch + flame; ziggurat = stepped
   tiers. Right now two of the three are the same stone cluster.
4. **Normalise draw scale per footprint.** Raw sizes span 188×594 to
   888×1055; define one px-per-tile scale so a 2×2 and a 3×3 occupy their
   footprint honestly, and store the anchor (bottom-center, per catalog) with
   each sprite.
5. **Contact shadow** under every building (still missing engine-side) — the
   crops have no baked ground shadow, so the renderer must add one or the
   buildings float.

## Re-test plan

After dressing: regenerate the montage, then render the player base and the
enemy plateau with the new sprites (`tools/qa/scene_shots.py`) and run the
48-pixel naming test on the screenshot, not on the source PNGs.
