//! Per-frame simulation systems.
//!
//! `simulate` advances the gameplay; `update_effects` and `update_camera` also
//! run during intermissions so menus never look frozen.

use crate::entities::*;
use crate::ffi::*;
use crate::math::{angle_delta, clamp, Vec2};
use crate::render::{color, View};
use crate::world::*;

/// Fixed simulation timestep.  `World::step` is always called with this value.
pub const FIXED_DT: f32 = 1.0 / 60.0;

const DASH_SPEED_MULT: f32 = 3.4;
const DASH_TIME: f32 = 0.17;
const ENEMY_SEPARATION: f32 = 26.0;

// ---------------------------------------------------------------------------
// entry points
// ---------------------------------------------------------------------------

pub fn simulate(w: &mut World, view: &View, input: &InputState, dt: f32) {
    update_aim(w, view, input);
    update_player(w, input, dt);
    update_weapons(w, dt);
    maybe_double_shot(w);
    update_phantoms(w, dt);
    update_projectiles(w, dt);
    update_enemy_shots(w, dt);
    update_enemies(w, dt);
    update_dash_damage(w);
    update_orbitals(w);
    update_lightning(w, dt);
    update_auto_collect(w, dt);
    update_spawns(w, view, dt);
    update_pickups(w, dt);
}

/// How much further than their own radius an enemy can strike.
pub const ENEMY_REACH: f32 = 1.10;

/// Charger timing, in seconds.  The coil is the tell: it stops moving, then
/// leaves.  Generous, because being one-shot out of nowhere is not a lesson.
const CHARGER_CYCLE: f32 = 2.6;
const CHARGER_WINDUP: f32 = 1.35;
const CHARGER_COIL: f32 = 0.45;
const CHARGER_DASH: f32 = 0.30;
const CHARGER_DASH_SPEED: f32 = 3.4;
/// Blood clot speed, world units per second.
const BLOOD_SPEED: f32 = 280.0;
/// How close a miser must be to pick a pocket.
const MISER_SIPHON_RANGE: f32 = 115.0;
const MAX_ENEMY_SHOTS: usize = 120;



pub fn update_effects(w: &mut World, dt: f32) {
    for p in w.particles.iter_mut() {
        p.pos += p.vel * dt;
        if p.drag > 0.0 {
            p.vel *= (-p.drag * dt).exp();
        }
        p.rot += p.spin * dt;
        p.life -= dt;
    }
    w.particles.retain(|p| p.life > 0.0);

    for f in w.floaters.iter_mut() {
        f.pos += f.vel * dt;
        f.vel *= (-3.0 * dt).exp();
        f.life -= dt;
    }
    w.floaters.retain(|f| f.life > 0.0);

    let mut clear_banner = false;
    if let Some(b) = &mut w.banner {
        b.t -= dt;
        if b.t <= 0.0 {
            clear_banner = true;
        }
    }
    if clear_banner {
        w.banner = None;
    }

    w.shake *= (-6.0 * dt).exp();
    if w.shake < 0.05 {
        w.shake = 0.0;
    }
}

pub fn update_camera(w: &mut World, view: &View, dt: f32, snap: bool) {
    w.zoom = view.fit_zoom();
    if !w.camera.is_finite() {
        w.camera = w.player.pos;
    }
    let target = camera_target(w.player.pos, view, w.zoom);
    w.camera = if snap { target } else { crate::math::damp_vec(w.camera, target, 10.0, dt) };
}

/// Screen shake offset, derived from the shake magnitude and the clock so it is
/// deterministic (and therefore reproducible in the screenshot tests).
pub fn shake_offset(w: &World) -> Vec2 {
    if w.shake <= 0.0 {
        return Vec2::ZERO;
    }
    let amount = w.shake * w.settings.shake_scale();
    if amount <= 0.0 {
        return Vec2::ZERO;
    }
    let t = w.time * 47.0;
    Vec2::new((t * 1.7).sin() * amount, (t * 2.3).cos() * amount * 0.8)
}

// ---------------------------------------------------------------------------
// aiming
// ---------------------------------------------------------------------------

fn screen_to_world(w: &World, view: &View, p: Vec2) -> Vec2 {
    (p - view.center() - shake_offset(w)) / w.zoom.max(0.01) + w.camera
}

fn update_aim(w: &mut World, view: &View, input: &InputState) {
    // Holding the pointer (mouse button, or the aim stick on touch) overrides
    // auto-aim; otherwise every weapon points at the closest enemy.
    if input.pointer_down && input.pointer_active {
        let world = screen_to_world(w, view, input.aim);
        let d = world - w.player.pos;
        if d.length_sq() > 4.0 {
            let mut aim = d.angle();
            // Aim assist blends a deliberate aim toward the nearest enemy, so a
            // near miss still lands without ever feeling like it aims for you.
            if w.settings.aim_assist {
                if let Some(target) = nearest_enemy(w, w.player.pos, 420.0) {
                    let to = w.enemies[target].pos - w.player.pos;
                    if to.length_sq() > 1.0 {
                        let want = to.angle();
                        let mut delta = want - aim;
                        while delta > core::f32::consts::PI {
                            delta -= core::f32::consts::TAU;
                        }
                        while delta < -core::f32::consts::PI {
                            delta += core::f32::consts::TAU;
                        }
                        aim += delta * 0.35;
                    }
                }
            }
            w.player.aim = aim;
            return;
        }
    }
    if let Some(target) = nearest_enemy(w, w.player.pos, 1_000_000.0) {
        let d = w.enemies[target].pos - w.player.pos;
        if d.length_sq() > 1.0 {
            w.player.aim = d.angle();
            return;
        }
    }
    if input.move_axis.length_sq() > 0.01 {
        w.player.aim = input.move_axis.angle();
    }
}

