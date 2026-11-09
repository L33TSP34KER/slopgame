# feature-audit-01 — DESIGN.md promises vs build

**0 GAP / 0 PARTIAL / 31 checks** — static + dynamic audit by mimo.

| feature | status | evidence |
|---|---|---|
| buildings: 9 Emberhold | PASS | missing none |
| buildings: 6 Hollow Host | PASS | missing none (roster total 16) |
| units: 6 player + hero + 6 enemy + boss | PASS | missing none (roster total 16: extras ['goblin', 'goblin-brute']) |
| hero abilities Q/W/E/R | PASS | ABILITIES keys: ['aegis', 'consecrate', 'daybreak', 'ember-lance'] |
| blacksmith / keep upgrades | PASS | UPGRADES keys: ['armor1', 'armor2', 'weapons1', 'weapons2'] |
| difficulties squire/knight/warlord | PASS | ['knight', 'squire', 'warlord'] |
| fog of war (explored + visible states) | PASS | evidence in render.py |
| day/night cycle | PASS | evidence in world/render |
| minimap with fog + camera rect | PASS | evidence in ui.py |
| box select + shift add | PASS | evidence in app.py |
| control groups ctrl+1..9 | PASS | evidence in app.py |
| attack-move / stop / hold hotkeys | PASS | evidence in app.py/ui.py |
| build placement ghost + validity | PASS | evidence in app.py/world |
| camera: WASD + edge + middle-drag + wheel zoom | PASS | evidence in app.py |
| idle worker F1 / objectives O / pause Esc | PASS | evidence in app.py |
| subgroup tabs (Tab) | PASS | evidence in app.py/ui.py |
| victory + defeat screens with stats | PASS | evidence in app |
| objective panel + bonus objective | PASS | evidence in defs/ui |
| alerts (under attack / low resources) | PASS | evidence in ui/world |
| settings: music/sfx volume | PASS | evidence in ui/audio |
| title menu: campaign/skirmish/controls/credits/quit | PASS | evidence in ui.py |
| enemy AI wave scheduler | PASS | evidence in ai/world |
| creep camps + bounty | PASS | evidence in world/mapgen |
| hero XP + levels + altar revive | PASS | evidence in defs/world |
| gather loop (gold + lumber round trip) | PASS | evidence in world/app |
| in-game credits mention Flare attribution | PASS | evidence in ui/credits |
| audio: 20 contracted SFX present | PASS | 20 files |
| audio: 3 music loops present | PASS | ['battle', 'menu', 'night'] |
| audio: SFX referenced by the game code | PASS | 20/20 referenced |
| audio: music tracks referenced | PASS | ['battle', 'menu'] |
| copy: my lore pack wired into the game | PASS | found 3/3 signature lines in engine |

## Gaps to close before release

- none
