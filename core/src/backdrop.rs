//! The procedural backdrop.
//!
//! The arena's mood is driven by the wave number: it starts in Hell and cycles
//! Hell -> Gold -> Lava -> Paradise -> Purple -> Godly -> Hell ..., interpolating
//! *smoothly* between neighbouring themes so the change is continuous rather
//! than a hard cut, and jittering the palette per run so two runs never look
//! quite the same.
//!
//! Each theme also drives the ambient particle field (embers, sparkles, motes,
//! orbs, ...), which is what actually sells the mood.

use crate::math::{lerp, Vec2, Rng};
use crate::render::color;

/// Waves spent in one theme before it starts blending into the next.
pub const WAVES_PER_THEME: f32 = 3.0;

#[derive(Copy, Clone, Debug)]
pub struct Ambient {
    /// Particles per second spawned around the camera.
    pub rate: f32,
    pub color: u32,
    pub size: (f32, f32),
    /// Vertical drift range, negative = falling.
    pub drift: (f32, f32),
    pub sway: f32,
    pub drag: f32,
    pub life: (f32, f32),
    pub additive: bool,
}

#[derive(Copy, Clone, Debug)]
pub struct Theme {
    pub name: &'static str,
    /// Outside the arena.
    pub deep: u32,
    pub floor: u32,
    pub grid: u32,
    pub edge: u32,
    /// Used for accents (HUD flourishes, arena pulse).
    pub accent: u32,
    pub ambient: Ambient,
}

pub const THEME_COUNT: usize = 6;

/// The cycle, in order.  Theme 0 is deliberately the hostile one.
pub const THEMES: [Theme; THEME_COUNT] = [
    // 0 -- HELL: charcoal and dried blood, embers drifting up.
    Theme {
        name: "HELL",
        deep: color::rgb(0x10, 0x05, 0x08),
        floor: color::rgb(0x1e, 0x0b, 0x11),
        grid: color::rgb(0x2c, 0x11, 0x1a),
        edge: color::rgb(0x6b, 0x1f, 0x2a),
        accent: color::rgb(0xff, 0x6b, 0x3c),
        ambient: Ambient {
            rate: 26.0,
            color: color::rgb(0xff, 0x7a, 0x3c),
            size: (2.0, 5.0),
            drift: (-34.0, -12.0),
            sway: 14.0,
            drag: 0.5,
            life: (1.6, 3.0),
            additive: true,
        },
    },
    // 1 -- GOLD: a treasury, dust motes catching the light.
    Theme {
        name: "GOLD",
        deep: color::rgb(0x12, 0x0e, 0x06),
        floor: color::rgb(0x24, 0x1d, 0x0d),
        grid: color::rgb(0x38, 0x2c, 0x14),
        edge: color::rgb(0x8a, 0x6c, 0x2a),
        accent: color::rgb(0xff, 0xd1, 0x66),
        ambient: Ambient {
            rate: 30.0,
            color: color::rgb(0xff, 0xd9, 0x8a),
            size: (1.5, 4.0),
            drift: (-18.0, 6.0),
            sway: 22.0,
            drag: 0.8,
            life: (1.8, 3.2),
            additive: true,
        },
    },
    // 2 -- LAVA: molten, heavy ash falling.
    Theme {
        name: "LAVA",
        deep: color::rgb(0x14, 0x07, 0x04),
        floor: color::rgb(0x2a, 0x10, 0x07),
        grid: color::rgb(0x46, 0x1c, 0x0c),
        edge: color::rgb(0xa8, 0x46, 0x18),
        accent: color::rgb(0xff, 0x8a, 0x2a),
        ambient: Ambient {
            rate: 34.0,
            color: color::rgb(0xff, 0x5a, 0x1e),
            size: (2.5, 6.5),
            drift: (-70.0, -24.0),
            sway: 10.0,
            drag: 0.4,
            life: (1.2, 2.4),
            additive: true,
        },
    },
    // 3 -- PARADISE: cool water and jade, light motes rising.
    Theme {
        name: "PARADISE",
        deep: color::rgb(0x04, 0x12, 0x16),
        floor: color::rgb(0x0b, 0x26, 0x28),
        grid: color::rgb(0x12, 0x3a, 0x36),
        edge: color::rgb(0x2e, 0xa8, 0x90),
        accent: color::rgb(0x8c, 0xf5, 0xd8),
        ambient: Ambient {
            rate: 24.0,
            color: color::rgb(0xa8, 0xff, 0xe8),
            size: (2.0, 5.5),
            drift: (-30.0, -10.0),
            sway: 30.0,
            drag: 0.6,
            life: (2.2, 3.8),
            additive: true,
        },
    },
    // 4 -- PURPLE: deep arcane, slow drifting orbs.
    Theme {
        name: "PURPLE",
        deep: color::rgb(0x0b, 0x05, 0x14),
        floor: color::rgb(0x1a, 0x0e, 0x2c),
        grid: color::rgb(0x28, 0x16, 0x44),
        edge: color::rgb(0x6c, 0x40, 0xc0),
        accent: color::rgb(0xc9, 0x8c, 0xff),
        ambient: Ambient {
            rate: 22.0,
            color: color::rgb(0xc0, 0x8a, 0xff),
            size: (3.0, 8.0),
            drift: (-20.0, 10.0),
            sway: 18.0,
            drag: 0.9,
            life: (2.6, 4.4),
            additive: true,
        },
    },
    // 5 -- GODLY: white marble and light, beams falling from above.
    Theme {
        name: "GODLY",
        deep: color::rgb(0x10, 0x11, 0x0c),
        floor: color::rgb(0x26, 0x27, 0x1e),
        grid: color::rgb(0x40, 0x42, 0x32),
        edge: color::rgb(0xc8, 0xbc, 0x74),
        accent: color::rgb(0xff, 0xf4, 0xb0),
        ambient: Ambient {
            rate: 32.0,
            color: color::rgb(0xff, 0xf6, 0xc8),
            size: (1.2, 3.4),
            drift: (-140.0, -70.0),
            sway: 4.0,
            drag: 0.2,
            life: (0.9, 1.6),
            additive: true,
        },
    },
];

