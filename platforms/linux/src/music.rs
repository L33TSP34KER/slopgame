//! Music playback.
//!
//! The system SDL2_mixer on many distributions is built without any codec
//! libraries -- this one links nothing but SDL2 itself, so `Mix_LoadMUS` cannot
//! open an `.ogg` at all.  Rather than depend on how the distro built the mixer,
//! this module decodes Ogg Vorbis itself with `libvorbisfile` and streams it
//! into SDL through `Mix_HookMusic`, which keeps the sound effects on SDL_mixer
//! and the music on our own decoder.
//!
//! Only Vorbis is supported (the format `tools/import_music.sh` produces from
//! any source file); files that fail to open are reported and skipped, and the
//! game simply plays without music.
//!
//! Track layout: `assets/audio/music/hell.ogg`..`godly.ogg` are per-theme; any
//! other `.ogg` in that folder joins a rotation pool, and a theme without its
//! own track picks `pool[theme % pool.len()]`.  So two tracks can score a whole
//! run, and dropping in a per-theme file later overrides just that theme.

#![allow(dead_code)]

use core::ffi::{c_char, c_int, c_long, c_void};
use core::sync::atomic::{AtomicBool, AtomicI32, AtomicUsize, Ordering};
use std::ffi::CString;
use std::path::{Path, PathBuf};

/// Order the mixer is opened with; the decoder converts to this.
pub const RATE: u32 = 44_100;
pub const CHANNELS: usize = 2;

const OV_STRUCT_SIZE: usize = 2048;
/// Frames pulled from the decoder per refill.
const FIFO_FRAMES: usize = 4096;

#[repr(C, align(8))]
struct OggVorbisFile([u8; OV_STRUCT_SIZE]);

#[repr(C)]
struct VorbisInfo {
    version: c_int,
    channels: c_int,
    rate: c_long,
    bitrate_upper: c_long,
    bitrate_nominal: c_long,
    bitrate_lower: c_long,
    bitrate_window: c_long,
    codec_setup: *mut c_void,
}

#[link(name = "vorbisfile")]
extern "C" {
    fn ov_fopen(path: *const c_char, vf: *mut OggVorbisFile) -> c_int;
    fn ov_info(vf: *mut OggVorbisFile, link: c_int) -> *mut VorbisInfo;
    fn ov_read(vf: *mut OggVorbisFile, buffer: *mut c_char, length: c_int, bigendianp: c_int,
               word: c_int, sgned: c_int, bitstream: *mut c_int) -> c_long;
    fn ov_pcm_seek(vf: *mut OggVorbisFile, pos: i64) -> c_int;
    fn ov_clear(vf: *mut OggVorbisFile) -> c_int;
}

#[link(name = "SDL2_mixer")]
extern "C" {
    fn Mix_HookMusic(
        mix_func: Option<unsafe extern "C" fn(*mut c_void, *mut u8, c_int)>,
        arg: *mut c_void,
    );
}

/// One opened, looping track.
struct Track {
    vf: Box<OggVorbisFile>,
    channels: usize,
    rate: u32,
    /// Decoded samples (interleaved, source layout) waiting to be played.
    fifo: Vec<i16>,
    /// Read cursor, in samples.
    cursor: usize,
    /// Fractional source position, for resampling to the mixer's rate.
    phase: f32,
    ended: bool,
    /// Total source frames consumed, for `position_seconds`.
    played_frames: u64,
}

impl Track {
    fn open(path: &Path) -> Option<Track> {
        let c_path = CString::new(path.to_string_lossy().as_bytes()).ok()?;
        let mut vf = Box::new(OggVorbisFile([0u8; OV_STRUCT_SIZE]));
        let rc = unsafe { ov_fopen(c_path.as_ptr(), &mut *vf) };
        if rc != 0 {
            return None;
        }
        let info = unsafe { ov_info(&mut *vf, -1) };
        if info.is_null() {
            unsafe { ov_clear(&mut *vf) };
            return None;
        }
        let info = unsafe { &*info };
        if info.channels < 1 || info.rate < 8_000 {
            unsafe { ov_clear(&mut *vf) };
            return None;
        }
        Some(Track {
            vf,
            channels: info.channels as usize,
            rate: info.rate as u32,
            fifo: Vec::with_capacity(FIFO_FRAMES * info.channels as usize),
            cursor: 0,
            phase: 0.0,
            ended: false,
            played_frames: 0,
        })
    }