/// Index of the closest materialised enemy within `range`.
fn nearest_enemy(w: &World, from: Vec2, range: f32) -> Option<usize> {
    let mut best: Option<(usize, f32)> = None;
    let r2 = range * range;
    for (i, e) in w.enemies.iter().enumerate() {
        if e.is_materialising() {
            continue;
        }
        let d2 = e.pos.distance_sq(from);
        if d2 > r2 {
            continue;
        }
        if best.map_or(true, |(_, bd)| d2 < bd) {
            best = Some((i, d2));
        }
    }
    best.map(|(i, _)| i)
}

// ---------------------------------------------------------------------------
// player
// ---------------------------------------------------------------------------

fn update_player(w: &mut World, input: &InputState, dt: f32) {
    {
        let p = &mut w.player;
        p.dash_cd = (p.dash_cd - dt).max(0.0);
        p.invuln = (p.invuln - dt).max(0.0);
        p.hurt_flash = (p.hurt_flash - dt).max(0.0);
        p.trail_t = (p.trail_t - dt).max(0.0);

        // Regeneration, and refilling spent dash charges.
        if p.stats.regen > 0.0 && p.hp < p.hp_max() {
            p.hp = (p.hp + p.stats.regen * dt).min(p.hp_max());
        }
        if p.dash_charges < p.dash_charge_max() {
            p.dash_recharge -= dt;
            if p.dash_recharge <= 0.0 && p.dash_charges < p.dash_charge_max() {
                p.dash_charges += 1;
                p.dash_recharge = if p.dash_charges < p.dash_charge_max() {
                    p.dash_cooldown_max()
                } else {
                    0.0
                };
            }
        }
    }

    let dir = input.move_axis.clamp_length(1.0);
    let want_dash = input.dash || (input.buttons & GC_BTN_DASH) != 0;

    let mut dash_started = false;
    let mut trail_at: Option<Vec2> = None;
    {
        let p = &mut w.player;
        if p.dash_t <= 0.0 && want_dash && p.dash_charges > 0 && dir.length_sq() > 0.04 {
            p.dash_t = DASH_TIME;
            p.dash_charges -= 1;
            if p.dash_recharge <= 0.0 {
                p.dash_recharge = p.dash_cooldown_max();
            }
            p.dash_dir = dir.normalize_or_zero();
            p.invuln = p.invuln.max(DASH_TIME + 0.05);
            dash_started = true;
        }

        if p.dash_t > 0.0 {
            p.dash_t -= dt;
            p.pos += p.dash_dir * (p.speed() * DASH_SPEED_MULT) * dt;
            p.vel = p.dash_dir * p.speed() * DASH_SPEED_MULT;
            if p.trail_t <= 0.0 {
                p.trail_t = 0.02;
                trail_at = Some(p.pos);
            }
        } else {
            p.vel = dir * p.speed();
            p.pos += p.vel * dt;
        }

        let r = p.radius;
        if !p.pos.is_finite() {
            // Last line of defence: a renderer feeding us NaN must not be able
            // to break the world.
            p.pos = Vec2::new(ARENA_W * 0.5, ARENA_H * 0.5);
            p.vel = Vec2::ZERO;
        }
        p.pos.x = clamp(p.pos.x, r + 6.0, ARENA_W - r - 6.0);
        p.pos.y = clamp(p.pos.y, r + 6.0, ARENA_H - r - 6.0);
    }

    if dash_started {
        let pos = w.player.pos;
        w.add_event(GC_EVT_DASH, pos.x, pos.y, 0.0);
        w.burst(pos, 10, color::XP, 130.0, 5.0, 0.3, true);
    }
    if let Some(pos) = trail_at {
        let size = w.player.radius * 1.5;
        w.particles.push(Particle {
            pos,
            vel: Vec2::ZERO,
            life: 0.3,
            life_max: 0.3,
            size,
            color: color::XP,
            rot: 0.0,
            spin: 0.0,
            drag: 0.0,
            additive: true,
        });
    }
}

// ---------------------------------------------------------------------------
// weapons
// ---------------------------------------------------------------------------

fn update_weapons(w: &mut World, dt: f32) {
    let aim = w.player.aim;
    let player_pos = w.player.pos;
    let dmg_mult = w.player.stats.damage_mult;
    let crit_chance = w.player.stats.crit_chance;
    let crit_mult = w.player.stats.crit_mult;
    let extra_pierce = w.player.stats.extra_pierce;
    let extra_arrows = w.player.stats.extra_arrows;
    let rate_mult = w.player.stats.rate_mult;

    for kind in WeaponKind::ALL {
        let idx = kind.index();
        if !w.player.weapons[idx].owned {
            continue;
        }
        w.player.weapons[idx].tick(dt);
        if !w.player.weapons[idx].ready() {
            continue;
        }

        // Auto-acquire, but fall back to firing along the aim direction when
        // nothing is in range (so the player can shoot into a crowd).
        let target_dir = match nearest_enemy(w, player_pos, kind.range()) {
            Some(i) => {
                let d = w.enemies[i].pos - player_pos;
                if d.length_sq() > 1.0 {
                    d.angle()
                } else {
                    aim
                }
            }
            None => {
                if kind == WeaponKind::Sword {
                    continue;
                }
                aim
            }
        };

        let dmg = w.player.weapons[idx].damage(dmg_mult);
        let interval = w.player.weapons[idx].interval(rate_mult);
        w.player.weapons[idx].cooldown = interval;
        w.player.weapons[idx].swing_dir = target_dir;

        let crit = w.rng.chance(crit_chance);
        let damage = if crit { dmg * crit_mult } else { dmg };

        match kind {
            WeaponKind::Gun => {
                spawn_projectile(w, player_pos, target_dir, damage, crit,
                                 ProjectileKind::Bolt, extra_pierce);
            }
            WeaponKind::Bow => {
                let arrows = 3 + extra_arrows;
                let spread = 0.20;
                for a in 0..arrows {
                    let offset = (a as f32 - (arrows - 1) as f32 * 0.5) * spread;
                    spawn_projectile(w, player_pos, target_dir + offset, damage, crit,
                                     ProjectileKind::Arrow, 1 + extra_pierce);
                }
            }
            WeaponKind::Sword => {
                w.player.weapons[idx].swing_t = 0.26;
                melee_arc(w, player_pos, target_dir, kind.range(), damage, crit);
            }
        }
        w.add_event(GC_EVT_SHOOT, player_pos.x, player_pos.y, kind.index() as f32);
    }
}

