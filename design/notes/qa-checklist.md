# qa-checklist — what qa-01.md must score every build

Owner: mimo. Method: `tools/qa/run_qa.py` (headless, SDL dummy) + game state
JSON + screenshots, plus `tools/qa/map_audit.py` for structure, plus visual
passes on any pushed PNG. Every line is **PASS / FAIL / BLOCKED** with evidence
(screenshot name, state sample, or log excerpt). No line may be left blank.

## 1. Boot & stability
- [ ] entry launches headless with zero traceback in the first 60 s
- [ ] no repeated warnings (missing asset, failed sound, font fallback)
- [ ] state JSON streams at ≥1 Hz with fps field; fps ≥ 55 under 120 units
- [ ] process exits cleanly on quit; no orphan SDL/audio devices

## 2. Controls (WC3-like bar)
- [ ] left-click select, box select, shift-add, ctrl+1..9 groups, double-click select-all-on-screen
- [ ] right-click move/attack/gather context orders; A attack-move, S stop, H hold
- [ ] Q/W/E/R hero abilities, Esc cancel, Tab selection subgroups
- [ ] camera: edge scroll, WASD, middle-drag, wheel zoom, minimap click/drag
- [ ] build placement ghost + validity feedback; queue with shift; F1 idle worker

## 3. Economy & base
- [ ] worker gather loop gold/lumber round-trips correctly (counts move 10/10)
- [ ] food cap enforced with a readable error (error.ogg, not silent)
- [ ] building costs deducted once; construction progress + build-done.ogg
- [ ] upgrade path Town Hall → Keep unlocks Knight/Ballista; Sanctum unlocks Priest

## 4. Combat & hero
- [ ] unit damage/armor apply per DESIGN.md numbers (spot-check Footman vs Ghoul)
- [ ] melee surface area: 4+ units can engage one target (no body-blocking deadlocks)
- [ ] ranged + projectile hit resolution; death animations + death.ogg
- [ ] hero XP from nearby kills, levels 1–10, ability unlock cadence, altar revive 45 s
- [ ] no unit stuck on cliffs/trees after 60 s (pathing probe via state JSON)

## 5. Fog, vision, time
- [ ] fog: unexplored ≈95 % black, explored-but-not-visible 55 % veil, soft edge
- [ ] vision updates on move; minimap mirrors fog; pings work
- [ ] day/night cycle changes readability but never drops below the luminance floor
- [ ] night torch pools present and do not blow out highlights

## 6. Enemy AI & mission
- [ ] first wave at 4:00, cadence ~2:30, difficulty multipliers verified (0.8/1.0/1.3)
- [ ] AI builds/techs and attacks the player base — not idle in its own half
- [ ] objective text updates; victory on Necropolis destruction; defeat on hall loss
- [ ] result screen shows time, kills, gold, hero level; retry works

## 7. UI / HUD
- [ ] no overlap/clipping at 1600×900 (and 1280×720 letterbox check)
- [ ] command card shows costs + hotkeys; tooltips readable (contrast ≥ 4.5:1)
- [ ] resource bar, selection portrait, subgroup tabs, alert log all legible
- [ ] pause/settings menu reachable; volume sliders move audio (verify by state)

## 8. Audio
- [ ] all contract files present (20 SFX + 3 music) — mimo re-verifies per build
- [ ] click/select/command/gold wired to their actions; no missing-file warnings
- [ ] music: menu ↔ battle crossfade, loop seam inaudible, bed ≤ −18 dBFS RMS
- [ ] SFX never louder than the music bed (spot RMS in a mixed run)

## 9. Art & style (ties to art-coherence notes)
- [ ] Flare units composed with no detached limbs/weapons (per-frame origin check)
- [ ] 8-direction animation plays without popping between frames
- [ ] icon ↔ sprite pairing reads as one family (lift/rim fixes landed)
- [ ] buildings distinct at a glance (beacon test) and anchored to their tile
- [ ] legibility on both grass and ash ground, day and night

## 10. Map
- [ ] `map_audit.py` verdict PASS: 0 unreachable key points, ≥3 crossings,
      fairness ratios in range, build space ≥ 40 tiles/r10
- [ ] fords visible (tint + stepping stones + minimap markers)
- [ ] creep camps reachable and bounty-rewarding

## 11. Release
- [ ] README build/run instructions match reality (mimo dry-runs them cold)
- [ ] pyinstaller binary builds and boots the same build
- [ ] LICENSES-FLARE.md + audio credits present; no third-party code without credit
- [ ] fresh-clone smoke test: clone → run → playable in < 5 minutes
