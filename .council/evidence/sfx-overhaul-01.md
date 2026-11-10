# sfx-overhaul-01 — research-driven SFX rebuild

Directive (human, verbatim): **"find a way to generate better sfx look internet"**

Scope: `assets/audio/**` (mimo's lane, overridden for this task and announced on
the bus with veto option). All 20 contract filenames regenerated in place;
music untouched. Engine manifest unchanged.

---

## 1. Research — what was read and what it changed

| # | Technique takeaway | Source | What changed in the pack |
|---|---|---|---|
| 1 | **sfxr-style recipes work because a fast downward frequency ramp + amplitude "punch" reads as weight/impact**, and arpeggio/pitch motion reads as pickup/reward. Presets: pickupCoin, explosion, powerUp, hitHurt, blipSelect. | DrPetter sfxr (MIT) https://www.drpetter.se/project_sfxr.html · jsfxr README https://cdn.jsdelivr.net/npm/jsfxr@1.4.1/README.md | `error` knocks now carry an explicit downward pitch ramp (560→360 Hz per knock); `command` drum ramp steepened 190→58 Hz with 0.6 ms attack; `explosion` blast sweep steepened 170→34 Hz with faster early collapse; `gold` keeps the detuned grain arpeggio. |
| 2 | **Layering doctrine: ATTACK (transient) → BODY (character) → TAIL (space) → SWEETENER.** "Layering: best results, more work" — complex sounds are built, not gestured. | game-audio skill doc https://github.com/ranbot-ai/awesome-skills/blob/main/skills/game-development-game-audio/SKILL.md | Every impact family now has a dedicated 0.6–1.0 ms noise transient (was 2–4 ms — soft), a modal/FM body, and a frequency-dependent IR tail. `sword` additionally gets a 4th "sweetener" layer: real blade whoosh. |
| 3 | **Karplus–Strong = noise burst through a filtered delay line**; excitation spectrum + loop filter set the pluck character; bright excitation = snap, loop LP = string damping. | https://en.wikipedia.org/wiki/Karplus%E2%80%93Strong_algorithm (Karplus & Strong 1983, *Digital Synthesis of Plucked String and Drum Timbres*) | `bow` string brightened (excitation brightness 0.65→0.80, loop LP 4500→6500 Hz, damping 0.986→0.988) + separate 1.2 ms string-slap transient on release. |
| 4 | **FM with non-integer modulator ratios makes inharmonic bell/percussive spectra; a decaying modulation index gives a bright attack that mellows** — this is why DX7 struck-metal/bell patches beat static modal rings. | https://en.wikipedia.org/wiki/Frequency_modulation_synthesis ("modulators at non-integer multiples … inharmonic bell-like and percussive spectra can be created") | New `fm_tone()` / `fm_partials()` in `dsp.py`. Replaces flat modal rings on: `sword` clang (carrier sweep 1900→1580 Hz, ratio 1.41, index 7 decaying), `holy`, `build-done`, `level-up`, `victory`, `defeat` bells (5-partial FM stacks with per-partial decay). |
| 5 | **Tasteful saturation adds harmonics/weight without loudness; but unfiltered sat harmonics create inter-sample peaks** that cost 1–2 dB of loudness in the lossy encode/limit loop. | Technique combo validated empirically during this task (see §5 findings) | `soft_sat()` (tanh, optional asymmetry = tube-ish even harmonics) applied per-sound at drive 1.2–1.9, always followed by a low-pass so sat harmonics cannot alias into ISP overshoot. |
| 6 | **Better synthetic IRs: frequency-dependent decay (HF damps fast, bass rings on), smeared early reflections, predelay, diffusion build-up** — a single-band exponential reads as "noise on a fader"; single-sample ER spikes comb-filter into metallic ringing. | Natural-IR exponential-decay premise: CCRMA paper https://ccrma.stanford.edu/~nlabate/220C/timeline/CDC-Paper.pdf (located via search; snippet consulted) | `make_ir()` rewritten in `dsp.py`: 3-band decay (low ×1.7, mid ×1.0, high ×0.55), 4 ms diffusion build-up, 10 densifying 1.5 ms smeared early taps instead of 4 raw spikes. All 20 sounds' tails use it. |
| 7 | **CC0 foley layers beat synthesis where real physics show through** (metal clang, coin jingle, axe bite, body fall); keep synthesis underneath for coherence. | Kenney CC0 packs (below) | 12 CC0 layers mixed under the synth in `select, command, gold, build, build-done, sword, holy, chop, death` — see §3. |

