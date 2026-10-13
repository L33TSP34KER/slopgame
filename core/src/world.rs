//! The game world: state machine, waves, progression economy, effects and the
//! save blob.  Per-frame simulation systems live in `systems.rs`, presentation
//! in `render_world.rs` and `ui.rs`.

use crate::backdrop::{spawn_ambient, Backdrop};
use crate::decor::Decor;
use crate::market::Market;
use crate::settings::{Settings, ROWS as SETTING_ROWS, ROW_BACK, ROW_RESET};
use crate::tree::{self};
use crate::entities::*;
use crate::ffi::*;
use crate::math::{clamp, Vec2};
use crate::render::{color, Rect, Renderer, View};

pub const ARENA_W: f32 = 2400.0;
pub const ARENA_H: f32 = 1560.0;

pub const SPAWN_TIME: f32 = 0.45;
pub const MAX_ENEMIES: usize = 340;
pub const MAX_PARTICLES: usize = 900;
pub const MAX_FLOATERS: usize = 64;
pub const MAX_PROJECTILES: usize = 400;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum State {
    Title,
    Playing,
    LevelUp,
    Shop,
    Paused,
    GameOver,
}

impl State {
    pub fn to_ffi(self) -> i32 {
        match self {
            State::Title => GC_STATE_TITLE,
            State::Playing => GC_STATE_PLAYING,
            State::LevelUp => GC_STATE_LEVEL_UP,
            State::Shop => GC_STATE_SHOP,
            State::Paused => GC_STATE_PAUSED,
            State::GameOver => GC_STATE_GAME_OVER,
        }
    }
}

/// Input for one step, already normalised by the shell.
#[derive(Copy, Clone, Debug, Default)]
pub struct InputState {
    pub move_axis: Vec2,
    /// Pointer position in virtual units (only meaningful when `pointer_active`).
    pub aim: Vec2,
    pub pointer_active: bool,
    pub pointer_down: bool,
    pub buttons: u32,
    /// Edge-detected by the shell (key press / button tap rather than hold).
    pub dash: bool,
    pub pause: bool,
    pub restart: bool,
    pub confirm: bool,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum BannerKind {
    WaveStart,
    /// A boss wave is starting (value = the wave).
    BossWave,
    WaveCleared,
    /// The 10-wave money quota was met (value = the goal that was met).
    CheckpointPassed,
    /// The quota was missed and the run is over (value = the goal missed).
    CheckpointFailed,
    /// The player spent a life (value = lives left).
    Revived,
    GameOver,
}

#[derive(Copy, Clone, Debug)]
pub struct Banner {
    pub kind: BannerKind,
    pub t: f32,
    pub max: f32,
    pub value: i32,
}

/// Progress through the upgrade tree.
#[derive(Clone, Debug)]
pub struct TreeState {
    /// Tiers owned per family.
    pub owned: [u8; tree::FAMILIES.len()],
    pub pan: Vec2,
    /// Drag state, so panning never buys something by accident.
    pub dragging: bool,
    pub press_at: Vec2,
    pub press_pan: Vec2,
    pub press_node: Option<usize>,
    /// The root node is owned from the first frame of a run.
    pub root_owned: bool,
    /// Set when the hive opens, so the view jumps to the frontier.
    pub center_requested: bool,
    /// Recently purchased node, for a flash.
    pub flash: f32,
    pub flash_node: usize,
}

impl TreeState {
    fn new() -> TreeState {
        TreeState {
            owned: [0; tree::FAMILIES.len()],
            pan: Vec2::ZERO,
            dragging: false,
            press_at: Vec2::ZERO,
            press_pan: Vec2::ZERO,
            press_node: None,
            root_owned: true,
            center_requested: true,
            flash: 0.0,
            flash_node: 0,
        }
    }

    pub fn tiers(&self, family: usize) -> u8 {
        self.owned.get(family).copied().unwrap_or(0)
    }
}

pub struct World {
    pub state: State,
    pub player: Player,
    pub enemies: Vec<Enemy>,
    pub projectiles: Vec<Projectile>,
    pub pickups: Vec<Pickup>,
    pub particles: Vec<Particle>,
    pub floaters: Vec<Floater>,
    pub events: Vec<gc_event>,

    pub rng: crate::math::Rng,
    pub seed: u32,
    /// Procedural, wave-driven arena mood.
    pub backdrop: Backdrop,
    /// Scenery: fixed props and a parallax layer, per theme.
    pub decor: Decor,
    /// Ghostly copies of the player, summoned on kills.
    pub phantoms: Vec<Phantom>,
    /// Blood clots in flight: hostile projectiles, kept apart from the player's.
    pub shots: Vec<crate::entities::EnemyShot>,
    /// Player settings, edited by the options screen.
    pub settings: Settings,
    /// The Market: repeatable economy upgrades, bought in the Hive.
    pub market: Market,
    /// The Market overlay is open over the Hive.
    pub market_open: bool,
    /// Row the pointer is over, for highlight.
    pub market_row: usize,
    /// The options overlay is open over whatever state is underneath.
    pub options_open: bool,
    /// Highlighted row, for pointer feedback.
    pub options_row: usize,
    /// Row whose slider is being dragged, if any.
    pub options_drag: Option<usize>,
    pub next_id: u32,

    pub wave: i32,
    pub spawn_left: i32,
    pub brutes_left: i32,
    pub colossi_left: i32,
    pub spawn_timer: f32,
    pub wave_t: f32,
    /// Set while the "wave cleared" banner is showing; counts down to the shop.
    pub wave_break_t: f32,
    /// True on a boss wave: one enormous enemy, and the rest of the wave is its
    /// own kind rather than the usual mix.
    pub boss_wave: bool,
    /// Which kind the boss (and its escort) is, on a boss wave.
    pub boss_kind: EnemyKind,
    /// Id of the live boss, or 0 when there is none.
    pub boss_id: u32,
    pub boss_hp: f32,
    pub boss_hp_max: f32,

    pub time: f32,
    pub best_score: i32,
    /// Cumulative money earned this run.  This -- not the purse -- is what the
    /// quota is measured against, so spending money never sets you back.
    pub money_earned: i32,

    /// Completed checkpoints.
    pub tier: i32,
    /// Cumulative earnings required at the next checkpoint.
    pub goal: i32,
    /// Wave at which the current goal is checked (10, 20, 30, ...).
    pub goal_wave: i32,
    /// Countdown to the next lightning strike.
    pub lightning_cd: f32,
    /// Fractional money gathered by the passive auto-collector.
    pub auto_pool: f32,

    pub camera: Vec2,
    /// World-to-virtual-unit scale, refreshed every frame from the view.
    pub zoom: f32,
    pub shake: f32,

    pub cards: [Perk; 3],
    pub cards_shown: usize,
    /// The between-round upgrade tree.
    pub tree: TreeState,
    pub banner: Option<Banner>,

    /// Seconds since the run ended; blocks accidental instant restarts.
    pub over_t: f32,
    /// Latest pointer position in virtual units, for hover feedback.
    pub pointer: Vec2,
    pub pointer_active: bool,
    pub prev_pointer_down: bool,
    pub prev_buttons: u32,
    pub debug_invuln: bool,
    /// Level-ups earned while an intermission was open.
    pub pending_level_ups: i32,
}

impl World {
    pub fn new(seed: u32, best_score: i32) -> World {
        let world = World {
            state: State::Title,
            player: Player::new(Vec2::new(ARENA_W * 0.5, ARENA_H * 0.5)),
            enemies: Vec::new(),
            projectiles: Vec::new(),
            pickups: Vec::new(),
            particles: Vec::new(),
            floaters: Vec::new(),
            events: Vec::new(),
            rng: crate::math::Rng::new(seed),
            seed,
            backdrop: Backdrop::new(&mut crate::math::Rng::new(seed)),
            decor: Decor::new(seed, Vec2::new(ARENA_W, ARENA_H)),
            phantoms: Vec::new(),
            shots: Vec::new(),
            settings: Settings::default(),
            market: Market::default(),
            market_open: false,
            market_row: 0,
            options_open: false,
            options_row: 0,
            options_drag: None,
            next_id: 1,
            wave: 1,
            spawn_left: 0,
            brutes_left: 0,
            colossi_left: 0,
            spawn_timer: 0.0,
            wave_t: 0.0,
            wave_break_t: 0.0,
            boss_wave: false,
            boss_kind: EnemyKind::Grunt,
            boss_id: 0,
            boss_hp: 0.0,
            boss_hp_max: 0.0,
            time: 0.0,
            best_score,
            money_earned: 0,
            tier: 0,
            goal: 0,
            goal_wave: GOAL_WAVE_STEP,
            lightning_cd: 0.0,
            auto_pool: 0.0,
            camera: Vec2::new(ARENA_W * 0.5, ARENA_H * 0.5),
            zoom: 1.0,
            shake: 0.0,
            cards: [Perk::Damage; 3],
            cards_shown: 0,
            tree: TreeState::new(),
            banner: None,
            over_t: 0.0,
            pointer: Vec2::ZERO,
            pointer_active: false,
            prev_pointer_down: false,
            prev_buttons: 0,
            debug_invuln: false,
            pending_level_ups: 0,
        };
        world
    }

