//! Entity definitions and the balance tables.
//!
//! Everything here is plain data owned by `World`; systems live in
//! `systems.rs` and rendering lives in `render_world.rs` / `ui.rs`.

// Some of this module is internal API used by tests or by other
// platforms' renderers, so unused-in-this-build items are expected.
#![allow(dead_code)]

use crate::math::Vec2;
use crate::sprite::SpriteId;

// ---------------------------------------------------------------------------
// enemies
// ---------------------------------------------------------------------------

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum EnemyKind {
    /// Fast, fragile, wave 1 onwards.  The baseline.
    Grunt,
    /// Slow, tanky, heavy hitter, from wave 3.
    Brute,
    /// A giant: much more health and damage, but it pays out massively.
    Colossus,
    /// Winds up in place, then crosses the arena in a straight line.
    Charger,
    /// Keeps its distance and lobs blood.
    Spitter,
    /// Fast, cowardly pickpocket: eats your money and runs.
    Miser,
    /// Circles you instead of closing, so it is never where you are aiming.
    Wisp,
    /// Bursts into grunts when killed.
    Blob,
    /// Heavily armoured and very slow.
    Bulwark,
    /// Mends every enemy around it.
    Mender,
    /// Explodes when killed.
    Boomslime,
    /// Blinks toward you rather than walking.
    Shade,
    /// Long-range sniper that refuses to be closed on.
    Lancer,
    /// Grows stronger the longer it lives.
    Devourer,
    /// Heals itself by hurting you.
    Leech,
    /// Leaves caltrops on the floor.
    Spiker,
}

/// Every kind, in the order `GC_DBG_SPAWN_ENEMY` indexes them and `DEFS`
/// describes them.
pub const ALL_KINDS: [EnemyKind; 16] = [
    EnemyKind::Grunt, EnemyKind::Brute, EnemyKind::Colossus,
    EnemyKind::Charger, EnemyKind::Spitter, EnemyKind::Miser,
    EnemyKind::Wisp, EnemyKind::Blob, EnemyKind::Bulwark,
    EnemyKind::Mender, EnemyKind::Boomslime, EnemyKind::Shade,
    EnemyKind::Lancer, EnemyKind::Devourer, EnemyKind::Leech,
    EnemyKind::Spiker,
];

/// True when a kind throws something, so spawn sites can stagger its first
/// throw rather than having a whole wave fire in unison.
pub fn is_thrower(kind: EnemyKind) -> bool {
    use crate::enemy_def::Behaviour as B;
    matches!(kind.behaviour(), B::Shooter | B::Trapper)
}

pub fn kind_from_index(i: i32) -> Option<EnemyKind> {
    ALL_KINDS.get(i.max(0) as usize).copied()
}

/// Everything about a kind lives in the catalogue; these are just typed doors
/// onto it, so adding a kind never means editing eleven matches.
impl EnemyKind {
    pub fn def(self) -> &'static crate::enemy_def::KindDef {
        &crate::enemy_def::DEFS[self as usize]
    }


    pub fn sprite(self) -> SpriteId {
        self.def().sprite
    }

    pub fn scale(self) -> f32 {
        self.def().scale
    }

    pub fn is_brute(self) -> bool {
        self.def().heavy
    }

    pub fn is_colossus(self) -> bool {
        self.def().colossal
    }

    pub fn behaviour(self) -> crate::enemy_def::Behaviour {
        self.def().behaviour
    }

    pub fn is_charger(self) -> bool {
        matches!(self.behaviour(), crate::enemy_def::Behaviour::Charger)
    }

    pub fn is_miser(self) -> bool {
        matches!(self.behaviour(), crate::enemy_def::Behaviour::Miser)
    }

    pub fn name(self) -> &'static str {
        self.def().name
    }

    pub fn base_hp(self) -> f32 {
        self.def().hp
    }

    /// HP grows with the wave so late waves stay threatening.  Superlinear:
    /// linear HP stopped mattering once player damage scaled up.
    pub fn hp_at(self, wave: i32) -> f32 {
        let w = (wave - 1).max(0) as f32;
        self.base_hp() * (1.0 + 0.34 * w + 0.020 * w * w)
    }

    pub fn speed(self) -> f32 {
        self.def().speed
    }

    pub fn damage(self) -> f32 {
        self.def().damage
    }

    pub fn radius(self) -> f32 {
        self.def().radius
    }

    pub fn xp(self) -> i32 {
        self.def().xp
    }

    pub fn money_chance(self) -> f32 {
        self.def().money_chance
    }

    pub fn money(self) -> i32 {
        self.def().money
    }

    /// Damage a charging body deals on impact -- deliberately more than its
    /// touch damage, because being hit by the dash should be a real mistake.
    pub fn dash_damage(self) -> f32 {
        if self.is_charger() { self.damage() + 7.0 } else { 0.0 }
    }

    /// Damage of one thrown blood clot (or caltrop).
    pub fn blood_damage(self) -> f32 {
        self.def().shot_damage
    }

    /// Distance a shooter tries to hold.  Anything with reach keeps its ring.
    pub fn standoff(self) -> f32 {
        self.def().standoff
    }

    pub fn throw_interval(self) -> f32 {
        self.def().throw_interval
    }

    /// Coins a miser can carry before it stops siphoning.
    pub fn purse(self) -> i32 {
        self.def().purse
    }

    /// Coins per second it lifts off you while close.
    pub fn siphon_rate(self) -> f32 {
        self.def().siphon
    }

    /// It only runs once it has a decent haul.
    pub fn flee_threshold(self) -> i32 {
        self.def().flee_at
    }
}

