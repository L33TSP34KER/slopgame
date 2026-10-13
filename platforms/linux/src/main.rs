//! Slime Arena -- Linux renderer.
//!
//! Owns the window, the SDL renderer, the textures, the input loop and the
//! screenshot/CI mode.  All game logic lives in `libgame_core.so`; see
//! `include/game_core.h` for the contract.
//!
//! Usage
//!   slime_arena                                  play
//!   slime_arena --headless --scenario tour       render scripted frames to PNGs
//!                                                (works with no GPU and no display)
//!
//! Options
//!   --headless            use the SDL "dummy" video driver + software renderer
//!   --scenario NAME       title | combat | levelup | shop | gameover | tour
//!   --frames N            stop after N simulated frames (headless)
//!   --out DIR             where screenshots and the headless save file go
//!   --width/--height      window size in pixels (default 1280x720)
//!   --seed N              deterministic run seed
//!   --assets DIR          where the PNGs from assets/dist live

mod audio;
mod core_api;
mod music;
mod png;
mod renderer;
mod sdl;

use audio::Audio;
use core_api::{Api, Mode};
use game_core::{gc_input, gc_settings, gc_status, GC_ABI_VERSION, GC_BTN_DASH, GC_BTN_PAUSE, GC_BTN_RESTART, GC_STATE_SHOP, GC_STATE_TITLE};
use renderer::Renderer;
use sdl::*;
use std::ffi::CString;
use std::path::{Path, PathBuf};
use std::time::Instant;

// -- command line -----------------------------------------------------------

struct Options {
    headless: bool,
    scenario: String,
    frames: u32,
    out_dir: PathBuf,
    width: i32,
    height: i32,
    seed: u32,
    assets: Option<String>,
    dump: u32,
    check_assets: bool,
    diag_textures: bool,
    stats: bool,
    audio: bool,
    no_audio: bool,
}

impl Default for Options {
    fn default() -> Self {
        Options {
            headless: false,
            scenario: "tour".to_string(),
            frames: 0,
            out_dir: PathBuf::from("screenshots"),
            width: 1280,
            height: 720,
            seed: 20240607,
            assets: None,
            dump: 0,
            check_assets: false,
            diag_textures: false,
            stats: false,
            audio: false,
            no_audio: false,
        }
    }
}

fn parse_args() -> Options {
    let mut o = Options::default();
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        let mut value = |name: &str| -> String {
            args.next().unwrap_or_else(|| {
                eprintln!("slime_arena: {} needs a value", name);
                std::process::exit(2);
            })
        };
        match arg.as_str() {
            "--headless" => o.headless = true,
            "--scenario" => o.scenario = value("--scenario"),
            "--frames" => o.frames = value("--frames").parse().unwrap_or(0),
            "--out" => o.out_dir = PathBuf::from(value("--out")),
            "--width" => o.width = value("--width").parse().unwrap_or(1280),
            "--height" => o.height = value("--height").parse().unwrap_or(720),
            "--seed" => o.seed = value("--seed").parse().unwrap_or(1),
            "--assets" => o.assets = Some(value("--assets")),
            "--dump" => o.dump = value("--dump").parse().unwrap_or(0),
            "--check-assets" => o.check_assets = true,
            "--diag-textures" => o.diag_textures = true,
            "--stats" => o.stats = true,
            "--audio" => o.audio = true,
            "--no-audio" => o.no_audio = true,
            "-h" | "--help" => {
                println!("{}", HELP);
                std::process::exit(0);
            }
            other => {
                eprintln!("slime_arena: unknown argument '{}'\n\n{}", other, HELP);
                std::process::exit(2);
            }
        }
    }
    o
}

const HELP: &str = "\
slime_arena -- Slime Arena on Linux (game logic in libgame_core.so)

  --headless          render without a display or GPU (SDL dummy driver)
  --scenario NAME     title | combat | levelup | shop | gameover | tour
  --frames N          stop after N frames in headless mode
  --out DIR           screenshot / save directory (default ./screenshots)
  --width W --height H  window size, default 1280x720
  --seed N            deterministic seed
  --assets DIR        override the assets/dist location

Diagnostics (no window needed, useful in CI):
  --check-assets      load every PNG and report its size and alpha range
  --diag-textures     render every texture plus colour reference blocks to a PNG
  --dump N            print the first N render commands of the first frame
  --stats             print a status line every simulated second (with --scenario survive)

Controls: WASD or arrows to move, mouse to aim, left button to aim manually,
space to dash, esc to pause, R to restart.";

// -- input ------------------------------------------------------------------

#[derive(Default)]
struct Held {
    keys: Vec<i32>,
    /// Key-down edges since the last frame (mute, volume, ...).
    presses: Vec<i32>,
    mouse: (f32, f32),
    pointer_down: bool,
    quit: bool,
    resized: bool,
    /// Wheel notches collected since the last frame.
    wheel: f32,
    /// A synthetic drag used to translate the wheel into panning.
    synth: Option<SynthDrag>,
}