/// Twin Fire: a chance for any shot to be doubled, at a slight angle.
fn maybe_double_shot(w: &mut World) {
    let chance = w.player.stats.double_shot;
    if chance <= 0.0 || !w.player.weapons[WeaponKind::Gun.index()].owned {
        return;
    }
    if !w.rng.chance(chance) {
        return;
    }
    let from = w.player.pos;
    let aim = w.player.aim;
    let dmg = w.player.weapons[WeaponKind::Gun.index()].damage(w.player.stats.damage_mult)
        * w.player.stats.ranged_mult
        * 0.9;
    spawn_projectile(w, from, aim + 0.07, dmg, false, ProjectileKind::Bolt, 0);
}

/// Phantoms drift around the player, shoot the nearest enemy, then vanish.
fn update_phantoms(w: &mut World, dt: f32) {
    if w.phantoms.is_empty() {
        return;
    }
    let player_pos = w.player.pos;
    let base = w.player.weapons[WeaponKind::Gun.index()].damage(1.0).max(6.0);
    let mut fired: Vec<(Vec2, f32)> = Vec::new();
    let mut died: Vec<Vec2> = Vec::new();
    // Resolve targets before touching the phantom list, so the borrow checker
    // (and the reader) can see that the two are independent.
    let targets: Vec<Option<Vec2>> = w
        .phantoms
        .iter()
        .map(|ph| nearest_enemy(w, ph.pos, 460.0).map(|i| w.enemies[i].pos))
        .collect();

    for (i, ph) in w.phantoms.iter_mut().enumerate() {
        ph.life -= dt;
        ph.phase += dt;
        if ph.life <= 0.0 {
            died.push(ph.pos);
            continue;
        }
        // Hover on a slow orbit around the player, drifting out of the corpse
        // first so the summon reads as a rise rather than a teleport.
        let spread = 54.0 + (i as f32 % 3.0) * 26.0;
        let angle = ph.phase * 0.7 + i as f32 * 2.1;
        let target = player_pos + Vec2::from_angle(angle) * spread;
        ph.pos = ph.pos.lerp(target, (dt * 3.0).min(1.0));
        ph.fire_cd -= dt;
        if let Some(target) = targets.get(i).copied().flatten() {
            let d = target - ph.pos;
            if d.length_sq() > 1.0 {
                ph.aim = Vec2::from_angle(d.angle());
            }
        }
        if ph.fire_cd <= 0.0 {
            ph.fire_cd = 0.55;
            fired.push((ph.pos, ph.aim.angle()));
        }
    }

    for (pos, angle) in fired {
        let dmg = base * w.player.stats.phantom_damage;
        spawn_projectile(w, pos, angle, dmg, false, ProjectileKind::Bolt, 0);
        w.add_event(GC_EVT_SHOOT, pos.x, pos.y, 99.0);
    }
    for pos in died {
        w.burst(pos, 10, 0xCCBBFF, 160.0, 5.0, 0.5, true);
    }
    w.phantoms.retain(|p| p.life > 0.0);
}

fn spawn_projectile(w: &mut World, from: Vec2, angle: f32, damage: f32, crit: bool,
                    kind: ProjectileKind, pierce: i32) {
    if w.projectiles.len() >= MAX_PROJECTILES {
        return;
    }
    let dir = Vec2::from_angle(angle);
    let speed = match kind {
        ProjectileKind::Bolt => WeaponKind::Gun.projectile_speed(),
        ProjectileKind::Arrow => WeaponKind::Bow.projectile_speed(),
    };
    w.projectiles.push(Projectile {
        pos: from + dir * (w.player.radius + 8.0),
        vel: dir * speed,
        damage,
        radius: match kind {
            ProjectileKind::Bolt => 8.0,
            ProjectileKind::Arrow => 7.0,
        },
        life: match kind {
            ProjectileKind::Bolt => 0.95,
            ProjectileKind::Arrow => 0.85,
        },
        pierce,
        kind,
        angle,
        hits: [0; 6],
        hit_count: 0,
        crit,
    });
}

fn melee_arc(w: &mut World, from: Vec2, angle: f32, range: f32, damage: f32, crit: bool) {
    let half_arc = 1.05; // ~120 degree swing
    let mut hits: Vec<(usize, Vec2)> = Vec::new();
    for (i, e) in w.enemies.iter().enumerate() {
        if e.is_materialising() {
            continue;
        }
        let d = e.pos - from;
        let dist = d.length();
        if dist > range + e.radius {
            continue;
        }
        if dist > 1.0 && angle_delta(angle, d.angle()).abs() > half_arc {
            continue;
        }
        hits.push((i, d.normalize_or_zero()));
    }
    // Damage back to front so indices stay valid while enemies are removed.
    hits.sort_by(|a, b| b.0.cmp(&a.0));
    for (i, dir) in hits {
        w.damage_enemy(i, damage, crit, dir * 260.0);
        if let Some(e) = w.enemies.get_mut(i) {
            e.slow_t = 0.7;
        }
    }
    // Sweep visual: an arc of additive sparks in the swing direction.
    for k in 0..10 {
        let a = angle - half_arc + (k as f32 / 9.0) * half_arc * 2.0;
        let p = from + Vec2::from_angle(a) * range * 0.8;
        w.particles.push(Particle {
            pos: p,
            vel: Vec2::from_angle(a) * 40.0,
            life: 0.16,
            life_max: 0.16,
            size: 9.0,
            color: color::WHITE,
            rot: a,
            spin: 0.0,
            drag: 2.0,
            additive: true,
        });
    }
}

// ---------------------------------------------------------------------------
// projectiles
// ---------------------------------------------------------------------------

