# Pacing evidence 01 — where the boredom lives (activity suite / p-c4f1a9e2)

Snapshot: `git archive HEAD | tar -x -C .pacing_scratch/base` @ **7ac2a7b55e239250d1b4c9ec3938641880957085**
(HEAD at snapshot time; the parallel agent has since committed 7130b1c + b9a857e — those were NOT measured.)
("Final consolidated campaign probe…"). All runs execute from that snapshot
(`sys.modules['emberfall'].__file__` verified inside `.pacing_scratch/base/emberfall/`);
the live tree, edited in parallel, was never run. Headless always:
`SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`.

## Method

Boot check (exit 0, no errors):
```
cd .pacing_scratch/base
<repo>/.venv/bin/python -m emberfall.main --qa --scene base --frames 60 --autoplay --speed 6
```
(repo-root `main.py` is the BROKER entry, not the game — the game is `python -m emberfall.main`.)
Measurement (harness `.pacing_scratch/pacing_run.py`, scratch-only, deleted with the snapshot):
```
cd .pacing_scratch/base
for r in m1 m3 m5 m9 sk_knight sk_warlord; do
  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy <repo>/.venv/bin/python ../pacing_run.py --run $r
done
```
Per run: `Game(Namespace(autoplay=True, speed=6, qa=False, ...))`, then
`start_mission(scenario=campaign.scenario(i), skip_intro=True)` (m1=i0, m3=i2, m5=i4,
m9=i8) or `start_mission(difficulty=<tier>, skip_intro=True)` (scenario=None) for classic
Ashen Vale. Step `g.update(1/60)` until outcome; caps 1800 game-s / 300 wall-s never
reached (all six ended at 316–565 game-s, 7–110 wall-s). Campaign save isolated via
`EMBERFALL_SAVE_PATH` in the scratch dir; nothing in the repo was written.
Sampled every frame: Necropolis HP (first damage, 30s timeline, per-150s damage), waves,
kills/losses, building completions, hero deaths, army size (15s), army order signature
(uid→order, compared only across units alive in both frames so a death can't fake a
change).

**Idle gap (spec definition)** = max gap between: army order changes, kills, buildings
completing, waves (0s and run-end are boundaries). **Strict gap** = same minus order
changes. Strict is reported because order changes here are dominated by autoplay's own
25s re-push (`auto_push_t = t+25` re-targets drifted units — m1's order events land at
127.6/152.7/177.8/… exactly 25.1s apart), i.e. bot housekeeping, not content.

## Results

| run | tier | outcome | t→first necro dmg | t→outcome | longest idle gap | strict gap | waves | hero deaths |
|---|---|---|---|---|---|---|---|---|
| m1 The First Ember | novice | **victory** | 110.5s | 545.3s | 36.5s (0→36) | **107.4s (392→500)** | 0 (first_wave=720 never fires) | 3 |
| m3 The Sunken Chapel | squire | defeat | 119.2s | 564.7s | 72.0s (493→565) | **183.8s (131→315)** | 1 @315.1 | 4 |
| m5 The Ashen Fields | squire | defeat | 137.0s | 563.4s | 56.2s (499→556) | **153.3s (162→315)** | 1 @315.1 | 4 |
| m9 The Hollow Crown | warlord | defeat | 143.2s | 326.6s | 77.3s (249→327) | 91.5s (235→327) | 1 @235.1 | 2 |
| sk Ashen Vale knight | knight | defeat | 106.8s | 528.6s | 75.6s (353→429) | **172.7s (92→265)** | 2 @275.1, 450.1 | 4 |
| sk Ashen Vale warlord | warlord | defeat | 106.8s | 316.1s | 57.6s (258→316) | 142.7s (92→235) | 1 @235.1 | 3 |

Necropolis progress over whole run: m1 3200→0 (broken); m3 648/4600 = **14%**; m5 758/5400
= **14%**; m9 82/7200 = **1%**; sk_knight 213/5200 = **4%**; sk_warlord 120/5200 = **2%**.
Zero-army seconds (no player combat unit alive): m1 0s, m3 **119s**, m5 30s, m9 36s,
sk_knight **126s**, sk_warlord 37s.

## Timeline buckets — 2 most damning runs (150s buckets: kills / necro-dmg / activity)

**sk_knight (defeat, 528.6s)** — objective untouched for 6 straight minutes:
```
  0-150  0/212/12  army 4→6, arrival 103s, first dmg 106.8s, army wiped by 135s
150-300  0/  0/23  army 1-3, wave#1 275s  <<< NO necro damage at all
300-450  1/  0/14  army 1-3 but ZERO at 375-420; wave#2 450s <<< still NO necro damage
450-600  0/  0/ 3  army 0 from 465s to end <<< nothing happens
necro flat 150→510s (360s, 4987/5200 held); strict no-event window 92.4→265.1s (173s)
```
**m3 (defeat, 564.7s)** — the pre-wave vacuum, then a trickle:
```
  0-150  0/441/12  arrival 115.7s, first dmg 119.2s, early trades
150-300  0/ 52/10  <<< 184s with zero kill/build/wave (131→315s)
300-450  2/  0/14  wave#1 lands 315.1s, then NO necro damage (flat 300→450s)
450-600  1/153/ 9  hall falls; strict gap 493→565s (72s) to end; zero-army 119s; 86% HP left
```

## Diagnosis — where the boredom lives

1. **The grind, not the walk.** Time-to-first-necro-damage is 107–143s in *every* run —
   the approach/setup phase is fine. What follows is the problem: m1, the easiest mission
   with the *smallest* Necropolis in the game (3200 HP), takes **435s (7m15s) of continuous
   siege from first hit to break** (545.3s total = **9m05s** for one mission). That already
   matches the human's "wait 10minute for necropolis to break".
