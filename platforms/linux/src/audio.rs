//! Linux audio: sound effects synthesised on the fly, music streamed from Ogg
//! Vorbis by our own decoder (see `music.rs`).
//!
//! Two deliberate choices:
//!
//! * **Music comes from files** in `assets/audio/music/`: `<theme>.ogg` per
//!   backdrop theme plus `menu.ogg` for the between-round hive, with any other
//!   `.ogg` forming a rotation pool.  Cross-faded when the mood changes.  If a
//!   track is missing the game simply plays no music.
//! * **Sound effects are synthesised**, so the game has sound with zero asset
//!   files.  If `assets/audio/sfx/<cue>.wav` exists it is used *instead* of the
//!   synth, so real samples can replace them one at a time.
//!
//! Everything here is driven by the core's event stream; the game logic never
//! knows whether a speaker exists.

#![allow(dead_code)]

use core::ffi::{c_int, c_void};
use std::path::Path;
use crate::music::Music;

// ---------------------------------------------------------------------------
// SDL2_mixer bindings (the subset used here)
// ---------------------------------------------------------------------------

pub type MixChunk = c_void;

/// SDL_AUDIO_S16LSB
const AUDIO_S16SYS: u16 = 0x8010;

#[link(name = "SDL2")]
extern "C" {
    fn SDL_RWFromMem(mem: *mut c_void, size: c_int) -> *mut c_void;
}

#[link(name = "SDL2_mixer")]
extern "C" {
    fn Mix_OpenAudio(freq: c_int, format: u16, channels: c_int, chunksize: c_int) -> c_int;
    fn Mix_CloseAudio();
    fn Mix_AllocateChannels(numchans: c_int) -> c_int;
    fn Mix_LoadWAV_RW(src: *mut c_void, freesrc: c_int) -> *mut MixChunk;
    fn Mix_FreeChunk(chunk: *mut MixChunk);
    fn Mix_PlayChannelTimed(channel: c_int, chunk: *mut MixChunk, loops: c_int,
                            ticks: c_int) -> c_int;
    fn Mix_Volume(channel: c_int, volume: c_int) -> c_int;
}

// ---------------------------------------------------------------------------
// cues
// ---------------------------------------------------------------------------

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Cue {
    Shoot,
    Hit,
    EnemyDie,
    PlayerHurt,
    PickupXp,
    PickupMoney,
    LevelUp,
    Buy,
    BuyFail,
    WaveStart,
    WaveClear,
    GameOver,
    UiClick,
    Dash,
    Lightning,
    CheckpointPassed,
    CheckpointFailed,
    Revived,
}

impl Cue {
    pub const ALL: [Cue; 18] = [
        Cue::Shoot, Cue::Hit, Cue::EnemyDie, Cue::PlayerHurt, Cue::PickupXp,
        Cue::PickupMoney, Cue::LevelUp, Cue::Buy, Cue::BuyFail, Cue::WaveStart,
        Cue::WaveClear, Cue::GameOver, Cue::UiClick, Cue::Dash, Cue::Lightning,
        Cue::CheckpointPassed, Cue::CheckpointFailed, Cue::Revived,
    ];

    pub fn index(self) -> usize {
        Cue::ALL.iter().position(|c| *c == self).unwrap_or(0)
    }

