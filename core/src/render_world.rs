//! World-space presentation: arena, entities, projectiles, particles, text.

use crate::entities::*;
use crate::ffi::{GC_FLAG_FLASH, GC_FLAG_NONE, GC_FLAG_SHADOW};
use crate::math::{clamp, PI, Vec2};
use crate::render::{color, fade, Rect, Renderer};
use crate::sprite::{weapon_rotation_for, SpriteId};
use crate::world::*;

/// Rotates the player art so its eyes point along the aim direction.  The eyes
/// sit at the top of the source art, i.e. at -90 degrees.
const PLAYER_ART_FORWARD: f32 = -PI * 0.5;

pub fn draw_world(w: &World, r: &mut Renderer) {
    let palette = w.backdrop.palette();
    draw_arena(r, &palette, w.time);
    // Scenery sits on the floor and behind everything that moves.
    w.decor.draw(r, &palette, w.time);

    // Phantoms: translucent copies of the player, so the upgrade is legible at
    // a glance without new art.
    for (i, ph) in w.phantoms.iter().enumerate() {
        let fade_t = (ph.life / ph.max_life).clamp(0.0, 1.0);
        let born = (1.0 - fade_t).min(1.0);
        let alpha = (0.18 + 0.34 * fade_t) * (1.0 - born * 0.0);
        let bob = (ph.phase * 2.0).sin() * 2.5;
        let p = r.world_to_screen(ph.pos + Vec2::new(0.0, bob));
        let size = (w.player.radius * 3.4) * r.zoom;
        // Ghost: a dark seat so it reads on a bright floor, a cold halo, the
        // sprite itself, then a wisp of trail.
        let halo = ((alpha * 150.0) as u32) << 24 | 0x66DDFF;
        r.rect_screen(p, size * 1.15, size * 1.15, ph.phase * 0.4, 0x22001144, 0);
        r.rect_screen(p, size * 1.7, size * 1.7, ph.phase * 0.4, halo, GC_FLAG_FLASH);
        r.rect_screen(p, size * 1.25, size * 1.25, -ph.phase * 0.5,
                      ((alpha * 190.0) as u32) << 24 | 0x88EEFF, GC_FLAG_FLASH);
        r.sprite_screen(SpriteId::Player, p, size, ph.phase * 0.12,
                        ((alpha * 255.0) as u32) << 24 | 0xDDE8FF, GC_FLAG_NONE);
        for k in 1..3 {
            let back = ph.pos - ph.aim * (k as f32 * 12.0);
            let q = r.world_to_screen(back + Vec2::new(0.0, bob));
            let a = (alpha * (0.30 - k as f32 * 0.09)).max(0.0);
            r.rect_screen(q, size * 0.7, size * 0.7, 0.0,
                          ((a * 255.0) as u32) << 24 | 0xCCBBFF, GC_FLAG_FLASH);
        }
        let _ = i;
    }
    draw_pickups(w, r);
    draw_spawn_telegraphs(w, r);
    draw_enemies(w, r);
    draw_player(w, r);
    draw_projectiles(w, r);
    draw_particles(w, r);
    draw_floaters(w, r);
}

fn draw_pickups(w: &World, r: &mut Renderer) {
    for p in &w.pickups {
        let bob = (p.phase).sin() * 3.0;
        let pos = p.pos + Vec2::new(0.0, bob);
        let sprite = p.kind.sprite();
        // Soft glow underneath so gems read against a dark floor.
        let screen = r.world_to_screen(pos);
        r.rect_screen(screen, sprite.design_width() * r.zoom * 1.6,
                      sprite.design_height() * r.zoom * 1.6, 0.0,
                      fade(p.kind.sprite_color(), 0.16), GC_FLAG_FLASH);
        r.sprite(sprite, pos, sprite.design_height(), 0.0, color::WHITE, GC_FLAG_NONE);
    }
}

fn draw_spawn_telegraphs(w: &World, r: &mut Renderer) {
    let tau = std::f32::consts::TAU;
    for e in &w.enemies {
        if !e.is_materialising() {
            continue;
        }
        let t = 1.0 - (e.spawn_t / SPAWN_TIME).clamp(0.0, 1.0);
        let radius = spawn_ring_radius(e);
        let screen = r.world_to_screen(e.pos);
        let rr = radius * r.zoom;
        let thick = (2.5 * r.zoom).max(1.0);
        let alpha = fade(color::SLIME_HOT, 0.20 + 0.55 * t);
        // An octagon rather than a box: rectangles cannot follow a circle, but
        // eight rotated segments read as a ring at any size.
        for k in 0..8 {
            let a0 = k as f32 * tau / 8.0;
            let a1 = (k + 1) as f32 * tau / 8.0;
            let p0 = screen + Vec2::from_angle(a0) * rr;
            let p1 = screen + Vec2::from_angle(a1) * rr;
            r.line(p0, p1, thick, alpha);
        }
        // A tighter inner ring for the last moments before it lands.
        if t > 0.55 {
            let inner = rr * (0.55 + 0.45 * (1.0 - t));
            for k in 0..8 {
                let a0 = k as f32 * tau / 8.0;
                let a1 = (k + 1) as f32 * tau / 8.0;
                let p0 = screen + Vec2::from_angle(a0) * inner;
                let p1 = screen + Vec2::from_angle(a1) * inner;
                r.line(p0, p1, thick, fade(color::WHITE, 0.35 * t));
            }
        }
    }
}

