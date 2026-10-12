//! Slime Arena -- shared game logic.
//!
//! This crate is the *entire* game: simulation, AI, collision, waves, economy,
//! progression, camera, text layout and HUD layout.  It is compiled to a shared
//! library (`libgame_core.so` / `.dylib` / Android `.so`) and driven through the
//! C ABI in `include/game_core.h` by thin, per-platform renderers.
//!
//! Nothing in here knows about a window, a GPU API, an input device or a
//! speaker.  A renderer's whole job is:
//!
//! ```text
//!   gc_create -> gc_resize -> loop { gc_update; draw gc_cmds; react to gc_events }
//! ```

mod backdrop;
mod decor;
mod entities;
mod ffi;
mod generated;
mod math;
mod render;
mod render_world;
mod settings;
mod sprite;
mod tree;
mod systems;
mod ui;
mod world;

pub use ffi::*;
pub use sprite::{SpriteId, SPRITE_COUNT};

use core::ffi::c_char;
use core::panic::AssertUnwindSafe;
use math::Vec2;
use render::Renderer;
use std::panic::{catch_unwind, UnwindSafe};
use world::{InputState, World};

/// Fixed simulation rate.  `gc_update` accumulates real time and runs as many
/// fixed steps as needed, so the logic is frame-rate independent and the tests
/// can step it exactly.
pub const FIXED_DT: f32 = systems::FIXED_DT;
const MAX_STEPS_PER_UPDATE: u32 = 6;
const MAX_FRAME_DT: f32 = 0.25;

/// One live game instance plus the per-frame output buffers.
pub struct Handle {
    world: World,
    renderer: Renderer,
    input: InputState,
    accumulator: f32,
    first_frame: bool,
    needs_render: bool,
    prev_buttons: u32,
}

impl Handle {
    fn new(seed: u32, view: render::View, best: i32) -> Handle {
        Handle {
            world: World::new(seed, best),
            renderer: Renderer::new(view),
            input: InputState::default(),
            accumulator: 0.0,
            first_frame: true,
            needs_render: true,
            prev_buttons: 0,
        }
    }

    /// Runs the fixed-step loop and, if anything moved, rebuilds the command list.
    fn advance(&mut self, dt: f32) {
        let dt = if dt.is_finite() { dt.clamp(0.0, MAX_FRAME_DT) } else { 0.0 };
        self.accumulator += dt;

        // Events are cleared once per gc_update so that a frame containing
        // several fixed steps still reports everything that happened in it.
        self.world.events.clear();

        let view = self.renderer.view.clone();
        let mut steps = 0;
        while self.accumulator >= FIXED_DT && steps < MAX_STEPS_PER_UPDATE {
            self.world.step(&view, &self.input, FIXED_DT, self.first_frame);
            self.first_frame = false;
            self.accumulator -= FIXED_DT;
            steps += 1;
            self.needs_render = true;
        }
        if steps == MAX_STEPS_PER_UPDATE {
            // Give up on the backlog rather than spiral (a long stall, or a
            // debugger pause) -- the game slows down instead of freezing.
            self.accumulator = 0.0;
        }

        if self.needs_render {
            self.render();
            self.needs_render = false;
        }
    }

    fn render(&mut self) {
        let shake = systems::shake_offset(&self.world);
        let camera = self.world.camera;
        let zoom = self.world.zoom;
        self.renderer.begin(camera, zoom, shake);
        render_world::draw_world(&self.world, &mut self.renderer);
        ui::draw_ui(&self.world, &mut self.renderer);
        // Pointer reticle last, so it sits on top of the HUD.
        if self.input.pointer_active && self.world.state == world::State::Playing {
            ui::draw_pointer(&self.world, &mut self.renderer, self.input.aim);
        }
    }