/// Press, move, release: the core pans on drag and buys on a tap, so a wheel
/// notch becomes a drag rather than a new ABI field.
#[derive(Copy, Clone)]
struct SynthDrag {
    origin: (f32, f32),
    dy: f32,
    frame: u32,
}

impl Held {
    fn key_down(&self, sym: i32) -> bool {
        self.keys.contains(&sym)
    }
}

fn poll_events(held: &mut Held) {
    let mut event = SdlEvent::default();
    while unsafe { SDL_PollEvent(&mut event) } != 0 {
        let kind = unsafe { event.type_ };
        match kind {
            SDL_QUIT => held.quit = true,
            SDL_KEYDOWN | SDL_KEYUP => {
                let key = unsafe { event.key };
                if key.repeat != 0 {
                    continue;
                }
                let sym = key.keysym.sym;
                if kind == SDL_KEYDOWN {
                    if !held.keys.contains(&sym) {
                        held.keys.push(sym);
                        held.presses.push(sym);
                    }
                } else {
                    held.keys.retain(|k| *k != sym);
                }
            }
            SDL_MOUSEMOTION => {
                let m = unsafe { event.motion };
                held.mouse = (m.x as f32, m.y as f32);
            }
            SDL_MOUSEBUTTONDOWN => {
                let b = unsafe { event.button };
                held.mouse = (b.x as f32, b.y as f32);
                if b.button == 1 {
                    held.pointer_down = true;
                }
            }
            SDL_MOUSEBUTTONUP => {
                let b = unsafe { event.button };
                held.mouse = (b.x as f32, b.y as f32);
                if b.button == 1 {
                    held.pointer_down = false;
                }
            }
            SDL_FINGERDOWN | SDL_FINGERMOTION => {
                let f = unsafe { event.finger };
                // Touch coordinates are normalised; convert with the window size.
                held.mouse = (f.x, f.y);
                held.pointer_down = true;
            }
            SDL_FINGERUP => {
                held.pointer_down = false;
            }
            SDL_MOUSEWHEEL => {
                let w = unsafe { event.wheel };
                let amount = if w.precise_y != 0.0 { w.precise_y } else { w.y as f32 };
                held.wheel += amount;
            }
            SDL_WINDOWEVENT => {
                let w = unsafe { event.window };
                if w.event == SDL_WINDOWEVENT_RESIZED || w.event == SDL_WINDOWEVENT_SIZE_CHANGED {
                    held.resized = true;
                }
            }
            _ => {}
        }
    }
}

fn build_input(held: &Held, scale: f32, fingerprint: bool) -> gc_input {
    // A wheel notch is played back as a quick drag.
    if let Some(s) = &held.synth {
        let progress = if s.frame == 0 { 0.0 } else { 1.0 };
        return gc_input {
            move_x: 0.0,
            move_y: 0.0,
            aim_x: s.origin.0 / scale.max(1.0),
            aim_y: (s.origin.1 + s.dy * progress) / scale.max(1.0),
            pointer_active: 1,
            pointer_down: i32::from(s.frame < 2),
            buttons: 0,
        };
    }
    let mut move_x = 0.0;
    let mut move_y = 0.0;
    if held.key_down(SDLK_a) || held.key_down(SDLK_LEFT) {
        move_x -= 1.0;
    }
    if held.key_down(SDLK_d) || held.key_down(SDLK_RIGHT) {
        move_x += 1.0;
    }
    if held.key_down(SDLK_w) || held.key_down(SDLK_UP) {
        move_y -= 1.0;
    }
    if held.key_down(SDLK_s) || held.key_down(SDLK_DOWN) {
        move_y += 1.0;
    }

    let mut buttons = 0;
    if held.key_down(SDLK_SPACE) {
        buttons |= GC_BTN_DASH;
    }
    if held.key_down(SDLK_ESCAPE) {
        buttons |= GC_BTN_PAUSE;
    }
    if held.key_down(SDLK_r) {
        buttons |= GC_BTN_RESTART;
    }

    let s = if scale > 0.0 { scale } else { 1.0 };
    let _ = fingerprint;
    gc_input {
        move_x,
        move_y,
        aim_x: held.mouse.0 / s,
        aim_y: held.mouse.1 / s,
        pointer_active: 1,
        pointer_down: i32::from(held.pointer_down),
        buttons,
    }
}

// -- scripted scenarios (headless verification) -----------------------------

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
enum Scenario {
    Title,
    /// Straight autoplay, no debug cheats: used to eyeball the difficulty curve.
    Survive,
    Combat,
    /// A run loaded with the phantom upgrades, to eyeball the ghost army.
    Phantom,
    /// The options screen, opened from the title.
    Options,
    /// All three specialist enemies on screen at once, for the art and behaviour
    /// to be looked at rather than assumed.
    Enemies,
    LevelUp,
    Shop,
    GameOver,
    Tour,
}