fn update_projectiles(w: &mut World, dt: f32) {
    let mut remove: Vec<usize> = Vec::new();
    for pi in 0..w.projectiles.len() {
        {
            let p = &mut w.projectiles[pi];
            p.pos += p.vel * dt;
            p.life -= dt;
        }
        if w.projectiles[pi].life <= 0.0
            || w.projectiles[pi].pos.x < -50.0
            || w.projectiles[pi].pos.y < -50.0
            || w.projectiles[pi].pos.x > ARENA_W + 50.0
            || w.projectiles[pi].pos.y > ARENA_H + 50.0
        {
            remove.push(pi);
            continue;
        }

        let (ppos, pradius, pdmg, pcirt) = {
            let p = &w.projectiles[pi];
            (p.pos, p.radius, p.damage, p.crit)
        };

        let mut hit_index: Option<usize> = None;
        for (ei, e) in w.enemies.iter().enumerate() {
            if e.is_materialising() || w.projectiles[pi].already_hit(e.id) {
                continue;
            }
            let rr = pradius + e.radius;
            if e.pos.distance_sq(ppos) <= rr * rr {
                hit_index = Some(ei);
                break;
            }
        }

        if let Some(ei) = hit_index {
            let id = w.enemies[ei].id;
            let dir = (w.enemies[ei].pos - ppos).normalize_or_zero();
            w.projectiles[pi].register_hit(id);
            let knock = dir * if pdmg > 18.0 { 190.0 } else { 90.0 };
            w.damage_enemy(ei, pdmg, pcirt, knock);

            // Frag rounds: splash everything around the impact.
            let blast = w.player.stats.explosive;
            if blast > 0.0 {
                let radius = 74.0;
                let mut splash: Vec<usize> = Vec::new();
                for (j, other) in w.enemies.iter().enumerate() {
                    if j == ei || other.is_materialising() {
                        continue;
                    }
                    if other.pos.distance_sq(ppos) <= (radius + other.radius).powi(2) {
                        splash.push(j);
                    }
                }
                splash.sort_unstable();
                for &j in splash.iter().rev() {
                    w.damage_enemy(j, pdmg * blast, false, Vec2::ZERO);
                }
                w.burst(ppos, 10, color::GOLD, 210.0, 6.0, 0.35, true);
                for k in 0..10 {
                    let a = k as f32 * (std::f32::consts::TAU / 10.0);
                    w.particles.push(Particle {
                        pos: ppos + Vec2::from_angle(a) * radius * 0.6,
                        vel: Vec2::from_angle(a) * 90.0,
                        life: 0.22,
                        life_max: 0.22,
                        size: 7.0,
                        color: color::GOLD,
                        rot: a,
                        spin: 0.0,
                        drag: 2.0,
                        additive: true,
                    });
                }
            }
            let left = w.projectiles[pi].pierce - 1;
            w.projectiles[pi].pierce = left;
            if left < 0 {
                remove.push(pi);
            }
        }
    }
    remove.sort_unstable();
    remove.dedup();
    for i in remove.into_iter().rev() {
        if i < w.projectiles.len() {
            w.projectiles.remove(i);
        }
    }
}

// ---------------------------------------------------------------------------
// enemies
// ---------------------------------------------------------------------------

