//! Sprite identifiers and the design sizes used when emitting quads.
//!
//! The art itself lives in `assets/dist/*.png`; the library only needs to know
//! how big each sprite should be drawn in world units and what its aspect ratio
//! is (generated from the trimmed PNGs so quads are never distorted).

use crate::math::PI;
use crate::generated::sprites::{aspect_of, file_of};

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
#[repr(i32)]
pub enum SpriteId {
    Player = 0,
    EnemyA = 1,
    EnemyB = 2,
    Gun = 3,
    Bow = 4,
    Sword = 5,
    Money = 6,
    Xp = 7,
}

pub const SPRITE_COUNT: usize = 8;

impl SpriteId {
    pub fn index(self) -> i32 {
        self as i32
    }

    pub fn aspect(self) -> f32 {
        aspect_of(self)
    }

    pub fn file(self) -> &'static str {
        file_of(self)
    }

    /// NUL terminated file name, for `gc_sprite_file()` and the C ABI.
    pub fn file_cstr(self) -> &'static str {
        match self {
            SpriteId::Player => "player.png\0",
            SpriteId::EnemyA => "enemy_a.png\0",
            SpriteId::EnemyB => "enemy_b.png\0",
            SpriteId::Gun => "gun.png\0",
            SpriteId::Bow => "bow.png\0",
            SpriteId::Sword => "sword.png\0",
            SpriteId::Money => "money.png\0",
            SpriteId::Xp => "xp.png\0",
        }
    }

    /// Height, in world units, that this sprite is drawn at by default.
    /// Width follows from the trimmed texture's aspect ratio.
    pub fn design_height(self) -> f32 {
        match self {
            SpriteId::Player => 62.0,
            SpriteId::EnemyA => 56.0,
            SpriteId::EnemyB => 80.0,
            SpriteId::Gun => 46.0,
            SpriteId::Bow => 50.0,
            SpriteId::Sword => 54.0,
            SpriteId::Money => 24.0,
            SpriteId::Xp => 22.0,
        }
    }

    pub fn design_width(self) -> f32 {
        self.design_height() * self.aspect()
    }
}

/// Every weapon in the source sheet is drawn diagonally, pointing up and to the
/// right: that is -45 degrees in the y-down screen space the renderers use.  To
/// aim a weapon at `angle`, a renderer rotates it by `angle - WEAPON_ART_ANGLE`,
/// i.e. `angle + PI/4`.
pub const WEAPON_ART_ANGLE: f32 = -PI / 4.0;

/// Font atlas file name (NUL terminated) for `gc_font_atlas()`.
pub const FONT_ATLAS_FILE: &str = "font_atlas.png\0";

pub fn weapon_rotation_for(aim_angle: f32) -> f32 {
    aim_angle - WEAPON_ART_ANGLE
}

pub fn all_sprites() -> [SpriteId; SPRITE_COUNT] {
    [
        SpriteId::Player,
        SpriteId::EnemyA,
        SpriteId::EnemyB,
        SpriteId::Gun,
        SpriteId::Bow,
        SpriteId::Sword,
        SpriteId::Money,
        SpriteId::Xp,
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sprite_table_is_complete_and_sane() {
        for id in all_sprites() {
            assert!(id.aspect() > 0.2 && id.aspect() < 5.0, "{:?} aspect {}", id, id.aspect());
            assert!(id.file().ends_with(".png"));
            assert!(id.design_height() > 0.0);
            assert!(id.design_width() > 0.0);
        }
    }

    #[test]
    fn weapon_rotation_aligns_art_with_aim() {
        // Aiming right (0 rad) must rotate the diagonal art by +45 degrees.
        assert!((weapon_rotation_for(0.0) - PI / 4.0).abs() < 1e-6);
    }

    #[test]
    fn c_string_names_match_the_generated_table() {
        // Catches drift between the hand written NUL terminated names and the
        // generated file names (which is what the renderers actually load).
        for id in all_sprites() {
            let with_nul = id.file_cstr();
            assert!(with_nul.ends_with('\0'), "{:?} must be NUL terminated", id);
            assert_eq!(&with_nul[..with_nul.len() - 1], id.file());
        }
        assert!(FONT_ATLAS_FILE.ends_with('\0'));
    }
}