    pub fn name(self) -> &'static str {
        match self {
            Cue::Shoot => "shoot",
            Cue::Hit => "hit",
            Cue::EnemyDie => "enemy_die",
            Cue::PlayerHurt => "player_hurt",
            Cue::PickupXp => "pickup_xp",
            Cue::PickupMoney => "pickup_money",
            Cue::LevelUp => "level_up",
            Cue::Buy => "buy",
            Cue::BuyFail => "buy_fail",
            Cue::WaveStart => "wave_start",
            Cue::WaveClear => "wave_clear",
            Cue::GameOver => "game_over",
            Cue::UiClick => "ui_click",
            Cue::Dash => "dash",
            Cue::Lightning => "lightning",
            Cue::CheckpointPassed => "checkpoint_passed",
            Cue::CheckpointFailed => "checkpoint_failed",
            Cue::Revived => "revived",
        }
    }

    /// Minimum seconds between two plays of this cue: a swarm must not turn
    /// into a wall of noise (or eat every mixer channel).
    pub fn cooldown(self) -> f32 {
        match self {
            Cue::Shoot => 0.045,
            Cue::Hit => 0.05,
            Cue::EnemyDie => 0.06,
            Cue::PickupXp => 0.05,
            Cue::PickupMoney => 0.06,
            Cue::PlayerHurt => 0.18,
            Cue::UiClick => 0.06,
            _ => 0.12,
        }
    }

    /// How far a play may be detuned.  Percussive cues can move a lot (it stops
    /// a stream of shots sounding like one machine); melodic cues barely move,
    /// so a level-up jingle never clashes with the music.
    pub fn pitch_spread(self) -> f32 {
        use Cue::*;
        match self {
            Shoot | Hit | EnemyDie | Dash | Lightning | PickupXp | PickupMoney => 0.10,
            LevelUp | CheckpointPassed | CheckpointFailed | Revived | WaveStart
            | WaveClear | Buy | BuyFail | GameOver => 0.02,
            _ => 0.06,
        }
    }

    pub fn volume(self) -> i32 {
        match self {
            Cue::Shoot => 42,
            Cue::Hit => 30,
            Cue::EnemyDie => 62,
            Cue::PlayerHurt => 92,
            Cue::PickupXp => 34,
            Cue::PickupMoney => 40,
            Cue::LevelUp => 92,
            Cue::Buy => 80,
            Cue::BuyFail => 60,
            Cue::WaveStart => 86,
            Cue::WaveClear => 86,
            Cue::GameOver => 100,
            Cue::UiClick => 44,
            Cue::Dash => 46,
            Cue::Lightning => 92,
            Cue::CheckpointPassed => 100,
            Cue::CheckpointFailed => 96,
            Cue::Revived => 100,
        }
    }

    /// Maps a `gc_event_type` from the core onto a cue.
    pub fn from_event(type_: i32) -> Option<Cue> {
        Some(match type_ {
            1 => Cue::Shoot,
            2 => Cue::Hit,
            3 => Cue::EnemyDie,
            4 => Cue::PlayerHurt,
            5 => Cue::PickupXp,
            6 => Cue::PickupMoney,
            7 => Cue::LevelUp,
            8 => Cue::Buy,
            9 => Cue::BuyFail,
            10 => Cue::WaveStart,
            11 => Cue::WaveClear,
            12 => Cue::GameOver,
            13 => Cue::UiClick,
            14 => Cue::Dash,
            15 => Cue::Lightning,
            16 => Cue::CheckpointPassed,
            17 => Cue::CheckpointFailed,
            18 => Cue::Revived,
            19 => Cue::Hit,          // blood hits something
            20 => Cue::BuyFail,      // money going the wrong way
            21 => Cue::WaveStart,    // a boss arriving
            _ => return None,
        })
    }
}

// ---------------------------------------------------------------------------
// synthesis
// ---------------------------------------------------------------------------

#[derive(Copy, Clone, PartialEq, Eq)]
enum Wave {
    Sine,
    Square,
    Saw,
    Noise,
}

#[derive(Copy, Clone)]
struct Seg {
    /// Frequency at the start and end of the segment (a sweep).
    f0: f32,
    f1: f32,
    start: f32,
    dur: f32,
    amp: f32,
    wave: Wave,
}

const fn seg(f0: f32, f1: f32, start: f32, dur: f32, amp: f32, wave: Wave) -> Seg {
    Seg { f0, f1, start, dur, amp, wave }
}

/// One small recipe per cue: a handful of swept tones is plenty for an arcade
/// game, and it keeps the whole sound bank in the source tree.  These are
/// `static` so `recipe` can hand out `&'static` slices.
use Wave::{Noise, Saw, Sine, Square};