pub struct Enemy {
    pub id: u32,
    pub kind: EnemyKind,
    pub pos: Vec2,
    pub vel: Vec2,
    pub hp: f32,
    pub hp_max: f32,
    pub radius: f32,
    /// Counts down while the enemy is materialising; it cannot hurt the player
    /// until it reaches zero.
    pub spawn_t: f32,
    pub hurt_flash: f32,
    pub knock: Vec2,
    /// Slow applied by the sword, in seconds.
    pub slow_t: f32,
    pub bob_phase: f32,
    pub attack_cd: f32,
    /// Counts down after a dash hit, so one dash damages a target once.
    pub dash_cd: f32,
    /// Free-running behaviour clock: the charger's wind-up/dash cycle.
    pub state_t: f32,
    /// Counts down to a spitter's next throw.
    pub shoot_cd: f32,
    /// Fractional coin accumulator for a siphoning miser.
    pub siphon: f32,
    /// Coins a miser has lifted off the player.
    pub stolen: i32,
    /// Counts down while a fleeing miser leaks a coin behind itself.
    pub leak_cd: f32,
    /// A boss: an enormous version of its kind, and the point of the wave.
    pub boss: bool,
    /// How much extra health a grower has accumulated (for its tell).
    pub growth_bonus: f32,
}

/// A clot of blood thrown by a spitter.  Hostile projectiles live in their own
/// list so they can never be confused with the player's.
#[derive(Clone, Debug)]
pub struct EnemyShot {
    pub pos: Vec2,
    pub vel: Vec2,
    pub damage: f32,
    pub radius: f32,
    pub life: f32,
    pub spin: f32,
    /// Caltrops sit still and wait to be walked on.
    pub stationary: bool,
}

impl Enemy {
    pub fn speed_now(&self) -> f32 {
        if self.slow_t > 0.0 {
            self.kind.speed() * 0.45
        } else {
            self.kind.speed()
        }
    }

    pub fn is_alive(&self) -> bool {
        self.hp > 0.0
    }

    /// How much harder than its kind this enemy hits.
    pub fn damage_mult(&self) -> f32 {
        if self.boss {
            crate::world::BOSS_DAMAGE_MULT
        } else {
            1.0
        }
    }

    /// Draw size multiplier, including boss bulk.
    pub fn scale_now(&self) -> f32 {
        self.kind.scale() * if self.boss { crate::world::BOSS_SIZE_MULT } else { 1.0 }
    }

    pub fn is_materialising(&self) -> bool {
        self.spawn_t > 0.0
    }
}

// ---------------------------------------------------------------------------
// weapons
// ---------------------------------------------------------------------------

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum WeaponKind {
    Gun = 0,
    Bow = 1,
    Sword = 2,
}

impl WeaponKind {
    pub const ALL: [WeaponKind; 3] = [WeaponKind::Gun, WeaponKind::Bow, WeaponKind::Sword];

    pub fn index(self) -> usize {
        self as usize
    }