    fn apply_input(&mut self, input: &gc_input) {
        let pressed = input.buttons & !self.prev_buttons;
        self.prev_buttons = input.buttons;
        // A renderer may hand us NaN or infinities (a lost touch, a divide by a
        // zero window size); the simulation must never see them.
        let finite = |v: f32| if v.is_finite() { v } else { 0.0 };
        self.input = InputState {
            move_axis: Vec2::new(finite(input.move_x), finite(input.move_y)).clamp_length(1.0),
            aim: Vec2::new(finite(input.aim_x), finite(input.aim_y)),
            pointer_active: input.pointer_active != 0,
            pointer_down: input.pointer_down != 0,
            buttons: input.buttons,
            dash: pressed & ffi::GC_BTN_DASH != 0,
            // Space doubles as "confirm" so the title and game-over screens can
            // be driven from the keyboard as well as by tapping.
            confirm: pressed & ffi::GC_BTN_DASH != 0,
            pause: pressed & ffi::GC_BTN_PAUSE != 0,
            restart: pressed & ffi::GC_BTN_RESTART != 0,
        };
    }
}

/// Runs `f`, converting a panic into `fallback` instead of letting it unwind
/// across the C ABI (which would be undefined behaviour for the shell).
fn guard<T: UnwindSafe>(fallback: T, f: impl FnOnce() -> T) -> T {
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(v) => v,
        Err(_) => {
            // A panic here is a bug, but a renderer must not be killed by it.
            eprintln!("game_core: caught panic in FFI entry point");
            fallback
        }
    }
}

// ---------------------------------------------------------------------------
// version / lifecycle
// ---------------------------------------------------------------------------

#[no_mangle]
pub extern "C" fn gc_abi_version() -> u32 {
    ffi::GC_ABI_VERSION
}

/// Creates a run.  Never returns NULL.
#[no_mangle]
pub extern "C" fn gc_create(seed: u32) -> *mut Handle {
    guard(std::ptr::null_mut(), || {
        let view = render::View::new(1280, 720, [0.0; 4]);
        Box::into_raw(Box::new(Handle::new(seed, view, 0)))
    })
}

/// Frees a run created by `gc_create`.  NULL is ignored.
///
/// # Safety
/// `h` must be a pointer returned by `gc_create` that has not been destroyed.
#[no_mangle]
pub unsafe extern "C" fn gc_destroy(h: *mut Handle) {
    if h.is_null() {
        return;
    }
    let _ = catch_unwind(AssertUnwindSafe(|| {
        drop(unsafe { Box::from_raw(h) });
    }));
}

// ---------------------------------------------------------------------------
// view
// ---------------------------------------------------------------------------

/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_resize(h: *mut Handle, fb_width: i32, fb_height: i32,
                                   safe_left: f32, safe_top: f32,
                                   safe_right: f32, safe_bottom: f32) {
    if h.is_null() {
        return;
    }
    guard((), || {
        let handle = unsafe { &mut *h };
        handle.renderer.view.resize(fb_width, fb_height,
                                    [safe_left, safe_top, safe_right, safe_bottom]);
        handle.needs_render = true;
        if handle.first_frame {
            // Snap the camera on the very first resize so the first drawn frame
            // is already centred on the player.
            systems::update_camera(&mut handle.world, &handle.renderer.view, FIXED_DT, true);
        }
    });
}

/// # Safety
/// `h` must be a valid handle and the out pointers must be writable.
#[no_mangle]
pub unsafe extern "C" fn gc_virtual_size(h: *const Handle, out_w: *mut f32, out_h: *mut f32) {
    if h.is_null() {
        return;
    }
    guard((), || {
        let handle = unsafe { &*h };
        if !out_w.is_null() {
            unsafe { *out_w = handle.renderer.view.virt_w };
        }
        if !out_h.is_null() {
            unsafe { *out_h = handle.renderer.view.virt_h };
        }
    });
}

/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_view_scale(h: *const Handle) -> f32 {
    if h.is_null() {
        return 1.0;
    }
    guard(1.0, || unsafe { (&*h).renderer.view.scale })
}