fn update_enemies(w: &mut World, dt: f32) {
    let player_pos = w.player.pos;
    let player_radius = w.player.radius;
    let count = w.enemies.len();

    // Separation keeps a swarm from collapsing into a single point.  O(n^2) is
    // fine at our entity cap and keeps the code allocation free.
    for i in 0..count {
        let pi = w.enemies[i].pos;
        let pri = w.enemies[i].radius;
        let mut push = Vec2::ZERO;
        for j in 0..count {
            if i == j {
                continue;
            }
            let d = pi - w.enemies[j].pos;
            let min = pri + w.enemies[j].radius;
            let d2 = d.length_sq();
            if d2 > 1e-4 && d2 < min * min {
                let dist = d2.sqrt();
                push += d * ((min - dist) / min) * ENEMY_SEPARATION;
            }
        }
        w.enemies[i].knock += push * dt * 8.0;
    }

    let mut contact_damage = 0.0;
    let mut retaliate: Vec<usize> = Vec::new();
    // Collected during the loop (the enemy list is borrowed) and applied after.
    let mut throws: Vec<(Vec2, Vec2, f32)> = Vec::new();
    let mut pocket: Vec<usize> = Vec::new();
    let mut leaked: Vec<(Vec2, i32)> = Vec::new();
    for (idx, e) in w.enemies.iter_mut().enumerate() {
        if e.spawn_t > 0.0 {
            e.spawn_t -= dt;
            continue;
        }
        e.hurt_flash = (e.hurt_flash - dt).max(0.0);
        e.slow_t = (e.slow_t - dt).max(0.0);
        e.attack_cd = (e.attack_cd - dt).max(0.0);
        e.dash_cd = (e.dash_cd - dt).max(0.0);

        let to_player = player_pos - e.pos;
        let dist = to_player.length();
        let dir = if dist > 1e-3 { to_player / dist } else { Vec2::ZERO };
        // Slight wobble so the swarm does not move as one rigid block.
        let wobble = Vec2::new((e.bob_phase + e.pos.x * 0.01).sin(),
                               (e.bob_phase + e.pos.y * 0.01).cos()) * 12.0;

        // Per-kind behaviour: how fast it wants to move, and whether it steers
        // at all, come out of here.
        let mut speed_mul = 1.0;
        let mut steers = true;
        let mut away = false;
        if e.kind.is_charger() {
            // A two-and-a-half second cycle: stalk, coil, strike, recover.
            e.state_t = (e.state_t + dt) % CHARGER_CYCLE;
            if e.state_t < CHARGER_WINDUP {
                // Stalking: close the distance, but stop short so the dash has
                // room to travel.
                if dist < 120.0 {
                    speed_mul = 0.0;
                }
            } else if e.state_t < CHARGER_WINDUP + CHARGER_COIL {
                // Coiling: nearly stopped, and this is where it locks on.
                speed_mul = 0.12;
                e.vel = dir * e.kind.speed() * CHARGER_DASH_SPEED;
            } else if e.state_t < CHARGER_WINDUP + CHARGER_COIL + CHARGER_DASH {
                // Dashing: a straight line at anything in the way.
                steers = false;
            } else {
                // Blown out, catching its breath.
                speed_mul = 0.30;
            }
        } else if e.kind.is_spitter() {
            // Hold the standoff ring: back off when crowded, close when far.
            let standoff = e.kind.standoff();
            if dist < standoff - 55.0 {
                away = true;
            } else if dist > standoff + 55.0 {
                speed_mul = 1.0;
            } else {
                speed_mul = 0.25;
            }
            e.shoot_cd -= dt;
            if e.shoot_cd <= 0.0 && dist < 620.0 && dist > 60.0 {
                e.shoot_cd = e.kind.throw_interval();
                let aim = if dir.length_sq() > 0.5 { dir } else { Vec2::new(1.0, 0.0) };
                throws.push((
                    e.pos + aim * (e.radius + 6.0),
                    aim * BLOOD_SPEED,
                    e.kind.blood_damage(),
                ));
            }
        } else if e.kind.is_miser() {
            // Runs at you, picks your pocket, then legs it with the loot.
            if e.stolen >= e.kind.flee_threshold() {
                away = true;
                e.leak_cd -= dt;
                if e.leak_cd <= 0.0 && e.stolen > 0 {
                    e.leak_cd = 1.1;
                    leaked.push((e.pos, 1));
                    e.stolen -= 1;
                }
            } else if dist < MISER_SIPHON_RANGE {
                speed_mul = 0.15;
                e.siphon += e.kind.siphon_rate() * dt;
            }
        }

        let steering = if away { -dir } else { dir };
        let desired = steering * e.speed_now() * speed_mul + wobble;
        if steers {
            e.vel = crate::math::damp_vec(e.vel, desired, 6.0, dt);
        }
        e.pos += (e.vel + e.knock) * dt;
        e.knock *= (-6.0 * dt).exp();
        e.pos.x = clamp(e.pos.x, e.radius, ARENA_W - e.radius);
        e.pos.y = clamp(e.pos.y, e.radius, ARENA_H - e.radius);

        // Contact damage, rate limited per enemy so a swarm cannot melt the
        // player in a single frame.
        // Enemies reach 10% further than they look like they should: their
        // hurtbox already includes the horns, so the attack lands a touch out.
        let reach = (player_radius + e.radius * 0.85) * ENEMY_REACH;
        if dist < reach && e.attack_cd <= 0.0 {
            e.attack_cd = 0.55;
            // A dashing charger is a different, much worse thing to be hit by.
            let dashing = e.kind.is_charger()
                && e.state_t >= CHARGER_WINDUP + CHARGER_COIL
                && e.state_t < CHARGER_WINDUP + CHARGER_COIL + CHARGER_DASH;
            contact_damage += if dashing { e.kind.dash_damage() } else { e.kind.damage() };
            retaliate.push(idx);
            if e.kind.is_miser() && e.stolen < e.kind.purse() {
                pocket.push(idx);
            }
        }
    }
    if contact_damage > 0.0 {
        w.hurt_player(contact_damage);
    }
    // Blood in the air.
    for (pos, vel, damage) in throws {
        if w.shots.len() < MAX_ENEMY_SHOTS {
            w.shots.push(crate::entities::EnemyShot {
                pos,
                vel,
                damage,
                radius: 9.0,
                life: 2.6,
                spin: w.rng.range(0.0, 6.28),
            });
            w.add_event(GC_EVT_ENEMY_SHOT, pos.x, pos.y, damage);
        }
    }
    // Whole coins lifted off the purse this frame.
    if !pocket.is_empty() {
        for idx in pocket {
            if w.player.money > 0 {
                if let Some(e) = w.enemies.get_mut(idx) {
                    if e.stolen < e.kind.purse() {
                        e.stolen += 1;
                    }
                }
                w.player.money -= 1;
                w.add_event(GC_EVT_MONEY_STOLEN, 0.0, 0.0, 1.0);
            }
        }
    }
    // Fractions accumulate in the enemy; convert to whole coins with what is
    // actually in the purse, so a miser can never take money you do not have.
    let mut total_siphon = 0.0f32;
    for e in w.enemies.iter_mut() {
        if e.kind.is_miser() && e.siphon >= 1.0 && e.stolen < e.kind.purse() {
            let whole = e.siphon.floor();
            let take = whole.min((w.player.money as f32).max(0.0));
            if take > 0.0 {
                e.siphon -= take;
                e.stolen += take as i32;
                total_siphon += take;
            } else {
                e.siphon = 0.0;
            }
        }
    }
    if total_siphon > 0.0 {
        w.player.money -= total_siphon as i32;
        w.add_event(GC_EVT_MONEY_STOLEN, w.player.pos.x, w.player.pos.y, total_siphon);
    }
    // A fleeing miser sheds coins behind itself.
    for (pos, value) in leaked {
        w.drop_pickup(pos, PickupKind::Money, value);
    }
    // Spite: anything that touched the player burns for it.
    let thorns = w.player.stats.thorns;
    if thorns > 0.0 && !retaliate.is_empty() {
        for &i in retaliate.iter().rev() {
            if i < w.enemies.len() {
                let dir = (w.enemies[i].pos - player_pos).normalize_or_zero();
                w.damage_enemy(i, thorns, false, dir * 140.0);
            }
        }
    }
}