impl Scenario {
    fn parse(name: &str) -> Scenario {
        match name {
            "phantom" => Scenario::Phantom,
            "options" => Scenario::Options,
            "enemies" => Scenario::Enemies,
            "title" => Scenario::Title,
            "survive" => Scenario::Survive,
            "combat" => Scenario::Combat,
            "levelup" => Scenario::LevelUp,
            "shop" => Scenario::Shop,
            "gameover" => Scenario::GameOver,
            _ => Scenario::Tour,
        }
    }
}

/// Drives the game with synthetic input and says when to capture a frame.
///
/// This is not a mock: it is the same ABI a human uses, including clicking the
/// real UI rectangles the library reports through `gc_ui_slot`/`gc_ui_button`.
struct Driver {
    scenario: Scenario,
    frame: u64,
    end: u64,
    shots: Vec<(u64, &'static str)>,
    pending: Option<&'static str>,
    click_at: Option<(u64, f32, f32)>,
    /// 0 = idle, 1..=2 = held, 3 = the release frame (same position).
    click_phase: u32,
}

impl Driver {
    fn new(scenario: Scenario) -> Driver {
        let (end, shots) = match scenario {
            Scenario::Title => (8, vec![(6, "01_title")]),
            Scenario::Survive => (90000, vec![]),
            Scenario::Enemies => (420, vec![(70, "01_enemy_charger"), (170, "02_enemy_spitter"),
                                            (300, "03_enemy_miser")]),
            Scenario::Options => (260, vec![(60, "01_options_open"), (150, "02_options_rows"),
                                           (240, "03_options_set")]),
            Scenario::Phantom => (520, vec![(150, "01_phantom_spawn"), (300, "02_phantom_fight"),
                                            (470, "03_phantom_fade")]),
            Scenario::Combat => (420, vec![(90, "01_combat_early"), (240, "02_combat_mid"),
                                           (410, "03_combat_late")]),
            Scenario::LevelUp => (160, vec![(60, "01_levelup_cards"), (150, "02_after_pick")]),
            Scenario::Shop => (320, vec![(140, "01_shop"), (300, "02_shop_bought")]),
            Scenario::GameOver => (400, vec![(210, "01_gameover")]),
            Scenario::Tour => (
                1500,
                vec![
                    // Capture the title before the click below starts the run.
                    (1, "01_title"),
                    (150, "02_combat_early"),
                    (420, "03_combat_mid"),
                    (560, "04_levelup_cards"),
                    (700, "05_combat_weapons"),
                    (900, "06_shop"),
                    (1000, "07_shop_bought"),
                    (1250, "08_combat_late"),
                    (1400, "09_gameover"),
                ],
            ),
        };
        Driver {
            scenario,
            frame: 0,
            end,
            shots,
            pending: None,
            click_at: None,
            click_phase: 0,
        }
    }

    /// Queues a click at a UI rect centre (virtual units).
    fn click(&mut self, x: f32, y: f32) {
        self.click_at = Some((self.frame + 1, x, y));
    }

