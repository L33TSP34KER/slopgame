# qa-input-01 — controls probe (play scene)

**0 FAIL / 19 checks** — synthetic pygame events driven through the engine's own `handle_event` / `update` paths (headless, no xdotool).

| control | result | detail |
|---|---|---|
| camera: held D / right-arrow pan | PASS | camera.x 1324 -> 1831 |
| camera: clamp stays in world | PASS | x=2231 |
| setup: units exist to click | PASS | 16 candidates |
| coords: unit projects on-screen | PASS | screen=(800,450) |
| select: left-click a unit | PASS | click (800,450) -> 1 selected |
| select: box select | PASS | 12 selected |
| select: shift-add | PASS | 12 -> 13 |
| select: ctrl+1 store, 1 recall | PASS | stored=True recalled=3 |
| order: right-click issues move | PASS | order=dict moved=7.01 tiles |
| order: unit actually walks there | PASS | moved 7.01 tiles of ~8.6 requested (target screen 947,592) |
| hotkey: A arms attack-move, Esc cancels | PASS | armed=True |
| hotkey: S stop handled | PASS | no exception |
| hotkey: SPACE selects hero | PASS | selection=1 |
| hotkey: F1 idle worker | PASS | selection=1 |
| build: B opens build menu, Esc cancels | PASS | menu=True placement=True after_esc=False |
| build: place a structure on clear ground | PASS | action=build_farm spot=(22, 69) in_progress=1 buildings 4->5 |
| hotkey: O toggles objectives | PASS | False -> False |
| hotkey: Esc pause/unpause | PASS | paused=True |
| minimap: click repositions camera | PASS | moved 2941px |

Re-run: `.venv/bin/python tools/qa/input_probe.py`