/// Blood clots: fly, hit the player, or burst on the floor.
fn update_enemy_shots(w: &mut World, dt: f32) {
    if w.shots.is_empty() {
        return;
    }
    let player_pos = w.player.pos;
    let player_radius = w.player.radius;
    let mut hits = 0.0f32;
    let mut bursts: Vec<(Vec2, bool)> = Vec::new();
    let mut i = 0;
    while i < w.shots.len() {
        let shot = &mut w.shots[i];
        shot.life -= dt;
        shot.pos += shot.vel * dt;
        shot.spin += dt * 6.0;
        let hit_player = shot.pos.distance_sq(player_pos)
            <= (player_radius * 0.85 + shot.radius).powi(2);
        if hit_player {
            hits += shot.damage;
            let pos = shot.pos;
            w.shots.swap_remove(i);
            bursts.push((pos, true));
            continue;
        }
        if shot.life <= 0.0 {
            let pos = shot.pos;
            w.shots.swap_remove(i);
            bursts.push((pos, false));
            continue;
        }
        i += 1;
    }
    if hits > 0.0 {
        w.hurt_player(hits);
    }
    for (pos, on_player) in bursts {
        if on_player {
            w.burst(pos, 8, color::HP, 150.0, 4.0, 0.35, false);
        } else {
            // A stain, not a spark: blood settles.
            w.burst(pos, 5, color::rgb(0x6e, 0x10, 0x1c), 60.0, 5.0, 0.7, false);
        }
    }
}

/// Blades that orbit the player and chew through anything they touch.
fn update_orbitals(w: &mut World) {
    let count = w.player.stats.orbitals;
    if count <= 0 {
        return;
    }
    let center = w.player.pos;
    let radius = 92.0;
    let blade_reach = 26.0;
    let damage = 18.0 + 6.0 * count as f32;
    let mut hits: Vec<(usize, Vec2)> = Vec::new();

    for blade in 0..count {
        let a = w.time * 2.3 + blade as f32 * (std::f32::consts::TAU / count as f32);
        let pos = center + Vec2::from_angle(a) * radius;
        for (i, e) in w.enemies.iter().enumerate() {
            if e.is_materialising() || e.dash_cd > 0.0 {
                continue;
            }
            let rr = blade_reach + e.radius;
            if e.pos.distance_sq(pos) <= rr * rr {
                hits.push((i, (e.pos - center).normalize_or_zero()));
            }
        }
    }
    hits.sort_by(|a, b| b.0.cmp(&a.0));
    hits.dedup_by_key(|(i, _)| *i);
    for (i, dir) in hits {
        w.damage_enemy(i, damage, false, dir * 120.0);
        if let Some(e) = w.enemies.get_mut(i) {
            e.dash_cd = 0.35;
        }
    }
}

// ---------------------------------------------------------------------------
// incremental mechanics
// ---------------------------------------------------------------------------

/// Dashing through enemies burns them (the "blazing dash" upgrade).
fn update_dash_damage(w: &mut World) {
    let damage = w.player.stats.dash_damage;
    if damage <= 0.0 || w.player.dash_t <= 0.0 {
        return;
    }
    let pos = w.player.pos;
    let reach = w.player.radius + 16.0;
    let mut hits: Vec<(usize, Vec2)> = Vec::new();
    for (i, e) in w.enemies.iter().enumerate() {
        if e.is_materialising() || e.dash_cd > 0.0 {
            continue;
        }
        if e.pos.distance_sq(pos) <= (reach + e.radius) * (reach + e.radius) {
            hits.push((i, (e.pos - pos).normalize_or_zero()));
        }
    }
    hits.sort_by(|a, b| b.0.cmp(&a.0));
    for (i, dir) in hits {
        w.damage_enemy(i, damage, false, dir * 300.0);
        if let Some(e) = w.enemies.get_mut(i) {
            e.dash_cd = 0.4;
        }
    }
}

/// Lightning strikes a random enemy, splashing everything around it.
fn update_lightning(w: &mut World, dt: f32) {
    let interval = w.player.stats.lightning_interval();
    if !interval.is_finite() {
        w.lightning_cd = 0.0;
        return;
    }
    w.lightning_cd -= dt;
    if w.lightning_cd > 0.0 {
        return;
    }
    w.lightning_cd = interval;

    // Reservoir sample one visible enemy without allocating.
    let mut target: Option<usize> = None;
    let mut seen = 0u32;
    for (i, e) in w.enemies.iter().enumerate() {
        if e.is_materialising() {
            continue;
        }
        seen += 1;
        if w.rng.next_u32() % seen == 0 {
            target = Some(i);
        }
    }
    let Some(target) = target else { return };

    let center = w.enemies[target].pos;
    let damage = w.player.stats.lightning_damage();
    let radius = 95.0;

    // Splash, applied back to front so removal is safe.
    let mut hits: Vec<usize> = Vec::new();
    for (i, e) in w.enemies.iter().enumerate() {
        if e.is_materialising() {
            continue;
        }
        if e.pos.distance_sq(center) <= (radius + e.radius) * (radius + e.radius) {
            hits.push(i);
        }
    }
    hits.sort_unstable();
    for &i in hits.iter().rev() {
        w.damage_enemy(i, damage, true, Vec2::ZERO);
    }

    w.add_event(GC_EVT_LIGHTNING, center.x, center.y, damage);
    w.shake = (w.shake + 10.0).min(20.0);

    // A jagged bolt from above, then a bright impact flash.
    let mut x = center.x;
    let mut y = center.y;
    let mut offset = 0.0;
    while offset < 620.0 {
        offset += w.rng.range(26.0, 46.0);
        let next_x = center.x + w.rng.range(-22.0, 22.0);
        let next_y = center.y - offset;
        let steps = 3;
        for s in 0..steps {
            let t = s as f32 / steps as f32;
            let px = x + (next_x - x) * t;
            let py = y + (next_y - y) * t;
            w.particles.push(Particle {
                pos: Vec2::new(px, py),
                vel: Vec2::ZERO,
                life: 0.22,
                life_max: 0.22,
                size: 7.0,
                color: color::XP,
                rot: 0.0,
                spin: 0.0,
                drag: 0.0,
                additive: true,
            });
        }
        x = next_x;
        y = next_y;
    }
    w.burst(center, 22, color::XP, 260.0, 7.0, 0.5, true);
    w.burst(center, 10, color::WHITE, 150.0, 5.0, 0.35, true);
    w.particles.push(Particle {
        pos: center,
        vel: Vec2::ZERO,
        life: 0.25,
        life_max: 0.25,
        size: radius * 1.4,
        color: color::XP,
        rot: 0.0,
        spin: 0.0,
        drag: 0.0,
        additive: true,
    });
}

