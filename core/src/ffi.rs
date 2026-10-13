//! The C ABI.
//!
//! Every type here mirrors `include/game_core.h` byte for byte.  The layout is
//! asserted by the unit tests below *and* by a `_Static_assert` block in the C
//! test harness (`tools/harness/harness.c`), so a drift between the header and
//! the library is a build failure rather than a mysterious rendering bug.

#![allow(non_camel_case_types)]
#![allow(dead_code)]

pub const GC_ABI_VERSION: u32 = 1;
pub const GC_DESIGN_HEIGHT: f32 = 720.0;

pub const GC_SPR_COUNT: usize = 8;

pub const GC_CMD_SPRITE: i32 = 1;
pub const GC_CMD_RECT: i32 = 2;
pub const GC_CMD_GLYPH: i32 = 3;

pub const GC_FLAG_NONE: i32 = 0;
pub const GC_FLAG_FLASH: i32 = 1;
pub const GC_FLAG_SHADOW: i32 = 2;

pub const GC_BTN_DASH: u32 = 1 << 0;
pub const GC_BTN_PAUSE: u32 = 1 << 1;
pub const GC_BTN_RESTART: u32 = 1 << 2;

pub const GC_STATE_TITLE: i32 = 0;
pub const GC_STATE_PLAYING: i32 = 1;
pub const GC_STATE_LEVEL_UP: i32 = 2;
pub const GC_STATE_SHOP: i32 = 3;
pub const GC_STATE_PAUSED: i32 = 4;
pub const GC_STATE_GAME_OVER: i32 = 5;

// gc_event_type
pub const GC_EVT_SHOOT: i32 = 1;
pub const GC_EVT_HIT: i32 = 2;
pub const GC_EVT_ENEMY_DIE: i32 = 3;
pub const GC_EVT_PLAYER_HURT: i32 = 4;
pub const GC_EVT_PICKUP_XP: i32 = 5;
pub const GC_EVT_PICKUP_MONEY: i32 = 6;
pub const GC_EVT_LEVEL_UP: i32 = 7;
pub const GC_EVT_BUY: i32 = 8;
pub const GC_EVT_BUY_FAIL: i32 = 9;
pub const GC_EVT_WAVE_START: i32 = 10;
pub const GC_EVT_WAVE_CLEAR: i32 = 11;
pub const GC_EVT_GAME_OVER: i32 = 12;
pub const GC_EVT_UI_CLICK: i32 = 13;
pub const GC_EVT_DASH: i32 = 14;
pub const GC_EVT_LIGHTNING: i32 = 15;
pub const GC_EVT_CHECKPOINT_PASSED: i32 = 16;
pub const GC_EVT_CHECKPOINT_FAILED: i32 = 17;
pub const GC_EVT_REVIVED: i32 = 18;
/// A spitter threw blood.  value = damage.
pub const GC_EVT_ENEMY_SHOT: i32 = 19;
/// A miser lifted coins off the player.  value = coins taken.
pub const GC_EVT_MONEY_STOLEN: i32 = 20;

// gc_debug_cmd
pub const GC_DBG_GIVE_MONEY: i32 = 1;
pub const GC_DBG_SET_WAVE: i32 = 2;
pub const GC_DBG_SKIP_WAVE: i32 = 3;
pub const GC_DBG_LEVEL_UP: i32 = 4;
pub const GC_DBG_KILL_PLAYER: i32 = 5;
pub const GC_DBG_GIVE_WEAPON: i32 = 6;
pub const GC_DBG_INVULNERABLE: i32 = 7;
pub const GC_DBG_SET_TIME: i32 = 8;
/// Player settings, as a renderer sees them.  Volumes are already normalised to
/// 0..1 so a shell only has to scale them to its own mixer.
#[repr(C)]
#[derive(Copy, Clone, Debug, Default, PartialEq)]
pub struct gc_settings {
    pub music: f32,
    pub sfx: f32,
    pub haptics: i32,
    pub shake: f32,
    pub damage_numbers: i32,
    /// 0 = low, 1 = medium, 2 = high.
    pub particles: i32,
    /// 0 = full, 1 = reduced.
    pub flashing: i32,
    pub aim_assist: i32,
    pub fullscreen: i32,
}

