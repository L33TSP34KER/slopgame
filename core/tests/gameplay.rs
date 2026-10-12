//! End-to-end gameplay tests.
//!
//! These deliberately drive the *public C ABI* rather than internal functions,
//! so they exercise exactly what a platform renderer sees: create, resize,
//! update, read commands/events/status, click UI rectangles, save and load.
//!
//! Run with `cargo test -p game_core`.

use game_core::*;
use std::ffi::CStr;

// ---------------------------------------------------------------------------
// a tiny scriptable client, i.e. what every renderer implements
// ---------------------------------------------------------------------------

struct Client {
    handle: *mut Handle,
    view_w: f32,
    view_h: f32,
    scale: f32,
    time: f32,
    frames: u32,
}

impl Client {
    fn new(seed: u32) -> Client {
        let mut client = Client {
            handle: gc_create(seed),
            view_w: 0.0,
            view_h: 0.0,
            scale: 1.0,
            time: 0.0,
            frames: 0,
        };
        assert!(!client.handle.is_null(), "gc_create returned NULL");
        client.resize(1280, 720, [0.0; 4]);
        client
    }

    fn resize(&mut self, w: i32, h: i32, safe: [f32; 4]) {
        unsafe { gc_resize(self.handle, w, h, safe[0], safe[1], safe[2], safe[3]) };
        let mut vw = 0.0;
        let mut vh = 0.0;
        unsafe { gc_virtual_size(self.handle, &mut vw, &mut vh) };
        self.view_w = vw;
        self.view_h = vh;
        self.scale = unsafe { gc_view_scale(self.handle) };
    }

    fn step(&mut self, input: &gc_input, dt: f32) {
        unsafe { gc_update(self.handle, input, dt) };
        self.time += dt;
        self.frames += 1;
    }

    /// Steps with neutral input (no pointer, no buttons).
    fn idle(&mut self, frames: u32) {
        let input = gc_input::default();
        for _ in 0..frames {
            self.step(&input, 1.0 / 60.0);
        }
    }

    fn cmds(&self) -> Vec<gc_cmd> {
        let mut count = 0;
        let ptr = unsafe { gc_cmds(self.handle, &mut count) };
        assert!(!ptr.is_null(), "gc_cmds returned NULL");
        unsafe { std::slice::from_raw_parts(ptr, count as usize) }.to_vec()
    }

    fn status(&self) -> gc_status {
        let mut status = gc_status::default();
        unsafe { gc_status_get(self.handle, &mut status) };
        status
    }

    fn button_center(&self, which: i32) -> (f32, f32) {
        let r = unsafe { gc_ui_button(self.handle, which) };
        (r.x + r.w * 0.5, r.y + r.h * 0.5)
    }

    fn slot_center(&self, index: i32) -> (f32, f32) {
        let r = unsafe { gc_ui_slot(self.handle, index) };
        (r.x + r.w * 0.5, r.y + r.h * 0.5)
    }

    /// A tap at a virtual-unit position: press, then release at the *same*
    /// place (the hive buys on release, so a drag can never spend money).
    fn click(&mut self, x: f32, y: f32) {
        let press = gc_input {
            aim_x: x,
            aim_y: y,
            pointer_active: 1,
            pointer_down: 1,
            ..Default::default()
        };
        let release = gc_input {
            aim_x: x,
            aim_y: y,
            pointer_active: 1,
            pointer_down: 0,
            ..Default::default()
        };
        self.step(&press, 1.0 / 60.0);
        self.step(&press, 1.0 / 60.0);
        self.step(&release, 1.0 / 60.0);
    }

    fn click_button(&mut self, which: i32) {
        let (x, y) = self.button_center(which);
        self.click(x, y);
    }

    fn click_slot(&mut self, index: i32) {
        let (x, y) = self.slot_center(index);
        self.click(x, y);
    }

    fn debug(&mut self, cmd: i32, value: f32) {
        unsafe { gc_debug(self.handle, cmd, value) };
    }

    fn start_run(&mut self) {
        self.click_button(0);
        assert_eq!(self.status().state, GC_STATE_PLAYING, "clicking start must begin a run");
    }
}

