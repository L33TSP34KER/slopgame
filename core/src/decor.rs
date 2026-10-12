//! Procedural scenery.
//!
//! The backdrop is more than a tint and a particle field: every theme scatters
//! its own *features* through the arena -- cracks and rubble in Hell, coin
//! mounds in Gold, lava pools, water ripples, arcane runes, marble columns --
//! plus a slow parallax layer of large soft shapes behind them.  Props live in
//! world space at fixed positions, so the arena reads as a place you are moving
//! through rather than a scrolling texture.
//!
//! The set is seeded from (run seed, theme index), so it is stable while you are
//! in a theme, different between themes, and reproducible for a given seed.
//! Theme changes cross-fade between two sets.

use crate::backdrop::Palette;
use crate::math::{Vec2, Rng, TAU};
use crate::render::{color, fade, Renderer};

/// Arena bounds are imported from the world; kept as a parameter so this module
/// has no dependency on the game state.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum PropKind {
    /// A jagged fissure in the floor.
    Crack,
    /// A heap of coins.
    Mound,
    /// A glowing pool of lava.
    Pool,
    /// Concentric water rings.
    Ripple,
    /// A rotating rune circle.
    Rune,
    /// A floating crystal shard.
    Crystal,
    /// A marble column.
    Column,
    /// A warm glow in the floor.
    Ember,
    /// A shaft of light from above.
    Shaft,
    /// Scattered debris.
    Rubble,
    /// A large soft out-of-focus blob.
    Bokeh,
}

#[derive(Copy, Clone, Debug)]
pub struct Prop {
    pub pos: Vec2,
    pub kind: PropKind,
    pub scale: f32,
    /// Per-prop random phase so animations do not march in lockstep.
    pub phase: f32,
    pub rot: f32,
    pub colour: u32,
}

#[derive(Clone, Debug)]
pub struct PropSet {
    pub theme: i32,
    /// Large, slow shapes drawn behind everything at reduced parallax.
    pub back: Vec<Prop>,
    /// Features on the arena floor.
    pub props: Vec<Prop>,
}

impl PropSet {
    /// Builds the scenery for one theme.
    pub fn generate(seed: u32, theme: i32, arena: Vec2) -> PropSet {
        let mut rng = Rng::new(seed ^ (theme as u32).wrapping_mul(0x9E37_79B9));
        let palette = crate::backdrop::THEMES[(theme as usize) % crate::backdrop::THEME_COUNT];

        let (kinds, back_kinds, accent, back_accent): (&[PropKind], &[PropKind], u32, u32) =
            match theme.rem_euclid(6) {
                0 => (&[PropKind::Crack, PropKind::Rubble, PropKind::Ember],
                      &[PropKind::Bokeh],
                      palette.accent, color::rgb(0x50, 0x12, 0x18)),
                1 => (&[PropKind::Mound, PropKind::Ember, PropKind::Bokeh],
                      &[PropKind::Bokeh],
                      palette.accent, color::rgb(0x50, 0x3c, 0x10)),
                2 => (&[PropKind::Pool, PropKind::Crack, PropKind::Rubble],
                      &[PropKind::Bokeh],
                      palette.accent, color::rgb(0x60, 0x1c, 0x08)),
                3 => (&[PropKind::Ripple, PropKind::Bokeh, PropKind::Crystal],
                      &[PropKind::Bokeh],
                      palette.accent, color::rgb(0x0e, 0x38, 0x34)),
                4 => (&[PropKind::Rune, PropKind::Crystal, PropKind::Bokeh],
                      &[PropKind::Bokeh],
                      palette.accent, color::rgb(0x24, 0x12, 0x44)),
                _ => (&[PropKind::Shaft, PropKind::Column, PropKind::Bokeh],
                      &[PropKind::Bokeh],
                      palette.accent, color::rgb(0x34, 0x32, 0x22)),
            };

        let pick = |rng: &mut Rng, kinds: &[PropKind]| -> PropKind {
            kinds[(rng.next_u32() as usize) % kinds.len()]
        };

        // Features: bigger and denser in the middle of the arena, so the centre
        // stays busy and the edges stay clean for combat.
        let mut props = Vec::with_capacity(34);
        for _ in 0..34 {
            let kind = pick(&mut rng, kinds);
            let pos = Vec2::new(rng.range(90.0, arena.x - 90.0),
                                rng.range(90.0, arena.y - 90.0));
            let mut scale = rng.range(0.7, 1.5);
            if kind == PropKind::Bokeh {
                scale *= 1.6;
            }
            props.push(Prop {
                pos,
                kind,
                scale,
                phase: rng.angle(),
                rot: rng.range(-0.4, 0.4),
                colour: accent,
            });
        }

        // The parallax layer: fewer, much larger, very soft.
        let mut back = Vec::with_capacity(16);
        for _ in 0..16 {
            let kind = pick(&mut rng, back_kinds);
            back.push(Prop {
                pos: Vec2::new(rng.range(0.0, arena.x), rng.range(0.0, arena.y)),
                kind,
                scale: rng.range(1.6, 3.4),
                phase: rng.angle(),
                rot: 0.0,
                colour: back_accent,
            });
        }

        PropSet { theme, back, props }
    }
}