    pub fn sprite(self) -> SpriteId {
        match self {
            WeaponKind::Gun => SpriteId::Gun,
            WeaponKind::Bow => SpriteId::Bow,
            WeaponKind::Sword => SpriteId::Sword,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            WeaponKind::Gun => "GUN",
            WeaponKind::Bow => "BOW",
            WeaponKind::Sword => "SWORD",
        }
    }

    pub fn describe(self) -> &'static str {
        match self {
            WeaponKind::Gun => "Single fast bolt",
            WeaponKind::Bow => "3-arrow spread, pierces",
            WeaponKind::Sword => "Wide melee arc",
        }
    }

    pub fn base_damage(self) -> f32 {
        match self {
            WeaponKind::Gun => 13.0,
            WeaponKind::Bow => 7.0,
            WeaponKind::Sword => 26.0,
        }
    }

    pub fn base_interval(self) -> f32 {
        match self {
            WeaponKind::Gun => 0.42,
            WeaponKind::Bow => 0.72,
            WeaponKind::Sword => 0.58,
        }
    }

    /// Maximum distance at which this weapon will acquire a target.
    pub fn range(self) -> f32 {
        match self {
            WeaponKind::Gun => 620.0,
            WeaponKind::Bow => 560.0,
            WeaponKind::Sword => 132.0,
        }
    }

    pub fn price(self) -> i32 {
        match self {
            WeaponKind::Gun => 0,
            WeaponKind::Bow => 32,
            WeaponKind::Sword => 46,
        }
    }

    pub fn projectile_speed(self) -> f32 {
        match self {
            WeaponKind::Gun => 900.0,
            WeaponKind::Bow => 760.0,
            WeaponKind::Sword => 0.0,
        }
    }
}

#[derive(Clone, Debug)]
pub struct Weapon {
    pub kind: WeaponKind,
    pub owned: bool,
    pub level: i32,
    pub cooldown: f32,
    /// Counts down after a sword swing so the arc can be drawn.
    pub swing_t: f32,
    pub swing_dir: f32,
}

impl Weapon {
    pub fn new(kind: WeaponKind) -> Weapon {
        Weapon {
            kind,
            owned: false,
            level: 1,
            cooldown: 0.0,
            swing_t: 0.0,
            swing_dir: 0.0,
        }
    }

    /// Seconds between shots, including the weapon's own and the player's
    /// attack-speed upgrades.
    pub fn interval(&self, rate_mult: f32) -> f32 {
        let lvl = 1.0 + 0.12 * (self.level - 1) as f32;
        (self.kind.base_interval() / (lvl * rate_mult)).max(0.06)
    }

    pub fn damage(&self, damage_mult: f32) -> f32 {
        let lvl = 1.0 + 0.18 * (self.level - 1) as f32;
        self.kind.base_damage() * lvl * damage_mult
    }

    pub fn ready(&self) -> bool {
        self.owned && self.cooldown <= 0.0
    }

    pub fn tick(&mut self, dt: f32) {
        self.cooldown -= dt;
        self.swing_t = (self.swing_t - dt).max(0.0);
    }
}

// ---------------------------------------------------------------------------
// player
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct Stats {
    pub damage_mult: f32,
    pub rate_mult: f32,
    pub speed_mult: f32,
    /// Pickup attraction radius, in world units.
    pub magnet: f32,
    pub crit_chance: f32,
    pub crit_mult: f32,
    pub extra_pierce: i32,
    pub extra_arrows: i32,
    pub max_hp_bonus: f32,
    pub dash_cd_mult: f32,

    // -- incremental layer -------------------------------------------------
    /// Damage dealt to enemies dashed through (0 = dash is only defensive).
    pub dash_damage: f32,
    /// Multiplier on the chance that an enemy drops money.
    pub drop_mult: f32,
    /// Multiplier on the value of dropped money.
    pub money_mult: f32,
    /// 0 = no lightning.  Each level shortens the interval and hits harder.
    pub lightning_level: i32,
    /// Fraction of the money lying on the ground that is gathered every second.
    pub auto_collect: f32,
    /// Fraction of incoming damage ignored (capped).
    pub armor: f32,
    /// Health regenerated per second.
    pub regen: f32,
    /// Health restored per kill.
    pub lifesteal: f32,
    /// Damage dealt back to anything that touches the player.
    pub thorns: f32,
    /// Multiplier on experience gained.
    pub xp_mult: f32,
    /// Fraction of the purse paid out as earnings at every wave clear.
    pub interest: f32,
    /// Fraction taken off shop prices.
    pub discount: f32,
    /// Orbiting blades: 0 = none.
    pub orbitals: i32,
    /// Projectile splash damage multiplier: 0 = none.
    pub explosive: f32,
    /// Multiplier on the wave-clear bonus.
    pub wave_bonus: f32,
    /// Extra revives.  This is the main "makes a run longer" upgrade.
    pub lives: i32,
    /// Dash charges available at once.
    pub dash_charges: i32,
    /// Multiplier on the invulnerability window after a hit.
    pub iframes_mult: f32,
    /// Multiplier on projectile size.
    pub proj_size: f32,
    pub melee_mult: f32,
    pub ranged_mult: f32,
    /// Health restored at every wave clear.
    pub wave_heal: f32,
    /// Multiplier on the lightning blast radius.
    pub lightning_radius: f32,
    /// Chance per kill that a phantom of the player appears.
    pub phantom_chance: f32,
    /// Phantom damage multiplier.
    pub phantom_damage: f32,
    /// How many phantoms may exist at once.
    pub phantom_count: i32,
    /// How long a phantom lasts, in seconds.
    pub phantom_life: f32,
    /// Chance for a shot to be doubled.
    pub double_shot: f32,
}