    // -- lifecycle ----------------------------------------------------------

    pub fn start_run(&mut self) {
        // Re-seeding from the same seed replays the same run, which is what
        // makes the automated screenshot tests reproducible.
        self.rng = crate::math::Rng::new(self.seed);
        self.backdrop.reseed(&mut self.rng);
        self.decor.reseed(self.seed);
        self.player = Player::new(Vec2::new(ARENA_W * 0.5, ARENA_H * 0.5));
        self.player.weapon_mut(WeaponKind::Gun).owned = true;
        self.enemies.clear();
        self.phantoms.clear();
        self.shots.clear();
        self.projectiles.clear();
        self.pickups.clear();
        self.particles.clear();
        self.floaters.clear();
        self.next_id = 1;
        self.wave = 1;
        self.time = 0.0;
        self.money_earned = 0;
        self.tier = 0;
        self.goal = self.goal_now();
        self.goal_wave = GOAL_WAVE_STEP;
        self.lightning_cd = 0.0;
        self.auto_pool = 0.0;
        self.shake = 0.0;
        self.pending_level_ups = 0;
        self.camera = self.player.pos;
        self.cards_shown = 0;
        self.tree = TreeState::new();
        self.start_wave();
    }

    pub fn start_wave(&mut self) {
        self.boss_wave = is_boss_wave(self.wave);
        self.boss_id = 0;
        self.boss_hp = 0.0;
        self.boss_hp_max = 0.0;

        if self.boss_wave {
            // Boss waves are one enormous enemy plus a crowd of its own kind --
            // no mixed bag, so the wave has a single, readable idea.
            self.boss_kind = boss_kind_for_wave(self.wave);
            let escort = (10 + self.wave * 2).clamp(12, 90);
            self.spawn_left = escort;
            self.brutes_left = 0;
            self.colossi_left = 0;
            self.spawn_timer = 0.9;
            self.wave_t = 0.0;
            self.wave_break_t = 0.0;
            self.state = State::Playing;
            self.banner = Some(Banner { kind: BannerKind::BossWave, t: 2.6, max: 2.6, value: self.wave });
            self.add_event(GC_EVT_WAVE_START, self.player.pos.x, self.player.pos.y, self.wave as f32);
            self.spawn_boss();
            return;
        }

        let (grunts, brutes, colossi) = wave_plan(self.wave);
        self.spawn_left = grunts + brutes + colossi;
        self.brutes_left = brutes;
        self.colossi_left = colossi;
        self.spawn_timer = 0.5;
        self.wave_t = 0.0;
        self.wave_break_t = 0.0;
        self.state = State::Playing;
        self.banner = Some(Banner { kind: BannerKind::WaveStart, t: 1.9, max: 1.9, value: self.wave });
        self.add_event(GC_EVT_WAVE_START, self.player.pos.x, self.player.pos.y, self.wave as f32);
    }

    /// Summons the wave's boss: a much larger, much angrier version of a kind
    /// you already know, so its tells still read.
    fn spawn_boss(&mut self) {
        let kind = self.boss_kind;
        let angle = self.rng.angle();
        let dist = 430.0;
        let at = self.player.pos + Vec2::from_angle(angle) * dist;
        let pos = Vec2::new(at.x.clamp(80.0, ARENA_W - 80.0), at.y.clamp(80.0, ARENA_H - 80.0));
        let hp = kind.hp_at(self.wave) * BOSS_HP_MULT;
        self.next_id += 1;
        let id = self.next_id;
        self.enemies.push(crate::entities::Enemy {
            id,
            kind,
            pos,
            vel: Vec2::ZERO,
            hp,
            hp_max: hp,
            radius: kind.radius() * BOSS_SIZE_MULT,
            spawn_t: 1.1,
            hurt_flash: 0.0,
            knock: Vec2::ZERO,
            slow_t: 0.0,
            bob_phase: self.rng.angle(),
            attack_cd: 0.0,
            dash_cd: 0.0,
            state_t: 0.0,
            shoot_cd: 1.2,
            siphon: 0.0,
            stolen: 0,
            leak_cd: 0.0,
            boss: true,
            growth_bonus: 0.0,
        });
        self.boss_id = id;
        self.boss_hp = hp;
        self.boss_hp_max = hp;
        self.shake = (self.shake + 14.0).min(22.0);
        self.burst(pos, 26, color::GOLD, 260.0, 8.0, 0.8, true);
        self.add_event(GC_EVT_BOSS_SPAWN, pos.x, pos.y, kind_index(kind) as f32);
    }

    pub(crate) fn on_wave_cleared(&mut self) {
        // Bounty raises the clear bonus; Interest pays a cut of the purse, which
        // is what makes a long run snowball.
        let bounty = self.player.stats.wave_bonus;
        let bonus = ((12 + self.wave * 3) as f32
            * (1.0 + self.wave as f32 * 0.05)
            * self.player.stats.money_mult
            * bounty)
            .round() as i32;
        self.earn_money(bonus);
        let interest = (self.player.money as f32 * self.player.stats.interest).round() as i32;
        if interest > 0 {
            self.earn_money(interest);
            self.floater(self.player.pos + Vec2::new(0.0, -52.0),
                         FloaterKind::Money(interest), color::GOLD, 22.0);
        }
        self.banner = Some(Banner { kind: BannerKind::WaveCleared, t: 2.4, max: 2.4, value: bonus });
        self.add_event(GC_EVT_WAVE_CLEAR, self.player.pos.x, self.player.pos.y, self.wave as f32);

        // The 10-wave quota is checked before the shop opens.
        if self.wave >= self.goal_wave && !self.check_quota() {
            return; // the run is over
        }

        // A level-up always takes priority over shopping.
        if self.pending_level_ups > 0 {
            self.open_level_up();
        } else {
            self.open_hive();
        }
    }

    /// Enters the between-round hive, asking the view to centre on the frontier.
    pub fn open_hive(&mut self) {
        self.tree.center_requested = true;
        self.tree.dragging = false;
        self.state = State::Shop;
    }

    /// Awards money and records it against the quota.
    pub fn earn_money(&mut self, amount: i32) {
        if amount <= 0 {
            return;
        }
        self.player.money += amount;
        self.money_earned += amount;
    }

    /// True if the run may continue.  Failing the quota ends the run.
    /// The tax for the current tier, after any Tax Rebate levels bought in the
    /// Market.  Every read of the goal goes through here, so the discount can
    /// never be bypassed.
    pub fn goal_now(&self) -> i32 {
        let raw = goal_for_tier(self.tier) as f64 * self.market.rebate_mult();
        raw.round().clamp(1.0, 2.0e9) as i32
    }

    /// Buys one Market level, applying its effect immediately.
    pub fn buy_market(&mut self, item: usize) -> bool {
        let mut money = self.player.money;
        // Stats is not Copy, so the effect is worked out on a copy and written
        // back only when the purchase actually happens.
        let mut stats = self.player.stats.clone();
        let bought = self.market.buy(item, &mut money, &mut stats);
        let pos = self.player.pos;
        if bought {
            self.player.money = money;
            self.player.stats = stats;
            // A rebate changes the tax that is currently due.
            self.goal = self.goal_now();
            self.add_event(GC_EVT_BUY, pos.x, pos.y, item as f32);
            self.floater(pos + Vec2::new(0.0, -46.0), FloaterKind::Label("MARKET"),
                         color::GOLD, 22.0);
        } else {
            self.add_event(GC_EVT_BUY_FAIL, pos.x, pos.y, item as f32);
        }
        bought
    }

    fn check_quota(&mut self) -> bool {
        let earned = self.money_earned;
        let goal = self.goal;
        if earned >= goal {
            self.tier += 1;
            // Checkpoint rewards: a real power spike, so meeting the quota feels
            // like a milestone rather than a tax.
            let stats = &mut self.player.stats;
            stats.damage_mult += 0.15;
            stats.max_hp_bonus += 30.0;
            self.player.hp = (self.player.hp + 60.0).min(self.player.hp_max());
            self.goal = self.goal_now();
            self.goal_wave += GOAL_WAVE_STEP;
            self.banner = Some(Banner {
                kind: BannerKind::CheckpointPassed,
                t: 3.2,
                max: 3.2,
                value: goal,
            });
            self.add_event(GC_EVT_CHECKPOINT_PASSED, self.player.pos.x, self.player.pos.y,
                           goal as f32);
            let p = self.player.pos;
            self.burst(p, 60, color::GOLD, 300.0, 9.0, 1.1, true);
            true
        } else {
            self.banner = Some(Banner {
                kind: BannerKind::CheckpointFailed,
                t: 4.0,
                max: 4.0,
                value: goal,
            });
            self.add_event(GC_EVT_CHECKPOINT_FAILED, self.player.pos.x, self.player.pos.y,
                           goal as f32);
            self.game_over();
            false
        }
    }

