# map-audit-01 — Ashen Vale structural audit

Generated from the game's own `generate_map()` by mimo. Verdict: **PASS** (0 findings)

## Checks

| check | value |
|---|---|
| walkable_components | 1 |
| main_component_tiles | 4126 |
| pockets_ge_3_tiles | 0 |
| key_points_total | 12 |
| key_points_unreachable | 0 |
| player_reaches | 12 |
| player_reaches_all | True |
| enemy_reaches | 12 |
| enemy_reaches_all | True |
| ford_clusters | 2 |
| ford_tiles | 108 |
| ramp_clusters | 3 |
| ramp_tiles | 50 |
| total_crossings | 5 |
| path_lengths | {'player->own_mine': 13.9, 'enemy->own_mine': 17.3, 'player->enemy_ramp': 62.8, 'enemy->player_approach': 69.8, 'player->nearest_neutral': 27.2, 'enemy->nearest_neutral': 47.8} |
| home_mine_distance_ratio | 1.24 |
| wood_near_player | 21 |
| wood_near_enemy | 0 |
| clear_tiles_player_r10 | 217 |
| clear_tiles_enemy_r10 | 317 |

## Mines

- (12,62) 12000g — player
- (74,8) 20000g — enemy
- (13,30) 10000g — neutral
- (37,32) 11000g — neutral
- (70,58) 10000g — neutral
- (44,54) 10000g — neutral

## Camps

- Mesa Warren @ (39,32) — 4 units
- Thornwood Warren @ (74,63) — 3 units
- Westford Warren @ (13,27) — 2 units
- Crossroads Warren @ (48,58) — 2 units

## Findings

- none — structure is sound