2. **That rate does not scale to later HP pools.** Best observed sustained siege DPS is
   m1's **7.35 HP/s** (3197 damage / 435s). At that rate — assuming the army survives,
   which it doesn't — 4600 HP = 10m26s, 5400 HP = 12m15s, 7200 HP = 16m20s of sieging
   *after* the 2-minute approach. Actual squire/warlord effective DPS was 0.45–1.78 HP/s,
   because…
3. **…the push evaporates and then nothing happens.** The army reaches the Necropolis,
   trades ~40s, dies (sk_knight 6→1 units by t=135s), and leaves a vacuum: **126s with
   zero army** (sk_knight) / **119s** (m3), during which the Necropolis takes **zero**
   damage for **360s (sk_knight)** and **150s (m3)**. Between broken push #1 and any
   re-engagement: no kill, no build, no wave for **173s (sk_knight)** / **184s (m3)**.
4. **The pre-wave dead zone is scheduled, not accidental.** squire `first_wave=315` puts
   a hard 5m15s of nothing incoming — m3's 131→315s and m5's 162→315s strict gaps end
   *exactly* at the wave timestamp. And m1's `first_wave=720` exceeds its 545s finish:
   **the first mission ships zero waves in nine minutes** — the only events on screen are
   the player's own siege and the bot's periodic re-push.
5. **Caveat on the spec gap column:** the 36–77s "idle gap" numbers are held down by
   autoplay's own 25s re-push cycle; they measure bot cadence, not content. The strict
   column (92–184s with no kill/build/wave) is the honest boredom figure, and it is a
   lower bound — a human watching an untouched Necropolis for 6 minutes (sk_knight) is
   not counted idle if his units twitch.

## Knobs — FOR MIMO'S BALANCE LANE (reversible; nothing implemented here)

1. **Necropolis HP trim per mission** — *motivation:* 3200 HP already costs 7m15s at the
   best observed 7.35 HP/s; 5400/7200 project to 12m15s/16m20s of siege. *Risk:* cut too
   far and the base assault ends before wave 2, killing the finale's tension — keep m1's
   3200 as the floor, trim the 4600+ pools (content lives in `campaign.SCENARIOS.necro_hp`).
2. **First-wave cadence** — *motivation:* squire `first_wave=315` produced the 184s (m3)
   and 153s (m5) pre-wave vacuums; novice `first_wave=720` > m1's 545s finish = **0 waves
   in mission 1**. *Risk:* pulling squire's wave earlier punishes the learning phase, and
   m1's lore promises "no real threat for twelve minutes" — for m1, prefer an activity
   event over a wave (coordinate with deepseek's suite, don't contradict the blurb).
3. **Siege damage vs buildings / defender uptime at the crown** — *motivation:* effective
   siege DPS collapses from 7.35 (m1) to 0.45–1.78 HP/s (tiers 3+); the Host wipes each
   arriving army in ~40s and then the objective is safe for 150–360s. *Risk:* weakening
   base defense turns the finale into a formality; alternatively trim the *first* defender
   response only, leaving waves intact.
4. **Earlier/faster reinforcement so a broken push re-forms** — *motivation:* 119–126s
   zero-army windows (m3, sk_knight) where the 173–184s strict gaps sit; the player has
   literally nothing on the field to act with. *Risk:* faster barracks rally/train times
   inflate eco pressure and can snowball — change train cadence, not unit cost.
5. **Pacing budget as a testable target: no >90s window without a kill/wave/build/event**
   — *motivation:* worst measured strict windows across all six runs: 184 / 173 / 153 /
   143 / 107 / 91s. *Risk:* satisfiable by events alone only if knob 1 also moves —
   otherwise the Necropolis grind remains and events become skippable filler.

## What the activity suite (built in parallel) will and will not fix

**WILL:** fill the measured dead windows — the strict 92–184s no-event gaps, the 119–126s
zero-army vacuums, and the pre-wave stretches (m3 131→315s, m5 162→315s, m1 235→341s).
Farms/camps/secret shop/timed events give the human something to *do* while macro builds
and armies rebuild. That directly addresses the "boring" half of the complaint.
**WILL NOT:** shorten the Necropolis grind — not m1's 435s siege, not the 12–16 minute
projections for 5400/7200 HP, not the 86–99% HP left standing at defeat. Objective pacing
is knobs 1/3 (balance lane), not content. Nor can events fill a window in which the player
has **no army at all** (119–126s measured) — that part needs knob 4.

## Honest limits

- Autoplay is a scripted bot (no retreat/formation): it wins only m1, so **time-to-victory
  is measurable for m1 alone**; the other rows are time-to-defeat. Absolute times are
  indicative for a human; the *structure* (arrival ~2min, then grind/vacuum) is what these
  runs establish. Hero deaths (2–4/run) are largely bot artifacts (no disengage logic).
- Variance: none found — seeded `Rng` (world seed, AI `Random(4242)`); **two full passes over
  all six runs were byte-identical** on outcome/time/damage/kills/idle-gap, so the "2 runs
  where variance is high" rule matched no run.
- Gaps sampled per frame (0.1 game-s at speed 6). Headless: no render/audio/fps (not asked).
  This harness wrote only scratch JSONs + this file. (`campaign-probe-01.json` changed in
  the live tree mid-session at 10:49 — a `--no-win` campaign_probe run by the parallel
  agent; its only writer is `tools/campaign_probe.py`, which I never invoked.)