    pub fn score(&self) -> i32 {
        self.player.kills * 10
            + (self.wave - 1).max(0) * 150
            + (self.player.level - 1) * 60
            + self.money_earned
    }

    // -- progression --------------------------------------------------------

    fn open_level_up(&mut self) {
        self.pending_level_ups = (self.pending_level_ups - 1).max(0);
        self.roll_cards();
        self.state = State::LevelUp;
        self.add_event(GC_EVT_LEVEL_UP, self.player.pos.x, self.player.pos.y,
                       self.player.level as f32);
        let p = self.player.pos;
        self.burst(p, 26, color::XP, 210.0, 7.0, 0.7, true);
    }

    fn roll_cards(&mut self) {
        let mut pool: Vec<Perk> = LEVEL_UP_PERKS.to_vec();
        let mut chosen = [Perk::Damage; 3];
        for slot in chosen.iter_mut() {
            if pool.is_empty() {
                *slot = Perk::Heal;
                continue;
            }
            let idx = (self.rng.next_u32() as usize) % pool.len();
            *slot = pool.remove(idx);
        }
        self.cards = chosen;
        self.cards_shown = 3;
    }

    pub fn apply_perk(&mut self, perk: Perk) {
        let stats = &mut self.player.stats;
        match perk {
            Perk::Damage => stats.damage_mult += 0.20,
            Perk::Rate => stats.rate_mult += 0.15,
            Perk::Speed => stats.speed_mult += 0.10,
            Perk::MaxHp => {
                stats.max_hp_bonus += 25.0;
            }
            Perk::Heal => {}
            Perk::Magnet => stats.magnet *= 1.40,
            Perk::Pierce => stats.extra_pierce += 1,
            Perk::Multishot => stats.extra_arrows += 1,
            Perk::Crit => stats.crit_chance += 0.07,
            Perk::DashCd => stats.dash_cd_mult = (stats.dash_cd_mult * 0.82).max(0.35),
            Perk::DashDamage => stats.dash_damage += 22.0,
            Perk::DropBonus => stats.drop_mult += 0.30,
            Perk::Greed => stats.money_mult += 0.25,
            Perk::Lightning => stats.lightning_level += 1,
            Perk::AutoCollect => stats.auto_collect = (stats.auto_collect + 0.15).min(1.0),
            Perk::Thorns => stats.thorns += 14.0,
            Perk::Regen => stats.regen += 0.6,
            Perk::Lifesteal => stats.lifesteal += 2.0,
            Perk::Armor => stats.armor = (stats.armor + 0.10).min(0.65),
            Perk::Revive => {
                stats.lives += 1;
                // A fresh life is worth having immediately.
            }
            Perk::ExtraDash => stats.dash_charges += 1,
            Perk::XpGain => stats.xp_mult += 0.25,
            Perk::Interest => stats.interest += 0.10,
            Perk::Discount => stats.discount = (stats.discount + 0.10).min(0.60),
            Perk::Orbital => stats.orbitals += 1,
            Perk::Explosive => stats.explosive += 0.55,
            Perk::WaveBonus => stats.wave_bonus += 0.30,
            Perk::Weapon(kind) => {
                let w = self.player.weapon_mut(kind);
                if w.owned {
                    w.level += 1;
                } else {
                    w.owned = true;
                    w.cooldown = 0.0;
                }
            }
        }
        // Healing has to clamp against the *new* max HP, so it happens after the
        // stat change above.
        match perk {
            Perk::MaxHp => self.player.hp = (self.player.hp + 25.0).min(self.player.hp_max()),
            Perk::Heal => self.player.hp = (self.player.hp + 45.0).min(self.player.hp_max()),
            _ => {}
        }
        let p = self.player.pos;
        self.burst(p, 18, color::GOLD, 170.0, 6.0, 0.55, true);
        self.floater(p + Vec2::new(0.0, -34.0), FloaterKind::Label(perk.title()),
                     color::GOLD, 22.0);
    }

    // -- the upgrade tree ---------------------------------------------------

    /// Can this node be bought right now (ignoring money)?
    pub fn node_available(&self, node: usize) -> bool {
        if node >= tree::NODE_COUNT {
            return false;
        }
        if tree::is_root(node) {
            return !self.tree.root_owned;
        }
        let family = tree::family_of(node);
        let tier = tree::tier_of(node);
        if self.tree.tiers(family) + 1 != tier {
            return false;
        }
        if tree::FAMILIES[family].min_wave > self.wave {
            return false;
        }
        match tree::requires(node) {
            Some(req) => self.node_owned(req),
            None => true,
        }
    }

    pub fn node_owned(&self, node: usize) -> bool {
        if node >= tree::NODE_COUNT {
            return false;
        }
        if tree::is_root(node) {
            return self.tree.root_owned;
        }
        self.tree.tiers(tree::family_of(node)) >= tree::tier_of(node)
    }

    /// Whether the hive should draw this node at all.
    ///
    /// Only the owned frontier and the layer just beyond it are shown, so the
    /// tree is revealed as it grows instead of being one enormous wall of nodes.
    pub fn node_visible(&self, node: usize) -> bool {
        if node >= tree::NODE_COUNT || self.node_owned(node) || self.node_available(node) {
            return true;
        }
        if !tree::is_root(node) && tree::FAMILIES[tree::family_of(node)].min_wave > self.wave {
            return false;
        }
        match tree::requires(node) {
            Some(req) => self.node_owned(req) || self.node_available(req),
            None => true,
        }
    }

    pub fn node_cost(&self, node: usize) -> i32 {
        if node >= tree::NODE_COUNT {
            return i32::MAX;
        }
        if tree::is_root(node) {
            return 0;
        }
        tree::cost(tree::family_of(node), self.tree.tiers(tree::family_of(node)), self.wave,
                   self.player.stats.discount)
    }

    /// Buys one tier.  Returns true when the purchase happened.
    pub fn buy_node(&mut self, node: usize) -> bool {
        if !self.node_available(node) {
            self.add_event(GC_EVT_BUY_FAIL, self.pointer.x, self.pointer.y, 0.0);
            return false;
        }
        let price = self.node_cost(node);
        if self.player.money < price {
            self.add_event(GC_EVT_BUY_FAIL, self.pointer.x, self.pointer.y, price as f32);
            return false;
        }
        self.player.money -= price;
        self.grant_node(node);
        self.add_event(GC_EVT_BUY, self.pointer.x, self.pointer.y, price as f32);
        true
    }

    /// Applies a node's effect without charging for it.
    pub fn grant_node(&mut self, node: usize) {
        if node >= tree::NODE_COUNT {
            return;
        }
        if tree::is_root(node) {
            if self.tree.root_owned {
                return;
            }
            self.tree.root_owned = true;
            // The seed of every build.
            let stats = &mut self.player.stats;
            stats.damage_mult += 0.10;
            stats.max_hp_bonus += 12.0;
            stats.speed_mult += 0.08;
            self.tree.flash = 0.5;
            self.tree.flash_node = node;
            let pos = self.player.pos;
            self.burst(pos, 26, color::GOLD, 220.0, 7.0, 0.7, true);
            return;
        }
        let family = tree::family_of(node);
        if self.tree.tiers(family) + 1 != tree::tier_of(node) {
            return;
        }
        self.tree.owned[family] += 1;
        let f = tree::family(node);
        self.player.stats.add(f.kind, f.per_tier);
        match f.kind {
            tree::StatKind::UnlockBow => {
                let w = self.player.weapon_mut(WeaponKind::Bow);
                if w.owned {
                    w.level += 1;
                } else {
                    w.owned = true;
                }
            }
            tree::StatKind::UnlockSword => {
                let w = self.player.weapon_mut(WeaponKind::Sword);
                if w.owned {
                    w.level += 1;
                } else {
                    w.owned = true;
                }
            }
            _ => {}
        }
        self.tree.flash = 0.5;
        self.tree.flash_node = node;
        let pos = self.player.pos;
        self.burst(pos, 14, color::GOLD, 150.0, 5.0, 0.45, true);
        self.floater(pos + Vec2::new(0.0, -34.0), FloaterKind::Label(f.name),
                     color::GOLD, 20.0);
    }

    /// Cheapest purchasable node, or the next one along the frontier.
    pub fn next_node_to_buy(&self) -> Option<usize> {
        let mut best: Option<(usize, i32)> = None;
        for node in 0..tree::NODE_COUNT {
            if !self.node_available(node) {
                continue;
            }
            let cost = self.node_cost(node);
            if best.map_or(true, |(_, c)| cost < c) {
                best = Some((node, cost));
            }
        }
        best.map(|(n, _)| n)
    }

    /// Number of tiers owned across the whole tree (used by the HUD).
    pub fn tree_tiers_owned(&self) -> i32 {
        self.tree.owned.iter().map(|t| *t as i32).sum()
    }

    // -- effects ------------------------------------------------------------

    pub fn add_event(&mut self, type_: i32, x: f32, y: f32, value: f32) {
        if self.events.len() < 256 {
            self.events.push(gc_event { type_, x, y, value });
        }
    }