    fn input(&mut self, api: &Api, handle: *mut game_core::Handle) -> gc_input {
        let f = self.frame;
        let mut input = gc_input {
            pointer_active: 1,
            ..Default::default()
        };

        // Aim follows a slow circle so the reticle and weapon rotation are both
        // visible in the captures; auto-aim still picks targets because the
        // button is not held.
        let aim_angle = f as f32 * 0.03;
        input.aim_x = 640.0 + aim_angle.cos() * 260.0;
        input.aim_y = 360.0 + aim_angle.sin() * 160.0;

        // Movement: a slow orbit around the arena centre.
        let orbit = f as f32 * 0.012;
        input.move_x = orbit.cos();
        input.move_y = orbit.sin() * 0.6;

        if f % 240 == 200 {
            input.buttons |= GC_BTN_DASH;
        }

        let debug = |cmd: i32, value: f32| unsafe { (api.debug)(handle, cmd, value) };
        let slot_center = |index: i32| -> (f32, f32) {
            let r = unsafe { (api.ui_slot)(handle, index) };
            (r.x + r.w * 0.5, r.y + r.h * 0.5)
        };
        let button_center = |which: i32| -> (f32, f32) {
            let r = unsafe { (api.ui_button)(handle, which) };
            (r.x + r.w * 0.5, r.y + r.h * 0.5)
        };
        // The options screen is an overlay, so it has no button slot: the driver
        // reaches it the way a player does, by clicking the title's button, and
        // then walks the rows by geometry.
        let options_button = || -> Option<(f32, f32)> {
            let r = unsafe { (api.ui_button)(handle, 5) };
            (r.w > 0.0).then(|| (r.x + r.w * 0.5, r.y + r.h * 0.5))
        };
        let option_row_center = |row: usize| -> Option<(f32, f32)> {
            // Rows are exposed as button slots 20.. just like every other
            // clickable thing the library owns.
            let r = unsafe { (api.ui_button)(handle, 20 + row as i32) };
            (r.w > 0.0).then(|| (r.x + r.w * 0.5, r.y + r.h * 0.5))
        };
        // Cheapest node that is on screen and affordable: what a player would
        // naturally tap next.
        let best_node = || -> Option<(f32, f32)> {
            let count = unsafe { (api.tree_count)() };
            let mut best: Option<(f32, f32, i32)> = None;
            for node in 0..count {
                if unsafe { (api.tree_state)(handle, node) } != 2 {
                    continue;
                }
                let rect = unsafe { (api.tree_rect)(handle, node) };
                if rect.w <= 0.0 {
                    continue;
                }
                let cost = unsafe { (api.tree_cost)(handle, node) };
                if best.map_or(true, |(_, _, c)| cost < c) {
                    best = Some((rect.x + rect.w * 0.5, rect.y + rect.h * 0.5, cost));
                }
            }
            best.map(|(x, y, _)| (x, y))
        };

        // -- scenario scripts -------------------------------------------------
        match self.scenario {
            Scenario::Title => {}
            Scenario::Survive => {
                if f == 2 {
                    let (x, y) = button_center(0);
                    self.click(x, y);
                }
                // Economy tuning run: invulnerable so the bot survives long
                // enough to show the income curve against the 10-wave quota.
                if f == 6 {
                    debug(game_core::GC_DBG_INVULNERABLE, 1.0);
                }
                // Kite in a wide circle, dashing whenever it is up.
                input.move_x = (f as f32 * 0.0075).cos();
                input.move_y = (f as f32 * 0.0075).sin();
                if f % 180 == 0 {
                    input.buttons |= GC_BTN_DASH;
                }
                // Buy from the hive whenever the shop is open, otherwise take
                // a level-up card.
                if f % 9 == 0 {
                    if let Some((x, y)) = best_node() {
                        self.click(x, y);
                    }
                } else if unsafe { (api.ui_slot_count)(handle) } == 3 && f % 9 == 4 {
                    let (x, y) = slot_center((f as i32 / 9) % 3);
                    self.click(x, y);
                } else if f % 9 == 6 && unsafe { (api.ui_slot_count)(handle) } == 0 {
                    let (x, y) = button_center(1);
                    self.click(x, y);
                }
            }
            Scenario::Combat | Scenario::GameOver => {
                if f == 2 {
                    let (x, y) = button_center(0);
                    self.click(x, y);
                }
                if f == 6 {
                    debug(game_core::GC_DBG_GIVE_MONEY, 400.0);
                    debug(game_core::GC_DBG_GIVE_WEAPON, 1.0);
                    debug(game_core::GC_DBG_GIVE_WEAPON, 2.0);
                    debug(game_core::GC_DBG_SET_WAVE, 4.0);
                }
                if self.scenario == Scenario::GameOver && f == 200 {
                    debug(game_core::GC_DBG_KILL_PLAYER, 0.0);
                }
            }
            Scenario::Enemies => {
                if f == 2 {
                    let (x, y) = button_center(0);
                    self.click(x, y);
                }
                if f == 6 {
                    debug(game_core::GC_DBG_GIVE_MONEY, 3000.0);
                    debug(game_core::GC_DBG_GIVE_WEAPON, 1.0);
                    debug(game_core::GC_DBG_SET_WAVE, 12.0);
                    // One of each specialist: charger, spitter, miser.
                    debug(game_core::GC_DBG_SPAWN_ENEMY, 3.0);
                    debug(game_core::GC_DBG_SPAWN_ENEMY, 4.0);
                    debug(game_core::GC_DBG_SPAWN_ENEMY, 5.0);
                }
                // Keep topping up so the frame is never empty.
                if f > 6 && f % 90 == 0 {
                    debug(game_core::GC_DBG_SPAWN_ENEMY, 3.0);
                    debug(game_core::GC_DBG_SPAWN_ENEMY, 4.0);
                    debug(game_core::GC_DBG_SPAWN_ENEMY, 5.0);
                }
            }
            Scenario::Options => {
                // Title -> OPTIONS, then walk the rows and step a couple of
                // values so the panel shows a mix of states.
                if f == 20 {
                    if let Some((x, y)) = options_button() {
                        self.click(x, y);
                    }
                }
                if (40..=200).contains(&f) && f % 20 == 0 {
                    let row = (f - 40) / 20;
                    if let Some((x, y)) = option_row_center(row as usize) {
                        self.click(x, y);
                    }
                }
                if f == 220 {
                    if let Some((x, y)) = option_row_center(4) {
                        self.click(x, y);
                    }
                }
            }
            Scenario::Phantom => {
                if f == 2 {
                    let (x, y) = button_center(0);
                    self.click(x, y);
                }
                if f == 6 {
                    debug(game_core::GC_DBG_GIVE_MONEY, 4000.0);
                    debug(game_core::GC_DBG_GIVE_WEAPON, 1.0);
                    debug(game_core::GC_DBG_SET_WAVE, 9.0);
                    // PHANTOM, PHANTOM FURY, PHANTOM SWARM, TWIN FIRE.
                    for _ in 0..5 {
                        debug(game_core::GC_DBG_GRANT_PERK, 35.0);
                    }
                    for _ in 0..4 {
                        debug(game_core::GC_DBG_GRANT_PERK, 36.0);
                    }
                    for _ in 0..3 {
                        debug(game_core::GC_DBG_GRANT_PERK, 37.0);
                    }
                    for _ in 0..3 {
                        debug(game_core::GC_DBG_GRANT_PERK, 38.0);
                    }
                }
            }
            Scenario::LevelUp => {
                if f == 2 {
                    let (x, y) = button_center(0);
                    self.click(x, y);
                }
                if f == 30 {
                    debug(game_core::GC_DBG_LEVEL_UP, 0.0);
                }
                if f == 120 {
                    // Pick the first card through the reported UI rect.
                    let (x, y) = slot_center(0);
                    self.click(x, y);
                }
            }
            Scenario::Shop => {
                if f == 2 {
                    let (x, y) = button_center(0);
                    self.click(x, y);
                }
                if f == 20 {
                    debug(game_core::GC_DBG_GIVE_MONEY, 500.0);
                    debug(game_core::GC_DBG_SET_WAVE, 3.0);
                }
                if f == 60 {
                    debug(game_core::GC_DBG_SKIP_WAVE, 0.0);
                }
                if f == 200 {
                    let (x, y) = slot_center(0);
                    self.click(x, y);
                }
                if f == 260 {
                    let (x, y) = slot_center(2);
                    self.click(x, y);
                }
            }
            Scenario::Tour => {
                if f == 3 {
                    let (x, y) = button_center(0);
                    self.click(x, y);
                }
                if f == 8 {
                    debug(game_core::GC_DBG_GIVE_WEAPON, 1.0);
                    debug(game_core::GC_DBG_GIVE_WEAPON, 2.0);
                    debug(game_core::GC_DBG_GIVE_MONEY, 600.0);
                    debug(game_core::GC_DBG_SET_WAVE, 5.0);
                }
                if f == 470 {
                    debug(game_core::GC_DBG_LEVEL_UP, 0.0);
                }
                if f == 620 {
                    let (x, y) = slot_center(1);
                    self.click(x, y);
                }
                if f == 760 {
                    debug(game_core::GC_DBG_SKIP_WAVE, 0.0);
                }
                // In the hive: buy a few nodes, panning between them.
                if (920..=1130).contains(&f) && f % 30 == 0 {
                    if let Some((x, y)) = best_node() {
                        self.click(x, y);
                    }
                }
                if f == 1140 {
                    let (x, y) = button_center(1);
                    self.click(x, y);
                }
                if f == 1180 {
                    debug(game_core::GC_DBG_SET_WAVE, 14.0);
                    debug(game_core::GC_DBG_GIVE_MONEY, 900.0);
                    // Buy a pile of the new upgrades so the late captures show
                    // orbitals, lightning, exploding rounds and extra lives.
                    for perk in [2.0, 3.0, 12.0, 15.0, 16.0, 17.0, 18.0, 19.0, 20.0,
                                 21.0, 22.0, 23.0, 24.0, 25.0, 26.0, 27.0, 28.0] {
                        debug(game_core::GC_DBG_GRANT_PERK, perk);
                    }
                }
                if f == 1380 {
                    debug(game_core::GC_DBG_KILL_PLAYER, 0.0);
                }
            }
        }

        // Apply a queued click: two held frames, then a release *at the same
        // spot* (the hive buys on release so that panning never spends money).
        if let Some((when, x, y)) = self.click_at {
            if f >= when {
                input.aim_x = x;
                input.aim_y = y;
                self.click_phase += 1;
                input.pointer_down = i32::from(self.click_phase <= 2);
                if self.click_phase > 3 {
                    self.click_at = None;
                    self.click_phase = 0;
                }
            }
        }

        self.frame += 1;
        input
    }