impl Drop for Client {
    fn drop(&mut self) {
        unsafe { gc_destroy(self.handle) };
    }
}

/// Every command must be sane: finite numbers, non-degenerate quads, UVs in
/// range.  A renderer would produce garbage otherwise.
fn assert_commands_sane(cmds: &[gc_cmd], context: &str) {
    for (i, c) in cmds.iter().enumerate() {
        let ctx = format!("{} command {}", context, i);
        for (name, v) in [("x", c.x), ("y", c.y), ("w", c.w), ("h", c.h), ("rot", c.rot)] {
            assert!(v.is_finite(), "{}: {} is not finite ({})", ctx, name, v);
        }
        assert!(c.w > 0.0 && c.w < 20000.0, "{}: bad width {}", ctx, c.w);
        assert!(c.h > 0.0 && c.h < 20000.0, "{}: bad height {}", ctx, c.h);
        assert!(c.rot.abs() < 1000.0, "{}: bad rotation {}", ctx, c.rot);
        match c.kind {
            GC_CMD_SPRITE => {
                assert!(c.sprite >= 0 && c.sprite < SPRITE_COUNT as i32,
                        "{}: sprite id out of range: {}", ctx, c.sprite);
            }
            GC_CMD_GLYPH => {
                assert!(c.u0 >= 0.0 && c.v0 >= 0.0 && c.u1 <= 1.0001 && c.v1 <= 1.0001,
                        "{}: uv out of range {} {} {} {}", ctx, c.u0, c.v0, c.u1, c.v1);
                assert!(c.u1 > c.u0 && c.v1 > c.v0, "{}: empty glyph uv", ctx);
            }
            GC_CMD_RECT => {}
            other => panic!("{}: unknown command kind {}", ctx, other),
        }
    }
}

// ---------------------------------------------------------------------------
// ABI surface
// ---------------------------------------------------------------------------

#[test]
fn reports_its_abi_version() {
    assert_eq!(gc_abi_version(), GC_ABI_VERSION);
}

#[test]
fn names_every_asset_a_renderer_must_load() {
    for i in 0..SPRITE_COUNT as i32 {
        let ptr = gc_sprite_file(i);
        assert!(!ptr.is_null(), "sprite {} has no file name", i);
        let name = unsafe { CStr::from_ptr(ptr) }.to_str().unwrap().to_string();
        assert!(name.ends_with(".png"), "sprite {} name is {}", i, name);
    }
    assert!(gc_sprite_file(-1).is_null());
    assert!(gc_sprite_file(SPRITE_COUNT as i32).is_null());

    let mut file: *const std::os::raw::c_char = std::ptr::null();
    let mut w = 0;
    let mut h = 0;
    unsafe { gc_font_atlas(&mut file, &mut w, &mut h) };
    assert!(!file.is_null());
    let name = unsafe { CStr::from_ptr(file) }.to_str().unwrap().to_string();
    assert!(name.ends_with(".png"));
    assert!(w > 0 && h > 0, "font atlas has no size");
}

#[test]
fn null_and_out_of_range_arguments_are_survivable() {
    // A sloppy renderer must not be able to crash the game logic.
    unsafe {
        gc_destroy(std::ptr::null_mut());
        gc_update(std::ptr::null_mut(), std::ptr::null(), 0.016);
        gc_resize(std::ptr::null_mut(), 100, 100, 0.0, 0.0, 0.0, 0.0);
        gc_debug(std::ptr::null_mut(), GC_DBG_GIVE_MONEY, 10.0);
        assert!(gc_cmds(std::ptr::null(), std::ptr::null_mut()).is_null());
        assert!(gc_events(std::ptr::null(), std::ptr::null_mut()).is_null());
        assert_eq!(gc_view_scale(std::ptr::null()), 1.0);
        assert_eq!(gc_save(std::ptr::null(), std::ptr::null_mut(), 0), -1);
    }

    let mut client = Client::new(7);
    // Negative / absurd sizes must not produce a broken view.
    client.resize(-5, 0, [0.0; 4]);
    assert!(client.scale > 0.0 && client.view_w > 0.0 && client.view_h > 0.0);
    client.step(&gc_input::default(), 0.016);
    assert_commands_sane(&client.cmds(), "after absurd resize");
}