    pub fn burst(&mut self, pos: Vec2, count: i32, color: u32, speed: f32, size: f32,
                 life: f32, additive: bool) {
        // Particle density is a setting: scale the count, but keep at least one
        // so an effect never disappears entirely.
        let scaled = (count as f32 * self.settings.particle_scale()).round() as i32;
        let count = if count > 0 { scaled.max(1) } else { 0 };
        for _ in 0..count {
            if self.particles.len() >= MAX_PARTICLES {
                return;
            }
            let dir = self.rng.unit_vec();
            let s = speed * self.rng.range(0.35, 1.0);
            let life_max = life;
            self.particles.push(Particle {
                pos,
                vel: dir * s,
                life: life * self.rng.range(0.6, 1.15),
                life_max,
                size: size * self.rng.range(0.55, 1.3),
                color,
                rot: self.rng.angle(),
                spin: self.rng.range(-8.0, 8.0),
                drag: 3.2,
                additive,
            });
        }
    }

    pub fn floater(&mut self, pos: Vec2, kind: FloaterKind, color: u32, size: f32) {
        if self.floaters.len() >= MAX_FLOATERS {
            return;
        }
        // Damage numbers can be switched off; the other floaters (XP, money,
        // level-up text) are not affected.
        if !self.settings.damage_numbers && matches!(kind, FloaterKind::Damage(_)) {
            return;
        }
        self.floaters.push(Floater {
            pos,
            vel: Vec2::new(0.0, -46.0),
            life: 0.85,
            life_max: 0.85,
            kind,
            size,
            color,
        });
    }

    pub fn damage_enemy(&mut self, index: usize, amount: f32, crit: bool, knock: Vec2) {
        if index >= self.enemies.len() {
            return;
        }
        let (pos, died, hp_frac, dealt) = {
            let e = &mut self.enemies[index];
            // Armour is a flat cut, so a bulwark shrugs off chip damage and only
            // respects real hits -- and the floating number shows what landed.
            let cut = (amount * (1.0 - e.kind.def().armor)).max(1.0);
            e.hp -= cut;
            e.hurt_flash = 0.14;
            e.knock += knock;
            (e.pos, e.hp <= 0.0, (e.hp / e.hp_max).clamp(0.0, 1.0), cut)
        };
        let _ = hp_frac;
        let amount = dealt;
        self.floater(pos + Vec2::new(0.0, -18.0), FloaterKind::Damage(amount.round() as i32),
                     if crit { color::GOLD } else { color::WHITE },
                     if crit { 24.0 } else { 18.0 });
        self.add_event(GC_EVT_HIT, pos.x, pos.y, amount);
        self.burst(pos, if crit { 6 } else { 3 }, color::SLIME_HOT, 150.0, 4.0, 0.28, false);
        if died {
            self.kill_enemy(index);
        }
    }

    /// Rolls the Phantom upgrade: a kill may leave a ghost of the player behind.
    fn try_summon_phantom(&mut self, at: Vec2) {
        let stats = &self.player.stats;
        let cap = stats.phantom_count.max(0) as usize;
        if cap == 0 || self.phantoms.len() >= cap || stats.phantom_chance <= 0.0 {
            return;
        }
        if !self.rng.chance(stats.phantom_chance) {
            return;
        }
        let life = stats.phantom_life.max(1.0);
        let damage = stats.phantom_damage;
        self.phantoms.push(Phantom {
            pos: at,
            origin: at,
            life,
            max_life: life,
            fire_cd: 0.35,
            aim: Vec2::new(1.0, 0.0),
            damage,
            phase: self.rng.range(0.0, 6.28),
        });
        self.burst(at, 12, 0xCCBBFF, 200.0, 7.0, 0.5, true);
        self.add_event(GC_EVT_REVIVED, at.x, at.y, 2.0);
    }

    /// Splitter children and a bomber's last word, applied where the corpse is.
    fn on_enemy_death(&mut self, pos: Vec2, kind: EnemyKind) {
        use crate::enemy_def::Behaviour as B;
        let def = kind.def();
        match def.behaviour {
            B::Splitter => {
                if let Some(child) = def.splits_into {
                    for k in 0..def.split_count.max(1) {
                        let angle = self.rng.angle();
                        let at = pos + Vec2::from_angle(angle) * (28.0 + 14.0 * k as f32);
                        let hp = child.hp_at(self.wave);
                        self.next_id += 1;
                        self.enemies.push(Enemy {
                            id: self.next_id,
                            kind: child,
                            pos: Vec2::new(at.x.clamp(20.0, ARENA_W - 20.0),
                                           at.y.clamp(20.0, ARENA_H - 20.0)),
                            vel: Vec2::ZERO,
                            hp, hp_max: hp,
                            radius: child.radius(),
                            spawn_t: 0.3,
                            hurt_flash: 0.0,
                            knock: Vec2::ZERO,
                            slow_t: 0.0,
                            bob_phase: self.rng.angle(),
                            attack_cd: 0.0,
                            dash_cd: 0.0,
                            state_t: 0.0,
                            shoot_cd: 0.0,
                            siphon: 0.0,
                            stolen: 0,
                            leak_cd: 0.0,
                            boss: false,
                            growth_bonus: 0.0,
                        });
                    }
                    let burst_at = pos;
                    self.burst(burst_at, 14, color::SLIME, 190.0, 6.0, 0.5, false);
                }
            }
            B::Bomber => {
                let radius = def.sigil_radius;
                let damage = def.sigil_power * (1.0 + 0.06 * self.wave as f32);
                self.burst(pos, 26, color::SLIME_HOT, 260.0, 9.0, 0.6, true);
                self.burst(pos, 10, color::WHITE, 180.0, 6.0, 0.35, true);
                self.shake = (self.shake + 8.0).min(20.0);
                if self.player.pos.distance_sq(pos) <= (radius + self.player.radius).powi(2) {
                    self.hurt_player(damage);
                }
            }
            _ => {}
        }
    }

    pub(crate) fn kill_enemy(&mut self, index: usize) {
        let e = self.enemies.remove(index);
        let pos = e.pos;
        let kind = e.kind;
        let e_stolen = e.stolen;
        let e_boss = e.boss;
        self.player.kills += 1;
        let leech = self.player.stats.lifesteal;
        if leech > 0.0 && self.player.hp < self.player.hp_max() {
            self.player.hp = (self.player.hp + leech).min(self.player.hp_max());
        }
        self.on_enemy_death(pos, kind);
        self.burst(pos, if kind.is_brute() { 26 } else { 14 }, color::SLIME, 260.0,
                   if kind.is_brute() { 9.0 } else { 6.0 }, 0.6, false);
        self.burst(pos, 6, color::WHITE, 180.0, 5.0, 0.35, true);
        self.add_event(GC_EVT_ENEMY_DIE, pos.x, pos.y,
                       if kind.is_brute() { 2.0 } else { 1.0 });
        self.shake = (self.shake + if kind.is_brute() { 7.0 } else { 2.6 }).min(18.0);

        // A boss is worth a pile, and its death is an event.
        if e_boss {
            self.boss_id = 0;
            self.boss_hp = 0.0;
            self.boss_hp_max = 0.0;
            self.shake = (self.shake + 20.0).min(26.0);
            self.burst(pos, 60, color::GOLD, 340.0, 12.0, 1.1, true);
            self.burst(pos, 24, color::WHITE, 240.0, 8.0, 0.7, true);
            let haul = 40 + self.wave * 6;
            for _ in 0..6 {
                self.drop_pickup(pos, PickupKind::Money, haul / 3);
            }
            self.floater(pos + Vec2::new(0.0, -70.0), FloaterKind::Label("BOSS DOWN"),
                         color::GOLD, 30.0);
        }
        // A miser drops what it lifted: the chase pays for itself.
        if e_stolen > 0 {
            let per = (e_stolen / 3).max(1);
            let mut left = e_stolen;
            while left > 0 {
                let chunk = per.min(left);
                self.drop_pickup(pos, PickupKind::Money, chunk);
                left -= chunk;
            }
            self.add_event(GC_EVT_MONEY_STOLEN, pos.x, pos.y, -(e_stolen as f32));
        }
        self.try_summon_phantom(pos);
        self.drop_pickup(pos, PickupKind::Xp, kind.xp());
        // Scavenger raises the drop *chance*; Greed raises the *value*.
        let chance = (kind.money_chance() * self.player.stats.drop_mult).min(1.0);
        let mut drops = 0;
        if self.rng.chance(chance) {
            drops += 1;
        }
        // Surplus drop chance spills over into a chance of a second pile.
        let overflow = (kind.money_chance() * self.player.stats.drop_mult) - 1.0;
        if overflow > 0.0 && self.rng.chance(overflow.min(1.0)) {
            drops += 1;
        }
        // Coins scale with the wave: without this, income flattens out (the
        // wave caps its enemy count) while the tax keeps compounding.
        let wave_worth = 1.0 + 0.10 * (self.wave - 1).max(0) as f32;
        let loot_mult = if e_boss { BOSS_LOOT_MULT as f32 } else { 1.0 };
        let value = ((kind.money() as f32) * loot_mult * self.player.stats.money_mult * wave_worth)
            .round()
            .max(1.0) as i32;
        for _ in 0..drops {
            self.drop_pickup(pos, PickupKind::Money, value);
        }
    }

