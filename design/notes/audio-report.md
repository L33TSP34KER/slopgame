# EMBERFALL — The Hollow Crown · Audio Pack Verification Report

**Scope:** `assets/audio/sfx/*.ogg` (20 files) + `assets/audio/music/*.ogg` (3 loops) — 23 files total.
**Provenance:** every sample is synthesized from scratch in Python 3.14 (numpy 2.5.1 + scipy 1.18.1) by the
generators in `assets/audio/_gen/` (`dsp.py` toolkit, `gen_sfx.py`, `gen_music.py`, `verify.py`). No downloaded,
sampled or third-party audio of any kind. 24-bit temp WAV (stdlib `wave`) → `ffmpeg -c:a libvorbis -q:a 6` → `.ogg`.
**Date:** verification run on the shipped files; exit code 0 (`python3 assets/audio/_gen/verify.py` → `ALL FILES PASS`).

---

## Musical direction

**Embers, bone and cold steel.** Everything sits in D minor so the whole pack speaks one language. The menu bed is
"embers dying": a solo cello plays short, low phrases in D minor separated by real silence, over a bed of pink-noise
hearth rumble and several hundred individually placed ember crackles, while a single warm Dm(add9) choir chord
(D2–D3–F3–A3–E4) swells for twenty seconds and never resolves — it simply lets go. The battle bed is "the dead army
marching": an 84 BPM heartbeat pulse (deep bone/tom on 1 and 2, ghost on 2 and 4, dry bone rattle on the off-beats)
underpins short male-choir "hah" stabs and a low choir drone, with cold, still string pads entering over an
8-bar Dm–Dm–Bb–F–Gm–Gm–Bb–A progression and a violin line that returns an octave higher on the second pass; the
arrangement is a real arc (bars 0–2 choir bed only → sparse half-time hits → full pulse + swells → full ensemble
bars 24–33 → decrescendo → sparse again), so the loop point lands back at its own starting level. Night is a quiet
vale: decorrelated wind layers breathing on integer-cycle LFOs, distant water, nine sparse cricket chirps and one
far-off bell tolling through a long outdoor reverb. SFX follow four timbral families — UI is dry wood
(modal block/knock/parchment), combat is metallic-plus-fleshy with a real transient, magic is airy (staggered
band-passed noise sweeps + shimmer), economy is bright and granular (coin grains, hammer, chime) — with modal
synthesis, Karplus-Strong (bowstring), formant-shaped brass/horn/choir voices and short convolution reverb on
every event.

---

## Verification table (all 23 shipped files)