    fn restart(&mut self) {
        unsafe { ov_pcm_seek(&mut *self.vf, 0) };
        self.cursor = 0;
        self.phase = 0.0;
        self.ended = false;
        self.played_frames = 0;
        self.fifo.clear();
    }

    /// Decodes more samples into the FIFO.  Returns `true` when it got some and
    /// `false` only at the end of the stream -- getting this backwards is what
    /// once made every track loop its first hundred milliseconds.
    fn refill(&mut self) -> bool {
        if self.ended {
            return false;
        }
        let want = FIFO_FRAMES * self.channels;
        let mut bytes = vec![0u8; want * 2];
        let mut bitstream = 0;
        let got = unsafe {
            ov_read(&mut *self.vf, bytes.as_mut_ptr() as *mut c_char, bytes.len() as c_int,
                    0, 2, 1, &mut bitstream)
        };
        if got <= 0 {
            self.ended = true;
            return false;
        }
        let samples = got as usize / 2;
        self.fifo.clear();
        self.fifo.reserve(samples);
        for i in 0..samples {
            self.fifo.push(i16::from_le_bytes([bytes[i * 2], bytes[i * 2 + 1]]));
        }
        self.cursor = 0;
        true
    }

    /// The next output frame (left, right), resampled and looping forever.
    ///
    /// The read position advances once per *frame*, not once per channel call,
    /// which is the other half of playing back at the right speed.
    fn next_frame(&mut self) -> (f32, f32) {
        loop {
            let frames = self.fifo.len() / self.channels;
            if self.cursor < frames {
                let base = self.cursor * self.channels;
                let left = self.fifo[base] as f32 / 32_768.0;
                let right = if self.channels > 1 {
                    self.fifo[base + 1] as f32 / 32_768.0
                } else {
                    left
                };
                // Source samples consumed per output frame.
                self.phase += self.rate as f32 / RATE as f32;
                let advance = self.phase.floor() as usize;
                if advance > 0 {
                    self.phase -= advance as f32;
                    self.cursor += advance;
                    self.played_frames += advance as u64;
                }
                return (left, right);
            }
            if !self.refill() {
                // End of track: loop back to the top.
                self.restart();
                if !self.refill() {
                    return (0.0, 0.0);
                }
            }
        }
    }

    /// Seconds of this track decoded so far (used by the tests).
    pub fn position_seconds(&self) -> f32 {
        self.played_frames as f32 / self.rate as f32
    }
}

/// Seconds a track takes to fade in while the previous one fades out.
const CROSSFADE: f32 = 1.4;

/// State the audio thread owns.  The main thread only touches the atomics.
struct Shared {
    tracks: Vec<Track>,
    /// Index of the track being played, if any.
    active: Option<usize>,
    /// The track fading out underneath it.
    previous: Option<usize>,
    /// 0..1 weight of `active` (1 = the crossfade has finished).
    cross: f32,
    /// Requested track (`usize::MAX` = nothing pending).
    request: AtomicUsize,
    volume: AtomicI32,
    muted: AtomicBool,
    /// Gain, ramped so mutes never click.
    gain: f32,
}

unsafe extern "C" fn hook(udata: *mut c_void, stream: *mut u8, len: c_int) {
    if udata.is_null() || stream.is_null() {
        return;
    }
    let shared = unsafe { &mut *(udata as *mut Shared) };
    let frames = (len as usize) / (CHANNELS * 2);
    let out = unsafe { core::slice::from_raw_parts_mut(stream as *mut i16, frames * CHANNELS) };
    out.fill(0);

    let volume = if shared.muted.load(Ordering::Relaxed) {
        0.0
    } else {
        shared.volume.load(Ordering::Relaxed).clamp(0, 128) as f32 / 128.0
    };

    // A new track fades in while the old one fades out.
    let requested = shared.request.swap(usize::MAX, Ordering::Relaxed);
    if requested != usize::MAX && Some(requested) != shared.active {
        if let Some(t) = shared.tracks.get_mut(requested) {
            t.restart();
        }
        shared.previous = shared.active;
        shared.active = Some(requested);
        shared.cross = 0.0;
    }

    let dt = frames as f32 / RATE as f32;
    let step = (dt / CROSSFADE).clamp(0.0, 1.0);
    // Mute/silence ramps over ~200 ms.
    let gain_step = (dt / 0.2).clamp(0.0, 1.0);

    for f in 0..frames {
        shared.gain += (volume - shared.gain) * gain_step;
        shared.cross = (shared.cross + step).min(1.0);
        let g = shared.gain;
        let t = shared.cross;
        let mut left = 0.0f32;
        let mut right = 0.0f32;

        if let Some(prev) = shared.previous {
            if t < 1.0 {
                if let Some(track) = shared.tracks.get_mut(prev) {
                    let (l, r) = track.next_frame();
                    left += l * (1.0 - t);
                    right += r * (1.0 - t);
                }
            } else {
                shared.previous = None;
            }
        }
        if let Some(active) = shared.active {
            if let Some(track) = shared.tracks.get_mut(active) {
                let (l, r) = track.next_frame();
                left += l * t;
                right += r * t;
            }
        }
        out[f * CHANNELS] = ((left * g).clamp(-1.0, 1.0) * 32_000.0) as i16;
        out[f * CHANNELS + 1] = ((right * g).clamp(-1.0, 1.0) * 32_000.0) as i16;
    }
}