// ---------------------------------------------------------------------------
// frame
// ---------------------------------------------------------------------------

/// Advances the simulation by `dt` seconds and rebuilds the command list.
///
/// # Safety
/// `h` must be a valid handle; `input` may be NULL (treated as no input).
#[no_mangle]
pub unsafe extern "C" fn gc_update(h: *mut Handle, input: *const gc_input, dt: f32) {
    if h.is_null() {
        return;
    }
    guard((), || {
        let handle = unsafe { &mut *h };
        if input.is_null() {
            handle.input = InputState::default();
        } else {
            handle.apply_input(unsafe { &*input });
        }
        handle.advance(dt);
    });
}

/// Returns the command list for the frame just simulated.  The pointer is owned
/// by the library and stays valid until the next `gc_update`.
///
/// # Safety
/// `h` must be a valid handle; `out_count` may be NULL.
#[no_mangle]
pub unsafe extern "C" fn gc_cmds(h: *const Handle, out_count: *mut i32) -> *const gc_cmd {
    if h.is_null() {
        return std::ptr::null();
    }
    guard(std::ptr::null(), || {
        let handle = unsafe { &*h };
        if !out_count.is_null() {
            unsafe { *out_count = handle.renderer.cmds.len() as i32 };
        }
        handle.renderer.cmds.as_ptr()
    })
}

/// Returns the events produced by the frame just simulated.  The pointer is
/// owned by the library and stays valid until the next `gc_update`.
///
/// # Safety
/// `h` must be a valid handle; `out_count` may be NULL.
#[no_mangle]
pub unsafe extern "C" fn gc_events(h: *const Handle, out_count: *mut i32) -> *const gc_event {
    if h.is_null() {
        return std::ptr::null();
    }
    guard(std::ptr::null(), || {
        let handle = unsafe { &*h };
        if !out_count.is_null() {
            unsafe { *out_count = handle.world.events.len() as i32 };
        }
        handle.world.events.as_ptr()
    })
}

/// # Safety
/// `h` must be a valid handle and `out` writable.
#[no_mangle]
pub unsafe extern "C" fn gc_status_get(h: *const Handle, out: *mut gc_status) {
    if h.is_null() {
        return;
    }
    guard((), || {
        if out.is_null() {
            return;
        }
        let handle = unsafe { &*h };
        unsafe { *out = handle.world.status() };
    });
}

/// Incremental progression snapshot.
///
/// # Safety
/// `h` must be a valid handle and `out` writable.
#[no_mangle]
pub unsafe extern "C" fn gc_progress_get(h: *const Handle, out: *mut gc_progress) {
    if h.is_null() {
        return;
    }
    guard((), || {
        if out.is_null() {
            return;
        }
        let handle = unsafe { &*h };
        unsafe {
            *out = gc_progress {
                tier: handle.world.tier,
                goal: handle.world.goal,
                goal_wave: handle.world.goal_wave,
                money_earned: handle.world.money_earned,
            }
        };
    });
}

// ---------------------------------------------------------------------------
// assets
// ---------------------------------------------------------------------------

/// File name of a sprite texture, as a NUL terminated C string.
#[no_mangle]
pub extern "C" fn gc_sprite_file(sprite: i32) -> *const c_char {
    match sprite {
        0..=7 => sprite::all_sprites()[sprite as usize].file_cstr().as_ptr() as *const c_char,
        _ => std::ptr::null(),
    }
}

/// File name and size of the font atlas.
///
/// # Safety
/// The out pointers must be writable (they may be NULL).
#[no_mangle]
pub unsafe extern "C" fn gc_font_atlas(file: *mut *const c_char, width: *mut i32,
                                       height: *mut i32) {
    guard((), || {
        if !file.is_null() {
            unsafe { *file = sprite::FONT_ATLAS_FILE.as_ptr() as *const c_char };
        }
        if !width.is_null() {
            unsafe { *width = generated::font_metrics::ATLAS_W as i32 };
        }
        if !height.is_null() {
            unsafe { *height = generated::font_metrics::ATLAS_H as i32 };
        }
    });
}