| file | dur (s) | ch | peak dBFS | true peak dBTP | RMS dBFS | DC | LUFS | mono peak/RMS | result |
|---|---|---|---|---|---|---|---|---|---|
| sfx/alert.ogg | 1.480 | 1 | -7.00 | -7.00 | -16.46 | -0.00001 | -17.7 |  | PASS |
| sfx/bow.ogg | 0.900 | 1 | -6.77 | -6.75 | -18.96 | +0.00001 | -18.1 |  | PASS |
| sfx/build-done.ogg | 1.120 | 1 | -8.00 | -7.98 | -18.96 | +0.00001 | -18.0 |  | PASS |
| sfx/build.ogg | 0.450 | 1 | -6.72 | -6.72 | -19.45 | -0.00005 | -19.4 |  | PASS |
| sfx/chop.ogg | 0.500 | 1 | -6.44 | -6.39 | -18.69 | -0.00003 | -19.9 |  | PASS |
| sfx/click.ogg | 0.180 | 1 | -7.43 | -7.40 | -20.89 | -0.00008 | -inf¹ |  | PASS |
| sfx/command.ogg | 0.550 | 1 | -7.18 | -7.17 | -18.92 | +0.00008 | -19.5 |  | PASS |
| sfx/death.ogg | 0.950 | 1 | -7.20 | -7.20 | -18.94 | -0.00006 | -18.9 |  | PASS |
| sfx/defeat.ogg | 4.000 | 1 | -7.97 | -7.97 | -16.46 | -0.00002 | -17.5 |  | PASS |
| sfx/error.ogg | 0.520 | 1 | -6.99 | -6.99 | -19.42 | -0.00001 | -20.6 |  | PASS |
| sfx/explosion.ogg | 1.050 | 1 | -6.97 | -6.27 | -19.54 | +0.00008 | -19.6 |  | PASS |
| sfx/gold.ogg | 0.750 | 1 | -7.61 | -7.49 | -19.49 | +0.00000 | -16.2 |  | PASS |
| sfx/holy.ogg | 1.120 | 1 | -8.85 | -8.85 | -18.47 | +0.00001 | -18.4 |  | PASS |
| sfx/horn.ogg | 2.480 | 1 | -7.00 | -7.00 | -16.97 | +0.00010 | -18.4 |  | PASS |
| sfx/level-up.ogg | 1.480 | 1 | -8.04 | -8.03 | -16.45 | +0.00001 | -16.5 |  | PASS |
| sfx/magic.ogg | 1.020 | 1 | -7.95 | -7.93 | -18.49 | -0.00001 | -17.2 |  | PASS |
| sfx/roar.ogg | 1.980 | 1 | -7.14 | -7.14 | -17.04 | -0.00016 | -17.5 |  | PASS |
| sfx/select.ogg | 0.420 | 1 | -6.82 | -6.79 | -19.50 | +0.00003 | -16.9 |  | PASS |
| sfx/sword.ogg | 0.750 | 1 | -6.45 | -6.45 | -18.44 | -0.00005 | -16.8 |  | PASS |
| sfx/victory.ogg | 4.000 | 1 | -6.80 | -6.66 | -16.48 | +0.00006 | -17.4 |  | PASS |
| music/battle.ogg | 114.286 | 2 | -7.10 | -7.10 | -21.55 | -0.00000 | -20.3 | -4.32/-18.60 | PASS |
| music/menu.ogg | 72.000 | 2 | -8.31 | -8.31 | -21.39 | +0.00004 | -17.9 | -6.18/-18.61 | PASS |
| music/night.ogg | 72.000 | 2 | -4.30 | -4.30 | -19.52 | -0.00001 | -16.4 | -1.49/-18.68 | PASS |

¹ `click.ogg` is 180 ms; EBU R128 gating needs ~400 ms blocks, so `loudnorm` reports `input_i = -inf`
(measurement limitation, not silence — RMS -20.89 dBFS confirms content).

**Contract checks:** codec = vorbis on all 23 · sample rate 44100 · SFX mono / music stereo · every SFX ≤ 1.2 s
except the noted ones (level-up 1.48, alert 1.48, horn 2.48, explosion 1.05, roar 1.98, victory 4.00, defeat 4.00)
· music 60–90 s (menu, night) and 90–120 s (battle) · SFX peak ≤ -6 dBFS (worst true peak **-6.27**) ·
music true peak ≤ -1 dBFS (worst native **-4.30**, worst mono-downmix **-1.49**) · music bed ≤ -18 dBFS
(**-18.60 … -18.68** as measured by `tools/qa/audio_review.py`) · no file below the -45 dBFS RMS floor ·
|DC| ≤ 0.002 on every file (worst |0.00016|).

**Loudness spread:** in-game SFX family (stingers excluded) **2.45 dB** (-20.89 … -18.44); whole pack
**5.10 dB** (-21.55 … -16.45, the top end being the four stingers, which are meant to sit above gameplay).
On the QA tool's mono-downmix basis (where music reads -18.6 rather than -19.5…-21.6) the pack spread is
**4.44 dB** (-20.89 … -16.45), down from the 8.56 dB the previous review measured.
Stingers: level-up -16.45, defeat -16.46, alert -16.46, victory -16.48, horn -16.97, roar -17.04.

---

## Loop continuity (wrap-around discontinuity per music file)

Loops are rendered periodic by construction: every event is placed with modulo wrap-around, all mix-bus filtering
is FFT-domain (circular) and the reverb is circular convolution, so the tail of the file is literally the head of
the next pass. The numbers below are measured on the **decoded OGG**.