pub struct Music {
    shared: Box<Shared>,
    /// Which opened track each backdrop theme maps to (`usize::MAX` = silence).
    slots: Vec<usize>,
    /// The between-round track.
    menu_slot: usize,
    /// What is currently requested, so a per-frame call is a no-op unless it
    /// actually changes.
    want: usize,
    open: bool,
    pub files: Vec<String>,
}

impl Music {
    /// Opens every track it can find.  Never fatal: no tracks means silence.
    pub fn new(asset_dir: &Path) -> Music {
        // Music is a source asset (it can be re-imported), so it lives next to
        // the built assets rather than inside the generated directory: check
        // `assets/dist/audio/music`, then `assets/audio/music` (the usual spot
        // when the asset dir is `assets/dist`), then a plain relative path.
        let mut candidates = vec![asset_dir.join("audio").join("music")];
        if let Some(parent) = asset_dir.parent() {
            candidates.push(parent.join("audio").join("music"));
        }
        candidates.push(PathBuf::from("assets/audio/music"));
        let dir = candidates
            .iter()
            .find(|d| d.is_dir())
            .cloned()
            .unwrap_or_else(|| asset_dir.join("audio").join("music"));
        let theme_names = ["hell", "gold", "lava", "paradise", "purple", "godly"];
        // `menu.ogg` scores the between-round hive; it is not part of the pool.
        let menu_name = "menu";

        let mut paths: Vec<PathBuf> = Vec::new();
        let mut menu_path: Option<usize> = None;
        let mut per_theme: Vec<Option<usize>> = vec![None; theme_names.len()];
        let mut others: Vec<PathBuf> = Vec::new();

        if let Ok(entries) = std::fs::read_dir(&dir) {
            let mut all: Vec<PathBuf> = entries
                .filter_map(|e| e.ok().map(|e| e.path()))
                .filter(|p| p.extension().map(|x| x == "ogg").unwrap_or(false))
                .collect();
            all.sort();
            for path in all {
                let stem = path.file_stem()
                    .map(|s| s.to_string_lossy().to_lowercase())
                    .unwrap_or_default();
                if stem == menu_name {
                    menu_path = Some(paths.len());
                } else {
                    match theme_names.iter().position(|n| *n == stem) {
                        Some(i) => per_theme[i] = Some(paths.len()),
                        None => others.push(path.clone()),
                    }
                }
                paths.push(path);
            }
        }

        // Open each distinct path once.
        let mut tracks: Vec<Track> = Vec::new();
        let mut opened: Vec<Option<usize>> = Vec::new();
        let mut names: Vec<String> = Vec::new();
        for path in &paths {
            match Track::open(path) {
                Some(t) => {
                    names.push(path.file_name().map(|s| s.to_string_lossy().into_owned())
                               .unwrap_or_default());
                    tracks.push(t);
                    opened.push(Some(tracks.len() - 1));
                }
                None => {
                    eprintln!("slime_arena: cannot decode {} (needs Ogg Vorbis; \
                               run tools/import_music.sh)", path.display());
                    opened.push(None);
                }
            }
        }

        // Theme slots use their own file when present, otherwise the pool.
        let pool: Vec<usize> = others
            .iter()
            .filter_map(|p| paths.iter().position(|q| q == p))
            .filter_map(|i| opened.get(i).copied().flatten())
            .collect();
        let mut slots = Vec::with_capacity(theme_names.len());
        for (i, own) in per_theme.iter().enumerate() {
            let slot = own.and_then(|p| opened.get(p).copied().flatten())
                .or_else(|| {
                    if pool.is_empty() {
                        None
                    } else {
                        Some(pool[i % pool.len()])
                    }
                });
            slots.push(slot.unwrap_or(usize::MAX));
        }

        let menu_slot = menu_path
            .and_then(|p| opened.get(p).copied().flatten())
            .unwrap_or(usize::MAX);
        let open = !tracks.is_empty();
        if open {
            for (i, name) in theme_names.iter().enumerate() {
                if slots[i] != usize::MAX {
                    println!("slime_arena: music {} -> {}", name,
                             names_of(&names, &opened, slots[i]));
                }
            }
            if menu_slot != usize::MAX {
                println!("slime_arena: music menu -> {}",
                         names_of(&names, &opened, menu_slot));
            } else {
                println!("slime_arena: no menu.ogg; the hive will keep the theme track");
            }
        }


        let shared = Box::new(Shared {
            tracks,
            active: None,
            previous: None,
            cross: 1.0,
            request: AtomicUsize::new(usize::MAX),
            volume: AtomicI32::new(44),
            muted: AtomicBool::new(false),
            gain: 0.0,
        });

        Music { shared, slots, menu_slot, want: usize::MAX, open, files: names }
    }