/// Owns the current scenery and cross-fades when the theme changes.
#[derive(Clone, Debug)]
pub struct Decor {
    current: PropSet,
    previous: Option<PropSet>,
    /// 0..1 for the cross-fade into `current`.
    fade: f32,
    arena: Vec2,
    seed: u32,
}

impl Decor {
    pub fn new(seed: u32, arena: Vec2) -> Decor {
        Decor {
            current: PropSet::generate(seed, 0, arena),
            previous: None,
            fade: 1.0,
            arena,
            seed,
        }
    }

    pub fn reseed(&mut self, seed: u32) {
        self.seed = seed;
        self.current = PropSet::generate(seed, 0, self.arena);
        self.previous = None;
        self.fade = 1.0;
    }

    /// Swaps in a theme's scenery and starts the cross-fade.
    pub fn set_theme(&mut self, theme: i32) {
        if theme == self.current.theme {
            return;
        }
        let old = core::mem::replace(&mut self.current,
                                     PropSet::generate(self.seed, theme, self.arena));
        self.previous = Some(old);
        self.fade = 0.0;
    }

    pub fn update(&mut self, dt: f32, theme: i32) {
        self.set_theme(theme);
        if self.fade < 1.0 {
            // ~1.2s cross-fade.
            self.fade = (self.fade + dt / 1.2).min(1.0);
            if self.fade >= 1.0 {
                self.previous = None;
            }
        }
    }

    pub fn draw(&self, r: &mut Renderer, palette: &Palette, time: f32) {
        // Outgoing set first, fading away.
        if let Some(prev) = &self.previous {
            let a = 1.0 - self.fade;
            draw_set(r, prev, palette, time, a);
        }
        draw_set(r, &self.current, palette, time, self.fade);
        vignette(r, palette);
    }

    fn draw_layer(r: &mut Renderer, props: &[Prop], time: f32, alpha: f32, parallax: f32,
                  camera: Vec2) {
        for p in props {
            // Parallax: shift the world position so a distant prop moves slower.
            let world = p.pos + camera * (1.0 - parallax);
            draw_prop(r, p, world, time, alpha, parallax);
        }
    }
}

fn draw_set(r: &mut Renderer, set: &PropSet, palette: &Palette, time: f32, alpha: f32) {
    if alpha <= 0.01 {
        return;
    }
    let camera = r.camera;
    Decor::draw_layer(r, &set.back, time, alpha * 0.55, 0.45, camera);
    Decor::draw_layer(r, &set.props, time, alpha, 1.0, camera);
    let _ = palette;
}

// ---------------------------------------------------------------------------
// the props themselves
// ---------------------------------------------------------------------------