/// An interpolated palette for the current moment.
#[derive(Copy, Clone, Debug)]
pub struct Palette {
    pub name: &'static str,
    pub next_name: &'static str,
    pub blend: f32,
    pub deep: u32,
    pub floor: u32,
    pub grid: u32,
    pub edge: u32,
    pub accent: u32,
    pub ambient: Ambient,
}

/// Tracks where in the cycle we are and applies per-run randomness.
#[derive(Clone, Debug)]
pub struct Backdrop {
    /// Continuous position in the theme cycle (0.0 = start of THEMES[0]).
    pub cursor: f32,
    /// Per-run brightness/hue jitter, one per theme, so no two runs match.
    jitter: [f32; THEME_COUNT],
    /// Per-run ambient rate multiplier.
    activity: f32,
    /// Accumulated spawn credit, so low rates still emit smoothly.
    credit: f32,
}

impl Backdrop {
    pub fn new(rng: &mut Rng) -> Backdrop {
        let mut jitter = [1.0f32; THEME_COUNT];
        for j in jitter.iter_mut() {
            *j = rng.range(0.82, 1.22);
        }
        Backdrop {
            cursor: 0.0,
            jitter,
            activity: rng.range(0.8, 1.25),
            credit: 0.0,
        }
    }

    /// Reseeds the per-run randomness (called when a run starts).
    pub fn reseed(&mut self, rng: &mut Rng) {
        for j in self.jitter.iter_mut() {
            *j = rng.range(0.82, 1.22);
        }
        self.activity = rng.range(0.8, 1.25);
        self.cursor = 0.0;
        self.credit = 0.0;
    }

    /// Advances the cycle from the wave number.  Wave 1 is the heart of Hell.
    pub fn update(&mut self, wave: i32, dt: f32) {
        let target = ((wave - 1).max(0) as f32) / WAVES_PER_THEME;
        // Ease toward the target so a wave change is a swell, not a jump.
        self.cursor = lerp(self.cursor, target, (1.0 - (-1.6 * dt).exp()).clamp(0.0, 1.0));
    }

    fn jittered(&self, index: usize, c: u32) -> u32 {
        tint(c, self.jitter[index % THEME_COUNT])
    }

    /// Index of the dominant theme right now (0..THEME_COUNT).
    pub fn theme_index(&self) -> i32 {
        let n = THEME_COUNT as f32;
        (self.cursor.rem_euclid(n).floor() as i32).rem_euclid(THEME_COUNT as i32)
    }

    pub fn palette(&self) -> Palette {
        let n = THEME_COUNT as f32;
        let wrapped = self.cursor.rem_euclid(n);
        let i = wrapped.floor() as usize % THEME_COUNT;
        let j = (i + 1) % THEME_COUNT;
        let t = (wrapped - wrapped.floor()).clamp(0.0, 1.0);

        let a = &THEMES[i];
        let b = &THEMES[j];
        Palette {
            name: a.name,
            next_name: b.name,
            blend: t,
            deep: mix(self.jittered(i, a.deep), self.jittered(j, b.deep), t),
            floor: mix(self.jittered(i, a.floor), self.jittered(j, b.floor), t),
            grid: mix(self.jittered(i, a.grid), self.jittered(j, b.grid), t),
            edge: mix(self.jittered(i, a.edge), self.jittered(j, b.edge), t),
            accent: mix(self.jittered(i, a.accent), self.jittered(j, b.accent), t),
            ambient: mix_ambient(a.ambient, b.ambient, t, self.activity),
        }
    }