## 2. License record (hard rule: no copyrighted samples)

| Source | URL | License | Taken | Where |
|---|---|---|---|---|
| Kenney — Impact Sounds (130 files) | https://kenney.nl/assets/impact-sounds | **CC0 1.0** (License.txt inside zip, copied to `assets/audio/_gen/cc0/LICENSE-kenney.txt`) | 7 layers | `cc0/*.wav` |
| Kenney — RPG Audio | https://kenney.nl/assets/rpg-audio | **CC0 1.0** (same, verified in zip) | 5 layers | `cc0/*.wav` |
| Kenney — Interface Sounds | https://kenney.nl/assets/interface-sounds | **CC0 1.0** (downloaded, evaluated, **not used** — clicks are too digital for a parchment/wood UI) | 0 | — |
| Sonniss GDC Bundle | https://sonniss.com/gdc-bundle-license/ (page 403/Cloudflare) + full EULA text http://ftpmirror.your.org/pub/misc/sonniss2017/Licensing.pdf | **Royalty-free EULA but NOT public domain**: "all right, title and interest … shall always remain the property of their respective copyright holders" | 0 | **EXCLUDED** by the asset-contract rule (only CC0/public-domain or own synthesis) |
| sfxr / jsfxr | https://www.drpetter.se/project_sfxr.html | MIT source code | 0 audio — techniques only | — |

Download path (no account, no JS): the Kenney page JS calls
`GET https://kenney.nl/download-link/<hex-of-asset-path>` with same-origin
`Referer`/`Origin` headers and receives a signed URL — implemented in
`assets/audio/_gen/fetch_cc0.py` (reproducible; re-run with
`--zip-dir DIR` for offline zips).

Layer material: 44.1 kHz mono 16-bit WAV, DC-clean, head-silence trimmed,
peak-normalized to −6 dBFS (`assets/audio/_gen/cc0/*.wav`, 450 KB total).
`fetch_cc0.py` records pack → file provenance per layer.

## 3. Strategy per sound family

| Family | Sounds | Strategy |
|---|---|---|
| UI/economy | click, select, command, error | Synthesis-first (soft wooden/parchment identity per contract); sharper 0.6–1.2 ms transients, sfxr pitch ramps (error), CC0 `cloth`/`tick`-family layers on select + command's muted-metal ring. |
| Weapons | sword, chop, bow | sword: synth flesh/thud/scrape **+ FM clang + CC0 knife-swipe, sword-metal, leather**; chop: synth crack/thud/splinters **+ CC0 axe-chop**; bow: brighter Karplus–Strong + string-slap transient (no layer — the string IS the sound). |
| Structures | build, build-done, death | build: synth wood modal **+ CC0 wood-light hammer strike**; build-done: FM bell chime **+ CC0 bell** on the final strike; death: synth whoosh/thud/clatter **+ CC0 body-fall + leather**. |
| Magic/world | magic, holy, explosion, roar | Fully synthesized: sparkle chirps + FM shimmer (magic), FM bell + CC0 bell (holy), crack + steep two-stage sweep + tanh grit (explosion — centroid pulled 7260→5070 Hz, it was too hissy for a siege impact), sub octave + vowel-glide formants + AM rasp + saturation (roar). |
| Banners/stingers | level-up, alert, horn, victory, defeat | Brass engine kept; brighter attack, FM bells on final chords, horn breath layers, tamed cymbial swell on victory (centroid 6076→3023 Hz — it was thin/hissy), timpani-weight low drums. |

Synthesis is **always** the bed; CC0 layers never replace it (gains 0.35–1.1
pre-normalization). Pure-synth sounds: click, error, bow, magic, explosion,
roar, level-up, alert, horn, victory, defeat.

## 4. Before / after metrics (all 20, mono 44.1 kHz OGG)

Measured with `assets/audio/_gen/metrics.py` (before = pack as committed, after = this
change). TP = true peak (ffmpeg loudnorm, dBTP).