static SHOOT: [Seg; 1] = [seg(880.0, 420.0, 0.0, 0.055, 0.5, Square)];
static HIT: [Seg; 1] = [seg(300.0, 180.0, 0.0, 0.04, 0.4, Noise)];
static ENEMY_DIE: [Seg; 2] = [
    seg(420.0, 90.0, 0.0, 0.16, 0.5, Saw),
    seg(180.0, 60.0, 0.0, 0.18, 0.35, Noise),
];
static PLAYER_HURT: [Seg; 2] = [
    seg(180.0, 70.0, 0.0, 0.22, 0.7, Square),
    seg(90.0, 50.0, 0.02, 0.24, 0.5, Saw),
];
static PICKUP_XP: [Seg; 1] = [seg(660.0, 1180.0, 0.0, 0.07, 0.34, Sine)];
static PICKUP_MONEY: [Seg; 2] = [
    seg(880.0, 880.0, 0.0, 0.05, 0.34, Square),
    seg(1320.0, 1320.0, 0.05, 0.08, 0.34, Square),
];
static LEVEL_UP: [Seg; 4] = [
    seg(523.0, 523.0, 0.0, 0.1, 0.45, Square),
    seg(659.0, 659.0, 0.1, 0.1, 0.45, Square),
    seg(784.0, 784.0, 0.2, 0.1, 0.45, Square),
    seg(1046.0, 1046.0, 0.3, 0.22, 0.5, Square),
];
static BUY: [Seg; 2] = [
    seg(700.0, 700.0, 0.0, 0.06, 0.4, Square),
    seg(1050.0, 1050.0, 0.06, 0.1, 0.4, Square),
];
static BUY_FAIL: [Seg; 2] = [
    seg(200.0, 200.0, 0.0, 0.07, 0.45, Square),
    seg(150.0, 150.0, 0.08, 0.12, 0.45, Square),
];
static WAVE_START: [Seg; 2] = [
    seg(196.0, 196.0, 0.0, 0.18, 0.5, Saw),
    seg(392.0, 392.0, 0.16, 0.26, 0.4, Saw),
];
static WAVE_CLEAR: [Seg; 3] = [
    seg(392.0, 392.0, 0.0, 0.12, 0.4, Square),
    seg(523.0, 523.0, 0.12, 0.12, 0.4, Square),
    seg(784.0, 784.0, 0.24, 0.3, 0.45, Square),
];
static GAME_OVER: [Seg; 2] = [
    seg(392.0, 196.0, 0.0, 0.5, 0.5, Saw),
    seg(196.0, 98.0, 0.3, 0.7, 0.5, Saw),
];
static UI_CLICK: [Seg; 1] = [seg(1200.0, 900.0, 0.0, 0.03, 0.3, Square)];
static DASH: [Seg; 1] = [seg(200.0, 1400.0, 0.0, 0.12, 0.36, Noise)];
static LIGHTNING: [Seg; 2] = [
    seg(2400.0, 300.0, 0.0, 0.05, 0.7, Noise),
    seg(140.0, 60.0, 0.02, 0.35, 0.6, Saw),
];
static CHECKPOINT_PASSED: [Seg; 4] = [
    seg(523.0, 523.0, 0.0, 0.12, 0.45, Square),
    seg(784.0, 784.0, 0.12, 0.12, 0.45, Square),
    seg(1046.0, 1046.0, 0.24, 0.12, 0.45, Square),
    seg(1568.0, 1568.0, 0.36, 0.4, 0.5, Square),
];
static CHECKPOINT_FAILED: [Seg; 3] = [
    seg(233.0, 233.0, 0.0, 0.25, 0.55, Saw),
    seg(155.0, 155.0, 0.2, 0.3, 0.55, Saw),
    seg(116.0, 58.0, 0.45, 0.6, 0.5, Saw),
];
static REVIVED: [Seg; 2] = [
    seg(392.0, 1568.0, 0.0, 0.35, 0.5, Square),
    seg(1046.0, 1046.0, 0.3, 0.4, 0.4, Sine),
];