// ---------------------------------------------------------------------------
// frame output
// ---------------------------------------------------------------------------

#[test]
fn a_frame_is_drawable_and_describes_the_hud() {
    let mut client = Client::new(11);
    client.idle(2);
    let cmds = client.cmds();
    assert!(cmds.len() > 50, "expected a populated frame, got {}", cmds.len());
    assert_commands_sane(&cmds, "title frame");

    let sprites = cmds.iter().filter(|c| c.kind == GC_CMD_SPRITE).count();
    let glyphs = cmds.iter().filter(|c| c.kind == GC_CMD_GLYPH).count();
    let rects = cmds.iter().filter(|c| c.kind == GC_CMD_RECT).count();
    assert!(sprites > 0, "the title screen should draw sprites");
    assert!(glyphs > 50, "the title screen should draw text");
    assert!(rects > 0, "the title screen should draw panels");
}

#[test]
fn the_view_follows_the_framebuffer_and_the_safe_area() {
    let mut client = Client::new(3);
    client.resize(1280, 720, [0.0; 4]);
    assert!((client.view_w - 1280.0).abs() < 0.5);
    assert!((client.view_h - 720.0).abs() < 0.5);
    assert!((client.scale - 1.0).abs() < 1e-4);

    // Same virtual size on a 2x display.
    client.resize(2560, 1440, [0.0; 4]);
    assert!((client.view_w - 1280.0).abs() < 0.5);
    assert!((client.scale - 2.0).abs() < 1e-3);

    // Portrait phone with a notch.  The design height is fixed, so a tall
    // framebuffer buys virtual *width*; the camera zoom is what keeps the
    // playable area sane on a narrow screen.
    client.resize(1170, 2532, [0.0, 132.0, 0.0, 102.0]);
    assert!((client.view_h - 720.0).abs() < 0.5, "design height is fixed");
    assert!(client.view_w < 400.0, "portrait is narrow in virtual units");
    let cmds = client.cmds();
    assert_commands_sane(&cmds, "portrait");

    // UI must stay inside the safe area.
    let (x, y) = client.button_center(0);
    assert!(x > 0.0 && x < client.view_w && y > 0.0 && y < client.view_h);
}

#[test]
fn every_command_stays_inside_a_sane_screen_range_when_the_camera_is_clamped() {
    let mut client = Client::new(5);
    client.start_run();
    // Walk hard into the arena wall.
    let input = gc_input { move_x: -1.0, move_y: -1.0, ..Default::default() };
    for _ in 0..240 {
        client.step(&input, 1.0 / 60.0);
    }
    let cmds = client.cmds();
    assert_commands_sane(&cmds, "against the wall");
}

// ---------------------------------------------------------------------------
// gameplay
// ---------------------------------------------------------------------------

#[test]
fn a_run_starts_survives_waves_and_ends() {
    let mut client = Client::new(1234);
    assert_eq!(client.status().state, GC_STATE_TITLE);
    client.start_run();

    // Play for a while with the player invulnerable, killing waves instantly.
    client.debug(GC_DBG_INVULNERABLE, 1.0);
    client.debug(GC_DBG_SET_WAVE, 3.0);
    client.idle(60);

    let mut status = client.status();
    assert_eq!(status.state, GC_STATE_PLAYING);
    assert_eq!(status.wave, 3);
    assert!(status.player_hp > 0.0);

    // Clear the wave: the game must move on to the hive.
    client.debug(GC_DBG_SKIP_WAVE, 0.0);
    client.idle(120);
    status = client.status();
    assert_eq!(status.state, GC_STATE_SHOP, "clearing a wave opens the hive");
    assert!(gc_tree_count() >= 200, "the upgrade tree must be big");

    // Buy the cheapest available node, then start the next wave.
    client.debug(GC_DBG_GIVE_MONEY, 1000.0);
    let before = client.status();
    let node = client.cheapest_available_node().expect("something must be buyable");
    let cost = unsafe { gc_tree_cost(client.handle, node) };
    let rect = unsafe { gc_tree_rect(client.handle, node) };
    assert!(rect.w > 0.0, "an available node must have a rectangle");
    client.click(rect.x + rect.w * 0.5, rect.y + rect.h * 0.5);
    let after = client.status();
    assert!(after.money < before.money, "buying must cost money ({} -> {})",
            before.money, after.money);
    assert_eq!(before.money - after.money, cost, "the price charged must be the quoted one");
    assert_eq!(unsafe { gc_tree_state(client.handle, node) }, 3, "the node is now owned");
    assert_eq!(after.state, GC_STATE_SHOP, "buying keeps the hive open");

    client.click_button(1);
    assert_eq!(client.status().state, GC_STATE_PLAYING);
    assert_eq!(client.status().wave, 4, "next wave advances the counter");

    // Death.
    client.debug(GC_DBG_KILL_PLAYER, 0.0);
    assert_eq!(client.status().state, GC_STATE_GAME_OVER);
    assert!(client.status().best_score > 0, "a score should have been banked");
}

