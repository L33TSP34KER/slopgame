//! Hand written SDL2 bindings -- only the subset this renderer needs.
//!
//! The renderer deliberately depends on nothing but the system SDL2 and libpng,
//! so the whole project builds offline with a bare `cargo run` (no crates to
//! download).  Everything here is a thin `extern "C"` declaration; the safe
//! wrappers live in `main.rs` / `renderer.rs`.

#![allow(non_camel_case_types)]
#![allow(non_upper_case_globals)]
#![allow(dead_code)]

use core::ffi::{c_char, c_int, c_void};

pub type SdlWindow = c_void;
pub type SdlRenderer = c_void;
pub type SdlTexture = c_void;

// -- init flags -------------------------------------------------------------
pub const SDL_INIT_TIMER: u32 = 0x0000_0001;
pub const SDL_INIT_VIDEO: u32 = 0x0000_0020;
pub const SDL_INIT_EVENTS: u32 = 0x0000_4000;

// -- window flags -----------------------------------------------------------
pub const SDL_WINDOWPOS_CENTERED: c_int = 0x2FFF_0000;
pub const SDL_WINDOW_SHOWN: u32 = 0x0000_0004;
pub const SDL_WINDOW_RESIZABLE: u32 = 0x0000_0020;
pub const SDL_WINDOW_ALLOW_HIGHDPI: u32 = 0x0000_2000;

// -- renderer flags ---------------------------------------------------------
pub const SDL_RENDERER_SOFTWARE: u32 = 0x0000_0001;
pub const SDL_RENDERER_ACCELERATED: u32 = 0x0000_0002;
pub const SDL_RENDERER_PRESENTVSYNC: u32 = 0x0000_0004;

// -- pixel formats ----------------------------------------------------------
// SDL_DEFINE_PIXELFORMAT(type=PACKED32(6), order, layout=8888(6), bits=32, bytes=4)
//                          | (order << 20)
//   order: XRGB=1 RGBX=2 ARGB=3 RGBA=4 BGRX=5 XBGR=6 ABGR=7 BGRA=8
/// Packed A,R,G,B -> memory B,G,R,A on little endian.
pub const SDL_PIXELFORMAT_ARGB8888: u32 = 0x1636_2004;
/// Packed A,B,G,R -> memory R,G,B,A on little endian: what libpng hands us and
/// what SDL_RenderReadPixels gives back, so no byte swapping is needed.
pub const SDL_PIXELFORMAT_ABGR8888: u32 = 0x1676_2004;

// -- texture / blend --------------------------------------------------------
pub const SDL_TEXTUREACCESS_STATIC: c_int = 0;
pub const SDL_BLENDMODE_NONE: c_int = 0x0000_0000;
pub const SDL_BLENDMODE_BLEND: c_int = 0x0000_0001;
pub const SDL_BLENDMODE_ADD: c_int = 0x0000_0002;
pub const SDL_FLIP_NONE: c_int = 0x0000_0000;

// -- event types ------------------------------------------------------------
pub const SDL_QUIT: u32 = 0x100;
pub const SDL_WINDOWEVENT: u32 = 0x200;
pub const SDL_WINDOW_FULLSCREEN_DESKTOP: u32 = 0x1001;
pub const SDL_KEYDOWN: u32 = 0x300;
pub const SDL_KEYUP: u32 = 0x301;
pub const SDL_MOUSEMOTION: u32 = 0x400;
pub const SDL_MOUSEBUTTONDOWN: u32 = 0x401;
pub const SDL_MOUSEBUTTONUP: u32 = 0x402;
pub const SDL_MOUSEWHEEL: u32 = 0x403;
pub const SDL_FINGERDOWN: u32 = 0x700;
pub const SDL_FINGERUP: u32 = 0x701;
pub const SDL_FINGERMOTION: u32 = 0x702;

pub const SDL_WINDOWEVENT_RESIZED: u8 = 4;
pub const SDL_WINDOWEVENT_SIZE_CHANGED: u8 = 5;