fn recipe(cue: Cue) -> &'static [Seg] {
    match cue {
        Cue::Shoot => &SHOOT,
        Cue::Hit => &HIT,
        Cue::EnemyDie => &ENEMY_DIE,
        Cue::PlayerHurt => &PLAYER_HURT,
        Cue::PickupXp => &PICKUP_XP,
        Cue::PickupMoney => &PICKUP_MONEY,
        Cue::LevelUp => &LEVEL_UP,
        Cue::Buy => &BUY,
        Cue::BuyFail => &BUY_FAIL,
        Cue::WaveStart => &WAVE_START,
        Cue::WaveClear => &WAVE_CLEAR,
        Cue::GameOver => &GAME_OVER,
        Cue::UiClick => &UI_CLICK,
        Cue::Dash => &DASH,
        Cue::Lightning => &LIGHTNING,
        Cue::CheckpointPassed => &CHECKPOINT_PASSED,
        Cue::CheckpointFailed => &CHECKPOINT_FAILED,
        Cue::Revived => &REVIVED,
    }
}

const SAMPLE_RATE: u32 = 44100;

/// How many detuned takes are baked for each cue.
const VARIANTS: usize = 5;

/// A tiny deterministic RNG, so a run's sound is reproducible.
struct Rng64(u64);

impl Rng64 {
    fn new(seed: u64) -> Rng64 {
        Rng64(seed | 1)
    }

    fn next_u32(&mut self) -> u32 {
        let mut x = self.0;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.0 = x;
        (x.wrapping_mul(0x2545_F491_4F6C_DD1D) >> 32) as u32
    }

    fn range(&mut self, lo: f32, hi: f32) -> f32 {
        lo + (self.next_u32() >> 8) as f32 / (1u32 << 24) as f32 * (hi - lo)
    }
}

/// Synthesises a cue into interleaved stereo PCM.
///
/// `pitch` scales every frequency, `speed` scales the timing, `amp` the level:
/// baking a few of these gives every play a slightly different character
/// without needing a pitch-shifting mixer.
fn synth_pcm(cue: Cue, pitch: f32, speed: f32, amp: f32) -> Vec<i16> {
    let segs = recipe(cue);
    let total = segs.iter().map(|s| (s.start + s.dur) / speed).fold(0.0f32, f32::max) + 0.06;
    let frames = (total * SAMPLE_RATE as f32) as usize;
    let mut pcm = vec![0i16; frames * 2];
    let mut noise = 0x1234_5678u32;

    for s in segs {
        let first = (s.start / speed * SAMPLE_RATE as f32) as usize;
        let count = (s.dur / speed * SAMPLE_RATE as f32) as usize;
        let mut phase = 0.0f32;
        for i in 0..count {
            let t = i as f32 / count.max(1) as f32;
            let freq = (s.f0 + (s.f1 - s.f0) * t) * pitch;
            phase += freq / SAMPLE_RATE as f32;
            if phase > 1.0 {
                phase -= 1.0;
            }
            let raw = match s.wave {
                Wave::Sine => (phase * core::f32::consts::TAU).sin(),
                Wave::Square => if phase < 0.5 { 1.0 } else { -1.0 },
                Wave::Saw => phase * 2.0 - 1.0,
                Wave::Noise => {
                    noise ^= noise << 13;
                    noise ^= noise >> 17;
                    noise ^= noise << 5;
                    (noise as f32 / u32::MAX as f32) * 2.0 - 1.0
                }
            };
            let attack = (t / 0.03).min(1.0);
            let env = attack * (-4.0 * t).exp();
            let v = (raw * env * s.amp * amp * 26_000.0) as i32;
            let idx = (first + i) * 2;
            if idx + 1 < pcm.len() {
                let mixed = (pcm[idx] as i32 + v).clamp(-32_000, 32_000);
                pcm[idx] = mixed as i16;
                pcm[idx + 1] = mixed as i16;
            }
        }
    }
    pcm
}

