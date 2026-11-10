# ability probe

`tools/ability_probe.py` — 15/15 PASS, headless, through the real targeting path (`handle_action` + `cast_at`).

| check | result | detail |
|---|---|---|
| scene has allies to stand in the blast | **PASS** | 18 allies |
| Daybreak with allies in radius does not crash | **PASS** | clean cast |
| Daybreak spends 140 mana and goes on a 90s cooldown | **PASS** | mana 220->80, cd=90s |
| Daybreak does not heal allies (it only stuns and burns) | **PASS** | allies at or below max hp |
| Daybreak damages and stuns the enemy in radius | **PASS** | hp 192->0, stun=2.0s |
| reported path (select, R, ground click) casts Daybreak without a crash | **PASS** | armed=True cd=90s state=playing |
| Consecrate heals the ally inside the fire | **PASS** | ally hp 110->220 |
| Consecrate spends 70 mana and goes on cooldown | **PASS** | mana 220->150, cd=12s |
| Ember Lance on empty ground is refused (no mana, no cooldown) | **PASS** | mana 220->220 |
| Ember Lance hits and stuns a target in range | **PASS** | hp 192->0, stun=1.2s |
| Ember Lance refuses an out-of-range target | **PASS** | hp 192->192 |
| Aegis shields the hero for 8s | **PASS** | shield=440 for 8.0s |
| Aegis charges its cooldown after use | **PASS** | cd=16s |
| An ability with no mana is refused, not cast | **PASS** | mana=5 |
| the game is still running after all casts | **PASS** | state=playing |

Regression: Daybreak raised `KeyError: 'heal'` whenever an ally stood inside its radius — the AoE branch healed every ally unconditionally, but `defs.ABILITIES['daybreak']` has no `heal` key. Same class of bug guarded for `stun` and `shield`, so an ability without them can no longer take the game down.