fn draw_prop(r: &mut Renderer, p: &Prop, at: Vec2, time: f32, alpha: f32, parallax: f32) {
    let s = p.scale;
    // Only bother with props that can be on screen.
    let zoom = r.zoom.max(0.01);
    let half = Vec2::new(r.view.virt_w * 0.5 / zoom, r.view.virt_h * 0.5 / zoom);
    let reach = 260.0 * s;
    let centre = r.camera * parallax;
    if (at.x - centre.x).abs() > half.x + reach || (at.y - centre.y).abs() > half.y + reach {
        return;
    }
    let pulse = 0.75 + 0.25 * (time * 1.6 + p.phase).sin();
    let a = alpha * pulse;

    match p.kind {
        PropKind::Crack => {
            // A jagged fissure with a hot core.
            let segs = 4;
            let mut from = at;
            let dir = Vec2::from_angle(p.rot);
            for i in 0..segs {
                let len = 46.0 * s * (0.7 + 0.3 * (i as f32));
                let bend = Vec2::from_angle(p.rot + (time * 0.05 + p.phase + i as f32).sin() * 0.4);
                let to = from + (dir + bend) * 0.5 * len;
                r.line_world(from, to, 9.0 * s, fade(color::BLACK, 0.5 * alpha));
                r.line_world(from, to, 3.0 * s, fade(p.colour, 0.35 * a));
                from = to;
            }
        }
        PropKind::Rubble => {
            for k in 0..4 {
                let off = Vec2::from_angle(p.phase + k as f32 * 1.7) * (22.0 * s);
                r.rect_world(at + off, 26.0 * s, 18.0 * s, p.rot + k as f32 * 0.6,
                             fade(color::rgb(0x2a, 0x2a, 0x30), 0.75 * alpha), 0);
                r.rect_world(at + off, 26.0 * s, 3.0 * s, p.rot + k as f32 * 0.6,
                             fade(color::WHITE, 0.06 * alpha), 0);
            }
        }
        PropKind::Mound => {
            // A heap of coins: five tiers that narrow as they stack, each with a
            // bright rim so the tiers stay legible instead of merging into a box.
            let tiers = 5;
            for k in 0..tiers {
                let t = k as f32;
                let w = (104.0 - t * 14.0) * s;
                let y = at.y + 22.0 * s - t * 13.0 * s;
                r.rect_world(Vec2::new(at.x, y + 2.0 * s), w, 13.0 * s, 0.0,
                             fade(color::BLACK, 0.30 * alpha), 0);
                r.rect_world(Vec2::new(at.x, y), w, 13.0 * s, 0.0,
                             fade(p.colour, (0.34 - t * 0.03) * alpha), 0);
                r.rect_world(Vec2::new(at.x, y - 4.5 * s), w * 0.92, 3.0 * s, 0.0,
                             fade(color::WHITE, 0.20 * alpha), 0);
                // A couple of loose coins at the base.
                if k == 0 {
                    for side in [-1.0f32, 1.0] {
                        r.rect_world(at + Vec2::new(side * (w * 0.5 + 16.0 * s), 6.0 * s),
                                     18.0 * s, 12.0 * s, 0.0,
                                     fade(p.colour, 0.30 * alpha), 0);
                    }
                }
            }
        }
        PropKind::Pool => {
            // Molten pool: nested bands, the middle one breathing.
            for k in 0..3 {
                let w = (120.0 - k as f32 * 30.0) * s;
                let h = (74.0 - k as f32 * 18.0) * s;
                r.rect_world(at, w, h, 0.0,
                             fade(color::rgb(0xff, 0x50, 0x10), (0.16 + 0.10 * k as f32) * a),
                             if k == 0 { 0 } else { crate::ffi::GC_FLAG_FLASH });
            }
        }
        PropKind::Ripple => {
            let grow = (time * 0.35 + p.phase).fract();
            for k in 0..3 {
                let t = ((grow + k as f32 / 3.0).fract()) * 1.0;
                let radius = (40.0 + t * 90.0) * s;
                let a2 = (1.0 - t) * 0.35 * alpha;
                ring(r, at, radius, 2.5 * s, fade(p.colour, a2));
            }
        }
        PropKind::Rune => {
            let spin = time * 0.25 + p.phase;
            ring(r, at, 70.0 * s, 3.0 * s, fade(p.colour, 0.30 * a));
            ring(r, at, 46.0 * s, 2.0 * s, fade(p.colour, 0.20 * a));
            for k in 0..6 {
                let dir = Vec2::from_angle(spin + k as f32 * TAU / 6.0);
                r.line_world(at + dir * 46.0 * s, at + dir * 70.0 * s, 3.0 * s,
                             fade(p.colour, 0.34 * a));
            }
        }
        PropKind::Crystal => {
            let hover = (time * 0.9 + p.phase).sin() * 6.0 * s;
            let c = at + Vec2::new(0.0, hover);
            r.rect_world(c, 40.0 * s, 40.0 * s, std::f32::consts::FRAC_PI_4,
                         fade(p.colour, 0.28 * a), 0);
            r.rect_world(c, 40.0 * s, 3.0 * s, std::f32::consts::FRAC_PI_4,
                         fade(color::WHITE, 0.22 * a), crate::ffi::GC_FLAG_FLASH);
            r.rect_world(c, 3.0 * s, 40.0 * s, std::f32::consts::FRAC_PI_4,
                         fade(color::WHITE, 0.22 * a), crate::ffi::GC_FLAG_FLASH);
        }
        PropKind::Column => {
            let h = 150.0 * s;
            r.rect_world(at + Vec2::new(10.0 * s, 0.0), 46.0 * s, h, 0.0,
                         fade(color::BLACK, 0.35 * alpha), 0);
            r.rect_world(at, 46.0 * s, h, 0.0, fade(color::rgb(0x3a, 0x38, 0x2c), 0.8 * alpha), 0);
            r.rect_world(at + Vec2::new(-14.0 * s, 0.0), 8.0 * s, h, 0.0,
                         fade(color::WHITE, 0.10 * alpha), 0);
            r.rect_world(at + Vec2::new(0.0, -h * 0.5), 60.0 * s, 12.0 * s, 0.0,
                         fade(color::rgb(0x4a, 0x48, 0x38), 0.8 * alpha), 0);
            r.rect_world(at + Vec2::new(0.0, h * 0.5), 60.0 * s, 12.0 * s, 0.0,
                         fade(color::rgb(0x4a, 0x48, 0x38), 0.8 * alpha), 0);
        }
        PropKind::Ember => {
            let radius = (16.0 + 8.0 * pulse) * s;
            r.rect_world(at, radius * 2.0, radius * 2.0, 0.0,
                         fade(p.colour, 0.22 * a), crate::ffi::GC_FLAG_FLASH);
        }
        PropKind::Shaft => {
            // A shaft of light: a long additive column, breathing slowly.
            let w = 70.0 * s;
            let sway = (time * 0.2 + p.phase).sin() * 24.0;
            r.rect_world(at + Vec2::new(sway, 0.0), w, 520.0 * s, 0.06,
                         fade(p.colour, (0.10 + 0.05 * pulse) * alpha),
                         crate::ffi::GC_FLAG_FLASH);
            r.rect_world(at + Vec2::new(sway, 0.0), w * 0.45, 520.0 * s, 0.06,
                         fade(color::WHITE, 0.07 * alpha), crate::ffi::GC_FLAG_FLASH);
        }
        PropKind::Bokeh => {
            let radius = 90.0 * s;
            soft_circle(r, at, radius, fade(p.colour, 0.13 * alpha));
            soft_circle(r, at, radius * 0.55, fade(p.colour, 0.10 * alpha));
        }
    }
}

