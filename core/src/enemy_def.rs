//! The enemy catalogue.
//!
//! Every enemy is a row in `DEFS`, and its *behaviour* is one of a dozen
//! primitives implemented in `systems.rs`.  Adding a kind is therefore data --
//! a sprite, some numbers, a behaviour and a wave gate -- rather than another
//! `match` arm in eleven functions.
//!
//! Behaviour parameters that a given kind does not use are left at their base
//! values and simply never read (a chaser has no `standoff`, a shooter has no
//! `split_count`).

use crate::entities::EnemyKind;
use crate::sprite::SpriteId;

/// What an enemy *does*, as opposed to how big or tough it is.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Behaviour {
    /// Walks at you and touches you.  The baseline.
    Chaser,
    /// Coils in place, then crosses the arena in a straight line.
    Charger,
    /// Holds a standoff ring and throws something at you.
    Shooter,
    /// Lifts coins out of your purse and runs with them.
    Miser,
    /// Circles you at a fixed radius instead of closing in.
    Orbiter,
    /// Teleports a step toward you every few seconds.
    Blinker,
    /// Gains health and damage the longer it stays alive.
    Grower,
    /// Bursts into smaller enemies when killed.
    Splitter,
    /// Mends nearby allies.
    Healer,
    /// Explodes when killed.
    Bomber,
    /// Heals itself by hurting you.
    Drainer,
    /// Leaves hazards lying on the floor.
    Trapper,
}

#[derive(Copy, Clone, Debug)]
pub struct KindDef {
    pub name: &'static str,
    pub sprite: SpriteId,
    pub behaviour: Behaviour,

    // -- size and numbers --------------------------------------------------
    pub scale: f32,
    pub hp: f32,
    pub speed: f32,
    pub damage: f32,
    pub radius: f32,
    pub xp: i32,
    pub money: i32,
    pub money_chance: f32,
    /// Counts as a heavy: bigger bursts, harder screen shake, more loot.
    pub heavy: bool,
    /// Counts as a colossus for the wave plan and the "big" spawn bookkeeping.
    pub colossal: bool,

    // -- defensive quirks --------------------------------------------------
    /// Flat fraction of incoming damage ignored (0..0.8).
    pub armor: f32,
    /// Fraction of the damage it deals that it heals back.
    pub lifesteal: f32,
    /// Fractional growth per second of health and damage (Grower).
    pub growth: f32,

    // -- ranged quirks -----------------------------------------------------
    pub standoff: f32,
    pub throw_interval: f32,
    pub shot_speed: f32,
    pub shot_damage: f32,

    // -- support and area quirks -------------------------------------------
    /// Radius of a heal aura or a death blast.
    pub sigil_radius: f32,
    /// Heal per second (Healer) or blast damage (Bomber).
    pub sigil_power: f32,

    // -- movement quirks ---------------------------------------------------
    pub orbit_radius: f32,
    pub blink_interval: f32,
    pub blink_step: f32,

    // -- death quirk -------------------------------------------------------
    pub splits_into: Option<EnemyKind>,
    pub split_count: i32,

    // -- purse quirk -------------------------------------------------------
    pub purse: i32,
    pub siphon: f32,
    pub flee_at: i32,

    // -- spawning ----------------------------------------------------------
    /// First wave it can appear on.
    pub min_wave: i32,
    /// Relative spawn weight among the kinds available on that wave.
    pub weight: f32,
    /// Whether a boss wave may pick it as the enormous one.
    pub boss_ok: bool,
}

/// Everything a kind does not use, so each row only states what it means.
pub const BASE: KindDef = KindDef {
    name: "",
    sprite: SpriteId::EnemyA,
    behaviour: Behaviour::Chaser,
    scale: 1.0,
    hp: 22.0,
    speed: 106.0,
    damage: 7.0,
    radius: 24.0,
    xp: 4,
    money: 1,
    money_chance: 0.34,
    heavy: false,
    colossal: false,
    armor: 0.0,
    lifesteal: 0.0,
    growth: 0.0,
    standoff: 0.0,
    throw_interval: f32::INFINITY,
    shot_speed: 280.0,
    shot_damage: 0.0,
    sigil_radius: 0.0,
    sigil_power: 0.0,
    orbit_radius: 0.0,
    blink_interval: 0.0,
    blink_step: 0.0,
    splits_into: None,
    split_count: 0,
    purse: 0,
    siphon: 0.0,
    flee_at: i32::MAX,
    min_wave: 1,
    weight: 1.0,
    boss_ok: false,
};