/// Passively gathers a share of the money lying on the floor.
fn update_auto_collect(w: &mut World, dt: f32) {
    let rate = w.player.stats.auto_collect;
    if rate <= 0.0 {
        return;
    }
    let mut on_ground = 0i32;
    for p in &w.pickups {
        if p.kind == PickupKind::Money {
            on_ground += p.value;
        }
    }
    if on_ground <= 0 {
        w.auto_pool = 0.0;
        return;
    }
    w.auto_pool += on_ground as f32 * rate * dt;

    // Bounded so a huge pile can never stall a frame.
    let mut taken = 0;
    while w.auto_pool >= 1.0 && taken < 40 {
        w.auto_pool -= 1.0;
        taken += 1;
        // Reaching for the *farthest* pile keeps the nearby ones worth walking to.
        let mut best: Option<(usize, f32)> = None;
        for (i, p) in w.pickups.iter().enumerate() {
            if p.kind != PickupKind::Money || p.value <= 0 {
                continue;
            }
            let d = p.pos.distance_sq(w.player.pos);
            if best.map_or(true, |(_, bd)| d > bd) {
                best = Some((i, d));
            }
        }
        let Some((i, _)) = best else { break };
        let pos = w.pickups[i].pos;
        w.pickups[i].value -= 1;
        if w.pickups[i].value <= 0 {
            w.pickups.remove(i);
        }
        w.earn_money(1);
        w.add_event(GC_EVT_PICKUP_MONEY, pos.x, pos.y, 1.0);
        w.particles.push(Particle {
            pos,
            vel: Vec2::new(0.0, -40.0),
            life: 0.4,
            life_max: 0.4,
            size: 5.0,
            color: color::MONEY_GREEN,
            rot: 0.0,
            spin: 0.0,
            drag: 1.0,
            additive: true,
        });
    }
}

// ---------------------------------------------------------------------------
// spawning
// ---------------------------------------------------------------------------

fn update_spawns(w: &mut World, view: &View, dt: f32) {
    if w.spawn_left > 0 {
        w.spawn_timer -= dt;
        if w.spawn_timer <= 0.0 {
            let batch = 1 + (w.wave / 3).min(4);
            for _ in 0..batch {
                if w.spawn_left <= 0 || w.enemies.len() >= MAX_ENEMIES {
                    break;
                }
                let kind = choose_kind(w);
                spawn_enemy(w, view, kind);
                w.spawn_left -= 1;
            }
            w.spawn_timer = (0.78 - 0.038 * w.wave as f32).max(0.16);
        }
        return;
    }

    if w.enemies.is_empty() {
        if w.wave_break_t <= 0.0 {
            w.wave_break_t = 0.7;
        } else {
            w.wave_break_t -= dt;
            if w.wave_break_t <= 0.0 {
                w.on_wave_cleared();
            }
        }
    }
}

fn choose_kind(w: &mut World) -> EnemyKind {
    // Colossi first: they are rare and should not be crowded out by the chaff.
    if w.colossi_left > 0 {
        let share = w.colossi_left as f32 / (w.spawn_left.max(1)) as f32;
        if w.rng.chance(share.max(0.05)) {
            w.colossi_left -= 1;
            return EnemyKind::Colossus;
        }
    }
    if w.brutes_left > 0 {
        // Brutes are spread through the wave rather than front-loaded.
        let share = w.brutes_left as f32 / (w.spawn_left.max(1)) as f32;
        if w.rng.chance(share.max(0.08)) {
            w.brutes_left -= 1;
            return EnemyKind::Brute;
        }
    }
    // The specialists, gated by wave so each one arrives with its own lesson.
    if w.wave >= 2 && w.rng.chance(0.20) {
        return EnemyKind::Charger;
    }
    if w.wave >= 4 && w.rng.chance(0.16) {
        return EnemyKind::Spitter;
    }
    if w.wave >= 6 && w.rng.chance(0.12) {
        return EnemyKind::Miser;
    }
    EnemyKind::Grunt
}

fn spawn_enemy(w: &mut World, view: &View, kind: EnemyKind) {
    let angle = w.rng.angle();
    let half = Vec2::new(view.virt_w * 0.5 / w.zoom.max(0.01),
                         view.virt_h * 0.5 / w.zoom.max(0.01));
    let distance = half.length() + 70.0;
    let mut pos = w.player.pos + Vec2::from_angle(angle) * distance;
    // Keep spawns inside the arena.
    pos.x = clamp(pos.x, 24.0, ARENA_W - 24.0);
    pos.y = clamp(pos.y, 24.0, ARENA_H - 24.0);

    let hp = kind.hp_at(w.wave);
    w.next_id += 1;
    w.enemies.push(Enemy {
        id: w.next_id,
        kind,
        pos,
        vel: Vec2::ZERO,
        hp,
        hp_max: hp,
        radius: kind.radius(),
        spawn_t: SPAWN_TIME,
        hurt_flash: 0.0,
        knock: Vec2::ZERO,
        slow_t: 0.0,
        bob_phase: w.rng.angle(),
        attack_cd: 0.0,
        dash_cd: 0.0,
        // Stagger the chargers so a wave does not wind up in unison.
        state_t: if kind.is_charger() { w.rng.range(0.0, 2.4) } else { 0.0 },
        shoot_cd: if kind.is_spitter() { w.rng.range(0.4, 2.1) } else { 0.0 },
        siphon: 0.0,
        stolen: 0,
        leak_cd: 0.0,
    });
}

// ---------------------------------------------------------------------------
// pickups
// ---------------------------------------------------------------------------