/// A ring of segments (the command set has no circles).
fn ring(r: &mut Renderer, centre: Vec2, radius: f32, thickness: f32, colour: u32) {
    const SEGMENTS: i32 = 12;
    for k in 0..SEGMENTS {
        let a0 = k as f32 * TAU / SEGMENTS as f32;
        let a1 = (k + 1) as f32 * TAU / SEGMENTS as f32;
        r.line_world(centre + Vec2::from_angle(a0) * radius,
                     centre + Vec2::from_angle(a1) * radius, thickness, colour);
    }
}

/// A soft disc, drawn as stacked bars so it reads as blurred rather than square.
fn soft_circle(r: &mut Renderer, centre: Vec2, radius: f32, colour: u32) {
    const BANDS: i32 = 7;
    let band_h = (radius * 2.0) / BANDS as f32;
    for k in 0..BANDS {
        let dy = -radius + (k as f32 + 0.5) * band_h;
        let t = (dy / radius).abs().min(1.0);
        let w = 2.0 * radius * (1.0 - t * t).max(0.0).sqrt();
        if w <= 1.0 {
            continue;
        }
        r.rect_world(centre + Vec2::new(0.0, dy), w, band_h + 1.0, 0.0, colour, 0);
    }
}

/// Darkened, accent-tinted screen edges: frames the action without hiding it.
fn vignette(r: &mut Renderer, palette: &Palette) {
    let content = r.view.content_rect();
    let thick = (content.h * 0.16).max(30.0);
    let steps = 4;
    for i in 0..steps {
        let t = i as f32 / steps as f32;
        let alpha = 0.16 * (1.0 - t);
        let inset = t * thick;
        let w = thick / steps as f32 * 1.5;
        let c = fade(palette.deep, alpha);
        r.rect(crate::render::Rect::new(content.x + inset, content.y + inset, content.w - inset * 2.0, w), c, 0);
        r.rect(crate::render::Rect::new(content.x + inset, content.y + content.h - inset - w, content.w - inset * 2.0, w), c, 0);
        r.rect(crate::render::Rect::new(content.x + inset, content.y + inset, w, content.h - inset * 2.0), c, 0);
        r.rect(crate::render::Rect::new(content.x + content.w - inset - w, content.y + inset, w, content.h - inset * 2.0), c, 0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scenery_is_deterministic_for_a_seed() {
        let a = PropSet::generate(7, 2, Vec2::new(2400.0, 1560.0));
        let b = PropSet::generate(7, 2, Vec2::new(2400.0, 1560.0));
        assert_eq!(a.props.len(), b.props.len());
        for (x, y) in a.props.iter().zip(b.props.iter()) {
            assert_eq!(x.kind, y.kind);
            assert!((x.pos.x - y.pos.x).abs() < 1e-3);
            assert!((x.pos.y - y.pos.y).abs() < 1e-3);
        }
    }

    #[test]
    fn different_themes_get_different_scenery() {
        let arena = Vec2::new(2400.0, 1560.0);
        let hell = PropSet::generate(3, 0, arena);
        let godly = PropSet::generate(3, 5, arena);
        assert_ne!(hell.props[0].kind, godly.props[0].kind,
                   "themes must look different");
    }

    #[test]
    fn props_stay_inside_the_arena() {
        let arena = Vec2::new(2400.0, 1560.0);
        for theme in 0..6 {
            let set = PropSet::generate(11, theme, arena);
            assert_eq!(set.props.len(), 34);
            assert_eq!(set.back.len(), 16);
            for p in &set.props {
                assert!(p.pos.x >= 80.0 && p.pos.x <= arena.x - 80.0);
                assert!(p.pos.y >= 80.0 && p.pos.y <= arena.y - 80.0);
                assert!(p.scale > 0.0);
            }
        }
    }

    #[test]
    fn a_theme_change_cross_fades_and_settles() {
        let arena = Vec2::new(2400.0, 1560.0);
        let mut d = Decor::new(5, arena);
        assert_eq!(d.current.theme, 0);
        d.update(0.1, 3);
        assert_eq!(d.current.theme, 3);
        assert!(d.previous.is_some(), "the old set should fade out");
        for _ in 0..40 {
            d.update(0.1, 3);
        }
        assert!(d.previous.is_none(), "the cross-fade must finish");
        assert!((d.fade - 1.0).abs() < 1e-3);
    }
}
