# qa-input-01 — controls probe (play scene)

**5 FAIL / 16 checks** — synthetic pygame events driven through the engine's own `handle_event`.

| control | result | detail |
|---|---|---|
| camera: held D / right-arrow pan | FAIL | camera.x 1324 -> 1324 |
| camera: clamp stays in world | PASS | x=1724 |
| setup: units exist to click | PASS | 16 candidates |
| select: left-click a unit | FAIL | click (1292,1723) -> 0 selected |
| select: box select | PASS | box -> 16 selected |
| select: shift-add | PASS | 16 -> 16 |
| select: ctrl+1 group then 1 recall | FAIL | group stored=False, recalled=0 |
| order: right-click move | FAIL | unit moved 0.00 tiles |
| hotkey: A arms attack-move, Esc cancels | PASS | True -> False |
| hotkey: S (stop) handled without error | PASS | no exception |
| hotkey: SPACE selects hero | PASS | selection=1 |
| hotkey: F1 idle worker | PASS | selection=1 |
| hotkey: O toggles objectives | PASS | False -> True |
| hotkey: Esc pause/unpause | PASS | play -> play |
| minimap: click repositions camera | PASS | camera moved 2936px |
| build: B arms placement, Esc cancels | FAIL | placement=False |