    /// Returns a screenshot label if this frame should be captured.
    fn shot(&mut self) -> Option<&'static str> {
        let f = self.frame.saturating_sub(1);
        if self.pending.is_some() {
            return self.pending.take();
        }
        if let Some((_, label)) = self.shots.iter().find(|(when, _)| *when == f as u64) {
            let label: &'static str = label;
            self.pending = Some(label);
        }
        self.pending.take()
    }

    fn finished(&self, frames_override: u32) -> bool {
        let limit = if frames_override > 0 { frames_override as u64 } else { self.end };
        self.frame >= limit
    }
}

// -- persistence ------------------------------------------------------------

fn default_save_path(headless: bool, out_dir: &Path) -> PathBuf {
    if headless {
        return out_dir.join("save.bin");
    }
    if let Ok(path) = std::env::var("SLIME_ARENA_SAVE") {
        return PathBuf::from(path);
    }
    let base = std::env::var("XDG_DATA_HOME").unwrap_or_else(|_| {
        let home = std::env::var("HOME").unwrap_or_else(|_| ".".to_string());
        format!("{}/.local/share", home)
    });
    PathBuf::from(base).join("slime_arena").join("save.bin")
}

fn load_save(api: &Api, handle: *mut game_core::Handle, path: &Path) {
    if let Ok(bytes) = std::fs::read(path) {
        let loaded = unsafe { (api.load)(handle, bytes.as_ptr(), bytes.len() as i32) };
        if loaded != 0 {
            println!("slime_arena: loaded save data from {}", path.display());
        }
    }
}

