//! Loading the shared game-logic library.
//!
//! The game logic is *not* part of this executable: at startup we `dlopen`
//! `libgame_core.so` and resolve the documented C ABI from `include/game_core.h`.
//!
//! If the shared library cannot be found (for example a bare `cargo run` in a
//! fresh checkout, before `cargo build -p game_core` has produced it) we fall
//! back to the statically linked copy of the very same crate, and say so on
//! stderr.  Both paths expose identical function pointers, so no other code in
//! this renderer knows the difference.

use core::ffi::{c_char, c_int, c_void, CStr};
use std::ffi::CString;
use game_core::{gc_cmd, gc_event, gc_input, gc_progress, gc_rect, gc_settings, gc_status, Handle};
use std::path::{Path, PathBuf};

const RTLD_NOW: c_int = 2;

#[link(name = "dl")]
extern "C" {
    fn dlopen(filename: *const c_char, flags: c_int) -> *mut c_void;
    fn dlsym(handle: *mut c_void, symbol: *const c_char) -> *mut c_void;
    fn dlerror() -> *const c_char;
}

/// Resolved entry points of the shared library.
///
/// Not every shell uses every entry point; keeping the full ABI here means a
/// renderer can start using one without touching the loader.
#[allow(non_snake_case, dead_code)]
pub struct Api {
    pub abi_version: unsafe extern "C" fn() -> u32,
    pub create: unsafe extern "C" fn(u32) -> *mut Handle,
    pub destroy: unsafe extern "C" fn(*mut Handle),
    pub resize: unsafe extern "C" fn(*mut Handle, i32, i32, f32, f32, f32, f32),
    pub virtual_size: unsafe extern "C" fn(*const Handle, *mut f32, *mut f32),
    pub view_scale: unsafe extern "C" fn(*const Handle) -> f32,
    pub update: unsafe extern "C" fn(*mut Handle, *const gc_input, f32),
    pub cmds: unsafe extern "C" fn(*const Handle, *mut i32) -> *const gc_cmd,
    pub events: unsafe extern "C" fn(*const Handle, *mut i32) -> *const gc_event,
    pub status_get: unsafe extern "C" fn(*const Handle, *mut gc_status),
    pub progress_get: unsafe extern "C" fn(*const Handle, *mut gc_progress),
    pub sprite_file: unsafe extern "C" fn(i32) -> *const c_char,
    pub font_atlas: unsafe extern "C" fn(*mut *const c_char, *mut i32, *mut i32),
    pub save: unsafe extern "C" fn(*const Handle, *mut u8, i32) -> i32,
    pub load: unsafe extern "C" fn(*mut Handle, *const u8, i32) -> i32,
    pub debug: unsafe extern "C" fn(*mut Handle, i32, f32),
    pub ui_slot: unsafe extern "C" fn(*const Handle, i32) -> gc_rect,
    pub ui_slot_count: unsafe extern "C" fn(*const Handle) -> i32,
    pub ui_button: unsafe extern "C" fn(*const Handle, i32) -> gc_rect,
    pub theme_index: unsafe extern "C" fn(*const Handle) -> i32,
    pub settings_get: unsafe extern "C" fn(*const Handle, *mut gc_settings) -> i32,
    pub options_open: unsafe extern "C" fn(*const Handle) -> i32,
    pub options_set_open: unsafe extern "C" fn(*mut Handle, i32),
    pub tree_count: unsafe extern "C" fn() -> i32,
    pub tree_rect: unsafe extern "C" fn(*const Handle, i32) -> gc_rect,
    pub tree_state: unsafe extern "C" fn(*const Handle, i32) -> i32,
    pub tree_cost: unsafe extern "C" fn(*const Handle, i32) -> i32,
    /// Keeps the dlopen handle alive for the process lifetime.
    _lib: Option<*mut c_void>,
}

/// How the game logic ended up in this process.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Mode {
    SharedLibrary,
    Static,
}

impl Mode {
    pub fn describe(self) -> &'static str {
        match self {
            Mode::SharedLibrary => "libgame_core.so (shared library)",
            Mode::Static => "statically linked game_core (shared library not found)",
        }
    }
}

impl Api {
    /// Loads the shared library, or falls back to the static copy.
    pub fn load() -> (Api, Mode) {
        for candidate in candidate_paths() {
            if !candidate.exists() {
                continue;
            }
            match unsafe { Self::from_dylib(&candidate) } {
                Ok(api) => return (api, Mode::SharedLibrary),
                Err(err) => {
                    eprintln!("slime_arena: {}: {}", candidate.display(), err);
                }
            }
        }
        (Self::static_api(), Mode::Static)
    }