/// A ghostly copy of the player that fights on its own for a while.
#[derive(Clone, Debug)]
pub struct Phantom {
    pub pos: Vec2,
    pub life: f32,
    pub max_life: f32,
    pub fire_cd: f32,
    pub aim: Vec2,
    pub damage: f32,
    pub phase: f32,
    /// Where it was born, so it drifts out of the corpse rather than popping.
    pub origin: Vec2,
}

impl Default for Stats {
    fn default() -> Self {
        Stats {
            damage_mult: 1.0,
            rate_mult: 1.0,
            speed_mult: 1.0,
            magnet: 105.0,
            crit_chance: 0.05,
            crit_mult: 2.0,
            extra_pierce: 0,
            extra_arrows: 0,
            max_hp_bonus: 0.0,
            dash_cd_mult: 1.0,
            dash_damage: 0.0,
            drop_mult: 1.0,
            money_mult: 1.0,
            lightning_level: 0,
            // The base game already vacuums up a fifth of what is on the floor,
            // so a passive player never leaves the arena empty handed.
            auto_collect: 0.20,
            armor: 0.0,
            regen: 0.0,
            lifesteal: 0.0,
            thorns: 0.0,
            xp_mult: 1.0,
            interest: 0.0,
            discount: 0.0,
            orbitals: 0,
            explosive: 0.0,
            wave_bonus: 1.0,
            lives: 0,
            dash_charges: 1,
            iframes_mult: 0.0,
            proj_size: 1.0,
            melee_mult: 1.0,
            ranged_mult: 1.0,
            wave_heal: 0.0,
            lightning_radius: 1.0,
            phantom_chance: 0.0,
            phantom_damage: 1.0,
            phantom_count: 0,
            phantom_life: 7.0,
            double_shot: 0.0,
        }
    }
}