/// Every kind, indexed by `EnemyKind as usize`.  Keep the order in step with
/// the enum, `ALL_KINDS` and `gc_sprite_id` in include/game_core.h.
pub const DEFS: [KindDef; 16] = [
    // ---- the original six -------------------------------------------------
    KindDef { name: "GRUNT", sprite: SpriteId::EnemyA, ..BASE },
    KindDef {
        name: "BRUTE", sprite: SpriteId::EnemyB, behaviour: Behaviour::Chaser,
        scale: 1.35, hp: 62.0, speed: 82.0, damage: 24.0, radius: 34.0,
        xp: 11, money: 3, money_chance: 0.85, heavy: true, min_wave: 3,
        weight: 0.9, boss_ok: true, ..BASE
    },
    KindDef {
        name: "COLOSSUS", sprite: SpriteId::EnemyB, behaviour: Behaviour::Chaser,
        scale: 2.35, hp: 260.0, speed: 60.0, damage: 42.0, radius: 58.0,
        xp: 70, money: 22, money_chance: 1.0, heavy: true, colossal: true,
        min_wave: 5, weight: 0.35, boss_ok: true, ..BASE
    },
    KindDef {
        name: "CHARGER", sprite: SpriteId::Charger, behaviour: Behaviour::Charger,
        scale: 1.12, hp: 36.0, speed: 104.0, damage: 12.0, radius: 26.0,
        xp: 7, money: 2, money_chance: 0.5, min_wave: 2, weight: 1.1,
        boss_ok: true, ..BASE
    },
    KindDef {
        name: "SPITTER", sprite: SpriteId::Spitter, behaviour: Behaviour::Shooter,
        scale: 1.18, hp: 30.0, speed: 86.0, damage: 7.0, radius: 28.0,
        xp: 6, money: 2, money_chance: 0.45, standoff: 250.0,
        throw_interval: 2.1, shot_speed: 280.0, shot_damage: 9.0,
        min_wave: 4, weight: 0.95, ..BASE
    },
    KindDef {
        name: "MISER", sprite: SpriteId::Miser, behaviour: Behaviour::Miser,
        scale: 0.86, hp: 26.0, speed: 138.0, damage: 6.0, radius: 21.0,
        xp: 6, money: 2, money_chance: 0.4, purse: 22, siphon: 2.5, flee_at: 8,
        min_wave: 6, weight: 0.7, ..BASE
    },

    // ---- ten more ---------------------------------------------------------
    KindDef {
        // Fast, fragile, and never where you are pointing.
        name: "WISP", sprite: SpriteId::Wisp, behaviour: Behaviour::Orbiter,
        scale: 0.8, hp: 18.0, speed: 152.0, damage: 6.0, radius: 18.0,
        xp: 5, money: 1, money_chance: 0.3, orbit_radius: 155.0,
        min_wave: 3, weight: 1.0, ..BASE
    },
    KindDef {
        // Killing it is not the end of it.
        name: "BLOB", sprite: SpriteId::Blob, behaviour: Behaviour::Splitter,
        scale: 1.2, hp: 50.0, speed: 74.0, damage: 9.0, radius: 30.0,
        xp: 8, money: 2, money_chance: 0.5,
        splits_into: Some(EnemyKind::Grunt), split_count: 3,
        min_wave: 4, weight: 0.85, ..BASE
    },
    KindDef {
        // Armoured front to back: you cannot out-DPS it, you have to out-walk it.
        name: "BULWARK", sprite: SpriteId::Bulwark, behaviour: Behaviour::Chaser,
        scale: 1.42, hp: 125.0, speed: 50.0, damage: 18.0, radius: 37.0,
        xp: 14, money: 3, money_chance: 0.9, heavy: true, armor: 0.45,
        min_wave: 7, weight: 0.6, boss_ok: true, ..BASE
    },
    KindDef {
        // The reason to kill things in the right order.
        name: "MENDER", sprite: SpriteId::Mender, behaviour: Behaviour::Healer,
        scale: 1.05, hp: 40.0, speed: 70.0, damage: 7.0, radius: 26.0,
        xp: 10, money: 2, money_chance: 0.6, sigil_radius: 190.0,
        sigil_power: 0.07, min_wave: 8, weight: 0.55, ..BASE
    },
    KindDef {
        // Do not kill it next to yourself.
        name: "BOOMSLIME", sprite: SpriteId::Boomslime, behaviour: Behaviour::Bomber,
        scale: 1.05, hp: 34.0, speed: 98.0, damage: 8.0, radius: 25.0,
        xp: 7, money: 2, money_chance: 0.5, sigil_radius: 175.0,
        sigil_power: 22.0, min_wave: 6, weight: 0.8, boss_ok: true, ..BASE
    },
    KindDef {
        // Closes the gap without crossing it.
        name: "SHADE", sprite: SpriteId::Shade, behaviour: Behaviour::Blinker,
        scale: 0.95, hp: 44.0, speed: 108.0, damage: 12.0, radius: 24.0,
        xp: 11, money: 2, money_chance: 0.6, blink_interval: 2.6,
        blink_step: 240.0, min_wave: 9, weight: 0.6, ..BASE
    },
    KindDef {
        // Long reach, fast bolt, and it will not let you close.
        name: "LANCER", sprite: SpriteId::Lancer, behaviour: Behaviour::Shooter,
        scale: 1.1, hp: 38.0, speed: 64.0, damage: 6.0, radius: 25.0,
        xp: 12, money: 3, money_chance: 0.7, standoff: 430.0,
        throw_interval: 1.7, shot_speed: 400.0, shot_damage: 14.0,
        min_wave: 10, weight: 0.7, ..BASE
    },
    KindDef {
        // Leave it alone and it becomes a problem.
        name: "DEVOURER", sprite: SpriteId::Devourer, behaviour: Behaviour::Grower,
        scale: 1.25, hp: 70.0, speed: 68.0, damage: 14.0, radius: 30.0,
        xp: 15, money: 3, money_chance: 0.8, heavy: true, growth: 0.07,
        min_wave: 12, weight: 0.6, boss_ok: true, ..BASE
    },
    KindDef {
        // It gets healthier the longer it stays on you.
        name: "LEECH", sprite: SpriteId::Leech, behaviour: Behaviour::Drainer,
        scale: 0.95, hp: 46.0, speed: 118.0, damage: 10.0, radius: 23.0,
        xp: 11, money: 2, money_chance: 0.6, lifesteal: 0.7,
        min_wave: 11, weight: 0.7, ..BASE
    },
    KindDef {
        // Area denial: it does not chase you, it makes chasing it expensive.
        name: "SPIKER", sprite: SpriteId::Spiker, behaviour: Behaviour::Trapper,
        scale: 1.06, hp: 42.0, speed: 88.0, damage: 9.0, radius: 26.0,
        xp: 12, money: 3, money_chance: 0.7, throw_interval: 2.2,
        shot_speed: 0.0, shot_damage: 7.0, min_wave: 10, weight: 0.65, ..BASE
    },
];