fn draw_enemies(w: &World, r: &mut Renderer) {
    for e in &w.enemies {
        let sprite = e.kind.sprite();
        let spawn_t = 1.0 - (e.spawn_t / SPAWN_TIME).clamp(0.0, 1.0);
        let base = e.kind.scale();
        let scale = if e.is_materialising() {
            base * (0.25 + 0.75 * spawn_t)
        } else {
            base * (1.0 + 0.06 * (e.bob_phase + w.time * 4.0).sin())
        };
        let height = sprite.design_height() * scale;
        let alpha = if e.is_materialising() { 0.35 + 0.65 * spawn_t } else { 1.0 };

        // Shadow keeps enemies readable against the floor.
        let shadow = r.world_to_screen(e.pos + Vec2::new(0.0, e.radius * 0.55));
        r.rect_screen(shadow, e.radius * 1.5 * r.zoom, e.radius * 0.6 * r.zoom, 0.0,
                      fade(color::BLACK, 0.22), GC_FLAG_NONE);

        r.sprite(sprite, e.pos, height, 0.0, fade(color::WHITE, alpha), GC_FLAG_NONE);
        if e.hurt_flash > 0.0 {
            // Additive white copy = hit flash, no extra pipeline needed.
            r.sprite(sprite, e.pos, height, 0.0,
                     fade(color::WHITE, e.hurt_flash / 0.14), GC_FLAG_FLASH);
        }
        if e.slow_t > 0.0 {
            r.sprite(sprite, e.pos, height, 0.0, fade(color::XP_BLUE, 0.35), GC_FLAG_FLASH);
        }

        // Health bar, only once damaged.
        let frac = (e.hp / e.hp_max).clamp(0.0, 1.0);
        if frac < 0.98 && !e.is_materialising() {
            let bw = e.radius * 1.5;
            let bh = 3.0;
            let bar = Rect::new(e.pos.x - bw * 0.5, e.pos.y - e.radius - 12.0, bw, bh);
            let screen = r.world_to_screen(bar.center());
            let size = Vec2::new(bw * r.zoom, (bh * r.zoom).max(2.0));
            r.rect_screen(screen, size.x, size.y, 0.0, fade(color::BLACK, 0.35), GC_FLAG_NONE);
            let fill_w = size.x * frac;
            r.rect_screen(Vec2::new(screen.x - size.x * 0.5 + fill_w * 0.5, screen.y),
                          fill_w, size.y, 0.0,
                          crate::systems::enemy_hp_color(frac), GC_FLAG_NONE);
        }
    }
}