    pub fn is_open(&self) -> bool {
        self.open
    }

    pub fn track_count(&self) -> usize {
        self.shared.tracks.len()
    }

    /// Installs the mixer hook.  Call once, after the mixer is open.
    pub fn install(&mut self) {
        if !self.open {
            return;
        }
        let ptr = &mut *self.shared as *mut Shared as *mut c_void;
        unsafe { Mix_HookMusic(Some(hook), ptr) };
    }

    /// Picks the track for the current moment: the menu track between rounds,
    /// otherwise the theme that matches the arena.  Safe to call every frame.
    pub fn select(&mut self, menu: bool, theme: i32) {
        if !self.open {
            return;
        }
        let slot = if menu {
            self.menu_slot
        } else {
            self.slots.get(theme.max(0) as usize).copied().unwrap_or(usize::MAX)
        };
        if slot == usize::MAX || slot == self.want {
            return;
        }
        self.want = slot;
        self.shared.request.store(slot, Ordering::Relaxed);
    }

    pub fn has_menu_track(&self) -> bool {
        self.menu_slot != usize::MAX
    }

    pub fn set_volume(&self, volume: i32) {
        self.shared.volume.store(volume.clamp(0, 128), Ordering::Relaxed);
    }

    pub fn set_muted(&self, muted: bool) {
        self.shared.muted.store(muted, Ordering::Relaxed);
    }

    pub fn shutdown(&mut self) {
        if !self.open {
            return;
        }
        unsafe { Mix_HookMusic(None, core::ptr::null_mut()) };
        self.shared.tracks.clear();
        self.open = false;
    }
}