| loop | wrap step (max sample delta) | interior p99.9 diff | interior p99.99 diff | step vs p99.99 | 20 ms wrap-crossfade max delta | 50 ms wrap-crossfade max delta | verdict |
|---|---|---|---|---|---|---|---|
| battle.ogg | **0.001301** | 0.050234 | 0.059895 | 2.2 % | 0.005053 | 0.005287 | seamless |
| menu.ogg | **0.002181** | 0.057013 | 0.087501 | 2.5 % | 0.003471 | 0.017885 | seamless |
| night.ogg | **0.029268** | 0.173704 | 0.268738 | 10.9 % | 0.088823 | 0.085501 | seamless |

*wrap step* = max `|x[0] − x[N−1]|` across the loop point (both channels). *interior p99.9 / p99.99* = the
99.9th/99.99th percentile of ordinary sample-to-sample differences inside the file, i.e. the natural motion of the
material — the wrap step is judged seamless when it is at or below that scale. *wrap-crossfade max delta* = the
largest sample delta inside a wrap-around crossfade that blends the last N ms with the first N ms (plus both of
that blend's edges), which is exactly what a looping player performs. night.ogg's larger absolute numbers are the
wind bed being noise: its wrap step is still 5.9× smaller than its own typical sample-to-sample motion, so the
junction is indistinguishable from the noise floor.

---

## Quality gate (what was actually run)

1. **ffprobe** on every file — codec `vorbis`, 44100 Hz, 1 or 2 channels, duration inside the contract window.
2. **Decode + measure** — sample peak and RMS from decoded `f32` PCM; true peak and integrated loudness from
   `ffmpeg -af loudnorm=print_format=json`; DC offset as the mean of decoded samples. Gain is found by bisecting
   through the *final* chain (gain → 20 Hz high-pass → soft limiter → mean removal → edge fades) so the shipped
   file's measured RMS hits its target while the ceiling is guaranteed; each encode is then re-measured and
   re-scaled until **true** peak (not just sample peak) is inside spec — that loop is what caught the
   inter-sample overshoots on `explosion`/`chop`/`sword`.
3. **Loop check** — decode each music file to PCM, take the first/last 20 ms and 50 ms, build the wrap-around
   crossfade, and compare every delta against the interior distribution (table above).
4. **Silence / length** — RMS floor -45 dBFS, no file longer than its spec.
5. **Loader check** — all 23 files load through the game's actual loader
   (`pygame-ce 2.5.8` / `SDL_mixer`, `SDL_AUDIODRIVER=dummy`) and report the expected lengths.

Re-run at any time:

```bash
python3 assets/audio/_gen/verify.py          # tables + gates, exit 0 = pass
python3 assets/audio/_gen/gen_sfx.py         # re-synthesize the 20 SFX
python3 assets/audio/_gen/gen_music.py       # re-synthesize the 3 loops (~4 min)
```

---

## Measurement notes / trade-offs

* **Mono vs stereo basis.** `tools/qa/audio_review.py` measures an `ffmpeg -ac 1` downmix (0.707/0.707), which
  reads **+0.8 … +3.0 dB** above the native stereo RMS depending on L/R correlation (menu +2.79, battle +2.95,
  night +0.84). The two readings of "music bed ≤ -18 dBFS" cannot both be satisfied at once, so the pack is
  aligned to the QA tool's basis: mono -18.60/-18.61/-18.68 (inside the requested -18…-19 window), native stereo
  -19.52/-21.39/-21.55. If a reviewer instead reads the spec as *native stereo* RMS, the bed sits 1.5–3.6 dB
  below -18 — still under the ceiling, never over.
* **night.ogg stereo is ~1.9 dB hotter** than menu/battle at equal mono level, because its wind layers are
  deliberately decorrelated for width (decorrelation lowers the mono sum). Mono level — what the QA gate and a
  mono speaker hear — is identical across all three tracks (-18.6 ± 0.04 dB).
* The earlier QA pass read `battle.ogg` as 73.57 s at -0.53 dBFS because it sampled the file while ffmpeg was
  re-encoding it; the shipped file is 114.286 s at native TP -7.10 / mono peak -4.32 (verified above).