/// Wraps interleaved stereo PCM in a WAV container.
fn wav_from_pcm(pcm: &[i16]) -> Vec<u8> {
    let data_bytes = (pcm.len() * 2) as u32;
    let mut wav = Vec::with_capacity(44 + pcm.len() * 2);
    wav.extend_from_slice(b"RIFF");
    wav.extend_from_slice(&(36 + data_bytes).to_le_bytes());
    wav.extend_from_slice(b"WAVEfmt ");
    wav.extend_from_slice(&16u32.to_le_bytes());
    wav.extend_from_slice(&1u16.to_le_bytes());
    wav.extend_from_slice(&2u16.to_le_bytes());
    wav.extend_from_slice(&SAMPLE_RATE.to_le_bytes());
    wav.extend_from_slice(&(SAMPLE_RATE * 4).to_le_bytes());
    wav.extend_from_slice(&4u16.to_le_bytes());
    wav.extend_from_slice(&16u16.to_le_bytes());
    wav.extend_from_slice(b"data");
    wav.extend_from_slice(&data_bytes.to_le_bytes());
    for sample in pcm {
        wav.extend_from_slice(&sample.to_le_bytes());
    }
    wav
}

/// Reads a PCM WAV into interleaved i16 plus its rate and channel count.
/// Returns `None` for anything it does not understand, so an exotic file simply
/// plays unaltered rather than breaking the mixer.
fn decode_wav(bytes: &[u8]) -> Option<(Vec<i16>, u32, u16, u16)> {
    if bytes.len() < 44 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return None;
    }
    let mut at = 12usize;
    let mut format = None;
    while at + 8 <= bytes.len() {
        let id = &bytes[at..at + 4];
        let size = u32::from_le_bytes([bytes[at + 4], bytes[at + 5], bytes[at + 6],
                                       bytes[at + 7]]) as usize;
        let body = at + 8;
        if id == b"fmt " && body + 16 <= bytes.len() {
            let kind = u16::from_le_bytes([bytes[body], bytes[body + 1]]);
            let channels = u16::from_le_bytes([bytes[body + 2], bytes[body + 3]]);
            let rate = u32::from_le_bytes([bytes[body + 4], bytes[body + 5], bytes[body + 6],
                                           bytes[body + 7]]);
            let bits = u16::from_le_bytes([bytes[body + 14], bytes[body + 15]]);
            format = Some((kind, channels, rate, bits));
        } else if id == b"data" && format.is_some() {
            let (kind, channels, rate, bits) = format?;
            if kind != 1 || (bits != 16 && bits != 8) || channels == 0 {
                return None;
            }
            let end = (body + size).min(bytes.len());
            let raw = &bytes[body..end];
            let pcm: Vec<i16> = if bits == 16 {
                raw.chunks_exact(2)
                    .map(|b| i16::from_le_bytes([b[0], b[1]]))
                    .collect()
            } else {
                raw.iter().map(|b| ((*b as i16) - 128) << 8).collect()
            };
            return Some((pcm, rate, channels, bits));
        }
        at = body + size + (size & 1);
    }
    None
}

/// Resamples decoded PCM to the mixer's rate/channel layout while shifting its
/// pitch: `speed` > 1 plays faster and higher.
fn resample_to_mixer(pcm: &[i16], rate: u32, channels: u16, speed: f32) -> Vec<i16> {
    let channels = channels.max(1) as usize;
    let frames = pcm.len() / channels;
    if frames == 0 {
        return Vec::new();
    }
    let step = (rate as f32 / SAMPLE_RATE as f32) * speed;
    let out_frames = ((frames as f32) / step) as usize;
    let mut out = Vec::with_capacity(out_frames * 2);
    for i in 0..out_frames {
        let src = i as f32 * step;
        let a = src.floor() as usize;
        let b = (a + 1).min(frames - 1);
        let t = src - a as f32;
        for ch in 0..2 {
            let ca = if ch < channels { pcm[a * channels + ch] } else { pcm[a * channels] };
            let cb = if ch < channels { pcm[b * channels + ch] } else { pcm[b * channels] };
            let v = ca as f32 + (cb as f32 - ca as f32) * t;
            out.push(v.clamp(-32_000.0, 32_000.0) as i16);
        }
    }
    out
}