fn store_save(api: &Api, handle: *mut game_core::Handle, path: &Path) {
    let mut buf = [0u8; 64];
    let written = unsafe { (api.save)(handle, buf.as_mut_ptr(), buf.len() as i32) };
    if written <= 0 {
        return;
    }
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let _ = std::fs::write(path, &buf[..written as usize]);
}

// -- main -------------------------------------------------------------------

fn main() {
    let opts = parse_args();

    if opts.headless {
        // The dummy video driver gives us a window-less window and a software
        // renderer, so the whole pipeline can run on a build machine.
        std::env::set_var("SDL_VIDEODRIVER", "dummy");
    }

    if unsafe { SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_TIMER) } != 0 {
        eprintln!("slime_arena: SDL_Init failed: {}", last_error());
        std::process::exit(1);
    }

    let quality = CString::new("1").unwrap();
    unsafe { SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY.as_ptr() as *const _, quality.as_ptr()) };

    let title = CString::new("Slime Arena").unwrap();
    let window = unsafe {
        SDL_CreateWindow(title.as_ptr(), SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                         opts.width, opts.height,
                         SDL_WINDOW_SHOWN | SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI)
    };
    if window.is_null() {
        eprintln!("slime_arena: SDL_CreateWindow failed: {}", last_error());
        unsafe { SDL_Quit() };
        std::process::exit(1);
    }

    let render_flags = if opts.headless {
        SDL_RENDERER_SOFTWARE
    } else {
        SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC
    };
    let mut raw = unsafe { SDL_CreateRenderer(window, -1, render_flags) };
    if raw.is_null() && !opts.headless {
        eprintln!("slime_arena: no accelerated renderer ({}); falling back to software",
                  last_error());
        raw = unsafe { SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE) };
    }
    if raw.is_null() {
        eprintln!("slime_arena: SDL_CreateRenderer failed: {}", last_error());
        unsafe { SDL_DestroyWindow(window) };
        unsafe { SDL_Quit() };
        std::process::exit(1);
    }

    let exit_code = run(&opts, window, raw);

    unsafe {
        SDL_DestroyRenderer(raw);
        SDL_DestroyWindow(window);
        SDL_Quit();
    }
    std::process::exit(exit_code);
}

/// Loads every texture and reports what is actually in the pixels.  Useful when
/// a texture looks right in an image viewer but wrong on screen.
fn check_assets(dir: &Path) {
    let names = ["player.png", "enemy_a.png", "enemy_b.png", "gun.png", "bow.png",
                 "sword.png", "money.png", "xp.png",
                 "charger.png", "spitter.png", "miser.png", "font_atlas.png"];
    for name in names {
        let path = dir.join(name);
        match png::load_rgba(&path.to_string_lossy()) {
            Ok(img) => {
                let mut min_a = 255u8;
                let mut max_a = 0u8;
                let mut opaque = 0usize;
                for px in img.pixels.chunks_exact(4) {
                    min_a = min_a.min(px[3]);
                    max_a = max_a.max(px[3]);
                    if px[3] > 8 {
                        opaque += 1;
                    }
                }
                println!("{:<16} {:>4}x{:<4} alpha {}..{}  visible px {}",
                         name, img.width, img.height, min_a, max_a, opaque);
            }
            Err(err) => println!("{:<16} FAILED: {}", name, err),
        }
    }
}

fn dump_commands(cmds: &[game_core::gc_cmd], limit: u32) {
    println!("--- {} commands, showing {}", cmds.len(), limit.min(cmds.len() as u32));
    let mut kinds = [0u32; 4];
    for c in cmds {
        let k = c.kind.clamp(0, 3) as usize;
        kinds[k] += 1;
    }
    println!("sprite={} rect={} glyph={} other={}",
             kinds[game_core::GC_CMD_SPRITE as usize],
             kinds[game_core::GC_CMD_RECT as usize],
             kinds[game_core::GC_CMD_GLYPH as usize], kinds[0]);
    for (i, c) in cmds.iter().take(limit as usize).enumerate() {
        if c.kind == game_core::GC_CMD_SPRITE {
            println!("{:4} SPRITE id={} c=({:.1},{:.1}) wh=({:.1},{:.1}) rot={:.2} rgba={:08x} flags={}",
                     i, c.sprite, c.x, c.y, c.w, c.h, c.rot, c.rgba, c.flags);
        } else if c.kind == game_core::GC_CMD_GLYPH {
            println!("{:4} GLYPH c=({:.1},{:.1}) wh=({:.1},{:.1}) uv=({:.3},{:.3})-({:.3},{:.3}) rgba={:08x} flags={}",
                     i, c.x, c.y, c.w, c.h, c.u0, c.v0, c.u1, c.v1, c.rgba, c.flags);
        } else {
            println!("{:4} RECT  c=({:.1},{:.1}) wh=({:.1},{:.1}) rot={:.2} rgba={:08x} flags={}",
                     i, c.x, c.y, c.w, c.h, c.rot, c.rgba, c.flags);
        }
    }
}