impl Stats {
    /// Applies one tier of an upgrade tree node.
    ///
    /// This is the single place where a `StatKind` becomes a number, which is
    /// why the tree can have hundreds of nodes without hundreds of code paths.
    pub fn add(&mut self, kind: crate::tree::StatKind, v: f32) {
        use crate::tree::StatKind as K;
        match kind {
            K::Damage => self.damage_mult += v,
            K::Rate => self.rate_mult += v,
            K::Speed => self.speed_mult += v,
            K::MaxHp => self.max_hp_bonus += v,
            K::Magnet => self.magnet *= 1.0 + v,
            K::Crit => self.crit_chance = (self.crit_chance + v).min(0.85),
            K::CritMult => self.crit_mult += v,
            K::Pierce => self.extra_pierce += v as i32,
            K::Arrows => self.extra_arrows += v as i32,
            K::DashCd => self.dash_cd_mult = (self.dash_cd_mult * (1.0 - v)).max(0.22),
            K::DashDamage => self.dash_damage += v,
            K::DashCharges => self.dash_charges += v as i32,
            K::Iframes => self.iframes_mult += v,
            K::Drop => self.drop_mult += v,
            K::Money => self.money_mult += v,
            K::AutoCollect => self.auto_collect = (self.auto_collect + v).min(1.0),
            K::Thorns => self.thorns += v,
            K::Regen => self.regen += v,
            K::Lifesteal => self.lifesteal += v,
            K::Armor => self.armor = (self.armor + v).min(0.72),
            K::Xp => self.xp_mult += v,
            K::Interest => self.interest += v,
            K::Discount => self.discount = (self.discount + v).min(0.75),
            K::WaveBonus => self.wave_bonus += v,
            K::WaveHeal => self.wave_heal += v,
            K::Lightning => self.lightning_level += v as i32,
            K::LightningRadius => self.lightning_radius += v,
            K::Orbitals => self.orbitals += v as i32,
            K::Explosive => self.explosive += v,
            K::ProjSize => self.proj_size += v,
            K::MeleeDamage => self.melee_mult += v,
            K::RangedDamage => self.ranged_mult += v,
            K::Lives => self.lives += v as i32,
            // A phantom tier also makes the phantoms linger; splitting the two
            // would have made a whole extra family for a very small knob.
            K::PhantomChance => {
                self.phantom_chance = (self.phantom_chance + v).min(0.9);
                self.phantom_life += 0.8;
            }
            K::PhantomPower => self.phantom_damage += v,
            K::PhantomCount => self.phantom_count += v as i32,
            K::DoubleShot => self.double_shot = (self.double_shot + v).min(0.95),
            // Weapon unlocks live on the player, not on the stat block.
            K::UnlockBow | K::UnlockSword => {}
        }
    }

    /// Seconds between lightning strikes; infinite when not owned.
    pub fn lightning_interval(&self) -> f32 {
        if self.lightning_level <= 0 {
            f32::INFINITY
        } else {
            (3.4 / (1.0 + 0.22 * (self.lightning_level - 1) as f32)).max(0.55)
        }
    }

    pub fn lightning_damage(&self) -> f32 {
        if self.lightning_level <= 0 {
            0.0
        } else {
            42.0 * (1.0 + 0.45 * (self.lightning_level - 1) as f32)
        }
    }
}

#[derive(Clone, Debug)]
pub struct Player {
    pub pos: Vec2,
    pub vel: Vec2,
    pub base_speed: f32,
    pub hp: f32,
    pub base_hp_max: f32,
    pub radius: f32,
    /// Aim angle in radians.
    pub aim: f32,
    pub level: i32,
    pub xp: f32,
    pub money: i32,
    pub kills: i32,
    /// Active dash time remaining.
    pub dash_t: f32,
    pub dash_cd: f32,
    /// Dash charges currently available (refilled by `dash_recharge`).
    pub dash_charges: i32,
    pub dash_recharge: f32,
    pub dash_dir: Vec2,
    pub invuln: f32,
    pub hurt_flash: f32,
    pub stats: Stats,
    pub weapons: [Weapon; 3],
    pub trail_t: f32,
}

impl Player {
    pub fn new(pos: Vec2) -> Player {
        Player {
            pos,
            vel: Vec2::ZERO,
            base_speed: 268.0,
            hp: 100.0,
            base_hp_max: 100.0,
            radius: 26.0,
            aim: 0.0,
            level: 1,
            xp: 0.0,
            money: 0,
            kills: 0,
            dash_t: 0.0,
            dash_cd: 0.0,
            dash_charges: 1,
            dash_recharge: 0.0,
            dash_dir: Vec2::X,
            invuln: 0.0,
            hurt_flash: 0.0,
            stats: Stats::default(),
            weapons: [
                Weapon::new(WeaponKind::Gun),
                Weapon::new(WeaponKind::Bow),
                Weapon::new(WeaponKind::Sword),
            ],
            trail_t: 0.0,
        }
    }

    pub fn hp_max(&self) -> f32 {
        self.base_hp_max + self.stats.max_hp_bonus
    }

    pub fn speed(&self) -> f32 {
        self.base_speed * self.stats.speed_mult
    }

    pub fn dash_cooldown_max(&self) -> f32 {
        2.6 * self.stats.dash_cd_mult
    }

    /// How many dashes can be stored at once.
    pub fn dash_charge_max(&self) -> i32 {
        self.stats.dash_charges.max(1)
    }

    pub fn weapon(&self, kind: WeaponKind) -> &Weapon {
        &self.weapons[kind.index()]
    }

    pub fn weapon_mut(&mut self, kind: WeaponKind) -> &mut Weapon {
        &mut self.weapons[kind.index()]
    }