// ---------------------------------------------------------------------------
// persistence
// ---------------------------------------------------------------------------

/// # Safety
/// `h` valid, `buf`/`cap` describe a writable buffer.
#[no_mangle]
pub unsafe extern "C" fn gc_save(h: *const Handle, buf: *mut u8, cap: i32) -> i32 {
    if h.is_null() {
        return -1;
    }
    guard(-1, || {
        if buf.is_null() || cap <= 0 {
            return -1;
        }
        let handle = unsafe { &*h };
        let out = unsafe { std::slice::from_raw_parts_mut(buf, cap as usize) };
        handle.world.save(out)
    })
}

/// # Safety
/// `h` valid, `data`/`len` describe a readable buffer.
#[no_mangle]
pub unsafe extern "C" fn gc_load(h: *mut Handle, data: *const u8, len: i32) -> i32 {
    if h.is_null() {
        return 0;
    }
    guard(0, || {
        if data.is_null() || len <= 0 {
            return 0;
        }
        let handle = unsafe { &mut *h };
        let bytes = unsafe { std::slice::from_raw_parts(data, len as usize) };
        i32::from(handle.world.load(bytes))
    })
}

// ---------------------------------------------------------------------------
// test / tooling hooks
// ---------------------------------------------------------------------------

/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_debug(h: *mut Handle, cmd: i32, value: f32) {
    if h.is_null() {
        return;
    }
    guard((), || {
        let handle = unsafe { &mut *h };
        handle.world.debug(cmd, value);
        handle.needs_render = true;
        if handle.first_frame {
            systems::update_camera(&mut handle.world, &handle.renderer.view, FIXED_DT, true);
        }
    });
}

/// A clickable rectangle, used by automated tests and by shells that want to
/// mirror the library's UI layout natively.
#[repr(C)]
#[derive(Copy, Clone, Debug, Default)]
pub struct gc_rect {
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
}

fn rect_to_ffi(r: render::Rect) -> gc_rect {
    gc_rect { x: r.x, y: r.y, w: r.w, h: r.h }
}

/// Rectangle of clickable slot `index` in the current state (cards or shop
/// items).  Returns an all-zero rect when the slot does not exist.
///
/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_ui_slot(h: *const Handle, index: i32) -> gc_rect {
    if h.is_null() {
        return gc_rect::default();
    }
    guard(gc_rect::default(), || {
        if index < 0 {
            return gc_rect::default();
        }
        let handle = unsafe { &*h };
        rect_to_ffi(handle.world.ui_slot(&handle.renderer.view, index as usize))
    })
}

/// Number of clickable slots in the current state.
///
/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_ui_slot_count(h: *const Handle) -> i32 {
    if h.is_null() {
        return 0;
    }
    guard(0, || {
        let handle = unsafe { &*h };
        handle.world.ui_slot_count(&handle.renderer.view) as i32
    })
}

/// Copies the player's settings into `out`.
///
/// Renderers use this for the things only they can do: mixer volume, haptics
/// and fullscreen.  Everything else is honoured inside the library.
///
/// # Safety
/// `h` must be a valid handle and `out` must be writable.
#[no_mangle]
pub unsafe extern "C" fn gc_settings_get(h: *const Handle, out: *mut gc_settings) -> i32 {
    if h.is_null() || out.is_null() {
        return -1;
    }
    let ok = guard(-1, || unsafe {
        let s = (&*h).world.settings;
        *out = gc_settings {
            music: s.music_norm(),
            sfx: s.sfx_norm(),
            haptics: i32::from(s.haptics),
            shake: s.shake_scale(),
            damage_numbers: i32::from(s.damage_numbers),
            particles: s.particles,
            flashing: s.flashing,
            aim_assist: i32::from(s.aim_assist),
            fullscreen: i32::from(s.fullscreen),
        };
        0
    });
    ok
}