fn update_pickups(w: &mut World, dt: f32) {
    let player_pos = w.player.pos;
    let player_radius = w.player.radius;
    let magnet = w.player.stats.magnet;

    for p in w.pickups.iter_mut() {
        p.phase += dt * 3.0;
        let to_player = player_pos - p.pos;
        let dist = to_player.length();

        if dist < magnet {
            // Accelerating attraction: snappier the closer it gets.
            let pull = 620.0 * (1.0 - dist / magnet).max(0.15);
            p.vel += to_player.normalize_or_zero() * pull * dt;
            p.attracted = true;
        }
        p.vel *= (-2.2 * dt).exp();
        p.pos += p.vel * dt;
        p.pos.x = clamp(p.pos.x, 8.0, ARENA_W - 8.0);
        p.pos.y = clamp(p.pos.y, 8.0, ARENA_H - 8.0);
    }

    let reach = player_radius + 16.0;
    let mut collected: Vec<usize> = Vec::new();
    for (i, p) in w.pickups.iter().enumerate() {
        if p.pos.distance_sq(player_pos) < reach * reach {
            collected.push(i);
        }
    }
    for &i in collected.iter().rev() {
        let pickup = w.pickups.remove(i);
        w.collect(pickup);
    }
}

// ---------------------------------------------------------------------------
// helpers shared with the HUD
// ---------------------------------------------------------------------------

/// Health bar colour for an enemy, from full to nearly dead.
pub fn enemy_hp_color(frac: f32) -> u32 {
    if frac > 0.6 {
        color::SLIME
    } else if frac > 0.3 {
        color::SLIME_HOT
    } else {
        color::WARN
    }
}

/// Strength of the low-health red vignette.
pub fn danger_fade(hp_frac: f32) -> f32 {
    clamp((0.35 - hp_frac) / 0.35, 0.0, 1.0) * 0.5
}

// ---------------------------------------------------------------------------
// the specialist enemies
// ---------------------------------------------------------------------------

#[cfg(test)]
mod specialist_tests {
    use super::*;
    use crate::entities::{EnemyKind, PickupKind};
    use crate::render::View;
    use crate::world::World;

    fn a_view() -> View {
        View::new(1280, 720, [0.0; 4])
    }

    fn world_at(wave: i32) -> World {
        let mut w = World::new(7, 0);
        w.start_run();
        w.wave = wave;
        w
    }

    #[test]
    fn specialists_arrive_on_their_own_waves() {
        // Wave 1 is grunts only: nothing new can appear yet.
        let mut w = world_at(1);
        for _ in 0..500 {
            assert_eq!(choose_kind(&mut w), EnemyKind::Grunt,
                       "a specialist spawned on wave 1");
        }
        // By the mid game all three are in rotation.
        let mut w = world_at(12);
        let (mut charger, mut spitter, mut miser) = (false, false, false);
        for _ in 0..800 {
            match choose_kind(&mut w) {
                EnemyKind::Charger => charger = true,
                EnemyKind::Spitter => spitter = true,
                EnemyKind::Miser => miser = true,
                _ => {}
            }
        }
        assert!(charger, "no chargers by wave 12");
        assert!(spitter, "no spitters by wave 12");
        assert!(miser, "no misers by wave 12");
    }

    #[test]
    fn a_spitter_throws_blood_that_hurts() {
        let view = a_view();
        let mut w = world_at(10);
        w.enemies.clear();
        spawn_enemy(&mut w, &view, EnemyKind::Spitter);
        w.enemies[0].pos = w.player.pos + Vec2::new(200.0, 0.0);
        w.enemies[0].spawn_t = 0.0;
        w.enemies[0].shoot_cd = 0.01;

        for _ in 0..30 {
            update_enemies(&mut w, 1.0 / 60.0);
        }
        assert!(!w.shots.is_empty(), "the spitter never threw anything");

        // Park a clot on the player: it must take damage and consume the clot.
        let hp_before = w.player.hp;
        w.player.invuln = 0.0;
        w.shots[0].pos = w.player.pos;
        update_enemy_shots(&mut w, 1.0 / 60.0);
        assert!(w.player.hp < hp_before, "blood did not hurt the player");
        assert!(w.shots.is_empty(), "the clot should be consumed on impact");
    }

    #[test]
    fn a_miser_steals_money_and_gives_it_back_when_killed() {
        let view = a_view();
        let mut w = world_at(10);
        w.enemies.clear();
        w.player.money = 500;
        spawn_enemy(&mut w, &view, EnemyKind::Miser);
        w.enemies[0].spawn_t = 0.0;

        // Stay in reach: it should siphon.
        for _ in 0..300 {
            w.enemies[0].pos = w.player.pos + Vec2::new(40.0, 0.0);
            update_enemies(&mut w, 1.0 / 60.0);
        }
        let stolen = w.enemies[0].stolen;
        assert!(stolen > 0, "the miser stole nothing in five seconds");
        assert!(w.player.money < 500, "the purse was never touched");
        // A fleeing miser sheds coins behind itself, so the purse only has to be
        // at least what it is still carrying -- never less than it started with.
        assert!(w.player.money + stolen <= 500,
                "the miser took more than the purse held ({} held, {} stolen)",
                w.player.money, stolen);

        // Killing it hands the coins back as pickups.
        w.pickups.clear();
        w.kill_enemy(0);
        let dropped: i32 = w.pickups.iter()
            .filter(|p| p.kind == PickupKind::Money)
            .map(|p| p.value)
            .sum();
        // It pays back everything it lifted, plus whatever ordinary loot its
        // kind would have dropped anyway.
        assert!(dropped >= stolen,
                "the miser kept {} of the {} it took", stolen, dropped.max(0));
        assert!(dropped < stolen + 40, "the payout looks wrong: {}", dropped);
    }

    #[test]
    fn a_charger_dash_is_worse_than_its_touch() {
        let view = a_view();
        let mut w = world_at(10);
        w.enemies.clear();
        spawn_enemy(&mut w, &view, EnemyKind::Charger);
        let e = &w.enemies[0];
        assert!(e.kind.dash_damage() > e.kind.damage(),
                "the dash should be the dangerous part");
        assert!(e.kind.is_charger() && e.state_t < CHARGER_CYCLE);
    }
}
