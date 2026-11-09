# release-check — 2026-11-09 02:35:41

**3 FAIL / 4 WARN / 43 checks**

| check | status | detail |
|---|---|---|
| audio:sfx/click | PASS | vorbis,44100,1 |
| audio:sfx/select | PASS | vorbis,44100,1 |
| audio:sfx/command | PASS | vorbis,44100,1 |
| audio:sfx/error | PASS | vorbis,44100,1 |
| audio:sfx/sword | PASS | vorbis,44100,1 |
| audio:sfx/bow | PASS | vorbis,44100,1 |
| audio:sfx/magic | PASS | vorbis,44100,1 |
| audio:sfx/holy | PASS | vorbis,44100,1 |
| audio:sfx/build | PASS | vorbis,44100,1 |
| audio:sfx/build-done | PASS | vorbis,44100,1 |
| audio:sfx/gold | PASS | vorbis,44100,1 |
| audio:sfx/chop | PASS | vorbis,44100,1 |
| audio:sfx/death | PASS | vorbis,44100,1 |
| audio:sfx/level-up | PASS | vorbis,44100,1 |
| audio:sfx/alert | PASS | vorbis,44100,1 |
| audio:sfx/horn | PASS | vorbis,44100,1 |
| audio:sfx/explosion | PASS | vorbis,44100,1 |
| audio:sfx/roar | PASS | vorbis,44100,1 |
| audio:sfx/victory | PASS | vorbis,44100,1 |
| audio:sfx/defeat | PASS | vorbis,44100,1 |
| audio:music/menu | PASS | 72.0s (want 60-90s) |
| audio:music/battle | PASS | 114.3s (want 90-120s) |
| audio:music/night | PASS | 72.0s (want 60-90s) |
| audio:SDL load | PASS | 23 files load |
| icons:svg contract | PASS | all present |
| icons:png runtime | PASS | all present |
| art:flare buildings | PASS | 14 sprites (want >=14) |
| doc:design/notes/flare-buildings.md | PASS | 22 lines |
| doc:LICENSES-FLARE.md | PASS | 41 lines |
| doc:design/notes/flare-import.md | PASS | 522 lines |
| license:flare | PASS | attribution complete |
| doc:design/DESIGN.md | PASS | present |
| doc:design/COLLAB.md | PASS | present |
| doc:design/ASSET-CONTRACT.md | PASS | present |
| doc:collaboration.md | PASS | present |
| doc:README run instructions | FAIL | still the broker README — no game run instructions |
| map:audit | FAIL | FAIL: 4 findings |
| map:finding | WARN | POCKET: 11 walkable region(s) of >=3 tiles are unreachable from the main map — sizes [20, 14, 13, 12, 9, 6, 5, 3], e.g. at [(16, 15), (23, 17), (17, 26), (21, 27), (10, 13), (42, 20), (10, 10), (13, 15)] |
| map:finding | FAIL | BLOCKER: key points not reachable: ['camp:Thornwood Warren'] |
| map:finding | WARN | player base cannot reach: ['camp:Thornwood Warren'] |
| map:finding | WARN | enemy base cannot reach: ['camp:Thornwood Warren'] |
| boot:headless | PASS | alive 25s, rc=0 |
| boot:state stream | WARN | 0 state lines |