    pub fn owns(&self, kind: WeaponKind) -> bool {
        self.weapons[kind.index()].owned
    }

    pub fn xp_needed(level: i32) -> f32 {
        // Gentle curve: 12, 21, 32, 45, ...
        12.0 + 9.0 * (level - 1) as f32 + 0.8 * ((level - 1) * (level - 1)) as f32
    }
}

// ---------------------------------------------------------------------------
// projectiles, pickups, effects
// ---------------------------------------------------------------------------

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum ProjectileKind {
    Bolt,
    Arrow,
}

#[derive(Clone, Debug)]
pub struct Projectile {
    pub pos: Vec2,
    pub vel: Vec2,
    pub damage: f32,
    pub radius: f32,
    pub life: f32,
    pub pierce: i32,
    pub kind: ProjectileKind,
    pub angle: f32,
    pub hits: [u32; 6],
    pub hit_count: usize,
    pub crit: bool,
}

impl Projectile {
    pub fn already_hit(&self, id: u32) -> bool {
        self.hits[..self.hit_count].contains(&id)
    }

    pub fn register_hit(&mut self, id: u32) {
        if self.hit_count < self.hits.len() {
            self.hits[self.hit_count] = id;
            self.hit_count += 1;
        }
    }
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum PickupKind {
    Xp,
    Money,
}

impl PickupKind {
    pub fn sprite(self) -> SpriteId {
        match self {
            PickupKind::Xp => SpriteId::Xp,
            PickupKind::Money => SpriteId::Money,
        }
    }

    /// Colour used for this pickup's trail particles and HUD accents.
    pub fn sprite_color(self) -> u32 {
        match self {
            PickupKind::Xp => crate::render::color::XP_BLUE,
            PickupKind::Money => crate::render::color::MONEY_GREEN,
        }
    }
}

#[derive(Clone, Debug)]
pub struct Pickup {
    pub pos: Vec2,
    pub vel: Vec2,
    pub kind: PickupKind,
    pub value: i32,
    pub phase: f32,
    pub attracted: bool,
}

#[derive(Clone, Debug)]
pub struct Particle {
    pub pos: Vec2,
    pub vel: Vec2,
    pub life: f32,
    pub life_max: f32,
    pub size: f32,
    pub color: u32,
    pub rot: f32,
    pub spin: f32,
    pub drag: f32,
    pub additive: bool,
}

impl Particle {
    /// 1 at birth, 0 at death -- drives size and alpha.
    pub fn t(&self) -> f32 {
        if self.life_max <= 0.0 {
            0.0
        } else {
            (self.life / self.life_max).clamp(0.0, 1.0)
        }
    }
}

#[derive(Copy, Clone, Debug)]
pub enum FloaterKind {
    /// Damage number.
    Damage(i32),
    /// Money pickup: "+3".
    Money(i32),
    /// XP pickup: "+4 XP".
    Xp(i32),
    /// Fixed label such as "LEVEL UP".
    Label(&'static str),
}

#[derive(Clone, Debug)]
pub struct Floater {
    pub pos: Vec2,
    pub vel: Vec2,
    pub life: f32,
    pub life_max: f32,
    pub kind: FloaterKind,
    pub size: f32,
    pub color: u32,
}

// ---------------------------------------------------------------------------
// progression: perks shared by level-up cards and the shop
// ---------------------------------------------------------------------------

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Perk {
    Damage,
    Rate,
    Speed,
    MaxHp,
    Heal,
    Magnet,
    Pierce,
    Multishot,
    Crit,
    DashCd,
    /// Dash damages what it passes through.
    DashDamage,
    /// Enemies drop money more often.
    DropBonus,
    /// Everything is worth more money.
    Greed,
    /// Periodic lightning strike on a random enemy.
    Lightning,
    /// Automatically gather money from the floor.
    AutoCollect,
    /// Damage things that touch you.
    Thorns,
    /// Health over time.
    Regen,
    /// Heal on every kill.
    Lifesteal,
    /// Ignore a share of incoming damage.
    Armor,
    /// Extra revives: the run-extender.
    Revive,
    /// An extra dash charge.
    ExtraDash,
    /// More experience from every gem.
    XpGain,
    /// A cut of your purse as earnings at every wave clear.
    Interest,
    /// Cheaper shop.
    Discount,
    /// Blades that orbit the player.
    Orbital,
    /// Projectiles explode on impact.
    Explosive,
    /// Bigger wave-clear payouts.
    WaveBonus,
    Weapon(WeaponKind),
}

impl Perk {
    pub fn title(self) -> &'static str {
        match self {
            Perk::Damage => "SHARPER ROUNDS",
            Perk::Rate => "FAST HANDS",
            Perk::Speed => "LIGHT FEET",
            Perk::MaxHp => "THICK SKIN",
            Perk::Heal => "FIELD MEDIC",
            Perk::Magnet => "MAGNETISM",
            Perk::Pierce => "DEEP CUT",
            Perk::Multishot => "SPLIT SHOT",
            Perk::Crit => "KEEN EYE",
            Perk::DashCd => "QUICK ROLL",
            Perk::DashDamage => "BLAZING DASH",
            Perk::DropBonus => "SCAVENGER",
            Perk::Greed => "GREED",
            Perk::Lightning => "STORM CALLER",
            Perk::AutoCollect => "MAGNETIC WALLET",
            Perk::Thorns => "SPITE",
            Perk::Regen => "SECOND WIND",
            Perk::Lifesteal => "LEECH",
            Perk::Armor => "PLATE",
            Perk::Revive => "EXTRA LIFE",
            Perk::ExtraDash => "TWIN DASH",
            Perk::XpGain => "SCHOLAR",
            Perk::Interest => "INTEREST",
            Perk::Discount => "HAGGLER",
            Perk::Orbital => "ORBITAL BLADE",
            Perk::Explosive => "FRAG ROUNDS",
            Perk::WaveBonus => "BOUNTY",
            Perk::Weapon(WeaponKind::Gun) => "GUN",
            Perk::Weapon(WeaponKind::Bow) => "BOW",
            Perk::Weapon(WeaponKind::Sword) => "SWORD",
        }
    }