/// 1 while the options screen is open.  The options overlay sits on top of the
/// title or pause screen and swallows input, so a renderer that dims or pauses
/// behind menus can use this.
///
/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_options_open(h: *const Handle) -> i32 {
    if h.is_null() {
        return 0;
    }
    guard(0, || i32::from(unsafe { (&*h).world.options_open }))
}

/// Opens or closes the options screen from the shell (a menu key, say).
///
/// The overlay only exists over the title and pause screens -- opening it
/// mid-wave would hide a fight that keeps running -- so a request made in any
/// other state is ignored rather than leaving a dimmed screen with no menu.
///
/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_options_set_open(h: *mut Handle, open: i32) {
    if h.is_null() {
        return;
    }
    let _ = guard((), || unsafe {
        let w = &mut (*h).world;
        w.options_open = open != 0 && w.options_available();
        if w.options_open {
            w.options_row = 0;
        }
    });
}

/// Index of the backdrop theme currently playing (0..5): HELL, GOLD, LAVA,
/// PARADISE, PURPLE, GODLY.  A renderer uses this to pick the music track, and
/// to cross-fade when it changes.
///
/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_theme_index(h: *const Handle) -> i32 {
    if h.is_null() {
        return 0;
    }
    guard(0, || unsafe { (&*h).world.backdrop.theme_index() })
}

/// Total number of upgrade tree nodes.
#[no_mangle]
pub extern "C" fn gc_tree_count() -> i32 {
    tree::NODE_COUNT as i32
}

/// Screen rectangle of a visible tree node, or a zero rect when it is not in
/// the current branch / not unlocked yet.
///
/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_tree_rect(h: *const Handle, node: i32) -> gc_rect {
    if h.is_null() || node < 0 {
        return gc_rect::default();
    }
    guard(gc_rect::default(), || {
        let handle = unsafe { &*h };
        let layout = ui::UiLayout::compute(&handle.renderer.view, &handle.world);
        // Only nodes whose middle is inside the interactive area are reportable:
        // a shell clicking the reported centre must hit what the library draws.
        match layout.tree.and_then(|t| t.node_rect(node as usize).filter(|r| t.clickable(*r))) {
            Some(r) if r.w > 0.0 => rect_to_ffi(r),
            _ => gc_rect::default(),
        }
    })
}

/// 0 = hidden, 1 = locked, 2 = available, 3 = owned.
///
/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_tree_state(h: *const Handle, node: i32) -> i32 {
    if h.is_null() || node < 0 || node as usize >= tree::NODE_COUNT {
        return 0;
    }
    guard(0, || {
        let handle = unsafe { &*h };
        let node = node as usize;
        if handle.world.node_owned(node) {
            3
        } else if handle.world.node_available(node) {
            2
        } else if tree::FAMILIES[tree::family_of(node)].min_wave <= handle.world.wave {
            1
        } else {
            0
        }
    })
}

/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_tree_cost(h: *const Handle, node: i32) -> i32 {
    if h.is_null() || node < 0 || node as usize >= tree::NODE_COUNT {
        return -1;
    }
    guard(-1, || unsafe { (&*h).world.node_cost(node as usize) })
}

/// Rectangle of a named button: 0 = primary (start/resume/play again),
/// 1 = shop "next wave", 2 = pause.
///
/// # Safety
/// `h` must be a valid handle.
#[no_mangle]
pub unsafe extern "C" fn gc_ui_button(h: *const Handle, which: i32) -> gc_rect {
    if h.is_null() {
        return gc_rect::default();
    }
    guard(gc_rect::default(), || {
        let handle = unsafe { &*h };
        rect_to_ffi(handle.world.ui_button(&handle.renderer.view, which))
    })
}
