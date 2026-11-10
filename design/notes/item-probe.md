# item / shop probe

`tools/item_probe.py` — 23/23 PASS, headless, driving the real UI hit-test path (shop key, tile clicks, satchel clicks, ground targeting).

| check | result | detail |
|---|---|---|
| probe boots into a playable mission | **PASS** | state=play hero=hero |
| P opens the purveyor | **PASS** | open=True |
| every shop tile is on screen | **PASS** | 15/15 tiles |
| buy Ashwood Blade: gold and satchel | **PASS** | gold=3960 items=['blade'] |
| buy Ashwood Blade: +8 damage applied | **PASS** | dmg (26, 32)->(34, 40) |
| buying the same item twice is refused | **PASS** |  |
| buy Whetstone | **PASS** | gold=3680 items=['blade', 'whet'] |
| forge Ember Warbrand consumes both parts | **PASS** | gold=3560 items=['warbrand'] |
| Ember Warbrand gives +18 damage and +20% attack speed | **PASS** | dmg (26, 32)->(44, 50) cd 1.450->1.208 |
| forging out of parts is refused | **PASS** |  |
| out of shop range: purchase refused | **PASS** | gold=3560 items=['warbrand'] |
| right-click sells for 50% of the tree | **PASS** | gold=3560->3880 (expected +320) |
| selling restores the stats | **PASS** | dmg=26 cd=1.450 |
| forge Ashen Step | **PASS** | items=['ashenstep'] |
| Ashen Step gives +10% move speed | **PASS** | speed 2.60->2.86 |
| clicking an active item starts ground targeting | **PASS** | targeting={'item': 0, 'iid': 'ashenstep', 'range': 6.0} |
| Ashen Step blinks the hero onto the clicked tile | **PASS** | moved 5.88 tiles, cd=16.0s |
| Ashen Step is refused while cooling down | **PASS** | cd=15.9s, position unchanged |
| forge Ember Flask from tonic + greaves | **PASS** | items=['ashenstep', 'flask'] |
| Ember Flask heals over its duration | **PASS** | hp 590 -> 590 (cast) -> 900 (6.5s later) |
| Ember Flask goes on cooldown | **PASS** | cd=39s |
| hero revives with level, growth and satchel intact | **PASS** | level 5->5, items=['ashenstep', 'flask'], dmg 38.800000000000004->38.800000000000004 |
| qa_state exposes items / stats / shop reach | **PASS** | items=['ashenstep', 'flask'] shop=True |

## Item economy as implemented

| item | tier | parts | forge fee | full tree | sells for | stats |
|---|---|---|---|---|---|---|
| Ashwood Blade | 1 | — | 240g | 240g | 120g | dmg 8 |
| Iron Buckler | 1 | — | 220g | 220g | 110g | armor 3 |
| Ember Tonic | 1 | — | 260g | 260g | 130g | hp 160 |
| Kindled Focus | 1 | — | 240g | 240g | 120g | mana 90, mana_regen 0.8 |
| Trail Greaves | 1 | — | 210g | 210g | 105g | move 0.08 |
| Whetstone | 1 | — | 280g | 280g | 140g | aspeed 0.12 |
| Ember Warbrand | 2 | blade + whet | 120g | 640g | 320g | dmg 18, aspeed 0.2 |
| Ashen Bulwark | 2 | buckler + tonic | 150g | 630g | 315g | armor 6, hp 300 |
| Cinder Plate | 2 | blade + buckler | 130g | 590g | 295g | dmg 14, armor 6 |
| Pyre Heart | 2 | tonic + focus | 150g | 650g | 325g | hp 350, mana 150, hp_regen 2.2 |
| Windstep Boots | 2 | greaves + whet | 140g | 630g | 315g | move 0.15, aspeed 0.22 |
| Ashen Step | 2 | greaves + focus | 180g | 630g | 315g | move 0.1, mana 70 |
| Ember Flask | 2 | tonic + greaves | 150g | 620g | 310g | hp 140, hp_regen 1.5 |
| Marshal's Regalia | 3 | cinder + pyre | 400g | 1640g | 820g | dmg 20, armor 9, hp 450, mana 180, hp_regen 1.2 |
| Warsong Talisman | 3 | warbrand + windstep | 380g | 1650g | 825g | dmg 26, aspeed 0.32, move 0.14 |