    /// Housekeeping for the ambient spawner: returns how many particles to emit.
    pub fn take_ambient_budget(&mut self, dt: f32, rate: f32) -> i32 {
        self.credit += rate * dt;
        let n = self.credit.floor() as i32;
        self.credit -= n as f32;
        n.clamp(0, 6)
    }
}

fn channel(c: u32, shift: u32) -> f32 {
    ((c >> shift) & 0xff) as f32
}

fn mix(a: u32, b: u32, t: f32) -> u32 {
    let ch = |shift: u32| lerp(channel(a, shift), channel(b, shift), t).round().clamp(0.0, 255.0) as u32;
    (0xff00_0000) | (ch(16) << 16) | (ch(8) << 8) | ch(0)
}

fn tint(c: u32, k: f32) -> u32 {
    let ch = |shift: u32| (channel(c, shift) * k).round().clamp(0.0, 255.0) as u32;
    (0xff00_0000) | (ch(16) << 16) | (ch(8) << 8) | ch(0)
}

fn mix_ambient(a: Ambient, b: Ambient, t: f32, activity: f32) -> Ambient {
    Ambient {
        rate: lerp(a.rate, b.rate, t) * activity,
        color: mix(a.color, b.color, t),
        size: (lerp(a.size.0, b.size.0, t), lerp(a.size.1, b.size.1, t)),
        drift: (lerp(a.drift.0, b.drift.0, t), lerp(a.drift.1, b.drift.1, t)),
        sway: lerp(a.sway, b.sway, t),
        drag: lerp(a.drag, b.drag, t),
        life: (lerp(a.life.0, b.life.0, t), lerp(a.life.1, b.life.1, t)),
        additive: a.additive || b.additive,
    }
}

/// Spawns one ambient particle for a palette, anywhere in a rectangle around
/// `center` (so the effect is always visible, wherever the camera is).
pub fn spawn_ambient(palette: &Palette, center: Vec2, half: Vec2, rng: &mut Rng) -> crate::entities::Particle {
    use crate::entities::Particle;
    let pos = Vec2::new(
        center.x + rng.range(-half.x, half.x),
        center.y + rng.range(-half.y, half.y),
    );
    let a = &palette.ambient;
    let v = rng.range(a.drift.0, a.drift.1);
    Particle {
        pos,
        vel: Vec2::new(rng.range(-a.sway, a.sway), v),
        life: rng.range(a.life.0, a.life.1),
        life_max: a.life.1,
        size: rng.range(a.size.0, a.size.1),
        color: a.color,
        rot: 0.0,
        spin: rng.range(-2.0, 2.0),
        drag: a.drag,
        additive: a.additive,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_cycle_starts_at_hell_and_wraps() {
        let mut rng = Rng::new(1);
        let b = Backdrop::new(&mut rng);
        let p = b.palette();
        assert_eq!(p.name, "HELL");
        assert!(p.blend.abs() < 1e-6);
    }

    #[test]
    fn later_waves_reach_every_theme_and_loop() {
        let mut rng = Rng::new(7);
        let mut b = Backdrop::new(&mut rng);
        // Jump the cursor directly (update() is an ease and would lag).
        let mut seen = [false; THEME_COUNT];
        for step in 0..THEME_COUNT * 4 {
            b.cursor = step as f32;
            let p = b.palette();
            let idx = THEMES.iter().position(|t| t.name == p.name).unwrap();
            seen[idx] = true;
        }
        assert!(seen.iter().all(|s| *s), "every theme must be reachable");
    }

    #[test]
    fn palettes_stay_opaque_and_in_range() {
        let mut rng = Rng::new(3);
        let mut b = Backdrop::new(&mut rng);
        for step in 0..400 {
            b.cursor = step as f32 * 0.05;
            let p = b.palette();
            for c in [p.deep, p.floor, p.grid, p.edge, p.accent, p.ambient.color] {
                assert_eq!(c >> 24, 0xff, "colour must stay opaque");
            }
            assert!(p.ambient.rate > 0.0 && p.ambient.rate < 200.0);
            assert!(p.ambient.size.0 > 0.0 && p.ambient.size.1 < 40.0);
        }
    }

    #[test]
    fn runs_are_jittered_differently() {
        let mut a = Backdrop::new(&mut Rng::new(11));
        let mut b = Backdrop::new(&mut Rng::new(22));
        a.cursor = 0.0;
        b.cursor = 0.0;
        assert_ne!(a.palette().floor, b.palette().floor,
                   "two seeds should not produce identical palettes");
    }

    #[test]
    fn ambient_budget_is_bounded_and_smooth() {
        let mut rng = Rng::new(5);
        let mut b = Backdrop::new(&mut rng);
        let mut total = 0;
        for _ in 0..600 {
            total += b.take_ambient_budget(1.0 / 60.0, 30.0);
        }
        // ~30/second for 10 seconds, within rounding.
        assert!((250..=350).contains(&total), "emitted {}", total);
    }
}