fn run(opts: &Options, window: *mut SdlWindow, raw: *mut SdlRenderer) -> i32 {
    let (api, mode) = Api::load();
    println!("slime_arena: game logic from {}", mode.describe());

    let abi = unsafe { (api.abi_version)() };
    if abi != GC_ABI_VERSION {
        eprintln!("slime_arena: ABI mismatch -- library {} vs shell {}",
                  abi, GC_ABI_VERSION);
        return 1;
    }

    let handle = unsafe { (api.create)(opts.seed) };
    if handle.is_null() {
        eprintln!("slime_arena: gc_create returned NULL");
        return 1;
    }

    // Assets.
    let mut asset_dir = None;
    for candidate in renderer::asset_dir_candidates(opts.assets.as_deref()) {
        if candidate.join("player.png").exists() {
            asset_dir = Some(candidate);
            break;
        }
    }
    let Some(asset_dir) = asset_dir else {
        eprintln!("slime_arena: could not find the sprite PNGs (assets/dist).\n\
                   Run ./tools/build_assets.sh, or pass --assets DIR.");
        unsafe { (api.destroy)(handle) };
        return 1;
    };
    println!("slime_arena: assets from {}", asset_dir.display());

    let mut renderer = Renderer::new(raw);
    if let Err(err) = renderer.load_assets(&api, handle, &asset_dir) {
        eprintln!("slime_arena: failed to load assets: {}", err);
        unsafe { (api.destroy)(handle) };
        return 1;
    }

    if opts.diag_textures {
        let _ = std::fs::create_dir_all(&opts.out_dir);
        let path = opts.out_dir.join("diag_textures.png");
        match renderer.diag_textures(&path, 1280, 720) {
            Ok(()) => println!("slime_arena: wrote {}", path.display()),
            Err(err) => eprintln!("slime_arena: diag failed: {}", err),
        }
        unsafe { (api.destroy)(handle) };
        return 0;
    }

    if opts.check_assets {
        check_assets(&asset_dir);
        unsafe { (api.destroy)(handle) };
        return 0;
    }

    // Audio: on by default when there is a window, opt-in for headless runs.
    let audio_enabled = !opts.no_audio && (!opts.headless || opts.audio)
        && std::env::var("SLIME_ARENA_AUDIO").map(|v| v != "0").unwrap_or(true);
    let mut audio = Audio::new(&asset_dir, audio_enabled);

    let save_path = default_save_path(opts.headless, &opts.out_dir);
    load_save(&api, handle, &save_path);

    // Window geometry in physical pixels.
    let mut fb_w = 0i32;
    let mut fb_h = 0i32;
    unsafe { SDL_GetWindowSizeInPixels(window, &mut fb_w, &mut fb_h) };
    if fb_w <= 0 || fb_h <= 0 {
        unsafe { SDL_GetWindowSize(window, &mut fb_w, &mut fb_h) };
    }
    unsafe { (api.resize)(handle, fb_w, fb_h, 0.0, 0.0, 0.0, 0.0) };

    if opts.headless {
        let _ = std::fs::create_dir_all(&opts.out_dir);
    }

    let mut held = Held::default();
    let mut fullscreen = false;
    let mut driver = Driver::new(Scenario::parse(&opts.scenario));
    let mut last = Instant::now();
    let mut frame: u64 = 0;
    let mut title_timer = Instant::now();

    loop {
        let dt = if opts.headless {
            1.0 / 60.0
        } else {
            let dt = last.elapsed().as_secs_f32();
            dt.clamp(0.0, 0.1)
        };
        last = Instant::now();

        poll_events(&mut held);
        if held.quit {
            break;
        }
        let mut state = gc_status::default();
        unsafe { (api.status_get)(handle, &mut state) };

        // Settings edited in the options screen: the shell owns volume and
        // fullscreen, the library owns everything else.
        {
            let mut set = gc_settings::default();
            if unsafe { (api.settings_get)(handle, &mut set) } == 0 {
                audio.set_volumes(set.music, set.sfx);
                if set.fullscreen != 0 && !fullscreen {
                    unsafe { SDL_SetWindowFullscreen(window, SDL_WINDOW_FULLSCREEN_DESKTOP) };
                    fullscreen = true;
                } else if set.fullscreen == 0 && fullscreen {
                    unsafe { SDL_SetWindowFullscreen(window, 0) };
                    fullscreen = false;
                }
            }
        }

        // A wheel notch scrolls the hive (and only the hive).
        if held.synth.is_none() && held.wheel != 0.0 {
            if state.state == GC_STATE_SHOP {
                held.synth = Some(SynthDrag {
                    origin: held.mouse,
                    // Wheel up (positive) should reveal what is above.
                    dy: (-held.wheel * 120.0).clamp(-360.0, 360.0),
                    frame: 0,
                });
            }
            held.wheel = 0.0;
        }
        if let Some(drag) = &mut held.synth {
            drag.frame += 1;
            if drag.frame > 2 {
                held.synth = None;
            }
        }
        if held.resized {
            held.resized = false;
            unsafe { SDL_GetWindowSizeInPixels(window, &mut fb_w, &mut fb_h) };
            if fb_w > 0 && fb_h > 0 {
                unsafe { (api.resize)(handle, fb_w, fb_h, 0.0, 0.0, 0.0, 0.0) };
            }
        }

        let scale = unsafe { (api.view_scale)(handle) };
        let input = if opts.headless {
            driver.input(&api, handle)
        } else {
            build_input(&held, scale, false)
        };

        for sym in held.presses.drain(..) {
            match sym {
                SDLK_M => {
                    let muted = audio.toggle_mute();
                    println!("slime_arena: audio {}", if muted { "muted" } else { "on" });
                }
                SDLK_O => {
                    let open = unsafe { (api.options_open)(handle) } != 0;
                    unsafe { (api.options_set_open)(handle, i32::from(!open)) };
                }
                SDLK_MINUS => audio.nudge_volume(-1),
                SDLK_EQUALS => audio.nudge_volume(1),
                _ => {}
            }
        }

        unsafe { (api.update)(handle, &input, dt) };

        // Sound follows the core's event stream and the arena's mood.
        {
            let mut count = 0i32;
            let events = unsafe { (api.events)(handle, &mut count) };
            if !events.is_null() && count > 0 {
                let events = unsafe { std::slice::from_raw_parts(events, count as usize) };
                for e in events {
                    audio.play_event(e.type_);
                }
            }
            // The hive and the title screen get the menu track; combat gets the
            // track for the arena's current mood.
            let menu = state.state == GC_STATE_SHOP || state.state == GC_STATE_TITLE;
            audio.select_music(menu, unsafe { (api.theme_index)(handle) });
            audio.update(dt);
        }

        let mut count = 0i32;
        let cmds = unsafe { (api.cmds)(handle, &mut count) };
        let cmds = if cmds.is_null() || count <= 0 {
            &[][..]
        } else {
            unsafe { std::slice::from_raw_parts(cmds, count as usize) }
        };

        if opts.dump > 0 && frame == 0 {
            dump_commands(cmds, opts.dump);
            unsafe { (api.destroy)(handle) };
            return 0;
        }

        renderer.scale = unsafe { (api.view_scale)(handle) };
        renderer.clear();
        renderer.draw(cmds);
        // Grain/dither film over the finished frame, under the OS cursor.
        renderer.draw_grain(fb_w as f32, fb_h as f32);
        renderer.present();

        if opts.stats && opts.headless && frame % 60 == 0 {
            let mut st = gc_status::default();
            unsafe { (api.status_get)(handle, &mut st) };
            let mut pr = game_core::gc_progress::default();
            unsafe { (api.progress_get)(handle, &mut pr) };
            println!(
                "t={:5.1}s wave={:<3} tier={:<2} lvl={:<3} kills={:<4} hp={:>5.1}/{:<5.1} \
                 $ {:<5} earned={:<6} quota={:<6} @w{:<3} score={}",
                st.time_alive, st.wave, pr.tier, st.level, st.kills, st.player_hp,
                st.player_hp_max, st.money, pr.money_earned, pr.goal, pr.goal_wave, st.score);
        }

        if opts.headless {
            if let Some(label) = driver.shot() {
                let path = opts.out_dir.join(format!("{}.png", label));
                match renderer.capture(&path, fb_w, fb_h) {
                    Ok(()) => println!("slime_arena: wrote {} ({} commands, {} draws)",
                                       path.display(), cmds.len(), renderer.draws),
                    Err(err) => eprintln!("slime_arena: screenshot failed: {}", err),
                }
            }
        }

        // Window title mirrors the game state, which is a nice smoke test that
        // status reporting works.
        if !opts.headless && title_timer.elapsed().as_secs_f32() > 0.5 {
            title_timer = Instant::now();
            let mut status = gc_status::default();
            unsafe { (api.status_get)(handle, &mut status) };
            let text = format!("Slime Arena -- wave {} | score {} | best {} | {} fps cmds {}",
                               status.wave, status.score, status.best_score, cmds.len(),
                               renderer.draws);
            if let Ok(c) = CString::new(text) {
                unsafe { SDL_SetWindowTitle(window, c.as_ptr()) };
            }
        }

        frame += 1;
        if opts.headless && driver.finished(opts.frames) {
            break;
        }
    }

    audio.shutdown();
    store_save(&api, handle, &save_path);
    unsafe { (api.destroy)(handle) };
    let _ = Mode::SharedLibrary;
    let _ = frame;
    0
}