    pub fn describe(self) -> &'static str {
        match self {
            Perk::Damage => "+20% damage",
            Perk::Rate => "+15% fire rate",
            Perk::Speed => "+10% move speed",
            Perk::MaxHp => "+25 max HP, heal 25",
            Perk::Heal => "Heal 45 HP",
            Perk::Magnet => "+40% pickup range",
            Perk::Pierce => "Shots pierce +1 enemy",
            Perk::Multishot => "+1 bow arrow",
            Perk::Crit => "+7% crit chance",
            Perk::DashCd => "-18% dash cooldown",
            Perk::DashDamage => "Dash burns through enemies",
            Perk::DropBonus => "+30% money drop chance",
            Perk::Greed => "+25% money value",
            Perk::Lightning => "Random lightning strikes",
            Perk::AutoCollect => "+15% auto-collected money",
            Perk::Thorns => "Burn what touches you",
            Perk::Regen => "+0.6 HP per second",
            Perk::Lifesteal => "+2 HP per kill",
            Perk::Armor => "-10% damage taken",
            Perk::Revive => "Revive once per life",
            Perk::ExtraDash => "+1 dash charge",
            Perk::XpGain => "+25% experience",
            Perk::Interest => "+10% interest per wave",
            Perk::Discount => "-10% shop prices",
            Perk::Orbital => "A blade orbits you",
            Perk::Explosive => "Shots explode on impact",
            Perk::WaveBonus => "+30% wave bonus",
            Perk::Weapon(WeaponKind::Gun) => "Single fast bolt",
            Perk::Weapon(WeaponKind::Bow) => "3-arrow spread, pierces",
            Perk::Weapon(WeaponKind::Sword) => "Wide melee arc",
        }
    }

    /// Base shop price.  Perks that are also offered as free level-up cards cost
    /// more, so buying is a shortcut rather than the main path.
    pub fn base_price(self) -> i32 {
        match self {
            Perk::Weapon(k) => k.price(),
            Perk::Heal => 14,
            Perk::MaxHp => 26,
            Perk::Damage => 30,
            Perk::Rate => 30,
            Perk::Speed => 24,
            Perk::Magnet => 18,
            Perk::Pierce => 34,
            Perk::Multishot => 30,
            Perk::Crit => 28,
            Perk::DashCd => 22,
            Perk::DashDamage => 38,
            Perk::DropBonus => 42,
            Perk::Greed => 48,
            Perk::Lightning => 55,
            Perk::AutoCollect => 34,
            Perk::Thorns => 36,
            Perk::Regen => 44,
            Perk::Lifesteal => 46,
            Perk::Armor => 50,
            Perk::Revive => 90,
            Perk::ExtraDash => 52,
            Perk::XpGain => 40,
            Perk::Interest => 58,
            Perk::Discount => 56,
            Perk::Orbital => 62,
            Perk::Explosive => 66,
            Perk::WaveBonus => 38,
        }
    }