/// One unaltered WAV in memory (used for the file-override path and tests).
#[allow(dead_code)]
fn render_wav(cue: Cue) -> Vec<u8> {
    wav_from_pcm(&synth_pcm(cue, 1.0, 1.0, 1.0))
}

// ---------------------------------------------------------------------------
// the audio system
// ---------------------------------------------------------------------------

pub struct Audio {
    open: bool,
    muted: bool,
    sfx_volume: i32,
    music_volume: i32,
    /// One bank of detuned takes per cue.
    chunks: Vec<Vec<*mut MixChunk>>,
    rng: Rng64,
    /// Vorbis streaming player (SDL_mixer itself often has no codecs built in).
    music: Music,
    cooldowns: [f32; 18],
    /// WAV bytes kept alive: SDL_mixer reads them through an RWops at load time
    /// only, but holding them costs nothing and makes debugging easier.
    _wavs: Vec<Vec<u8>>,
}

impl Audio {
    /// Opens the device.  Failure is never fatal: the game runs silent.
    pub fn new(asset_dir: &Path, enabled: bool) -> Audio {
        let mut audio = Audio {
            open: false,
            muted: false,
            sfx_volume: 102,
            music_volume: 77,
            chunks: Vec::new(),
            rng: Rng64::new(0xC0FF_EE00_1234_5678),
            music: Music::new(asset_dir),
            cooldowns: [0.0; 18],
            _wavs: Vec::new(),
        };
        audio.music.set_volume(audio.music_volume);
        if !enabled {
            return audio;
        }
        unsafe {
            if Mix_OpenAudio(SAMPLE_RATE as c_int, AUDIO_S16SYS, 2, 512) != 0 {
                eprintln!("slime_arena: no audio device (running silent)");
                return audio;
            }
            Mix_AllocateChannels(24);
        }
        audio.open = true;

        // Sound effects: bake several detuned takes of each cue, either from the
        // synth or from a WAV the artist dropped in.
        for cue in Cue::ALL {
            let spread = cue.pitch_spread();
            let override_path = asset_dir.join("audio").join("sfx")
                .join(format!("{}.wav", cue.name()));
            let file_pcm = std::fs::read(&override_path).ok().and_then(|b| decode_wav(&b));

            let mut bank = Vec::with_capacity(VARIANTS);
            for v in 0..VARIANTS {
                // The first take is the reference; the rest are detuned.
                let (pitch, speed, amp) = if v == 0 {
                    (1.0, 1.0, 1.0)
                } else {
                    let p = audio.rng.range(1.0 - spread, 1.0 + spread);
                    (p, audio.rng.range(0.92, 1.10), audio.rng.range(0.85, 1.05))
                };
                let wav = match &file_pcm {
                    Some((pcm, rate, channels, _bits)) => {
                        let shifted = resample_to_mixer(pcm, *rate, *channels, speed);
                        wav_from_pcm(&shifted)
                    }
                    None => wav_from_pcm(&synth_pcm(cue, pitch, speed, amp)),
                };
                let mut chunk: *mut MixChunk = core::ptr::null_mut();
                unsafe {
                    let rw = SDL_RWFromMem(wav.as_ptr() as *mut c_void, wav.len() as c_int);
                    if !rw.is_null() {
                        chunk = Mix_LoadWAV_RW(rw, 1);
                    }
                }
                audio._wavs.push(wav);
                bank.push(chunk);
            }
            audio.chunks.push(bank);
        }

        // Music: our own Vorbis decoder, streamed into the mixer through a hook.
        audio.music.install();

        audio
    }

    pub fn is_open(&self) -> bool {
        self.open
    }

    /// Advances cue cooldowns.
    pub fn update(&mut self, dt: f32) {
        for c in self.cooldowns.iter_mut() {
            *c = (*c - dt).max(0.0);
        }
    }