pub const GC_DBG_ADD_EARNED: i32 = 9;
pub const GC_DBG_GRANT_PERK: i32 = 10;
/// Spawns a few of one enemy kind around the player.  value = kind index:
/// 0 grunt, 1 brute, 2 colossus, 3 charger, 4 spitter, 5 miser.
pub const GC_DBG_SPAWN_ENEMY: i32 = 11;

/// One draw command.  `(x, y)` is always the centre of the quad and `rot`
/// rotates clockwise about it.
#[repr(C)]
#[derive(Copy, Clone, Debug, Default, PartialEq)]
pub struct gc_cmd {
    pub kind: i32,
    pub sprite: i32,
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
    pub rot: f32,
    pub rgba: u32,
    pub u0: f32,
    pub v0: f32,
    pub u1: f32,
    pub v1: f32,
    pub flags: i32,
    pub _pad: i32,
}

#[repr(C)]
#[derive(Copy, Clone, Debug, Default)]
pub struct gc_input {
    pub move_x: f32,
    pub move_y: f32,
    pub aim_x: f32,
    pub aim_y: f32,
    pub pointer_active: i32,
    pub pointer_down: i32,
    pub buttons: u32,
}

#[repr(C)]
#[derive(Copy, Clone, Debug, Default, PartialEq)]
pub struct gc_event {
    pub type_: i32,
    pub x: f32,
    pub y: f32,
    pub value: f32,
}

#[repr(C)]
#[derive(Copy, Clone, Debug, Default)]
pub struct gc_status {
    pub wave: i32,
    pub level: i32,
    pub kills: i32,
    pub money: i32,
    pub score: i32,
    pub best_score: i32,
    pub state: i32,
    pub player_hp: f32,
    pub player_hp_max: f32,
    pub time_alive: f32,
}

/// Incremental progression snapshot (additive ABI, see game_core.h).
#[repr(C)]
#[derive(Copy, Clone, Debug, Default, PartialEq)]
pub struct gc_progress {
    pub tier: i32,
    pub goal: i32,
    pub goal_wave: i32,
    pub money_earned: i32,
}

#[cfg(test)]
mod tests {
    use super::*;
    use core::mem::{align_of, size_of};

    // These numbers are duplicated as _Static_assert in the C harness.  If you
    // change the header, change both or the build breaks.
    #[test]
    fn abi_sizes_match_header() {
        assert_eq!(size_of::<gc_cmd>(), 56);
        assert_eq!(align_of::<gc_cmd>(), 4);
        assert_eq!(size_of::<gc_input>(), 28);
        assert_eq!(size_of::<gc_event>(), 16);
        assert_eq!(size_of::<gc_status>(), 40);
        assert_eq!(size_of::<gc_progress>(), 16);
    }

    #[test]
    fn abi_offsets_match_header() {
        let cmd = gc_cmd::default();
        let base = &cmd as *const gc_cmd as usize;
        let off = |p: *const u8| p as usize - base;
        unsafe {
            assert_eq!(off(&cmd.kind as *const i32 as *const u8), 0);
            assert_eq!(off(&cmd.sprite as *const i32 as *const u8), 4);
            assert_eq!(off(&cmd.x as *const f32 as *const u8), 8);
            assert_eq!(off(&cmd.y as *const f32 as *const u8), 12);
            assert_eq!(off(&cmd.w as *const f32 as *const u8), 16);
            assert_eq!(off(&cmd.h as *const f32 as *const u8), 20);
            assert_eq!(off(&cmd.rot as *const f32 as *const u8), 24);
            assert_eq!(off(&cmd.rgba as *const u32 as *const u8), 28);
            assert_eq!(off(&cmd.u0 as *const f32 as *const u8), 32);
            assert_eq!(off(&cmd.v0 as *const f32 as *const u8), 36);
            assert_eq!(off(&cmd.u1 as *const f32 as *const u8), 40);
            assert_eq!(off(&cmd.v1 as *const f32 as *const u8), 44);
            assert_eq!(off(&cmd.flags as *const i32 as *const u8), 48);
            assert_eq!(off(&cmd._pad as *const i32 as *const u8), 52);
        }
    }
}