#[test]
fn levelling_up_offers_three_distinct_choices_that_can_be_taken() {
    let mut client = Client::new(99);
    client.start_run();
    client.debug(GC_DBG_INVULNERABLE, 1.0);
    client.debug(GC_DBG_LEVEL_UP, 0.0);
    assert_eq!(client.status().state, GC_STATE_LEVEL_UP);
    assert_eq!(client.ui_slot_count(), 3, "a level-up offers three cards");

    // The card rectangles must be distinct and inside the view.
    let rects: Vec<gc_rect> = (0..3).map(|i| unsafe { gc_ui_slot(client.handle, i) }).collect();
    for r in &rects {
        assert!(r.w > 0.0 && r.h > 0.0);
        assert!(r.x >= 0.0 && r.x + r.w <= client.view_w + 1.0);
        assert!(r.y >= 0.0 && r.y + r.h <= client.view_h + 1.0);
    }
    assert!(rects[0].x < rects[1].x, "cards should be laid out left to right in landscape");

    let level_before = client.status().level;
    client.click_slot(1);
    let status = client.status();
    assert_eq!(status.state, GC_STATE_PLAYING, "picking a card resumes play");
    assert_eq!(status.level, level_before);
}

#[test]
fn enemies_spawn_chase_and_can_be_killed_for_xp_and_money() {
    let mut client = Client::new(4242);
    client.start_run();
    client.debug(GC_DBG_INVULNERABLE, 1.0);
    client.debug(GC_DBG_SET_WAVE, 2.0);

    // Let the swarm build up, then confirm it actually converges on the player.
    client.idle(180);
    let mut saw_enemy = false;
    for _ in 0..600 {
        client.step(&gc_input::default(), 1.0 / 60.0);
        if client.cmds().iter().any(|c| c.kind == GC_CMD_SPRITE && c.sprite == 1) {
            saw_enemy = true;
            break;
        }
    }
    assert!(saw_enemy, "enemies should be drawn during a wave");

    // Play it out: the gun auto-fires, so kills and pickups must accumulate.
    for _ in 0..1800 {
        client.step(&gc_input::default(), 1.0 / 60.0);
    }
    let status = client.status();
    assert!(status.kills > 0, "auto-fire should kill something eventually");
    assert!(status.score > 0);
}

#[test]
fn the_player_can_be_hurt_and_dashing_is_a_defensive_option() {
    let mut client = Client::new(31337);
    client.start_run();
    client.debug(GC_DBG_SET_WAVE, 4.0);

    // Stand still in the swarm until damage lands.
    let mut hurt = false;
    for _ in 0..2400 {
        client.step(&gc_input::default(), 1.0 / 60.0);
        if client.status().player_hp < client.status().player_hp_max {
            hurt = true;
            break;
        }
    }
    assert!(hurt, "standing in a swarm must eventually hurt the player");

    // Dashing while surrounded should trigger the dash event and its i-frames.
    let mut dashed = false;
    let input = gc_input {
        move_x: 1.0,
        buttons: GC_BTN_DASH,
        pointer_active: 1,
        ..Default::default()
    };
    for _ in 0..240 {
        client.step(&input, 1.0 / 60.0);
        let mut count = 0;
        let events = unsafe { gc_events(client.handle, &mut count) };
        let events = unsafe { std::slice::from_raw_parts(events, count as usize) };
        if events.iter().any(|e| e.type_ == GC_EVT_DASH) {
            dashed = true;
            break;
        }
    }
    assert!(dashed, "holding dash should produce a dash event");
}