fn names_of(names: &[String], opened: &[Option<usize>], track: usize) -> String {
    for (i, o) in opened.iter().enumerate() {
        if *o == Some(track) {
            return names.get(i).cloned().unwrap_or_default();
        }
    }
    String::from("?")
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Finds a shipped track from wherever the test happens to run.
    fn shipped_track() -> Option<PathBuf> {
        for p in ["assets/audio/music/menu.ogg",
                  "../../assets/audio/music/menu.ogg",
                  "../../../assets/audio/music/menu.ogg"] {
            let path = PathBuf::from(p);
            if path.exists() {
                return Some(path);
            }
        }
        None
    }

    #[test]
    fn decodes_a_real_track_and_loops_it() {
        let Some(path) = shipped_track() else {
            return; // no music checked in; nothing to prove
        };
        let mut t = Track::open(&path).expect("a shipped .ogg must open");
        assert_eq!(t.channels, 2, "imported music is stereo");
        assert_eq!(t.rate, RATE, "imported music is 44.1 kHz");

        // A second of audio must actually contain audio.
        let mut peak = 0.0f32;
        for _ in 0..RATE {
            let (l, _r) = t.next_frame();
            peak = peak.max(l.abs());
        }
        assert!(peak > 0.01, "decoded track is silent (peak {peak})");
        // ...and it must be a *second* of audio, not a stuttering buffer.
        assert!((t.position_seconds() - 1.0).abs() < 0.05,
                "one second of playback advanced {}", t.position_seconds());

        // Regression: the opening must not repeat.  Collect two windows and
        // require them to differ; looping the first buffer made them identical.
        let first: Vec<f32> = (0..RATE / 2).map(|_| t.next_frame().0).collect();
        let second: Vec<f32> = (0..RATE / 2).map(|_| t.next_frame().0).collect();
        let same = first.iter().zip(second.iter()).filter(|(a, b)| (*a - *b).abs() < 1e-6)
            .count();
        assert!(same < first.len() / 10,
                "the track is repeating itself ({} of {} samples identical)",
                same, first.len());

        // Playback keeps moving forward, and still loops past the end.
        let before = t.position_seconds();
        for _ in 0..(RATE * 4) {
            t.next_frame();
        }
        assert!(t.position_seconds() > before + 3.5,
                "position did not advance ({} -> {})", before, t.position_seconds());
    }

    /// Root-mean-square level of `pcm`.
    fn rms(pcm: &[f32]) -> f32 {
        if pcm.is_empty() {
            return 0.0;
        }
        (pcm.iter().map(|v| v * v).sum::<f32>() / pcm.len() as f32).sqrt()
    }

    /// Cross-checks the decoder against ffmpeg, which is an independent
    /// implementation: same file, same window, same level.  Catches a swapped
    /// channel, a wrong sample format or a wrong playback rate.  Skipped when
    /// ffmpeg is not installed.
    #[test]
    fn our_decode_matches_ffmpeg() {
        let Some(path) = shipped_track() else { return };
        let Ok(out) = std::process::Command::new("ffmpeg")
            .args(["-v", "error", "-i"])
            .arg(&path)
            .args(["-t", "2", "-f", "s16le", "-ac", "2", "-ar", "44100", "-"])
            .output()
        else {
            return;
        };
        if !out.status.success() || out.stdout.is_empty() {
            return;
        }
        // ffmpeg writes interleaved stereo; take the left channel to compare
        // against our own left channel.
        let all: Vec<i16> = out.stdout
            .chunks_exact(2)
            .map(|b| i16::from_le_bytes([b[0], b[1]]))
            .collect();
        let theirs: Vec<f32> = all.iter().step_by(2)
            .map(|v| *v as f32 / 32_768.0)
            .collect();

        let mut t = Track::open(&path).expect("a shipped .ogg must open");
        let ours: Vec<f32> = (0..theirs.len().min(RATE as usize * 2))
            .map(|_| t.next_frame().0)
            .collect();

        let (a, b) = (rms(&ours), rms(&theirs[..ours.len()]));
        assert!(a > 0.001, "our decode is silent");
        let ratio = a / b;
        assert!((0.85..1.15).contains(&ratio),
                "level mismatch against ffmpeg: ours {a:.4}, theirs {b:.4} (ratio {ratio:.3})");

        // Spot-check that the waveform tracks, not just its loudness.  A codec
        // may introduce a small constant delay, so allow a shift and require
        // some offset to line up well.
        let window = ours.len().min(theirs.len());
        let mut best = (0.0f32, 0i32);
        for lag in -2048i32..=2048 {
            let mut close = 0usize;
            let mut total = 0usize;
            for i in 0..window {
                let j = i as i32 + lag;
                if j < 0 || j as usize >= theirs.len() {
                    continue;
                }
                total += 1;
                if (ours[i] - theirs[j as usize]).abs() < 0.05 {
                    close += 1;
                }
            }
            if total > window / 2 {
                let agreement = close as f32 / total as f32;
                if agreement > best.0 {
                    best = (agreement, lag);
                }
            }
        }
        assert!(best.0 > 0.9,
                "waveform does not match ffmpeg (best {:.1}% at lag {})",
                best.0 * 100.0, best.1);
    }

    #[test]
    fn a_missing_directory_is_silent_not_fatal() {
        let m = Music::new(Path::new("/definitely/not/here"));
        assert!(!m.is_open());
        assert_eq!(m.track_count(), 0);
        // Every theme still resolves to "nothing", and asking for one is safe.
        assert!(m.slots.iter().all(|s| *s == usize::MAX));
    }
}