    pub fn drop_pickup(&mut self, pos: Vec2, kind: PickupKind, value: i32) {
        if self.pickups.len() > 600 {
            return;
        }
        let dir = Vec2::from_angle(self.rng.angle());
        self.pickups.push(Pickup {
            pos,
            vel: dir * self.rng.range(40.0, 110.0),
            kind,
            value,
            phase: self.rng.angle(),
            attracted: false,
        });
    }

    pub fn hurt_player(&mut self, amount: f32) {
        if self.debug_invuln || self.player.invuln > 0.0 || self.player.dash_t > 0.0 {
            return;
        }
        let taken = amount * (1.0 - self.player.stats.armor.clamp(0.0, 0.9));
        self.player.hp -= taken;
        self.player.invuln = 0.65;
        self.player.hurt_flash = 0.3;
        self.shake = (self.shake + 9.0).min(20.0);
        let p = self.player.pos;
        self.add_event(GC_EVT_PLAYER_HURT, p.x, p.y, taken);
        self.burst(p, 12, color::HP, 200.0, 6.0, 0.5, false);
        self.floater(p + Vec2::new(0.0, -40.0), FloaterKind::Damage(taken.round() as i32),
                     color::WARN, 22.0);
        if self.player.hp <= 0.0 {
            if self.player.stats.lives > 0 {
                // Spend a life: revive with half health and a moment of grace.
                self.player.stats.lives -= 1;
                self.player.hp = (self.player.hp_max() * 0.5).max(1.0);
                self.player.invuln = 2.4;
                self.shake = 20.0;
                let p = self.player.pos;
                self.banner = Some(Banner {
                    kind: BannerKind::Revived,
                    t: 2.2,
                    max: 2.2,
                    value: self.player.stats.lives,
                });
                self.add_event(GC_EVT_REVIVED, p.x, p.y, self.player.stats.lives as f32);
                self.burst(p, 70, color::GOLD, 340.0, 10.0, 1.1, true);
                self.burst(p, 30, color::WHITE, 220.0, 7.0, 0.8, true);
            } else {
                self.player.hp = 0.0;
                self.game_over();
            }
        }
    }

    fn game_over(&mut self) {
        self.state = State::GameOver;
        self.over_t = 0.0;
        let score = self.score();
        self.banner = Some(Banner { kind: BannerKind::GameOver, t: 3.0, max: 3.0, value: score });
        if score > self.best_score {
            self.best_score = score;
        }
        self.add_event(GC_EVT_GAME_OVER, self.player.pos.x, self.player.pos.y, score as f32);
        let p = self.player.pos;
        self.burst(p, 60, color::INK_SOFT, 320.0, 10.0, 1.0, false);
        self.burst(p, 24, color::WHITE, 240.0, 6.0, 0.7, true);
    }

    pub fn add_xp(&mut self, amount: i32) {
        let amount = ((amount as f32) * self.player.stats.xp_mult).round().max(1.0) as i32;
        self.player.xp += amount as f32;
        let mut needed = Player::xp_needed(self.player.level);
        while self.player.xp >= needed {
            self.player.xp -= needed;
            self.player.level += 1;
            self.pending_level_ups += 1;
            needed = Player::xp_needed(self.player.level);
        }
        if self.pending_level_ups > 0 && self.state == State::Playing {
            self.open_level_up();
        }
    }

    pub fn collect(&mut self, pickup: Pickup) {
        match pickup.kind {
            PickupKind::Xp => {
                self.add_xp(pickup.value);
                self.add_event(GC_EVT_PICKUP_XP, pickup.pos.x, pickup.pos.y, pickup.value as f32);
                self.floater(pickup.pos, FloaterKind::Xp(pickup.value), color::XP_BLUE, 17.0);
            }
            PickupKind::Money => {
                self.earn_money(pickup.value);
                self.add_event(GC_EVT_PICKUP_MONEY, pickup.pos.x, pickup.pos.y,
                               pickup.value as f32);
                self.floater(pickup.pos, FloaterKind::Money(pickup.value), color::MONEY_GREEN, 17.0);
            }
        }
        self.burst(pickup.pos, 4, pickup.kind.sprite_color(), 90.0, 4.0, 0.3, true);
    }

    // -- save / load --------------------------------------------------------

    /// Writes a small versioned blob.  Returns bytes written, or -1 if `out` is
    /// too small.
    pub fn save(&self, out: &mut [u8]) -> i32 {
        // 16 bytes of run data, then the settings.  Older saves simply stop
        // short, and the tail is then left at its defaults.
        if out.len() < 32 {
            return -1;
        }
        out[0..4].copy_from_slice(b"SLA1");
        out[4..8].copy_from_slice(&self.best_score.to_le_bytes());
        out[8..12].copy_from_slice(&self.seed.to_le_bytes());
        out[12..16].copy_from_slice(&GC_ABI_VERSION.to_le_bytes());
        out[16..28].copy_from_slice(&self.settings.encode());
        out[28..32].copy_from_slice(&self.market.encode());
        32
    }

    pub fn load(&mut self, data: &[u8]) -> bool {
        if data.len() < 16 || &data[0..4] != b"SLA1" {
            return false;
        }
        let best = i32::from_le_bytes([data[4], data[5], data[6], data[7]]);
        if (0..1_000_000_000).contains(&best) {
            self.best_score = best;
        }
        // Settings and the Market live in the tail; a short (older) blob keeps
        // the defaults, which is also what makes the format forward compatible.
        if data.len() >= 28 {
            self.settings = Settings::decode(&data[16..28]);
        }
        if data.len() >= 32 {
            self.market = crate::market::Market::decode(&data[28..32]);
            // Levels are stored, not their effects: re-apply them so a loaded
            // run has the income it was saved with.
            let mut stats = self.player.stats.clone();
            self.market.reapply_all(&mut stats);
            self.player.stats = stats;
            self.goal = self.goal_now();
        }
        true
    }

    pub fn status(&self) -> gc_status {
        gc_status {
            wave: self.wave,
            level: self.player.level,
            kills: self.player.kills,
            money: self.player.money,
            score: self.score(),
            best_score: self.best_score,
            state: self.state.to_ffi(),
            player_hp: self.player.hp,
            player_hp_max: self.player.hp_max(),
            time_alive: self.time,
        }
    }

    // -- debug hooks --------------------------------------------------------

    pub fn debug(&mut self, cmd: i32, value: f32) {
        match cmd {
            GC_DBG_GIVE_MONEY => self.earn_money(value as i32),
            GC_DBG_ADD_EARNED => self.money_earned += value as i32,
            GC_DBG_SET_WAVE => {
                self.wave = (value as i32).max(1);
                self.start_wave();
            }
            GC_DBG_SKIP_WAVE => {
                self.enemies.clear();
                self.projectiles.clear();
                self.spawn_left = 0;
                self.pickups.clear();
            }
            GC_DBG_LEVEL_UP => {
                self.player.level += 1;
                self.pending_level_ups += 1;
                self.open_level_up();
            }
            GC_DBG_KILL_PLAYER => {
                let hp = self.player.hp;
                self.player.hp = 0.0;
                self.player.invuln = 0.0;
                self.debug_invuln = false;
                let _ = hp;
                self.game_over();
            }
            GC_DBG_SPAWN_ENEMY => {
                // A few of one kind, spread around the player: the screenshot
                // driver has no other way to summon a specific specialist.
                if let Some(kind) = crate::entities::kind_from_index(value as i32) {
                    let base = self.player.pos;
                    for k in 0..3 {
                        let angle = self.rng.angle();
                        let at = base + Vec2::from_angle(angle) * (170.0 + 60.0 * k as f32);
                        let hp = kind.hp_at(self.wave);
                        self.next_id += 1;
                        self.enemies.push(crate::entities::Enemy {
                            id: self.next_id,
                            kind,
                            pos: Vec2::new(at.x.clamp(20.0, ARENA_W - 20.0),
                                           at.y.clamp(20.0, ARENA_H - 20.0)),
                            vel: Vec2::ZERO,
                            hp,
                            hp_max: hp,
                            radius: kind.radius(),
                            spawn_t: 0.0,
                            hurt_flash: 0.0,
                            knock: Vec2::ZERO,
                            slow_t: 0.0,
                            bob_phase: self.rng.angle(),
                            attack_cd: 0.0,
                            dash_cd: 0.0,
                            state_t: if kind.is_charger() { k as f32 * 0.9 } else { 0.0 },
                            shoot_cd: if crate::entities::is_thrower(kind) { 0.3 + k as f32 * 0.5 } else { 0.0 },
                            siphon: 0.0,
                            stolen: 0,
                            leak_cd: 0.0,
                            boss: false,
                            growth_bonus: 0.0,
                        });
                    }
                }
            }
            GC_DBG_GRANT_PERK => {
                // Grants the next tier of a family: a cheap way for the tests
                // and the screenshot driver to fill out the tree.
                let family = value as usize;
                if family < tree::FAMILIES.len() {
                    let tier = self.tree.tiers(family) + 1;
                    if tier <= tree::TIERS {
                        self.grant_node(tree::node_id(family, tier));
                    }
                }
            }
            GC_DBG_GIVE_WEAPON => {
                if let Some(kind) = weapon_from_index(value as i32) {
                    self.player.weapon_mut(kind).owned = true;
                }
            }
            GC_DBG_INVULNERABLE => self.debug_invuln = value != 0.0,
            GC_DBG_SET_TIME => self.time = value,
            _ => {}
        }
    }