#[test]
fn events_are_reported_for_the_renderer_to_turn_into_sound_and_haptics() {
    let mut client = Client::new(8);
    client.start_run();
    client.debug(GC_DBG_INVULNERABLE, 1.0);
    client.debug(GC_DBG_SET_WAVE, 5.0);

    let mut seen = std::collections::HashSet::new();
    for f in 0..900 {
        client.step(&gc_input::default(), 1.0 / 60.0);
        // Force a fresh wave through the normal path so the start event lands
        // inside a simulated frame (where renderers actually observe it).
        if f == 5 {
            client.debug(GC_DBG_SET_WAVE, 6.0);
        }
        let mut count = 0;
        let events = unsafe { gc_events(client.handle, &mut count) };
        assert!(!events.is_null());
        let events = unsafe { std::slice::from_raw_parts(events, count as usize) };
        for e in events {
            assert!(e.x.is_finite() && e.y.is_finite() && e.value.is_finite());
            seen.insert(e.type_);
        }
    }
    assert!(seen.contains(&GC_EVT_SHOOT), "weapons should report firing");
    assert!(seen.contains(&GC_EVT_WAVE_START), "waves should report starting");
}

// ---------------------------------------------------------------------------
// determinism, persistence, robustness
// ---------------------------------------------------------------------------

#[test]
fn the_same_seed_and_inputs_reproduce_the_exact_same_frames() {
    fn run(seed: u32) -> Vec<Vec<gc_cmd>> {
        let mut client = Client::new(seed);
        let mut frames = Vec::new();
        // Title frame, then a scripted run: start, buff up, fight.
        for f in 0..600u32 {
            let input = gc_input {
                move_x: (f as f32 * 0.05).cos(),
                move_y: (f as f32 * 0.05).sin(),
                aim_x: 640.0 + (f as f32 * 0.1).cos() * 200.0,
                aim_y: 360.0 + (f as f32 * 0.1).sin() * 120.0,
                pointer_active: 1,
                pointer_down: 0,
                buttons: if f == 300 { GC_BTN_DASH } else { 0 },
            };
            if f == 2 {
                let (x, y) = client.button_center(0);
                let click = gc_input { aim_x: x, aim_y: y, pointer_active: 1, pointer_down: 1,
                                       ..Default::default() };
                client.step(&click, 1.0 / 60.0);
            }
            if f == 5 {
                client.debug(GC_DBG_GIVE_MONEY, 500.0);
                client.debug(GC_DBG_GIVE_WEAPON, 1.0);
                client.debug(GC_DBG_SET_WAVE, 4.0);
            }
            client.step(&input, 1.0 / 60.0);
            if f % 25 == 0 {
                frames.push(client.cmds());
            }
        }
        frames
    }

    let a = run(2024);
    let b = run(2024);
    assert_eq!(a.len(), b.len());
    for (i, (fa, fb)) in a.iter().zip(b.iter()).enumerate() {
        assert_eq!(fa.len(), fb.len(), "frame {} has a different command count", i);
        for (ca, cb) in fa.iter().zip(fb.iter()) {
            assert_eq!(ca, cb, "frame {} diverged", i);
        }
    }

    // A different seed must actually produce a different run.
    let c = run(777);
    assert!(a.iter().zip(c.iter()).any(|(fa, fc)| fa != fc),
            "different seeds should not produce identical runs");
}