fn draw_player(w: &World, r: &mut Renderer) {
    let p = &w.player;
    // Flicker while invulnerable after a hit (but not while dashing).
    let flicker = p.invuln > 0.0 && p.dash_t <= 0.0 && ((w.time * 30.0) as i32 % 2 == 0);
    let alpha = if flicker { 0.45 } else { 1.0 };

    let shadow = r.world_to_screen(p.pos + Vec2::new(0.0, p.radius * 0.5));
    r.rect_screen(shadow, p.radius * 1.6 * r.zoom, p.radius * 0.6 * r.zoom, 0.0,
                  fade(color::BLACK, 0.25), GC_FLAG_NONE);

    // Soft additive glow so the player never gets lost in a crowd.
    r.sprite(SpriteId::Player, p.pos, SpriteId::Player.design_height() * 1.45,
             p.aim - PLAYER_ART_FORWARD, fade(color::WHITE, 0.12), GC_FLAG_FLASH);

    // Owned weapons, primary first (gun, then bow, then sword).
    let mut owned = [WeaponKind::Gun; 3];
    let mut owned_count = 0usize;
    for kind in WeaponKind::ALL {
        if p.owns(kind) {
            owned[owned_count] = kind;
            owned_count += 1;
        }
    }

    // Secondary weapons ride on the player's back, drawn *behind* the body so
    // the silhouette stays readable.
    for (i, kind) in owned[..owned_count].iter().enumerate().skip(1) {
        let sprite = kind.sprite();
        let angle = p.aim + PI + (i as f32 - 1.0) * 0.55;
        let reach = p.radius * 1.05;
        let pos = p.pos + Vec2::from_angle(angle) * reach;
        r.sprite(sprite, pos, sprite.design_height() * 0.55,
                 weapon_rotation_for(angle), fade(color::WHITE, 0.85 * alpha), GC_FLAG_NONE);
    }

    // The body.
    r.sprite(SpriteId::Player, p.pos, SpriteId::Player.design_height(),
             p.aim - PLAYER_ART_FORWARD, fade(color::WHITE, alpha), GC_FLAG_NONE);
    if p.hurt_flash > 0.0 {
        r.sprite(SpriteId::Player, p.pos, SpriteId::Player.design_height(),
                 p.aim - PLAYER_ART_FORWARD,
                 fade(color::WARN, p.hurt_flash / 0.3), GC_FLAG_FLASH);
    }

    // The primary weapon is held out in front, or swept through its arc while
    // the sword is swinging.
    if owned_count > 0 {
        let kind = owned[0];
        let weapon = &p.weapons[kind.index()];
        let sprite = kind.sprite();
        let mut angle = p.aim;
        let mut scale = 1.0;
        let mut reach = p.radius * 0.55 + sprite.design_height() * 0.42;
        if kind == WeaponKind::Sword {
            if weapon.swing_t > 0.0 {
                let t = 1.0 - (weapon.swing_t / 0.26).clamp(0.0, 1.0);
                let half = 1.05;
                angle = weapon.swing_dir - half + t * half * 2.0;
                scale = 1.0 + 0.25 * (1.0 - (t * 2.0 - 1.0).abs());
                reach = p.radius * 0.45 + kind.range() * 0.32;
            } else {
                // Shouldered: tilted so it does not cover the player's face.
                angle = p.aim + 0.5;
                reach = p.radius * 0.85;
            }
        }
        let pos = p.pos + Vec2::from_angle(angle) * reach;
        r.sprite(sprite, pos, sprite.design_height() * scale,
                 weapon_rotation_for(angle), fade(color::WHITE, alpha), GC_FLAG_NONE);
    }

    // Orbiting blades.
    let orbitals = p.stats.orbitals;
    if orbitals > 0 {
        let radius = 92.0;
        for k in 0..orbitals {
            let a = w.time * 2.3 + k as f32 * (std::f32::consts::TAU / orbitals as f32);
            let pos = p.pos + Vec2::from_angle(a) * radius;
            r.sprite(SpriteId::Sword, pos, SpriteId::Sword.design_height() * 0.8,
                     weapon_rotation_for(a + std::f32::consts::FRAC_PI_2),
                     fade(color::WHITE, 0.9), GC_FLAG_NONE);
            let glow = r.world_to_screen(pos);
            r.rect_screen(glow, 26.0 * r.zoom, 26.0 * r.zoom, a,
                          fade(color::XP, 0.18), GC_FLAG_FLASH);
        }
    }

    // Muzzle hint: a small additive dot at the barrel tip.
    let tip = p.pos + Vec2::from_angle(p.aim) * (p.radius + 20.0);
    let screen = r.world_to_screen(tip);
    r.rect_screen(screen, 5.0 * r.zoom, 5.0 * r.zoom, p.aim, fade(color::GOLD, 0.30),
                  GC_FLAG_FLASH);
}

fn draw_projectiles(w: &World, r: &mut Renderer) {
    for p in &w.projectiles {
        let (len, thick, col) = match p.kind {
            ProjectileKind::Bolt => (26.0, 7.0, if p.crit { color::GOLD } else { color::XP_BLUE }),
            ProjectileKind::Arrow => (20.0, 5.0, if p.crit { color::GOLD } else { color::WHITE }),
        };
        let screen = r.world_to_screen(p.pos);
        r.rect_screen(screen, len * r.zoom, thick * r.zoom, p.angle, col, GC_FLAG_FLASH);
        // Bright core.
        r.rect_screen(screen, len * 0.55 * r.zoom, thick * 0.45 * r.zoom, p.angle,
                      fade(color::WHITE, 0.85), GC_FLAG_FLASH);
    }
}

fn draw_particles(w: &World, r: &mut Renderer) {
    for p in &w.particles {
        let t = p.t();
        let size = p.size * (0.35 + 0.65 * t);
        let alpha = t * t;
        let screen = r.world_to_screen(p.pos);
        let flags = if p.additive { GC_FLAG_FLASH } else { GC_FLAG_NONE };
        r.rect_screen(screen, size * r.zoom, size * r.zoom, p.rot, fade(p.color, alpha), flags);
    }
}

fn draw_floaters(w: &World, r: &mut Renderer) {
    for f in &w.floaters {
        let t = (f.life / f.life_max).clamp(0.0, 1.0);
        let alpha = clamp(t * 1.6, 0.0, 1.0);
        let screen = r.world_to_screen(f.pos);
        let text = match f.kind {
            FloaterKind::Damage(n) => crate::buf_format!(24, "{}", n),
            FloaterKind::Money(n) => crate::buf_format!(24, "+${}", n),
            FloaterKind::Xp(n) => crate::buf_format!(24, "+{} XP", n),
            FloaterKind::Label(s) => crate::buf_format!(24, "{}", s),
        };
        let size = f.size * (0.85 + 0.35 * (1.0 - t));
        r.text(text.as_str(), screen.x, screen.y, size, 0.5, fade(f.color, alpha),
               GC_FLAG_SHADOW);
    }
}
