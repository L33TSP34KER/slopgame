# Music overhaul 01 — epic orchestral war-march pack (menu / battle / night)

Council: **p-9c1e77d2** · lane: `assets/audio/music/**` (mimo) · generator: `assets/audio/_gen/gen_music.py`

Human directive (verbatim): **"make world of warcraft like music / dota 2 like / classical music but march of war"**

All three loops were recomposed from scratch (real melody/harmony/form, not soundscapes),
synthesized with the existing `dsp.py` toolkit — **`dsp.py` itself was not modified**, so
`gen_sfx.py` and the 20 committed SFX are byte-identical to before.

---

## 1. Research → what changed musically

| source | what it said (concrete) | what changed in the tracks |
|---|---|---|
| [The Music of World of Warcraft — "Lore of Epic Music", UC eScholarship](https://escholarship.org/uc/item/2xk8k2mx) (direct fetch **HTTP 403 / CloudFront**; used search-indexed excerpts of the document text) | (a) it isolates "two variables in the epic style in the music of World of Warcraft"; (b) WoW's music "does not go from point A to point B but" repeats/loops; (c) the way "to make this transition seamless is to interrupt the loopable phrase" rather than fade | Read as *theme + orchestral mass* being the two variables: the battle carries **one** memorable horn theme through four orchestrations (solo → doubled → lifted → tutti) while orchestral mass/dynamics is the second variable (15 dB measured arc). Everything is written as **loopable 8-bar phrases whose last bar lands on the intro's level/chord** instead of a through-composed cue |
| [Idan Zion — WoW Dragonflight scoring techniques (LinkedIn)](https://www.linkedin.com/posts/idanzion_tuesdaytips-scoringtechniques-musiccomposer-activity-7404203995646386176-adIr) (fetched in full) | three vertical layers: high fragile (violins/flutes/celeste/harp arpeggio) vs **mid/low doubling** (violas+horns+bassoons = "lush line"); **choir enters only after the mid-cue crescendo** "to show a shift in the energy"; companion post: melody = strings in 3 octaves + choir, countermelody = horns, bells/cymbals **sparingly** for punctuation | Choir is *absent* in the intro, appears as soft low bed at bar 8, and the mid "ah" wash starts only at **bar 24 (after the crescendo)**; melody is horn + string unison + **octave-up sparkle** on the B lift and reprise; crash used on **5 section downbeats only**; bells added to the **menu** phrase downbeats (bars 4/12/18) instead of battle |
| [Tim Larkin and DotA 2 on Top Score — YourClassical/MPR](https://www.yourclassical.org/story/2013/08/15/tim-larkin-and-dota-2-on-top-score) (fetched in full) | the game's Asian look started him on shakuhachi, then it "developed a gothic feel … So I've kept that tone since it's been **orchestral and big**"; the art/gameplay drove the musical choices; music is written for a living game over years | Chose **gothic-minor + big orchestra** (D minor with a harmonic-minor dominant A/C#) and **dropped the ethnic palette** — the previous pack's bone/wood percussion identity was replaced by orchestral snare + taiko + timpani; "orchestral and big" is the stated reason for full-band tutti reprise |
| [Holst, *The Planets* — "Mars, the Bringer of War" (Wikipedia)](https://en.wikipedia.org/wiki/Mars,_the_Bringer_of_War) (fetched section wikitext via API) | Mars "is in a relentless 5/4 ostinato for most of its duration. **It opens quietly**, the first two bars played by percussion … **builds to a … dissonant climax**"; Venus "opens with a **solo horn theme** answered quietly"; Saturn: "solemn melody introduced by the trombones … taken up by the full orchestra", "slow processional … rises to a frightening climax before fading away" | Battle keeps the Mars strategy but in 4/4 per the brief: **relentless 8th-note ostinato from bar 0 to bar 55, opening quietly, single loud climax at the reprise, decay after**. Menu takes Venus/Saturn's plan literally: **solo horn anthem** over pads with low-choir/timpani, solemn and fading at the loop |

---

## 2. Structure maps

### battle.ogg — 120.000 BPM, 4/4, **D minor** (aeolian + harmonic-minor V), 56 bars × 2.000 s = **112.000 s**
`BEAT = 22050` samples (exact), `BAR = 88200`.

| bars | section | chords (1/bar) | instrumentation |
|---|---|---|---|
| 0–7 | **INTRO** (quiet) | Dm Dm Bb Bb Dm Dm Gm A | spiccato ostinato (root/fifth eighths), timpani heartbeat on 1, string pad, low choir bed from bar 4, bass from bar 4, taiko from bar 5, **distant horn foreshadows the theme head (A–B♭–A–G) in bar 7** |
| 8–15 | **THEME A #1** | Dm Bb F C Dm Bb Gm A | solo **horn theme** (dotted march rhythm 1.5/0.5/1/1), ostinato, bass, pad, taiko 1+3, light snare from bar 12, 16th snare fill bar 15, cadence choir "ah" bar 15 |
| 16–23 | **THEME A #2** (full) | same | horns + **strings doubling in unison**, octave-up spiccato layer, low-brass dotted stabs on 1 and 3, full snare figure, choir "hah" stabs, crash, cadence choir + 16th fill bar 23 |
| 24–31 | **B LIFT** (relative-major tilt) | Bb F C Dm Bb F Gm A | **high strings lead the B theme**, horn counter, octave sparkle, **mid choir "ah" wash enters here** (after the crescendo), drums at full, crash bar 24, cadence choir + fill bar 31 |
| 32–39 | **BREAK / build** | Dm Bb Gm A ×2 | layers stripped (bass 0.45, pad 0.58, choir 0.62, no melody, snare out) → ostinato + taiko vamp; **snare 16th crescendo roll bars 38–39**, rising dominant (A) low-brass + choir pedal bars 38–39 |
| 40–47 | **REPRISE** (loudest) | Dm Bb F C Dm Bb Gm A | tutti: horns + strings + octave + **choir doubling the melody**, crash, drums 1.30, cadence choir + fill bar 47 |
| 48–55 | **CODA** (decays into the intro) | Dm Bb F C Dm Gm A Dm | theme head → cadence → bars 52–53 horn F–G–A / B♭ hold → bars 54–55 only ostinato + timpani + pad (same Dm chord as bar 0) |

Theme A (bars, pitch, rhythm — all beats):

| bar | chord | notes (beat: dur) |
|---|---|---|
| 1 | Dm | A4 (0:1.5) B♭4 (1.5:0.5) A4 (2:1) G4 (3:1) |
| 2 | Bb | F4 (0:1.5) G4 (1.5:0.5) F4 (2:1) D4 (3:1) |
| 3 | F | A4 (0:1.5) B♭4 (1.5:0.5) A4 (2:1) G4 (3:1) |
| 4 | C | G4 (0:1.5) A4 (1.5:0.5) G4 (2:1) E4 (3:1) |
| 5 | Dm | A4 (0:1.5) B♭4 (1.5:0.5) C5 (2:1) **D5 (3:1)** ← climax |
| 6 | Bb | D5 (0:2) C5 (2:1) B♭4 (3:1) |
| 7 | Gm | G4 (0:1.5) A4 (1.5:0.5) B♭4 (2:1) A4 (3:1) |
| 8 | A | A4 (0:1.5) G4 (1.5:0.5) F4 (2:1) E4 (3:1) ← half cadence, loops back to A4 |

Theme B (bars 24–31, an octave above Theme A, F-major tilt): F5 G5 F5 D5 | C5 D5 C5 A4 | E5 F5 E5 G5 | F5 (2) E5 D5 | D5 C5 B♭4 D5 | C5 D5 C5 A4 | B♭4 C5 D5 C5 | E5 (2) C♯5 (2) → dominant back into the break.

Ostinato (every bar, 8 spiccato eighths): `root root 5th root | root 5th root 5th`
(Dm: D3 D3 A3 D3 D3 A3 D3 A3 — transposed per chord), accented on beats 1 and 3.

### menu.ogg — **66.667 BPM** (0.900 s beat, exact), 4/4, D minor, 20 bars × 3.600 s = **72.000 s**

| bars | section | chords | instrumentation |
|---|---|---|---|
| 0–3 | INTRO (quietest, -21…-24 dB) | Dm Dm Gm A | ash bed + ember crackle (contract), string pad (fc 2.5 kHz), **low choir**, **soft timpani heartbeat (beats 1+3, every bar, all 20 bars)**, cello answers (D3, F3, E3), **distant horn anticipation A4 sustained bar 2** |
| 4–11 | ANTHEM statement 1 | Dm Bb F C Dm Bb Gm A | **solo horn anthem** over string pads + low choir, cello counter-answers (bars 6/10), **bell toll bar 4** |
| 12–19 | ANTHEM statement 2 (fullest) | Dm Bb F C Dm Bb Gm A | horn + string unison + faint high choir; **bell tolls bars 12 & 18**; bar 18 quotes the battle theme head (A–B♭–A–G), bar 19 F4→E4 over the dominant, decays into bar 0 |

Anthem (bars 4–11, repeated 12–19 with a varied ending): A4 (3) B♭4 | D5 (2) C5 B♭4 | A4 (4) | G4 (3) E4 | F4 (2) G4 A4 | B♭4 (3) A4 | G4 (2) A4 B♭4 | A4 (4) ‖ then 2nd pass: … G4 (2) E4 (2) | F4 (2) G4 A4 | B♭4 (2) A4 G4 | **A4 B♭4 A4 G4** (theme head) | F4 (2) E4 (2).

### night.ogg — **72.000 s**, unmetered (all bed LFOs use integer cycles over the loop)
Bed unchanged in character (wind ×2, air hiss, water, sparse crickets, one far bell at 41 s) plus the war-march world, all mixed **under** the bed:

| element | times (s) | level | processing |
|---|---|---|---|
| distant lone horn call — D4 F4 D4 then C4 E4 D4 | 9.0 / 12.4 / 14.6 and 45.0 / 48.2 / 50.8 | 0.038 / 0.034 (was 0.115) | lp 1.5 kHz, dull brass, event IR (3.2 s, wet 0.55) |
| far-off low drum pulses (taiko pairs) | 4.0+4.55, 16, 28, 40, 52, 64 | 0.046 / 0.036 / 0.028 | same event reverb |
| far-off bell | 41 | 0.065 (baseline 0.24) | lp 1.7 kHz + event reverb |

**Flagged-slice verification (principal spot-check, 22:3x):** measuring the 40.5–45 s window of the
*shipped* file with the event bed isolated (raw-build comparison, then the file's +12.0 dB
normalization): **bed −17.4 dBFS, bell −20.2 dBFS → the bell sits 2.8 dB UNDER the bed.** The
residual peak of that slice (−14.9 dB vs neighbours ≈ −18…−20) is the bed's own wind LFO
breathing (bed-only raw arc spans −28.4…−35.2 dB), not a foreground blast. Since the check,
the bell layer was cut −4.3 dB (0.105 → 0.065) and the horn a further −2.6 dB (0.048 → 0.038).

---

## 3. Before / after metrics

All numbers measured with `dsp.read_pcm_f32` + `ffmpeg -ac 1` (the QA downmix), identical code for both columns; BEFORE files are the previous pack.

| metric | battle BEFORE | battle AFTER | menu BEFORE | menu AFTER | night BEFORE | night AFTER |
|---|---|---|---|---|---|---|
| duration (s) | 114.286 | **112.000** | 72.000 | 72.000 | 72.000 | 72.000 |
| native peak dBFS | -7.10 | -7.22 | -8.31 | -8.06 | -4.30 | -5.19 |
| true peak dBTP | -7.10 | -7.22 | -8.31 | -8.06 | -4.30 | -5.18 |
| native RMS dBFS | -21.55 | -21.54 | -21.39 | -21.38 | -19.52 | -19.25 |
| mono peak dBFS | -4.32 | -4.33 | -6.18 | -5.60 | -1.49 | -3.26 |
| mono RMS dBFS (bed, gate ≤ -18) | -18.60 | -18.60 | -18.61 | -18.63 | -18.68 | -18.78 |
| LUFS | -20.27 | -19.87 | -17.95 | -18.97 | -16.42 | -16.07 |
| spectral centroid Hz | 1921 | 2823 | 1396 | 1656 | 2013 | 2050 |
| seam wrap step (max \|x[0]-x[N-1]\|) | 0.001301 | 0.003428 | 0.002181 | 0.003883 | 0.029268 | 0.035535 |
| interior p99.99 first-diff | 0.059895 | 0.077638 | 0.087501 | 0.065010 | 0.268738 | 0.285913 |
| **step / p99.99** (verify's seam test, ≤1 = seamless) | 0.022 | **0.044** | 0.025 | **0.060** | 0.109 | **0.124** |
| 20 ms wrap-xfade max delta | 0.005053 | 0.006116 | 0.003471 | 0.029859 | 0.088823 | 0.088247 |
| gap20 (head-vs-tail 20 ms) | 0.097933 | 0.046355 | 0.060359 | 0.298208 | 0.585457 | 0.636756 |
| first 2 s RMS (loop head) | -28.58 | -31.15 | -15.72 | -19.55 | -19.32 | -18.52 |
| last 2 s RMS (loop tail) | -25.50 | -30.74 | -18.35 | -19.08 | -17.93 | -17.21 |
| **loop-boundary level delta** (head − tail) | -3.08 dB | **-0.41 dB** | +2.63 dB | **-0.47 dB** | -1.39 dB | **-1.31 dB** |

### RMS-over-time arc — 8 segments (mono dBFS)

| track | s1 | s2 | s3 | s4 | s5 | s6 | s7 | s8 |
|---|---|---|---|---|---|---|---|---|
| battle BEFORE | -27.4 | -22.5 | -19.5 | -18.1 | -17.3 | -16.4 | -16.2 | -19.6 |
| **battle AFTER** | **-26.9** | -21.0 | -18.2 | -17.2 | **-19.2** (break) | -17.9 | **-15.5** (peak) | -20.0 |
| **menu AFTER** | -22.2 | -22.1 | -19.3 | -19.2 | -17.7 | **-16.0** | -17.6 | -18.3 |
| night BEFORE | -21.2 | -21.4 | -18.9 | -22.1 | **-13.5** (bell blast) | -19.9 | -21.0 | -19.5 |
| **night AFTER** | -20.1 | -19.5 | -18.0 | -21.0 | **-16.3** | -18.7 | -20.0 | -18.5 |

### RMS-over-time arc — 16 segments (mono dBFS) with structure labels

**battle AFTER** (7 s = 3.5 bars per slice):
```
intro        A1        A2         B lift      BREAK       REPRISE     CODA
-30.4 -25.0 -21.8 -20.3 -18.3 -18.0 -17.3 -17.2 -18.1 -20.8 -20.3 -16.3 -15.4 -15.7 -18.1 -23.5
```
→ build **15.0 dB** from intro to the reprise peak, a **3.6 dB break dip**, then a decay that
lands 0.4 dB from the head of the loop. Battle BEFORE for comparison was a monotone swell with
no break: `-29.6 -25.9 -23.1 -22.0 -20.1 -18.9 -18.9 -17.5 -18.3 -16.5 -16.8 -16.1 -16.4 -16.0 -17.8 -22.8`.

**menu AFTER**: `-21.3 -23.5 -22.8 -21.4 -19.1 -19.6 -19.6 -18.9 -17.6 -17.8 -16.0 -16.1 -17.1 -18.3 -17.5 -19.3`
(BEFORE had a near-silent −43.3 dB slice and an intro *louder* than the statement: `-16.9 -19.8 -18.9 -16.1 -43.3 -22.9 …`).

**night AFTER**: `-18.9 -21.8 -19.3 -19.7 -18.2 -17.8 -20.9 -21.1 -18.1 -14.9 -20.0 -17.7 -18.9 -21.5 -20.8 -17.1`
(BEFORE peaked at −11.1 on the bell blast).

### Section-level proxies (battle, mono)

| section | melody band 400–800 Hz (dB rel) | verdict |
|---|---|---|
| intro 0–7 | -12.5 | no theme |
| theme A1 8–15 | -12.3 | solo horn (register narrow) |
| theme A2 16–23 | -9.5 | doubled |
| B lift 24–31 | **-6.6** | brightest |
| break 32–39 | **-13.0** | melody absent, as intended |
| reprise 40–47 | -7.9 | tutti |
| coda 48–55 | -8.4 | cadence |

**Note-level theme detection** (energy at each written note's f0 + 2nd harmonic vs the local
band floor, ±detour bands): battle theme A1 **31/31 notes, mean +10.7 dB**; A2 31/31, +11.7 dB;
reprise 31/31, +11.7 dB; control (same notes tested against the no-melody break) **+2.4 dB** →
the theme sits ~9 dB above the detector's noise floor. Menu anthem: 13/17 (median +4.4 dB) and
11/17 (median +3.0 dB) vs control (median +0.7 dB) — honest note: the menu's pad + choir occupy
the horn's own register, so the metric under-reports; the melody-band share tells the same story
more clearly (intro slices −10.9 dB share → anthem slices −2.0…−3.2 dB share, an 8 dB jump).

**Spectral-centroid variance over time** (16 slices, Hz): battle mean 1664, std 494, range 1648
(dark intro 881 → bright reprise 2466); menu mean 1253, std 196, range 657 (intro 895 →
statement 2 1552); night mean 2018, std 254, range 968. No section is a static drone.

**Attack transients** (short-window energy peaks vs local level, 16 slices): battle 969 attacks
(8.65/s, present in all 16 slices including the intro), menu 424 (5.89/s, all 16), night 369
(5.12/s, all 16). `audio_review.py` reports `possible_clicks: []` for all 23 files.

---

## 4. Style checklist vs the brief (honest)

| ask | status | evidence |
|---|---|---|
| horn-led main theme in a minor key, stepwise, WoW-like | **YES** | Theme A above, on `brass()` horn section (3-voice detuned saw stack → horn formants 300/800/1600/2900 Hz, swell attack, delayed vibrato); 31/31 notes detected at +10.7 dB |
| theme doubled by strings / distant choir | **YES** | bars 16+: string unison; bars 24/40+: octave sparkle; low choir bed from bar 8, mid choir wash from bar 24, choir doubling the reprise line |
| Dota-2 trailer weight (ostinato, brass stabs, percussion, full-ensemble reprise) | **YES** | 8th-note spiccato ostinato in all 56 bars, low-brass dotted stabs, taiko+snare+timpani, tutti reprise at bars 40–47 |
| classical war march (staccato strings, snare+taiko+timpani spine, dotted brass, choir on cadences, 8/16-bar form) | **YES** | 7×8-bar phrases; snare 16th fills at bars 15/23/31/47/51 and a 2-bar crescendo roll 38–39; cadence choir "ah" at 15/23/31/47 |
| B-section lift to relative major / bVI | **YES** | bars 24–31 over Bb–F–C–Dm, melody an octave up, highest centroid slice group before the break |
| dynamic build measurable as RMS-over-time (intro quiet → reprise loudest) | **YES** | arc16 above: −30.4 → −15.4 (15.0 dB), break dip −3.6 dB, coda decay |
| bar-aligned seamless loop | **YES** | step/p99.99 = 0.044 / 0.060 / 0.124; head-vs-tail 2 s delta −0.41 / −0.47 / −1.31 dB; verify verdict "seamless" ×3 |
| menu: slow, solemn, majestic, horn anthem over pads + low choir + soft timpani heartbeat, NOT a battle track | **YES** | 66.67 BPM, no snare/taiko anywhere, timpani on beats 1+3 of all 20 bars, bell + cello + crackle, arc is a gentle 5 dB swell |
| night: quiet vale + distant horn + faint far-off drums, mixed WAY under | **YES** | bell −20.2 vs bed −17.4 dBFS in-window (2.8 dB under); horn/drums add ≤2 dB to any 4.5 s slice; night is the brightest-but-still-quiet bed (centroid 2050 Hz, mono −18.78) |
| bed ≤ −18 dBFS RMS, stereo 44.1 kHz OGG, durations | **YES** | -18.60 / -18.63 / -18.78 dBFS mono, 44 100 Hz stereo vorbis, 112 / 72 / 72 s |
| **weakness I did not fully fix** | noted | menu gap20 rose 0.060 → 0.298 because the menu loop point now lands on a timpani downbeat attack while the tail decays — musically correct for a loop (gated metric passes with 6 % margin, `possible_clicks: []`) but it is a larger raw head/tail difference than the old pack; night's native RMS sits only 0.25 dB under verify's −19.0 cap (narrowest margin in the pack) |

---

## 5. Gates

### 5.1 `python3 assets/audio/_gen/verify.py` → **ALL FILES PASS** (exit 0)

```
| file | dur (s) | ch | peak dBFS | true peak dBTP | RMS dBFS | DC | LUFS | mono peak/RMS | result |
| music/battle.ogg | 112.000 | 2 | -7.22 | -7.22 | -21.54 | -0.00003 | -19.9 | -4.33/-18.60 | PASS |
| music/menu.ogg   |  72.000 | 2 | -8.06 | -8.06 | -21.38 | +0.00000 | -19.0 | -5.60/-18.63 | PASS |
| music/night.ogg  |  72.000 | 2 | -5.19 | -5.18 | -19.25 | -0.00000 | -16.1 | -3.26/-18.78 | PASS |

LOOP CONTINUITY
| battle.ogg | 0.003428 | 0.059265 | 0.077638 | 0.006116 | 0.006021 | 0.046355 | seamless |
| menu.ogg   | 0.003883 | 0.049110 | 0.065010 | 0.029859 | 0.038856 | 0.298208 | seamless |
| night.ogg  | 0.035535 | 0.186873 | 0.285913 | 0.088247 | 0.095672 | 0.636756 | seamless |

pack RMS spread: 5.09 dB (-21.54 .. -16.45)
ALL FILES PASS
```
(all 20 SFX rows also PASS — untouched)

### 5.2 `python3 tools/qa/audio_review.py` (no flags, read-only use) → exit 0

```json
{"files": 23, "peak_db_range": [-10.57, -3.26], "rms_db_range": [-21.01, -16.45],
 "loudness_spread_db": 4.56, "possible_clicks": [], "dc_offsets": [],
 "fails": [], "rms_fails": [], "duration_fails": []}
```
`design/notes/audio-review.md` → **"no technical flags"**; music rows:
battle 112.0 s / centroid 2823 / low 0.721 / high 0.003 · menu 72.0 s / 1656 / 0.215 / 0.0 ·
night 72.0 s / 2050 / 0.411 / 0.001.

### 5.3 `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python tools/qa/release_check.py`

```json
{"qa": {"release_fail": 0, "release_warn": 0, "release_checks": 44}}
```
→ **0 FAIL / 0 WARN / 44 checks** (exit 0)

---

## 6. Reproduce

```bash
cd /run/media/wyene/disk/project/game
python3 assets/audio/_gen/gen_music.py            # rebuild all three (menu, battle, night)
python3 assets/audio/_gen/verify.py               # gate 1: ALL FILES PASS
python3 tools/qa/audio_review.py                  # gate 2: no flags -> design/notes/audio-review.{png,md}
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python tools/qa/release_check.py   # gate 3: 0/0/44
```

Iteration log (3 renders per the "measure, don't guess" bar):
1. **pass 1** — arc built correctly (15 dB) but the break dip was only ~1.5 dB, the top end was
   hissy (centroid 4202 Hz), menu intro was *louder* than its anthem (cello at 0.62), night's
   horn sat at bed level.
2. **pass 2** — break stripped harder (bass 0.70→0.45, pad 0.78→0.58, drums 0.55→0.38),
   snare/crash/spiccato top end tamed (centroid 4202 → 2823 Hz), night horn −6 dB, bell −4 dB.
3. **pass 3** — menu rebalanced (pad 0.60→0.46 + fc 3000→2500, horn 0.55→0.95, cello
   0.62→0.42) so the anthem leads; snare section fills + cadence choir "ah" added to battle.
4. **pass 4 (spot-check follow-up)** — night bell 0.105→0.065 (−4.3 dB) and horn 0.048→0.038
   (−2.6 dB), plus a per-track mono target (night −18.78) to keep native RMS 0.25 dB inside
   verify's cap.
