# map-audit-01 — Ashen Vale structural audit

Generated from the game's own `generate_map()` by mimo. Verdict: **FAIL** (4 findings)

## Checks

| check | value |
|---|---|
| walkable_components | 72 |
| main_component_tiles | 4982 |
| pockets_ge_3_tiles | 11 |
| key_points_total | 12 |
| key_points_unreachable | 1 |
| player_reaches | 11 |
| player_reaches_all | False |
| enemy_reaches | 11 |
| enemy_reaches_all | False |
| ford_clusters | 2 |
| ford_tiles | 108 |
| ramp_clusters | 3 |
| ramp_tiles | 50 |
| total_crossings | 5 |
| path_lengths | {'player->own_mine': 13.0, 'enemy->own_mine': 16.1, 'player->enemy_ramp': 59.4, 'enemy->player_approach': 65.8, 'player->nearest_neutral': 25.8, 'enemy->nearest_neutral': 44.7} |
| home_mine_distance_ratio | 1.24 |
| wood_near_player | 21 |
| wood_near_enemy | 0 |
| clear_tiles_player_r10 | 262 |
| clear_tiles_enemy_r10 | 317 |

## Mines

- (12,62) 12000g — player
- (74,8) 20000g — enemy
- (13,30) 10000g — neutral
- (37,32) 11000g — neutral
- (70,58) 10000g — neutral
- (44,54) 10000g — neutral

## Camps

- Mesa Pack @ (39,32) — 4 units
- Thornwood Pack @ (74,63) — 3 units
- Westford Pack @ (13,27) — 2 units
- Crossroads Pack @ (48,58) — 2 units

## Findings

- POCKET: 11 walkable region(s) of >=3 tiles are unreachable from the main map — sizes [20, 14, 13, 12, 9, 6, 5, 3], e.g. at [(16, 15), (23, 17), (17, 26), (21, 27), (10, 13), (42, 20), (10, 10), (13, 15)]
- BLOCKER: key points not reachable: ['camp:Thornwood Pack']
- player base cannot reach: ['camp:Thornwood Pack']
- enemy base cannot reach: ['camp:Thornwood Pack']