    pub fn play(&mut self, cue: Cue) {
        if !self.open || self.muted {
            return;
        }
        let idx = cue.index();
        if self.cooldowns[idx] > 0.0 {
            return;
        }
        self.cooldowns[idx] = cue.cooldown();
        let Some(bank) = self.chunks.get(idx) else { return };
        if bank.is_empty() {
            return;
        }
        let pick = (self.rng.next_u32() as usize) % bank.len();
        let chunk = bank[pick];
        if chunk.is_null() {
            return;
        }
        let volume = (cue.volume() * self.sfx_volume / 128).clamp(0, 128);
        unsafe {
            Mix_Volume(-1, volume);
            Mix_PlayChannelTimed(-1, chunk, 0, -1);
        }
    }

    pub fn play_event(&mut self, type_: i32) {
        if let Some(cue) = Cue::from_event(type_) {
            self.play(cue);
        }
    }

    /// Chooses the right track for the moment: the menu track between rounds,
    /// the theme track while playing.  Cross-faded; safe to call every frame.
    pub fn select_music(&mut self, menu: bool, theme: i32) {
        if !self.open {
            return;
        }
        self.music.select(menu, theme);
    }

    pub fn toggle_mute(&mut self) -> bool {
        self.muted = !self.muted;
        self.music.set_muted(self.muted);
        if !self.open {
            return self.muted;
        }
        unsafe {
            Mix_Volume(-1, if self.muted { 0 } else { self.sfx_volume });
        }
        self.muted
    }

    /// Sets both volumes from the settings screen (0..1 each).
    pub fn set_volumes(&mut self, music: f32, sfx: f32) {
        self.music_volume = (music.clamp(0.0, 1.0) * 128.0).round() as i32;
        self.sfx_volume = (sfx.clamp(0.0, 1.0) * 128.0).round() as i32;
        self.music.set_volume(self.music_volume);
        if !self.muted {
            unsafe { Mix_Volume(-1, self.sfx_volume) };
        }
    }

    /// `delta` is in 1/128ths, as SDL_mixer uses.
    pub fn nudge_volume(&mut self, delta: i32) {
        if !self.open {
            return;
        }
        if delta > 0 {
            self.music_volume = (self.music_volume + 16).min(128);
        } else {
            self.music_volume = (self.music_volume - 16).max(0);
        }
        self.music.set_volume(self.music_volume);
        println!("slime_arena: music volume {}/128", self.music_volume);
    }

    pub fn shutdown(&mut self) {
        if !self.open {
            return;
        }
        self.music.shutdown();
        unsafe {
            for bank in self.chunks.iter() {
                for c in bank.iter() {
                    if !c.is_null() {
                        Mix_FreeChunk(*c);
                    }
                }
            }
            Mix_CloseAudio();
        }
        self.chunks.clear();
        self.open = false;
    }
}