#[cfg(test)]
mod tests {
    use super::*;
    use crate::entities::{kind_from_index, EnemyKind, ALL_KINDS};

    #[test]
    fn the_table_covers_every_kind_in_order() {
        for (i, kind) in ALL_KINDS.iter().enumerate() {
            assert_eq!(*kind as usize, i, "ALL_KINDS is out of step with the enum");
            let def = DEFS[i];
            assert!(!def.name.is_empty(), "kind {} has no name", i);
            assert!(def.hp > 0.0 && def.speed > 0.0 && def.radius > 0.0,
                    "{} has nonsense stats", def.name);
            assert!(def.damage >= 0.0);
            assert!((0.0..0.8).contains(&def.armor), "{} armour out of range", def.name);
            assert!(def.weight > 0.0, "{} can never spawn", def.name);
            assert_eq!(kind_from_index(i as i32), Some(*kind));
        }
        assert_eq!(ALL_KINDS.len(), DEFS.len());
    }

    #[test]
    fn every_kind_is_reachable_by_its_own_wave() {
        // A kind gated behind a wave nobody reaches is content that does not
        // exist; keep the gates inside a sane run.
        for def in DEFS.iter() {
            assert!((1..=20).contains(&def.min_wave),
                    "{} unlocks on wave {}", def.name, def.min_wave);
        }
        // And there are enough of them to be worth calling a catalogue.
        assert!(DEFS.len() >= 16, "expected at least sixteen kinds");
    }

    #[test]
    fn every_behaviour_is_used_by_something() {
        // A behaviour nothing uses is dead code pretending to be a feature.
        let all = [
            Behaviour::Chaser, Behaviour::Charger, Behaviour::Shooter,
            Behaviour::Miser, Behaviour::Orbiter, Behaviour::Blinker,
            Behaviour::Grower, Behaviour::Splitter, Behaviour::Healer,
            Behaviour::Bomber, Behaviour::Drainer, Behaviour::Trapper,
        ];
        for b in all {
            assert!(DEFS.iter().any(|d| d.behaviour == b), "no kind uses {:?}", b);
        }
    }

    #[test]
    fn boss_candidates_are_the_heavy_hitters() {
        let bosses: Vec<&KindDef> = DEFS.iter().filter(|d| d.boss_ok).collect();
        assert!(bosses.len() >= 5, "too few boss candidates");
        for b in bosses {
            assert!(b.hp >= 30.0 && b.damage >= 6.0,
                    "{} would make a toothless boss", b.name);
        }
    }
}