#[test]
fn best_score_survives_a_save_load_round_trip() {
    let mut client = Client::new(17);
    client.start_run();
    client.debug(GC_DBG_INVULNERABLE, 1.0);
    client.debug(GC_DBG_SET_WAVE, 6.0);
    client.debug(GC_DBG_GIVE_MONEY, 250.0);
    client.idle(120);
    client.debug(GC_DBG_KILL_PLAYER, 0.0);
    let best = client.status().best_score;
    assert!(best > 0);

    let mut blob = [0u8; 64];
    let written = unsafe { gc_save(client.handle, blob.as_mut_ptr(), blob.len() as i32) };
    assert!(written > 0, "gc_save must produce a blob");
    assert_eq!(&blob[0..4], b"SLA1", "the blob should be self describing");

    // A fresh run loads the same best score back.
    let mut other = Client::new(18);
    assert_eq!(other.status().best_score, 0);
    let loaded = unsafe { gc_load(other.handle, blob.as_ptr(), written) };
    assert_eq!(loaded, 1);
    assert_eq!(other.status().best_score, best);

    // Garbage must be rejected without crashing.
    let junk = [0xFFu8; 32];
    assert_eq!(unsafe { gc_load(other.handle, junk.as_ptr(), junk.len() as i32) }, 0);
    assert_eq!(unsafe { gc_load(other.handle, std::ptr::null(), 0) }, 0);
    assert_eq!(unsafe { gc_save(client.handle, blob.as_mut_ptr(), 4) }, -1);
}

#[test]
fn a_long_brutal_run_never_produces_a_broken_frame() {
    // Mash everything at once: dash, pause, restart, huge waves, absurd input.
    let mut client = Client::new(5150);
    client.start_run();
    client.debug(GC_DBG_INVULNERABLE, 1.0);
    client.debug(GC_DBG_SET_WAVE, 12.0);
    client.debug(GC_DBG_GIVE_MONEY, 5000.0);

    for f in 0..4000u32 {
        let t = f as f32;
        let input = gc_input {
            move_x: (t * 0.31).sin() * 3.0,   // deliberately out of range
            move_y: (t * 0.17).cos() * 3.0,
            aim_x: if f % 97 == 0 { f32::NAN } else { (t * 0.07).cos() * 4000.0 + 640.0 },
            aim_y: (t * 0.11).sin() * 2000.0 + 360.0,
            pointer_active: 1,
            pointer_down: i32::from(f % 53 == 0),
            buttons: match f % 211 {
                0 => GC_BTN_DASH,
                1 => GC_BTN_PAUSE,
                2 => GC_BTN_RESTART,
                _ => 0,
            },
        };
        client.step(&input, if f % 500 == 0 { 0.5 } else { 1.0 / 60.0 });
        assert_commands_sane(&client.cmds(), &format!("brutal frame {}", f));
    }

    // Whatever state we ended in, the game must still be able to restart.
    client.click_button(0);
    client.idle(5);
    assert_commands_sane(&client.cmds(), "after restarting");
}

#[test]
fn extreme_frame_times_are_clamped_instead_of_exploding() {
    let mut client = Client::new(6);
    client.start_run();
    for dt in [0.0, 1e-6, 1.0, 100.0, -1.0, f32::NAN, f32::INFINITY] {
        client.step(&gc_input::default(), dt);
        assert_commands_sane(&client.cmds(), &format!("dt = {}", dt));
    }
}

/// Convenience: number of clickable slots in the current state.
impl Client {
    fn ui_slot_count(&self) -> i32 {
        unsafe { gc_ui_slot_count(self.handle) }
    }

    /// Cheapest node that is currently purchasable, found through the ABI only.
    fn cheapest_available_node(&self) -> Option<i32> {
        let count = gc_tree_count();
        let mut best: Option<(i32, i32)> = None;
        for node in 0..count {
            if unsafe { gc_tree_state(self.handle, node) } != 2 {
                continue;
            }
            let cost = unsafe { gc_tree_cost(self.handle, node) };
            let rect = unsafe { gc_tree_rect(self.handle, node) };
            if rect.w <= 0.0 {
                continue;
            }
            if best.map_or(true, |(_, c)| cost < c) {
                best = Some((node, cost));
            }
        }
        best.map(|(n, _)| n)
    }
}