// -- keys -------------------------------------------------------------------
pub const SDLK_ESCAPE: i32 = 27;
pub const SDLK_SPACE: i32 = 32;
pub const SDLK_a: i32 = 97;
pub const SDLK_d: i32 = 100;
#[allow(non_upper_case_globals)]
pub const SDLK_M: i32 = 109;
pub const SDLK_O: i32 = 111;
pub const SDLK_MINUS: i32 = 45;
pub const SDLK_EQUALS: i32 = 61;
pub const SDLK_r: i32 = 114;
pub const SDLK_s: i32 = 115;
pub const SDLK_w: i32 = 119;
pub const SDLK_LEFT: i32 = 1_073_741_904;
pub const SDLK_RIGHT: i32 = 1_073_741_903;
pub const SDLK_UP: i32 = 1_073_741_906;
pub const SDLK_DOWN: i32 = 1_073_741_905;

// -- hints ------------------------------------------------------------------
pub const SDL_HINT_RENDER_SCALE_QUALITY: &[u8] = b"SDL_RENDER_SCALE_QUALITY\0";
pub const SDL_HINT_RENDER_DRIVER: &[u8] = b"SDL_RENDER_DRIVER\0";
pub const SDL_HINT_VIDEODRIVER: &[u8] = b"SDL_VIDEODRIVER\0";

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlRect {
    pub x: c_int,
    pub y: c_int,
    pub w: c_int,
    pub h: c_int,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlFRect {
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlFPoint {
    pub x: f32,
    pub y: f32,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlKeysym {
    pub scancode: c_int,
    pub sym: c_int,
    pub mod_: u16,
    pub unused: u32,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlKeyboardEvent {
    pub type_: u32,
    pub timestamp: u32,
    pub window_id: u32,
    pub state: u8,
    pub repeat: u8,
    pub padding2: u8,
    pub padding3: u8,
    pub keysym: SdlKeysym,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlMouseMotionEvent {
    pub type_: u32,
    pub timestamp: u32,
    pub window_id: u32,
    pub which: u32,
    pub state: u32,
    pub x: i32,
    pub y: i32,
    pub xrel: i32,
    pub yrel: i32,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlMouseButtonEvent {
    pub type_: u32,
    pub timestamp: u32,
    pub window_id: u32,
    pub which: u32,
    pub button: u8,
    pub state: u8,
    pub clicks: u8,
    pub padding1: u8,
    pub x: i32,
    pub y: i32,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlWindowEvent {
    pub type_: u32,
    pub timestamp: u32,
    pub window_id: u32,
    pub event: u8,
    pub padding1: u8,
    pub padding2: u8,
    pub padding3: u8,
    pub data1: i32,
    pub data2: i32,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlMouseWheelEvent {
    pub type_: u32,
    pub timestamp: u32,
    pub window_id: u32,
    pub which: u32,
    pub x: i32,
    pub y: i32,
    pub direction: u32,
    pub precise_x: f32,
    pub precise_y: f32,
    pub mouse_x: i32,
    pub mouse_y: i32,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlTouchFingerEvent {
    pub type_: u32,
    pub timestamp: u32,
    pub touch_id: i64,
    pub finger_id: i64,
    pub x: f32,
    pub y: f32,
    pub dx: f32,
    pub dy: f32,
    pub pressure: f32,
}

#[repr(C)]
#[derive(Copy, Clone, Default, Debug)]
pub struct SdlQuitEvent {
    pub type_: u32,
    pub timestamp: u32,
}

/// SDL_Event is a 56 byte union; the padding member fixes the size.
#[repr(C)]
#[derive(Copy, Clone)]
pub union SdlEvent {
    pub type_: u32,
    pub key: SdlKeyboardEvent,
    pub motion: SdlMouseMotionEvent,
    pub button: SdlMouseButtonEvent,
    pub wheel: SdlMouseWheelEvent,
    pub window: SdlWindowEvent,
    pub finger: SdlTouchFingerEvent,
    pub quit: SdlQuitEvent,
    pub padding: [u8; 56],
}

impl Default for SdlEvent {
    fn default() -> Self {
        SdlEvent { padding: [0; 56] }
    }
}

#[link(name = "SDL2")]
extern "C" {
    pub fn SDL_Init(flags: u32) -> c_int;
    pub fn SDL_Quit();
    pub fn SDL_GetError() -> *const c_char;
    pub fn SDL_SetHint(name: *const c_char, value: *const c_char) -> c_int;

    pub fn SDL_CreateWindow(title: *const c_char, x: c_int, y: c_int, w: c_int, h: c_int,
                            flags: u32) -> *mut SdlWindow;
    pub fn SDL_DestroyWindow(window: *mut SdlWindow);
    pub fn SDL_SetWindowTitle(window: *mut SdlWindow, title: *const c_char);
    pub fn SDL_SetWindowFullscreen(window: *mut SdlWindow, flags: u32) -> c_int;
    pub fn SDL_GetWindowSize(window: *mut SdlWindow, w: *mut c_int, h: *mut c_int);
    /// Physical pixel size (SDL 2.26+); what the renderer should draw at.
    pub fn SDL_GetWindowSizeInPixels(window: *mut SdlWindow, w: *mut c_int, h: *mut c_int);

    pub fn SDL_CreateRenderer(window: *mut SdlWindow, index: c_int, flags: u32)
        -> *mut SdlRenderer;
    pub fn SDL_DestroyRenderer(renderer: *mut SdlRenderer);
    pub fn SDL_RenderClear(renderer: *mut SdlRenderer) -> c_int;
    pub fn SDL_RenderPresent(renderer: *mut SdlRenderer);
    pub fn SDL_SetRenderDrawColor(renderer: *mut SdlRenderer, r: u8, g: u8, b: u8, a: u8)
        -> c_int;
    pub fn SDL_SetRenderDrawBlendMode(renderer: *mut SdlRenderer, mode: c_int) -> c_int;
    pub fn SDL_RenderFillRectF(renderer: *mut SdlRenderer, rect: *const SdlFRect) -> c_int;
    /// NOTE: the source rect is an integer SDL_Rect even in the float variants;
    /// only the destination rect is float.
    pub fn SDL_RenderCopyF(renderer: *mut SdlRenderer, texture: *mut SdlTexture,
                           src: *const SdlRect, dst: *const SdlFRect) -> c_int;
    pub fn SDL_RenderCopyExF(renderer: *mut SdlRenderer, texture: *mut SdlTexture,
                             src: *const SdlRect, dst: *const SdlFRect, angle: f64,
                             center: *const SdlFPoint, flip: c_int) -> c_int;
    pub fn SDL_RenderReadPixels(renderer: *mut SdlRenderer, rect: *const SdlRect,
                                format: u32, pixels: *mut c_void, pitch: c_int) -> c_int;

    pub fn SDL_CreateTexture(renderer: *mut SdlRenderer, format: u32, access: c_int,
                             w: c_int, h: c_int) -> *mut SdlTexture;
    pub fn SDL_UpdateTexture(texture: *mut SdlTexture, rect: *const SdlRect,
                             pixels: *const c_void, pitch: c_int) -> c_int;
    pub fn SDL_DestroyTexture(texture: *mut SdlTexture);
    pub fn SDL_SetTextureBlendMode(texture: *mut SdlTexture, mode: c_int) -> c_int;
    pub fn SDL_SetTextureColorMod(texture: *mut SdlTexture, r: u8, g: u8, b: u8) -> c_int;
    pub fn SDL_SetTextureAlphaMod(texture: *mut SdlTexture, a: u8) -> c_int;

    pub fn SDL_PollEvent(event: *mut SdlEvent) -> c_int;
}

/// Convenience: last SDL error as a String.
pub fn last_error() -> String {
    unsafe {
        let p = SDL_GetError();
        if p.is_null() {
            return "unknown SDL error".to_string();
        }
        core::ffi::CStr::from_ptr(p).to_string_lossy().into_owned()
    }
}