    // -- main step ----------------------------------------------------------

    /// One fixed simulation step.
    pub fn step(&mut self, view: &View, input: &InputState, dt: f32, snap_camera: bool) {
        // NOTE: events are cleared once per gc_update() by the caller, not here,
        // so events from every fixed step in a frame reach the renderer.
        self.handle_input(view, input);
        if self.state == State::GameOver {
            self.over_t += dt;
        }
        match self.state {
            State::Title | State::GameOver => {}
            State::Playing => {
                self.time += dt;
                crate::systems::simulate(self, view, input, dt);
            }
            State::LevelUp | State::Shop | State::Paused => {}
        }
        self.update_ambient(view, dt);
        if self.state != State::Paused {
            crate::systems::update_effects(self, dt);
            crate::systems::update_camera(self, view, dt, snap_camera);
        }
        self.prev_pointer_down = input.pointer_down;
        self.prev_buttons = input.buttons;
    }

    /// Keeps the ambient particle field alive around the camera, themed by the
    /// wave.  Runs in every state, so menus sit inside a living backdrop.
    pub fn update_ambient(&mut self, view: &View, dt: f32) {
        self.backdrop.update(self.wave, dt);
        self.decor.update(dt, self.backdrop.theme_index());
        // Leave headroom for combat effects.
        if self.particles.len() > MAX_PARTICLES / 2 {
            return;
        }
        let palette = self.backdrop.palette();
        let half = Vec2::new(
            view.virt_w * 0.5 / self.zoom.max(0.01) + 40.0,
            view.virt_h * 0.5 / self.zoom.max(0.01) + 40.0,
        );
        let budget = self.backdrop.take_ambient_budget(dt, palette.ambient.rate);
        for _ in 0..budget {
            let p = spawn_ambient(&palette, self.camera, half, &mut self.rng);
            self.particles.push(p);
        }
    }

    /// The options overlay only makes sense over a screen that is not a fight.
    pub fn options_available(&self) -> bool {
        matches!(self.state, State::Title | State::Paused)
    }

    /// Rows of the options screen, and how a click on one is interpreted.
    ///
    /// Returns true when the options screen consumed the input, so the state
    /// underneath never sees it.
    fn handle_options(&mut self, layout: &crate::ui::UiLayout, input: &InputState) -> bool {
        if !self.options_open {
            self.options_drag = None;
            return false;
        }
        let clicked = input.pointer_down && !self.prev_pointer_down;
        let rows = crate::settings::rows();

        if clicked || input.pointer_down {
            for i in 0..SETTING_ROWS {
                let Some(rect) = layout.option_row(i) else { continue };
                if !rect.contains(input.aim) {
                    continue;
                }
                self.options_row = i;
                if clicked {
                    if i == ROW_BACK {
                        self.options_open = false;
                        self.add_event(GC_EVT_UI_CLICK, input.aim.x, input.aim.y, 0.0);
                    } else if i == ROW_RESET {
                        self.settings = Settings::default();
                        self.add_event(GC_EVT_UI_CLICK, input.aim.x, input.aim.y, 1.0);
                    } else {
                        // A click anywhere on a value row steps it, and the
                        // right-hand third steps back, so a slider is usable
                        // with nothing but taps.
                        let third = rect.x + rect.w * 0.66;
                        let dir = if input.aim.x >= third { -1 } else { 1 };
                        match rows[i].kind {
                            crate::settings::RowKind::Slider(_) => {
                                let track_x = rect.x + rect.w * 0.45;
                                let track_w = rect.w * 0.5;
                                let f = (input.aim.x - track_x) / track_w;
                                if (0.0..=1.0).contains(&f) {
                                    self.settings.set_fraction(i, f);
                                } else {
                                    self.settings.adjust(i, dir);
                                }
                            }
                            _ => self.settings.adjust(i, 1),
                        }
                        self.add_event(GC_EVT_UI_CLICK, input.aim.x, input.aim.y, 2.0);
                    }
                }
                if matches!(rows[i].kind, crate::settings::RowKind::Slider(_))
                    && input.pointer_down
                {
                    self.options_drag = Some(i);
                }
                break;
            }
        }

        // Dragging a slider keeps following the pointer.
        if input.pointer_down {
            if let Some(i) = self.options_drag {
                if let Some(rect) = layout.option_row(i) {
                    let track_x = rect.x + rect.w * 0.45;
                    let track_w = rect.w * 0.5;
                    self.settings.set_fraction(i, (input.aim.x - track_x) / track_w);
                }
            }
        } else {
            self.options_drag = None;
        }
        true
    }

    /// Market overlay input.  Returns true when it consumed the input.
    fn handle_market(&mut self, layout: &crate::ui::UiLayout, input: &InputState) -> bool {
        if !self.market_open {
            return false;
        }
        let clicked = input.pointer_down && !self.prev_pointer_down;
        for i in 0..crate::market::ITEMS {
            let Some(rect) = layout.market_row_rect(i) else { continue };
            if rect.contains(input.aim) {
                self.market_row = i;
                if clicked {
                    self.buy_market(i);
                }
                // Swallow everything else: the Hive must not pan or buy behind
                // the panel.
                return true;
            }
        }
        if clicked {
            if layout.market_close.contains(input.aim) {
                self.market_open = false;
            }
            return true;
        }
        true
    }

    fn handle_input(&mut self, view: &View, input: &InputState) {
        let clicked = input.pointer_down && !self.prev_pointer_down;
        self.pointer = input.aim;
        self.pointer_active = input.pointer_active;
        let pause_pressed = input.pause
            || ((input.buttons & GC_BTN_PAUSE) != 0
                && (self.prev_buttons & GC_BTN_PAUSE) == 0);
        let restart_pressed = input.restart
            || ((input.buttons & GC_BTN_RESTART) != 0
                && (self.prev_buttons & GC_BTN_RESTART) == 0);

        // Leaving a state that can host an overlay closes it, so a run that
        // resumes never has a menu stuck over it.
        if self.options_open && !self.options_available() {
            self.options_open = false;
        }
        if self.market_open && self.state != State::Shop {
            self.market_open = false;
        }
        if pause_pressed {
            self.state = match self.state {
                State::Playing => State::Paused,
                State::Paused => State::Playing,
                other => other,
            };
        }

        let layout = crate::ui::UiLayout::compute(view, self);
        if self.handle_options(&layout, input) {
            return;
        }
        if self.state == State::Shop && self.handle_market(&layout, input) {
            return;
        }

        match self.state {
            State::Title => {
                if clicked && layout.options_button.contains(input.aim) {
                    self.options_open = true;
                    self.options_row = 0;
                } else if clicked || input.confirm {
                    self.start_run();
                } else if layout.start_button.contains(input.aim) && input.confirm {
                    self.start_run();
                }
            }
            State::LevelUp => {
                if clicked {
                    for i in 0..layout.slot_count {
                        if layout.slot(i).contains(input.aim) {
                            let perk = self.cards[i];
                            self.apply_perk(perk);
                            self.cards_shown = 0;
                            self.add_event(GC_EVT_UI_CLICK, input.aim.x, input.aim.y, i as f32);
                            if self.pending_level_ups > 0 {
                                self.open_level_up();
                            } else {
                                self.state = State::Playing;
                            }
                            break;
                        }
                    }
                }
            }
            State::Shop => {
                // The hive is bigger than the screen: tabs pick a branch, a drag
                // pans, and a tap buys.  Buying happens on *release* so a pan
                // never spends money.
                // When the hive opens, jump the view to the frontier so the
                // player is never dropped into an empty corner of the tree.
                if self.tree.center_requested {
                    self.tree.center_requested = false;
                    if let Some(t) = layout.tree {
                        let target = if self.tree_tiers_owned() == 0 {
                            Some(tree::ROOT)
                        } else {
                            self.next_node_to_buy()
                        };
                        if let Some(target) = target {
                            if let Some(rect) = t.node_rect(target) {
                                let focus = Vec2::new(t.origin.x + t.width * 0.5,
                                                      t.origin.y + t.height * 0.5);
                                self.tree.pan = t.clamp_pan(self.tree.pan + rect.center() - focus);
                            }
                        }
                    }
                }

                let mut consumed = false;
                if clicked {
                    if layout.market_button.contains(input.aim) {
                        self.market_open = true;
                        self.market_row = 0;
                        consumed = true;
                    }
                    if layout.next_button.contains(input.aim) {
                        self.add_event(GC_EVT_UI_CLICK, input.aim.x, input.aim.y, 99.0);
                        self.wave += 1;
                        self.start_wave();
                        consumed = true;
                    }
                }

                if !consumed && input.pointer_active {
                    if input.pointer_down {
                        if !self.tree.dragging {
                            self.tree.dragging = true;
                            self.tree.press_at = input.aim;
                            self.tree.press_pan = self.tree.pan;
                            self.tree.press_node =
                                layout.tree.and_then(|t| t.node_at(input.aim));
                        } else {
                            let delta = input.aim - self.tree.press_at;
                            if delta.length() > 8.0 {
                                if let Some(t) = layout.tree {
                                    self.tree.pan = t.clamp_pan(self.tree.press_pan - delta);
                                }
                            }
                        }
                    } else if self.tree.dragging {
                        self.tree.dragging = false;
                        let moved = (input.aim - self.tree.press_at).length();
                        if moved < 12.0 {
                            if let Some(node) = self.tree.press_node.take() {
                                self.buy_node(node);
                            }
                        }
                        self.tree.press_node = None;
                    }
                }
            }
            State::Paused => {
                if clicked && layout.options_button.contains(input.aim) {
                    self.options_open = true;
                    self.options_row = 0;
                } else if layout.start_button.contains(input.aim) && (clicked || input.confirm) {
                    self.state = State::Playing;
                }
            }
            State::GameOver => {
                // A short lockout stops the death frame from also being the
                // restart tap (players usually mash fire/dash).
                if self.over_t > 0.8 && (restart_pressed || input.confirm || clicked) {
                    self.start_run();
                }
            }
            State::Playing => {}
        }
    }