| file | dur s (b→a) | true peak dBTP (b→a) | RMS dBFS (b→a) | centroid Hz (b→a) | crest dB (b→a) |
|---|---|---|---|---|---|
| click | 0.18 → 0.18 | -7.4 → -9.11 | -20.89 → -21.01 | 1598 → 1731 | 13.46 → 11.87 |
| select | 0.42 → 0.42 | -6.79 → -7.42 | -19.5 → -19.46 | 4334 → 3133 | 12.68 → 12.01 |
| command | 0.55 → 0.55 | -7.17 → -8.53 | -18.92 → -18.93 | 1739 → 1578 | 11.74 → 10.37 |
| error | 0.52 → 0.52 | -6.99 → -8.32 | -19.42 → -19.43 | 929 → 851 | 12.44 → 11.11 |
| gold | 0.75 → 0.75 | -7.49 → -8.5 | -19.49 → -19.5 | 4795 → 4940 | 11.87 → 10.95 |
| build | 0.45 → 0.45 | -6.72 → -8.08 | -19.45 → -19.43 | 1790 → 968 | 12.73 → 11.35 |
| build-done | 1.12 → 1.12 | -7.98 → -9.58 | -18.96 → -18.99 | 2087 → 4455 | 10.96 → 9.4 |
| bow | 0.9 → 0.9 | -6.75 → -7.61 | -18.96 → -18.98 | 1729 → 1599 | 12.2 → 11.3 |
| sword | 0.75 → 0.75 | -6.45 → -6.72 | -18.44 → -18.49 | 4479 → 4065 | 11.99 → 11.49 |
| magic | 1.02 → 1.02 | -7.93 → -8.04 | -18.49 → -18.5 | 3380 → 3487 | 10.54 → 10.44 |
| holy | 1.12 → 1.12 | -8.85 → -10.5 | -18.47 → -18.47 | 4494 → 3980 | 9.62 → 7.97 |
| chop | 0.5 → 0.5 | -6.39 → -7.51 | -18.69 → -18.67 | 4402 → 4436 | 12.25 → 11.16 |
| death | 0.95 → 0.95 | -7.2 → -7.3 | -18.94 → -18.95 | 1479 → 1949 | 11.74 → 11.65 |
| explosion | 1.05 → 1.05 | -6.27 → -8.36 | -19.54 → -18.99 | 7260 → 5070 | 12.57 → 10.57 |
| level-up | 1.48 → 1.48 | -8.03 → -10.57 | -16.45 → -16.45 | 1834 → 4473 | 8.41 → 5.88 |
| alert | 1.48 → 1.48 | -7.0 → -7.93 | -16.46 → -16.48 | 1073 → 1924 | 9.46 → 8.55 |
| horn | 2.48 → 2.48 | -7.0 → -7.97 | -16.97 → -16.97 | 689 → 735 | 9.97 → 9.0 |
| roar | 1.98 → 1.98 | -7.14 → -8.15 | -17.04 → -17.03 | 3043 → 3202 | 9.9 → 8.87 |
| victory | 4.0 → 4.0 | -6.66 → -7.94 | -16.48 → -16.49 | 6076 → 3023 | 9.67 → 8.55 |
| defeat | 4.0 → 4.0 | -7.97 → -8.23 | -16.46 → -16.46 | 604 → 880 | 8.49 → 8.23 |

Highlights a human can judge without listening:

- **Durations identical to the before-pack and inside contract for all 20.**
- **RMS on target everywhere** (per-family targets in `SPEC` unchanged except
  `click` +0.5 compensation, see §5): in-game SFX spread 2.54 dB
  (before 2.45) — pack balance preserved.
- **Centroid moves are deliberate**: explosion 7260→5070 (siege impact no
  longer hissy), victory 6076→3023 (brass stinger now warm, not thin),
  select 4334→3133 (parchment, not plastic), build 1790→968 (real hammer
  weight), build-done 2087→4455 and level-up 1834→4473 (FM bells/brass
  brightened dull chimes), alert 1073→1924 (breath + drum clicks = more
  present alarm).