impl Drop for Audio {
    fn drop(&mut self) {
        self.shutdown();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_cue_has_a_recipe_and_a_unique_index() {
        for (i, cue) in Cue::ALL.iter().enumerate() {
            assert_eq!(cue.index(), i, "cue {:?} index mismatch", cue);
            assert!(!recipe(*cue).is_empty(), "{:?} has no recipe", cue);
            assert!(cue.cooldown() > 0.0);
            assert!(cue.volume() > 0 && cue.volume() <= 128);
            assert!(!cue.name().is_empty());
        }
    }

    #[test]
    fn event_mapping_covers_the_whole_abi() {
        // gc_event_type is 1..=18 today; every one must map to a cue.
        for t in 1..=18 {
            assert!(Cue::from_event(t).is_some(), "event {} is unmapped", t);
        }
        assert!(Cue::from_event(0).is_none());
        assert!(Cue::from_event(99).is_none());
    }

    #[test]
    fn detuned_takes_differ_in_pitch_and_length() {
        let mut rng = Rng64::new(99);
        let flat = synth_pcm(Cue::Shoot, 1.0, 1.0, 1.0);
        let high = synth_pcm(Cue::Shoot, 1.0 + Cue::Shoot.pitch_spread(), 1.0, 1.0);
        assert_eq!(flat.len(), high.len(), "pitch alone must not change length");
        assert_ne!(flat, high, "detuning must actually change the sound");

        let fast = synth_pcm(Cue::Shoot, 1.0, 1.12, 1.0);
        assert!(fast.len() < flat.len(), "a faster take must be shorter");

        // The variants a cue actually ships with must not be clones of each other.
        let mut seen: Vec<Vec<i16>> = Vec::new();
        for v in 0..VARIANTS {
            let (pitch, speed, amp) = if v == 0 {
                (1.0, 1.0, 1.0)
            } else {
                (rng.range(0.9, 1.1), rng.range(0.92, 1.10), rng.range(0.85, 1.05))
            };
            seen.push(synth_pcm(Cue::EnemyDie, pitch, speed, amp));
        }
        for i in 1..seen.len() {
            assert_ne!(seen[i], seen[0], "take {} is identical to the reference", i);
        }
    }

    #[test]
    fn melodic_cues_stay_nearly_in_tune() {
        assert!(Cue::LevelUp.pitch_spread() < 0.05);
        assert!(Cue::Shoot.pitch_spread() > Cue::LevelUp.pitch_spread());
    }

    #[test]
    fn a_wav_round_trips_through_the_decoder() {
        let pcm = synth_pcm(Cue::Buy, 1.0, 1.0, 1.0);
        let wav = wav_from_pcm(&pcm);
        let (decoded, rate, channels, bits) = decode_wav(&wav).expect("our own WAV must decode");
        assert_eq!(rate, SAMPLE_RATE);
        assert_eq!(channels, 2);
        assert_eq!(bits, 16);
        assert_eq!(decoded, pcm);
        // Garbage must be rejected rather than misread.
        assert!(decode_wav(b"not a wav at all, definitely not").is_none());
        assert!(decode_wav(&wav[..20]).is_none());
    }

    #[test]
    fn resampling_shortens_and_lengthens_as_asked() {
        let pcm = synth_pcm(Cue::Lightning, 1.0, 1.0, 1.0);
        let fast = resample_to_mixer(&pcm, SAMPLE_RATE, 2, 1.5);
        let slow = resample_to_mixer(&pcm, SAMPLE_RATE, 2, 0.5);
        assert!(fast.len() < pcm.len());
        assert!(slow.len() > pcm.len());
        // A different source rate is compensated for.
        let from_48k = resample_to_mixer(&pcm, 48_000, 2, 1.0);
        assert!(from_48k.len() < pcm.len());
        // Mono is widened to stereo rather than dropped.
        let mono: Vec<i16> = pcm.iter().step_by(2).copied().collect();
        let widened = resample_to_mixer(&mono, SAMPLE_RATE, 1, 1.0);
        assert_eq!(widened.len(), mono.len() * 2);
    }

    #[test]
    fn rendered_wavs_are_well_formed_and_audible() {
        for cue in Cue::ALL {
            let wav = render_wav(cue);
            assert!(wav.len() > 44, "{:?} produced no audio", cue);
            assert_eq!(&wav[0..4], b"RIFF");
            assert_eq!(&wav[8..12], b"WAVE");
            assert_eq!(&wav[36..40], b"data");
            let declared = u32::from_le_bytes([wav[40], wav[41], wav[42], wav[43]]) as usize;
            assert_eq!(declared + 44, wav.len(), "{:?} has a bad data size", cue);
            // Not silence.
            let peak = wav[44..]
                .chunks_exact(2)
                .map(|b| i16::from_le_bytes([b[0], b[1]]).unsigned_abs())
                .max()
                .unwrap_or(0);
            assert!(peak > 500, "{:?} is silent (peak {})", cue, peak);
            assert!(peak < 32_000, "{:?} clips (peak {})", cue, peak);
        }
    }
}