    /// Latest pointer position in virtual units (hover feedback).
    pub fn pointer_pos(&self) -> Vec2 {
        self.pointer
    }

    pub fn pointer_active(&self) -> bool {
        self.pointer_active
    }

    /// Clickable UI rectangles for the current state, recomputed on demand so
    /// shells (and the automated tests) can query them without a render pass.
    pub fn ui_slot(&self, view: &View, index: usize) -> Rect {
        let layout = crate::ui::UiLayout::compute(view, self);
        layout.slot(index)
    }

    pub fn ui_button(&self, view: &View, which: i32) -> Rect {
        let layout = crate::ui::UiLayout::compute(view, self);
        match which {
            0 => layout.start_button,
            1 => layout.next_button,
            2 => layout.pause_button,
            3 => layout.prev_button,
            4 => layout.next_page_button,
            // 5 is the options button on the title and pause screens.
            5 => layout.options_button,
            // 6 opens the Market from the Hive; 50.. sell its four items, and
            // 54 closes it.
            6 => layout.market_button,
            50..=60 => layout.market_row_rect((which - 50) as usize).unwrap_or_default(),
            61 => layout.market_close,
            // 20.. give every row of the open options screen.
            20..=40 => layout
                .option_row((which - 20) as usize)
                .unwrap_or_default(),
            _ => Rect::default(),
        }
    }

    /// Number of clickable slots in the current state.
    pub fn ui_slot_count(&self, view: &View) -> usize {
        crate::ui::UiLayout::compute(view, self).slot_count
    }
}

/// Every fifth wave is a boss wave.
pub const BOSS_EVERY: i32 = 5;
/// How much more health and size the boss gets over its kind.
pub const BOSS_HP_MULT: f32 = 16.0;
pub const BOSS_SIZE_MULT: f32 = 3.1;
/// How much harder it hits, and how much more it is worth.
pub const BOSS_DAMAGE_MULT: f32 = 2.4;
pub const BOSS_LOOT_MULT: i32 = 26;

pub fn is_boss_wave(wave: i32) -> bool {
    wave > 0 && wave % BOSS_EVERY == 0
}

/// Bosses cycle through the kinds, so each boss wave teaches its escort's tells
/// before turning them up to eleven.
pub fn boss_kind_for_wave(wave: i32) -> EnemyKind {
    // Straight from the catalogue: anything marked `boss_ok`, in table order,
    // and gated so a boss cannot arrive before its kind is unlocked.
    let step = (wave / BOSS_EVERY - 1).max(0);
    let candidates: Vec<EnemyKind> = crate::entities::ALL_KINDS
        .iter()
        .copied()
        .filter(|k| k.def().boss_ok && k.def().min_wave <= wave)
        .collect();
    if candidates.is_empty() {
        return EnemyKind::Grunt;
    }
    candidates[step as usize % candidates.len()]
}

fn kind_index(kind: EnemyKind) -> i32 {
    crate::entities::ALL_KINDS.iter().position(|k| *k == kind).unwrap_or(0) as i32
}

/// Waves between quota checkpoints.
pub const GOAL_WAVE_STEP: i32 = 10;
/// The quota is a *tax*: it escalates hard, and the only way to keep paying it
/// is to invest in the economy (Greed, Interest, Bounty, Scavenger) rather than
/// pure damage.  Tuning knob, right here.
const GOAL_BASE: f64 = 750.0;
/// Written as the ratio it is: $750 at wave 10, $7 000 at wave 20, and the same
/// step every checkpoint after that.
const GOAL_GROWTH: f64 = 7000.0 / 750.0;

/// The money quota for checkpoint `tier`:
///
/// | wave | tax |
/// |------|-----|
/// | 10 | $750 |
/// | 20 | $7 000 |
/// | 30 | $65 333 |
/// | 40 | $609 778 |
/// | 50 | $5 691 259 |
/// | 60 | $53 118 415 |
/// | 70 | clamped to $2B |
///
/// A ~x9.3 step every ten waves.  Income has to grow about 25% *per wave* to
/// keep pace, which only a compounding economy (Interest on a hoarded purse,
/// plus the wave-scaled coin value and bounty) can do -- see the note in the
/// README.  Runs are expected to end somewhere in the 30s or 40s.
///
/// Calibrated against what a maxed economy can actually *earn*.  An earlier
/// x4.5 curve looked fine on paper and was impossible in practice: income is
/// bounded (the wave caps out at 150 enemies and a coin used to be worth the
/// same at wave 50 as at wave 1) while the tax compounded every checkpoint, so
/// a run that bought every money upgrade still failed at wave 50.  x3.0 keeps
/// it genuinely exponential -- each checkpoint is a bigger jump than the last --
/// while staying inside reach of coin scaling, the wave bounty and Interest.
pub fn goal_for_tier(tier: i32) -> i32 {
    let t = tier.clamp(0, 20) as f64;
    let raw = GOAL_BASE * GOAL_GROWTH.powf(t);
    raw.min(2.0e9).round() as i32
}

/// Composition of a wave: (grunts, brutes, colossi).
///
/// Deliberately denser than the first version -- the arena is meant to feel
/// busy, and the colossi are the risk/reward spice from wave 5 onwards.
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_tax_is_exponential_and_never_decreases() {
        let mut prev = 0;
        for tier in 0..12 {
            let g = goal_for_tier(tier);
            assert!(g >= prev, "tier {} lowered the tax ({} -> {})", tier, prev, g);
            // Strictly increasing until it reaches the i32 ceiling, after which
            // it parks there rather than wrapping around.
            if prev > 0 && prev < 2_000_000_000 {
                assert!(g > prev, "tier {} did not raise the tax ({} -> {})", tier, prev, g);
            }
            prev = g;
        }
        // Really exponential: each step is a bigger *ratio* than the last, i.e.
        // the curve bends upwards rather than flattening into a line.
        // The two anchors the curve is defined by.
        assert_eq!(goal_for_tier(0), 750, "wave 10 must ask for 750");
        assert_eq!(goal_for_tier(1), 7_000, "wave 20 must ask for 7000");
        // Every step is the same ratio, and it is a big one.
        let ratios: Vec<f64> = (0..5)
            .map(|t| goal_for_tier(t + 1) as f64 / goal_for_tier(t) as f64)
            .collect();
        for r in &ratios {
            assert!(*r > 9.0 && *r < 9.7, "ratio {} is not ~9.33", r);
        }
        assert!(goal_for_tier(2) > 60_000);
        assert!(goal_for_tier(3) > 600_000);
        assert!(goal_for_tier(4) > 5_000_000);
    }

    #[test]
    fn every_fifth_wave_is_a_boss_wave() {
        assert!(!is_boss_wave(1));
        assert!(!is_boss_wave(4));
        assert!(is_boss_wave(5));
        assert!(is_boss_wave(10));
        assert!(is_boss_wave(50));
        // A boss is always something the catalogue marks as boss-worthy and
        // that has actually unlocked by then -- never an early-game grunt wave
        // bossing a wave 40 run, and never a kind that does not exist yet.
        for wave in (BOSS_EVERY..=120).step_by(BOSS_EVERY as usize) {
            let kind = boss_kind_for_wave(wave);
            let def = kind.def();
            assert!(def.boss_ok, "{} is not a boss candidate (wave {})", def.name, wave);
            assert!(def.min_wave <= wave, "{} unlocked after wave {}", def.name, wave);
        }
        // And the rotation spreads: a long run sees several different bosses.
        let mut seen: Vec<EnemyKind> = Vec::new();
        for wave in (BOSS_EVERY..=120).step_by(BOSS_EVERY as usize) {
            let k = boss_kind_for_wave(wave);
            if !seen.contains(&k) {
                seen.push(k);
            }
        }
        assert!(seen.len() >= 4, "only {} distinct bosses in 24 boss waves", seen.len());
    }