    pub fn is_weapon(self) -> bool {
        matches!(self, Perk::Weapon(_))
    }

    /// Perks that stop being useful once their cap is reached.
    pub fn max_stacks(self) -> i32 {
        match self {
            Perk::Revive => 3,
            Perk::Weapon(_) => 1,
            _ => 99,
        }
    }
}

/// Cards offered on level up.
///
/// Deliberately limited to the core body stats: the interesting, build-defining
/// upgrades are bought with money between rounds, which is what makes the
/// economy the centre of the game.
pub const LEVEL_UP_PERKS: [Perk; 6] = [
    Perk::Damage,
    Perk::Rate,
    Perk::Speed,
    Perk::MaxHp,
    Perk::Heal,
    Perk::Magnet,
];

/// Everything the shop can sell, in display order.  The UI pages through it.
pub const SHOP_PERKS: [Perk; 29] = [
    Perk::Weapon(WeaponKind::Bow),
    Perk::Weapon(WeaponKind::Sword),
    Perk::Damage,
    Perk::Rate,
    Perk::MaxHp,
    Perk::Speed,
    Perk::Heal,
    Perk::Magnet,
    Perk::Crit,
    Perk::Pierce,
    Perk::Multishot,
    Perk::DashCd,
    Perk::DashDamage,
    Perk::DropBonus,
    Perk::Greed,
    Perk::Lightning,
    Perk::AutoCollect,
    Perk::Thorns,
    Perk::Regen,
    Perk::Lifesteal,
    Perk::Armor,
    Perk::Revive,
    Perk::ExtraDash,
    Perk::XpGain,
    Perk::Interest,
    Perk::Discount,
    Perk::Orbital,
    Perk::Explosive,
    Perk::WaveBonus,
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn enemy_scaling_is_monotonic() {
        for kind in [EnemyKind::Grunt, EnemyKind::Brute] {
            let mut prev = 0.0;
            for wave in 1..25 {
                let hp = kind.hp_at(wave);
                assert!(hp > prev, "{:?} hp must grow with the wave", kind);
                prev = hp;
            }
        }
    }

    #[test]
    fn brutes_are_tankier_and_slower() {
        assert!(EnemyKind::Brute.hp_at(3) > EnemyKind::Grunt.hp_at(3));
        assert!(EnemyKind::Brute.speed() < EnemyKind::Grunt.speed());
        assert!(EnemyKind::Brute.damage() > EnemyKind::Grunt.damage());
    }

    #[test]
    fn xp_curve_is_increasing() {
        let mut prev = 0.0;
        for level in 1..30 {
            let need = Player::xp_needed(level);
            assert!(need > prev);
            prev = need;
        }
    }

    #[test]
    fn weapon_upgrades_improve_damage_and_rate() {
        let mut w = Weapon::new(WeaponKind::Gun);
        let d1 = w.damage(1.0);
        let i1 = w.interval(1.0);
        w.level = 4;
        assert!(w.damage(1.0) > d1);
        assert!(w.interval(1.0) < i1);
    }

    #[test]
    fn every_perk_has_text_and_a_price() {
        for perk in LEVEL_UP_PERKS.iter().chain(SHOP_PERKS.iter()) {
            assert!(!perk.title().is_empty());
            assert!(!perk.describe().is_empty());
            assert!(perk.base_price() >= 0);
        }
    }

    #[test]
    fn projectile_pierce_bookkeeping_is_bounded() {
        let mut p = Projectile {
            pos: Vec2::ZERO,
            vel: Vec2::ZERO,
            damage: 1.0,
            radius: 4.0,
            life: 1.0,
            pierce: 10,
            kind: ProjectileKind::Bolt,
            angle: 0.0,
            hits: [0; 6],
            hit_count: 0,
            crit: false,
        };
        for id in 1..12u32 {
            assert!(!p.already_hit(id));
            p.register_hit(id);
        }
        assert_eq!(p.hit_count, 6, "hit list must not overflow");
        assert!(p.already_hit(6));
        assert!(!p.already_hit(7));
    }
}