    unsafe fn from_dylib(path: &Path) -> Result<Api, String> {
        let c_path = CString::new(path.to_string_lossy().as_bytes())
            .map_err(|_| "path contains a NUL byte".to_string())?;
        let lib = unsafe { dlopen(c_path.as_ptr(), RTLD_NOW) };
        if lib.is_null() {
            return Err(format!("dlopen failed: {}", dlerror_string()));
        }

        // Resolve a symbol and reinterpret it as the ABI function pointer.
        unsafe fn sym<T>(lib: *mut c_void, name: &str) -> Result<T, String> {
            let c_name = CString::new(name).map_err(|_| "bad symbol".to_string())?;
            let ptr = unsafe { dlsym(lib, c_name.as_ptr()) };
            if ptr.is_null() {
                return Err(format!("missing symbol {}: {}", name, dlerror_string()));
            }
            Ok(unsafe { core::mem::transmute_copy::<*mut c_void, T>(&ptr) })
        }

        unsafe {
            let api = Api {
                abi_version: sym(lib, "gc_abi_version")?,
                create: sym(lib, "gc_create")?,
                destroy: sym(lib, "gc_destroy")?,
                resize: sym(lib, "gc_resize")?,
                virtual_size: sym(lib, "gc_virtual_size")?,
                view_scale: sym(lib, "gc_view_scale")?,
                update: sym(lib, "gc_update")?,
                cmds: sym(lib, "gc_cmds")?,
                events: sym(lib, "gc_events")?,
                status_get: sym(lib, "gc_status_get")?,
                progress_get: sym(lib, "gc_progress_get")?,
                sprite_file: sym(lib, "gc_sprite_file")?,
                font_atlas: sym(lib, "gc_font_atlas")?,
                save: sym(lib, "gc_save")?,
                load: sym(lib, "gc_load")?,
                debug: sym(lib, "gc_debug")?,
                ui_slot: sym(lib, "gc_ui_slot")?,
                ui_slot_count: sym(lib, "gc_ui_slot_count")?,
                ui_button: sym(lib, "gc_ui_button")?,
                theme_index: sym(lib, "gc_theme_index")?,
                settings_get: sym(lib, "gc_settings_get")?,
                options_open: sym(lib, "gc_options_open")?,
                options_set_open: sym(lib, "gc_options_set_open")?,
                tree_count: sym(lib, "gc_tree_count")?,
                tree_rect: sym(lib, "gc_tree_rect")?,
                tree_state: sym(lib, "gc_tree_state")?,
                tree_cost: sym(lib, "gc_tree_cost")?,
                _lib: Some(lib),
            };
            Ok(api)
        }
    }

    fn static_api() -> Api {
        Api {
            abi_version: game_core::gc_abi_version,
            create: game_core::gc_create,
            destroy: game_core::gc_destroy,
            resize: game_core::gc_resize,
            virtual_size: game_core::gc_virtual_size,
            view_scale: game_core::gc_view_scale,
            update: game_core::gc_update,
            cmds: game_core::gc_cmds,
            events: game_core::gc_events,
            status_get: game_core::gc_status_get,
            progress_get: game_core::gc_progress_get,
            sprite_file: game_core::gc_sprite_file,
            font_atlas: game_core::gc_font_atlas,
            save: game_core::gc_save,
            load: game_core::gc_load,
            debug: game_core::gc_debug,
            ui_slot: game_core::gc_ui_slot,
            ui_slot_count: game_core::gc_ui_slot_count,
            ui_button: game_core::gc_ui_button,
            theme_index: game_core::gc_theme_index,
            settings_get: game_core::gc_settings_get,
            options_open: game_core::gc_options_open,
            options_set_open: game_core::gc_options_set_open,
            tree_count: game_core::gc_tree_count,
            tree_rect: game_core::gc_tree_rect,
            tree_state: game_core::gc_tree_state,
            tree_cost: game_core::gc_tree_cost,
            _lib: None,
        }
    }

    /// Reads a `const char*` returned by the library.
    ///
    /// # Safety
    /// `p` must be a NUL terminated string owned by the library.
    pub unsafe fn cstr(p: *const c_char) -> String {
        if p.is_null() {
            return String::new();
        }
        unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned()
    }
}

fn dlerror_string() -> String {
    unsafe {
        let p = dlerror();
        if p.is_null() {
            "unknown dlopen error".to_string()
        } else {
            CStr::from_ptr(p).to_string_lossy().into_owned()
        }
    }
}

/// Where to look for `libgame_core.so`, most specific first.
fn candidate_paths() -> Vec<PathBuf> {
    let mut out = Vec::new();

    if let Ok(explicit) = std::env::var("SLIME_ARENA_CORE") {
        out.push(PathBuf::from(explicit));
    }

    // Next to the executable (how a shipped build is laid out).
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            out.push(dir.join("libgame_core.so"));
            // target/debug/deps -> target/debug
            if let Some(up) = dir.parent() {
                out.push(up.join("libgame_core.so"));
            }
            if let Some(up) = dir.parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
                out.push(up.join("target/debug/libgame_core.so"));
                out.push(up.join("target/release/libgame_core.so"));
            }
        }
    }

    out.push(PathBuf::from("target/debug/libgame_core.so"));
    out.push(PathBuf::from("target/release/libgame_core.so"));
    out.push(PathBuf::from("libgame_core.so"));
    out
}