- **Crest −0.5…−1.5 dB typical** — the expected signature of tasteful
  saturation (density up, spike down); no file is over-limited (min crest 5.9
  on the dense level-up fanfare, was 8.4 — its peak sits 2.5 dB lower at the
  same RMS, i.e. more headroom, not more compression).
- **True peak headroom increased on every file**; worst TP in pack −6.72 dBTP
  (contract ceiling −6.0).

## 5. Findings worth keeping

1. **Saturation without a low-pass is a loudness trap.** `sword` saturated its
   transient but had no post-sat LP, creating +2.43 dB inter-sample peak
   (4× oversampled); the encode/limit loop then cut 1.3 dB of RMS to satisfy
   true peak (−19.77 vs −18.5 target). Measured component-wise: layers alone
   gap 0.01 dB, +sat gap 2.56 dB, +sat+LP12k back to ~0.2. Fix shipped: LP
   after sat; sword now −18.49 RMS / −6.72 TP.
2. **Vorbis flush appends ~22 ms of silence to the shortest file** (decoded
   8896 vs source 7938 samples for `click`), diluting ffmpeg-measured RMS by
   0.5 dB. Compensated by raising click's chain target −21.0 → −20.5 so the
   decoded file measures −21.01, i.e. on the design value under the same
   metric `tools/qa/audio_review.py` uses.
3. Sharp transients are safe only if the *first* granule carries them:
   attacks were lengthened 0.4→0.6 ms minimum everywhere (still <1 ms, still
   reads as snap) to keep encoder warm-up loss negligible.

## 6. Listenability proxy (no ears available)

Checked programmatically on the decoded files (`metrics.py`):

- **edge discontinuity** (max |Δ| at first/last sample pair ÷ RMS): ≤ 0.04 all
  files (pack was ≤ 0.09 before); threshold for flagging is 2.0 → none.
- **fades**: last-5-ms level ≤ −42 dBFS on every file (tails end at zero);
  first-5-ms level shows attack present on all transient sounds (−7.7 … −16.9
  dBFS). Swell-type sounds (`magic` −50.6, `death` −51.5, `roar` −31.4) have
  late peaks *by design* — identical structure in the before-pack (−49.2 /
  −51.7 / −40.2): airy whoosh, lead-in whoosh, growl fade-in.
- **DC offset**: |dc| ≤ 0.0003 everywhere (limit 0.002).
- **Clipping**: peak ≤ −6.72 dBFS on all — nothing near 0 dBFS.
- **Montage eyeball**: `design/notes/audio-review.png` regenerated — all 20
  show onset attack, monotone decay, faded tails; spectrograms show spectral
  motion (no static-blob beeps).

## 7. Verification / gates

| Gate | Result |
|---|---|
| `python3 assets/audio/_gen/verify.py` | **ALL FILES PASS, exit 0** — 20 SFX + 3 music: vorbis, 44.1 kHz, mono, duration in contract, sample peak ≤ −6, true peak ≤ −6, DC ≤ 0.002, RMS > −45; music loops still "seamless". Pack RMS spread 5.10 dB (all files incl. music), in-game SFX (stingers excluded) 2.54 dB. |
| `python3 tools/qa/audio_review.py` | 23 files, `possible_clicks: []`, `dc_offsets: []`, `fails: []`, `rms_fails: []`, `duration_fails: []`, loudness spread 4.56 dB (before 4.44) → **no flags** (flag threshold 8 dB). |
| `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python tools/qa/release_check.py` | **0 FAIL / 0 WARN / 44 checks** (identical to baseline taken before the change), including `audio:SDL load` — every contract filename loads through the engine loader. |
| Filenames | 20/20 contract names, byte-identical list; `emberfall/src/audio.py` reads only `sfx/` and `music/` (non-recursive) so `_gen/cc0/*.wav` is invisible to the game. |

## 8. Reproduce

```bash
python3 assets/audio/_gen/fetch_cc0.py            # re-download CC0 layers (or --zip-dir)
python3 assets/audio/_gen/gen_sfx.py              # regenerate all 20 OGGs
python3 assets/audio/_gen/verify.py               # quality gate
python3 assets/audio/_gen/metrics.py --json out.json   # before/after table
python3 tools/qa/audio_review.py                  # montage + flags
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python tools/qa/release_check.py
```