    #[test]
    fn a_boss_wave_spawns_one_boss_and_an_escort_of_its_own_kind() {
        let mut w = World::new(3, 0);
        w.start_run();
        w.wave = 10; // a boss wave
        w.start_wave();
        assert!(w.boss_wave);
        let bosses: Vec<&crate::entities::Enemy> = w.enemies.iter().filter(|e| e.boss).collect();
        assert_eq!(bosses.len(), 1, "a boss wave must have exactly one boss");
        let boss = bosses[0];
        assert_eq!(boss.kind, w.boss_kind);
        // It is enormous next to its own kind.
        assert!(boss.radius > boss.kind.radius() * 2.5, "the boss is not big enough");
        assert!(boss.hp_max > boss.kind.hp_at(10) * 10.0, "the boss is not tough enough");
        // And the escort is all the same kind, with no mixed bag.
        assert!(w.spawn_left > 0, "a boss wave with no escort");
        for _ in 0..200 {
            assert_eq!(crate::systems::choose_kind_for_test(&mut w), w.boss_kind,
                       "the escort is not all one kind");
        }
    }

    #[test]
    fn a_normal_wave_has_no_boss() {
        let mut w = World::new(3, 0);
        w.start_run();
        w.wave = 7;
        w.start_wave();
        assert!(!w.boss_wave);
        assert!(w.enemies.is_empty(), "a normal wave spawns nothing up front");
        assert_eq!(w.boss_id, 0);
    }

    #[test]
    fn a_tax_rebate_lowers_the_tax_that_is_actually_due() {
        let mut w = World::new(1, 0);
        w.start_run();
        w.tier = 4; // wave 50, where the curve bites
        let full = goal_for_tier(4);
        assert_eq!(w.goal_now(), full, "with no rebates the tax must be the full ask");

        // Buy one rebate directly (bypassing the price, which is the Market's
        // business, not this test's).
        w.market.levels[3] = 3;
        let discounted = w.goal_now();
        assert!(discounted < full, "the rebate did nothing");
        assert!(discounted as f64 > full as f64 * 0.85,
                "three rebates should not halve the tax");
        // And the floor holds however many are bought.
        w.market.levels[3] = 250;
        let floored = w.goal_now();
        assert!(floored >= (full as f64 * 0.39) as i32, "the floor leaked");
    }

    #[test]
    fn the_tax_never_overflows_a_32_bit_purse() {
        for tier in 0..64 {
            let g = goal_for_tier(tier);
            assert!(g > 0, "tier {} wrapped around to {}", tier, g);
            assert!(g <= 2_000_000_000);
        }
    }
}

pub fn wave_plan(wave: i32) -> (i32, i32, i32) {
    let grunts = 8 + wave * 3;
    let brutes = if wave >= 3 { (wave - 1) / 2 } else { 0 };
    let colossi = if wave >= 5 { 1 + (wave - 5) / 4 } else { 0 };
    (grunts.min(150), brutes.min(40), colossi.min(10))
}

pub fn weapon_from_index(i: i32) -> Option<WeaponKind> {
    match i {
        0 => Some(WeaponKind::Gun),
        1 => Some(WeaponKind::Bow),
        2 => Some(WeaponKind::Sword),
        _ => None,
    }
}

/// Camera position for the current view, clamped so the arena never shows void.
pub fn camera_target(player_pos: Vec2, view: &View, zoom: f32) -> Vec2 {
    let half_w = view.virt_w * 0.5 / zoom.max(0.01);
    let half_h = view.virt_h * 0.5 / zoom.max(0.01);
    let mut target = player_pos;
    target.x = if ARENA_W > half_w * 2.0 {
        clamp(target.x, half_w, ARENA_W - half_w)
    } else {
        ARENA_W * 0.5
    };
    target.y = if ARENA_H > half_h * 2.0 {
        clamp(target.y, half_h, ARENA_H - half_h)
    } else {
        ARENA_H * 0.5
    };
    target
}

/// Draws the arena floor, grid and border (world space).
pub fn draw_arena(r: &mut Renderer, palette: &crate::backdrop::Palette, time: f32) {
    use crate::render::fade;
    r.rect(Rect::new(-40.0, -40.0, r.view.virt_w + 80.0, r.view.virt_h + 80.0),
           palette.deep, 0);
    r.rect_world(Vec2::new(ARENA_W * 0.5, ARENA_H * 0.5), ARENA_W, ARENA_H, 0.0,
                 palette.floor, 0);

    let step = 120.0;
    let zoom = r.zoom.max(0.01);
    let half = Vec2::new(r.view.virt_w * 0.5 / zoom, r.view.virt_h * 0.5 / zoom);
    let min = Vec2::new((r.camera.x - half.x).max(0.0), (r.camera.y - half.y).max(0.0));
    let max = Vec2::new((r.camera.x + half.x).min(ARENA_W), (r.camera.y + half.y).min(ARENA_H));

    let mut x = (min.x / step).floor() * step;
    while x <= max.x {
        let p = r.world_to_screen(Vec2::new(x, (min.y + max.y) * 0.5));
        r.rect_screen(p, 1.0, (max.y - min.y) * zoom, 0.0, palette.grid, 0);
        x += step;
    }
    let mut y = (min.y / step).floor() * step;
    while y <= max.y {
        let p = r.world_to_screen(Vec2::new((min.x + max.x) * 0.5, y));
        r.rect_screen(p, (max.x - min.x) * zoom, 1.0, 0.0, palette.grid, 0);
        y += step;
    }

    // A coarser overlay grid: gives the floor slabs and a sense of distance.
    let big = step * 4.0;
    let strong = crate::render::mix_colour(palette.grid, palette.edge, 0.35);
    let mut x = (min.x / big).floor() * big;
    while x <= max.x {
        let p = r.world_to_screen(Vec2::new(x, (min.y + max.y) * 0.5));
        r.rect_screen(p, 2.0, (max.y - min.y) * zoom, 0.0, strong, 0);
        x += big;
    }
    let mut y = (min.y / big).floor() * big;
    while y <= max.y {
        let p = r.world_to_screen(Vec2::new((min.x + max.x) * 0.5, y));
        r.rect_screen(p, (max.x - min.x) * zoom, 2.0, 0.0, strong, 0);
        y += big;
    }

    // Border: a solid wall plus a slow accent pulse so the arena breathes.
    let t = 6.0;
    let pulse = 0.10 + 0.10 * (time * 1.1).sin().abs();
    r.rect_world(Vec2::new(ARENA_W * 0.5, t * 0.5), ARENA_W, t, 0.0, palette.edge, 0);
    r.rect_world(Vec2::new(ARENA_W * 0.5, ARENA_H - t * 0.5), ARENA_W, t, 0.0, palette.edge, 0);
    r.rect_world(Vec2::new(t * 0.5, ARENA_H * 0.5), t, ARENA_H, 0.0, palette.edge, 0);
    r.rect_world(Vec2::new(ARENA_W - t * 0.5, ARENA_H * 0.5), t, ARENA_H, 0.0, palette.edge, 0);
    let glow = fade(palette.accent, pulse);
    r.rect_world(Vec2::new(ARENA_W * 0.5, t), ARENA_W, t, 0.0, glow, GC_FLAG_FLASH);
    r.rect_world(Vec2::new(ARENA_W * 0.5, ARENA_H - t), ARENA_W, t, 0.0, glow, GC_FLAG_FLASH);
    r.rect_world(Vec2::new(t, ARENA_H * 0.5), t, ARENA_H, 0.0, glow, GC_FLAG_FLASH);
    r.rect_world(Vec2::new(ARENA_W - t, ARENA_H * 0.5), t, ARENA_H, 0.0, glow, GC_FLAG_FLASH);
}

pub fn hp_fraction(player: &Player) -> f32 {
    if player.hp_max() <= 0.0 {
        0.0
    } else {
        clamp(player.hp / player.hp_max(), 0.0, 1.0)
    }
}

pub fn xp_fraction(player: &Player) -> f32 {
    let need = Player::xp_needed(player.level);
    if need <= 0.0 {
        0.0
    } else {
        clamp(player.xp / need, 0.0, 1.0)
    }
}

/// Radius of the materialise telegraph ring while an enemy spawns.
pub fn spawn_ring_radius(e: &Enemy) -> f32 {
    let t = 1.0 - (e.spawn_t / SPAWN_TIME).clamp(0.0, 1.0);
    e.radius * (0.6 + 1.9 * t)
}
