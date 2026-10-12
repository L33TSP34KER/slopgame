//! The upgrade tree.
//!
//! Every between-round upgrade is a node in a honeycomb skill tree.  Nodes are
//! generated from a compact table of *families*: each family is a chain of eight
//! tiers ("SHARPER ROUNDS I..VIII"), and tier N of a family requires tier N-1.
//! On top of those chains, keystone families require a tier in a *different*
//! family, which is what turns the hive into a tree rather than a list.
//!
//! 32 families x 8 tiers = 256 nodes, and the whole thing is data: adding a
//! family is one line, and no effect needs its own code (see `StatKind`).

use crate::math::Vec2;
use crate::render::Rect;
use crate::sprite::SpriteId;

/// How many tiers each family has.
pub const TIERS: u8 = 8;

#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum Branch {
    Combat,
    Survival,
    Mobility,
    Economy,
    Arcane,
}

impl Branch {
    /// Accent colour, so branches are readable in the hive.
    pub fn color(self) -> u32 {
        use crate::render::color;
        match self {
            Branch::Combat => color::rgb(0xff, 0x7a, 0x5c),
            Branch::Survival => color::rgb(0x7c, 0xe0, 0x8a),
            Branch::Mobility => color::rgb(0x6c, 0xd0, 0xff),
            Branch::Economy => color::rgb(0xff, 0xd1, 0x66),
            Branch::Arcane => color::rgb(0xc0, 0x8a, 0xff),
        }
    }
}

/// What a single tier of a family does.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum StatKind {
    Damage,
    Rate,
    Speed,
    MaxHp,
    Magnet,
    Crit,
    CritMult,
    Pierce,
    Arrows,
    DashCd,
    DashDamage,
    DashCharges,
    Iframes,
    Drop,
    Money,
    AutoCollect,
    Thorns,
    Regen,
    Lifesteal,
    Armor,
    Xp,
    /// Chance per kill to summon a phantom of the player.
    PhantomChance,
    /// Phantom damage.
    PhantomPower,
    /// How many phantoms can exist at once.
    PhantomCount,
    /// Chance for a shot to fire twice.
    DoubleShot,
    Interest,
    Discount,
    WaveBonus,
    WaveHeal,
    Lightning,
    LightningRadius,
    Orbitals,
    Explosive,
    ProjSize,
    MeleeDamage,
    RangedDamage,
    /// Unlocks the bow on the first tier, then levels it.
    UnlockBow,
    /// Unlocks the sword on the first tier, then levels it.
    UnlockSword,
    /// An extra revive.
    Lives,
}

#[derive(Copy, Clone, Debug)]
pub struct Family {
    pub name: &'static str,
    pub blurb: &'static str,
    pub branch: Branch,
    pub kind: StatKind,
    /// Effect added by *each* tier.
    pub per_tier: f32,
    pub cost: i32,
    pub cost_growth: f32,
    /// Weapon families show their sprite on the node.
    pub icon: Option<SpriteId>,
    /// Wave before the family appears at all.
    pub min_wave: i32,
    /// A keystone family only unlocks once another family has a given tier:
    /// (family index, tiers required).
    pub unlock: Option<(u8, u8)>,
}

const fn fam(name: &'static str, blurb: &'static str, branch: Branch, kind: StatKind,
             per_tier: f32, cost: i32, cost_growth: f32, icon: Option<SpriteId>,
             min_wave: i32, unlock: Option<(u8, u8)>) -> Family {
    Family { name, blurb, branch, kind, per_tier, cost, cost_growth, icon, min_wave, unlock }
}

// Family indices are referenced by `unlock`, so keep the order stable.
pub const FAMILIES: [Family; 39] = [
    // -- COMBAT ------------------------------------------------------------
    fam("SHARPER ROUNDS", "+18% damage", Branch::Combat, StatKind::Damage, 0.18, 26, 1.52, None, 1, None),
    fam("FAST HANDS", "+12% fire rate", Branch::Combat, StatKind::Rate, 0.12, 26, 1.52, None, 1, None),
    fam("DEEP CUT", "shots pierce +1", Branch::Combat, StatKind::Pierce, 1.0, 34, 1.58, None, 2, None),
    fam("SPLIT SHOT", "+1 arrow", Branch::Combat, StatKind::Arrows, 1.0, 40, 1.62, None, 4, None),
    fam("KEEN EYE", "+6% crit chance", Branch::Combat, StatKind::Crit, 0.06, 28, 1.52, None, 1, None),
    fam("EXECUTIONER", "+25% crit damage", Branch::Combat, StatKind::CritMult, 0.25, 44, 1.60, None, 3, Some((4, 3))),
    fam("HEAVY SLUG", "+9% shot size", Branch::Combat, StatKind::ProjSize, 0.09, 30, 1.52, None, 2, None),
    fam("SHARPER STEEL", "+20% melee damage", Branch::Combat, StatKind::MeleeDamage, 0.20, 32, 1.54, None, 2, None),
    // -- PHANTOMS: the attack branch that fights for you -------------------
    fam("PHANTOM", "+3% chance a kill summons a phantom", Branch::Combat,
        StatKind::PhantomChance, 0.03, 58, 1.66, Some(SpriteId::Player), 5, Some((3, 2))),
    fam("PHANTOM FURY", "+30% phantom damage", Branch::Combat,
        StatKind::PhantomPower, 0.30, 64, 1.62, Some(SpriteId::Player), 6, Some((35, 2))),
    fam("PHANTOM SWARM", "+1 phantom at a time", Branch::Combat,
        StatKind::PhantomCount, 1.0, 92, 1.78, Some(SpriteId::Player), 8, Some((36, 3))),
    fam("TWIN FIRE", "+9% chance to fire twice", Branch::Combat,
        StatKind::DoubleShot, 0.09, 70, 1.64, None, 6, Some((4, 4))),
    // -- SURVIVAL ----------------------------------------------------------
    fam("THICK SKIN", "+20 max HP", Branch::Survival, StatKind::MaxHp, 20.0, 24, 1.50, None, 1, None),
    fam("SECOND WIND", "+0.5 HP/s", Branch::Survival, StatKind::Regen, 0.5, 30, 1.56, None, 1, None),
    fam("PLATE", "-6% damage taken", Branch::Survival, StatKind::Armor, 0.06, 34, 1.55, None, 2, None),
    fam("LEECH", "+1.5 HP per kill", Branch::Survival, StatKind::Lifesteal, 1.5, 36, 1.56, None, 2, None),
    fam("SPITE", "+10 thorns", Branch::Survival, StatKind::Thorns, 10.0, 30, 1.55, None, 3, None),
    fam("EXTRA LIFE", "revive once", Branch::Survival, StatKind::Lives, 1.0, 120, 1.85, None, 6, Some((10, 3))),
    fam("VITALITY", "+18 HP per wave", Branch::Survival, StatKind::WaveHeal, 18.0, 46, 1.60, None, 5, Some((9, 3))),
    fam("RANGED MASTERY", "+16% ranged damage", Branch::Combat, StatKind::RangedDamage, 0.16, 30, 1.54, None, 1, None),
    // -- MOBILITY ----------------------------------------------------------
    fam("LIGHT FEET", "+8% move speed", Branch::Mobility, StatKind::Speed, 0.08, 22, 1.50, None, 1, None),
    fam("QUICK ROLL", "-12% dash cooldown", Branch::Mobility, StatKind::DashCd, 0.12, 26, 1.50, None, 1, None),
    fam("BLAZING DASH", "+22 dash damage", Branch::Mobility, StatKind::DashDamage, 22.0, 38, 1.56, None, 2, None),
    fam("TWIN DASH", "+1 dash charge", Branch::Mobility, StatKind::DashCharges, 1.0, 64, 1.70, None, 3, Some((17, 2))),
    fam("PHASE SHIFT", "+15% i-frames", Branch::Mobility, StatKind::Iframes, 0.15, 42, 1.58, None, 5, Some((19, 2))),
    // -- ECONOMY -----------------------------------------------------------
    fam("SCAVENGER", "+20% drop chance", Branch::Economy, StatKind::Drop, 0.20, 28, 1.52, None, 1, None),
    fam("GREED", "+20% money", Branch::Economy, StatKind::Money, 0.20, 30, 1.56, None, 1, None),
    fam("INTEREST", "+6% interest per wave", Branch::Economy, StatKind::Interest, 0.06, 54, 1.62, None, 4, Some((22, 3))),
    fam("HAGGLER", "-6% shop prices", Branch::Economy, StatKind::Discount, 0.06, 60, 1.60, None, 4, None),
    fam("BOUNTY", "+20% wave bonus", Branch::Economy, StatKind::WaveBonus, 0.20, 32, 1.54, None, 2, None),
    fam("MAGNETISM", "+25% pickup range", Branch::Economy, StatKind::Magnet, 0.25, 24, 1.50, None, 1, None),
    fam("MAGNETIC WALLET", "+10% auto-collect", Branch::Economy, StatKind::AutoCollect, 0.10, 40, 1.58, None, 3, Some((26, 2))),
    // -- ARCANE ------------------------------------------------------------
    fam("STORM CALLER", "lightning strikes", Branch::Arcane, StatKind::Lightning, 1.0, 70, 1.66, None, 4, None),
    fam("CHAIN LIGHTNING", "+16% blast radius", Branch::Arcane, StatKind::LightningRadius, 0.16, 62, 1.60, None, 6, Some((28, 3))),
    fam("ORBITAL BLADE", "+1 orbiting blade", Branch::Arcane, StatKind::Orbitals, 1.0, 88, 1.70, Some(SpriteId::Sword), 5, Some((7, 2))),
    fam("FRAG ROUNDS", "+35% explosion", Branch::Arcane, StatKind::Explosive, 0.35, 66, 1.62, None, 5, Some((6, 2))),
    fam("SCHOLAR", "+20% experience", Branch::Arcane, StatKind::Xp, 0.20, 44, 1.56, None, 2, None),
    // -- WEAPONS (kept last so the unlock references above stay valid) -----
    fam("BOW", "unlock, then +1 level", Branch::Combat, StatKind::UnlockBow, 1.0, 48, 1.60, Some(SpriteId::Bow), 1, None),
    fam("SWORD", "unlock, then +1 level", Branch::Combat, StatKind::UnlockSword, 1.0, 62, 1.62, Some(SpriteId::Sword), 2, None),
];

/// The single node every run starts from.  Owned from the first frame; every
/// family's first tier hangs off it, so the tree literally grows outwards.
pub const ROOT: usize = 0;

/// Total node count: the root plus 35 families x 8 tiers = 281.
pub const NODE_COUNT: usize = 1 + FAMILIES.len() * TIERS as usize;

/// Node index for (family, tier).  `tier` is 1-based.
pub const fn node_id(family: usize, tier: u8) -> usize {
    1 + family * TIERS as usize + (tier as usize - 1)
}

pub fn is_root(node: usize) -> bool {
    node == ROOT
}

/// Family index of a node.  The root reports family 0 so that callers which do
/// not special-case it still get a sane answer instead of wrapping around.
pub fn family_of(node: usize) -> usize {
    if node <= ROOT {
        0
    } else {
        (node - 1) / TIERS as usize
    }
}

/// Tier of a node.  The root reports tier 1.
pub fn tier_of(node: usize) -> u8 {
    if node <= ROOT {
        1
    } else {
        (((node - 1) % TIERS as usize) as u8) + 1
    }
}

pub fn family_opt(node: usize) -> Option<&'static Family> {
    if is_root(node) || node >= NODE_COUNT {
        None
    } else {
        Some(&FAMILIES[family_of(node)])
    }
}

pub fn family(node: usize) -> &'static Family {
    family_opt(node).unwrap_or(&FAMILIES[0])
}

/// The node that must be owned before `node` can be bought.
pub fn requires(node: usize) -> Option<usize> {
    if is_root(node) {
        return None;
    }
    let f = family_of(node);
    let t = tier_of(node);
    if t > 1 {
        // Within a chain: the tier below.
        return Some(node_id(f, t - 1));
    }
    // Tier one either hangs off the root, or -- for a keystone family -- off a
    // tier in a different chain, which is what makes this a tree.
    match FAMILIES[f].unlock {
        Some((other, tiers)) => Some(node_id(other as usize, tiers)),
        None => Some(ROOT),
    }
}

/// True when this node is the tier-one entry of a keystone family.
pub fn is_keystone(node: usize) -> bool {
    !is_root(node) && tier_of(node) == 1 && FAMILIES[family_of(node)].unlock.is_some()
}

/// The root's own text.
pub const ROOT_NAME: &'static str = "AWAKENING";
pub const ROOT_BLURB: &'static str = "the tree grows from here";

impl Family {
    /// Sprite shown on a node, or `None` when the node draws a procedural icon
    /// instead (see `ui::family_icon`).  Combat, economy and arcane families use
    /// the game's own art; the body-stat families get drawn glyphs so a column
    /// of survival nodes does not look like a row of identical faces.
    pub fn badge(self) -> Option<SpriteId> {
        if self.icon.is_some() {
            return self.icon;
        }
        match self.kind {
            StatKind::Damage | StatKind::ProjSize | StatKind::Explosive
            | StatKind::RangedDamage => Some(SpriteId::Gun),
            StatKind::Rate | StatKind::Arrows | StatKind::Pierce => Some(SpriteId::Bow),
            StatKind::MeleeDamage | StatKind::Orbitals | StatKind::Crit
            | StatKind::CritMult => Some(SpriteId::Sword),
            StatKind::Drop | StatKind::Money | StatKind::Interest | StatKind::Discount
            | StatKind::WaveBonus | StatKind::AutoCollect | StatKind::Magnet => {
                Some(SpriteId::Money)
            }
            StatKind::Xp | StatKind::LightningRadius => Some(SpriteId::Xp),
            StatKind::PhantomChance | StatKind::PhantomPower | StatKind::PhantomCount => {
                Some(SpriteId::Player)
            }
            StatKind::UnlockBow => Some(SpriteId::Bow),
            StatKind::UnlockSword => Some(SpriteId::Sword),
            // Drawn by the UI.
            StatKind::MaxHp | StatKind::Regen | StatKind::Armor | StatKind::Lifesteal
            | StatKind::Thorns | StatKind::Lives | StatKind::Speed | StatKind::DashCd
            | StatKind::DashDamage | StatKind::DashCharges | StatKind::Iframes
            | StatKind::WaveHeal | StatKind::Lightning | StatKind::DoubleShot => None,
        }
    }
}

const ROMAN: [&str; TIERS as usize] =
    ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"];

pub fn tier_label(tier: u8) -> &'static str {
    ROMAN[(tier.clamp(1, TIERS) - 1) as usize]
}

/// Cost of the *next* tier of a family, given how many tiers are owned.
pub fn cost(family_index: usize, owned_tiers: u8, wave: i32, discount: f32) -> i32 {
    let f = &FAMILIES[family_index];
    let step = f.cost_growth.powi(owned_tiers as i32);
    let wave_scale = 1.0 + 0.055 * (wave - 1) as f32;
    let raw = f.cost as f32 * step * wave_scale * (1.0 - discount.clamp(0.0, 0.75));
    (raw.round() as i32).max(1)
}

/// Formats "NAME III" into a fixed buffer (no allocation in the draw path).
pub struct NodeLabel<const N: usize> {
    buf: crate::render::Buf<N>,
}

impl<const N: usize> NodeLabel<N> {
    pub fn new(family_index: usize, tier: u8) -> NodeLabel<N> {
        use core::fmt::Write as _;
        let mut buf = crate::render::Buf::<N>::new();
        let _ = write!(buf, "{} {}", FAMILIES[family_index].name, tier_label(tier));
        NodeLabel { buf }
    }

    pub fn as_str(&self) -> &str {
        self.buf.as_str()
    }
}

// ---------------------------------------------------------------------------
// honeycomb layout
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// on-screen layout: a pannable hive
// ---------------------------------------------------------------------------

/// Maps the hive to the screen.  Both the renderer and the input handler use
/// this, so a click can never land on a different node than the one drawn.
#[derive(Copy, Clone, Debug)]
pub struct TreeLayout {
    /// Top-left of the viewport, in virtual units.
    pub origin: Vec2,
    pub width: f32,
    pub height: f32,
    pub pan: Vec2,
    pub hex_w: f32,
    pub hex_h: f32,
    pub gap: f32,
}

impl TreeLayout {
    pub fn new(origin: Vec2, width: f32, height: f32, pan: Vec2, hex_w: f32) -> TreeLayout {
        // Small cells are the point: more of the tree on screen at once means
        // less dragging between the options you are comparing.
        let hex_w = hex_w.clamp(46.0, 124.0);
        let hex_h = hex_w * 1.18;
        let gap = hex_w * 0.10;
        let mut layout = TreeLayout {
            origin,
            width,
            height,
            pan: Vec2::ZERO,
            hex_w,
            hex_h,
            gap,
        };
        layout.pan = layout.clamp_pan(pan);
        layout
    }

    pub fn x_step(&self) -> f32 {
        self.hex_w + self.gap
    }

    pub fn y_step(&self) -> f32 {
        // Rows interlock, but with small cells they need a little more air or
        // the labels of one row land on the next.
        self.hex_h * 0.84
    }

    /// Total size of the tree.
    pub fn content_size(&self) -> Vec2 {
        let rows = (FAMILIES.len() + 1) as f32;
        Vec2::new(
            (TIERS as f32 + 1.0) * self.x_step() + self.hex_w * 0.5,
            (rows - 1.0) * self.y_step() + self.hex_h,
        )
    }

    pub fn clamp_pan(&self, pan: Vec2) -> Vec2 {
        let content = self.content_size();
        let max_x = (content.x - self.width).max(0.0);
        let max_y = (content.y - self.height).max(0.0);
        Vec2::new(pan.x.clamp(0.0, max_x), pan.y.clamp(0.0, max_y))
    }

    /// Screen rectangle of a node.  The root sits on the left, halfway down;
    /// each family then runs to the right as its own chain.
    pub fn node_rect(&self, node: usize) -> Option<Rect> {
        if node >= NODE_COUNT {
            return None;
        }
        let (col, row) = self.grid(node);
        let stagger = if (row as i32) % 2 == 1 { self.x_step() * 0.5 } else { 0.0 };
        let x = self.origin.x + col * self.x_step() + stagger - self.pan.x;
        let y = self.origin.y + row * self.y_step() - self.pan.y;
        Some(Rect::new(x, y, self.hex_w, self.hex_h))
    }

    /// Grid cell of a node: (column, row).
    pub fn grid(&self, node: usize) -> (f32, f32) {
        let root_row = (FAMILIES.len() / 2) as f32;
        if is_root(node) {
            return (0.0, root_row);
        }
        let family_index = family_of(node);
        let tier = tier_of(node) as f32;
        let row = if (family_index as f32) < root_row {
            family_index as f32
        } else {
            family_index as f32 + 1.0
        };
        (tier, row)
    }

    /// True when any part of a cell could be on screen.
    ///
    /// Drawing uses this rather than a strict containment test: a node must
    /// never pop in and out while you drag, it should slide off the edge.  The
    /// bands above and below the viewport (the header and the detail strip) are
    /// painted afterwards, so they mask whatever slides under them.
    pub fn intersects_view(&self, rect: Rect) -> bool {
        let pad = rect.h.max(rect.w);
        rect.x + rect.w >= self.origin.x - pad
            && rect.x <= self.origin.x + self.width + pad
            && rect.y + rect.h >= self.origin.y - pad
            && rect.y <= self.origin.y + self.height + pad
    }

    /// True when a cell can actually be hit: its middle has to be inside the
    /// interactive area, so a tap on a half-hidden node under the header does
    /// not buy something the player cannot see.
    pub fn clickable(&self, rect: Rect) -> bool {
        self.point_in_view(rect.center())
    }

    pub fn point_in_view(&self, p: Vec2) -> bool {
        p.x >= self.origin.x
            && p.x <= self.origin.x + self.width
            && p.y >= self.origin.y
            && p.y <= self.origin.y + self.height
    }

    /// Scroll position as 0..1 for each axis, and how much of the content is
    /// visible, so a renderer can draw a scrollbar.
    pub fn scroll(&self) -> (f32, f32, f32, f32) {
        let content = self.content_size();
        let range_x = (content.x - self.width).max(0.0);
        let range_y = (content.y - self.height).max(0.0);
        let tx = if range_x > 0.0 { (self.pan.x / range_x).clamp(0.0, 1.0) } else { 0.0 };
        let ty = if range_y > 0.0 { (self.pan.y / range_y).clamp(0.0, 1.0) } else { 0.0 };
        let vis_x = (self.width / content.x).clamp(0.05, 1.0);
        let vis_y = (self.height / content.y).clamp(0.05, 1.0);
        (tx, ty, vis_x, vis_y)
    }

    /// The node under a point, if any (a real hexagon test, so the interlocking
    /// rows do not steal each other's clicks).
    pub fn node_at(&self, p: Vec2) -> Option<usize> {
        let root_row = (FAMILIES.len() / 2) as f32;
        let local_y = p.y - self.origin.y + self.pan.y;
        let approx_row = (local_y / self.y_step()).round().max(0.0);
        // The row of the root is shifted by half a cell, so check both parities.
        let mut row = approx_row - 1.0;
        while row <= approx_row + 1.0 {
            if row >= 0.0 {
                let row = row as usize;
                for node in self.nodes_in_row(row, root_row) {
                    if let Some(rect) = self.node_rect(node) {
                        if !self.intersects_view(rect) || !self.point_in_view(p) {
                            continue;
                        }
                        let c = rect.center();
                        let nx = (p.x - c.x).abs() / (rect.w * 0.5);
                        let ny = (p.y - c.y).abs() / (rect.h * 0.5);
                        if ny <= 1.0 && nx <= 1.0
                            && nx <= if ny <= 0.5 { 1.0 } else { 2.0 * (1.0 - ny) }
                        {
                            return Some(node);
                        }
                    }
                }
            }
            row += 1.0;
        }
        None
    }

    /// Nodes whose cell lives in `row`: the root row holds the root, every other
    /// row holds one family's chain.
    fn nodes_in_row(&self, row: usize, root_row: f32) -> Vec<usize> {
        if (row as f32) == root_row {
            return vec![ROOT];
        }
        let family_index = if (row as f32) < root_row { row } else { row - 1 };
        if family_index >= FAMILIES.len() {
            return Vec::new();
        }
        (1..=TIERS).map(|t| node_id(family_index, t)).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn there_are_at_least_two_hundred_nodes() {
        assert!(NODE_COUNT >= 200, "only {} nodes", NODE_COUNT);
    }

    #[test]
    fn every_nodes_prerequisite_comes_earlier_in_its_chain() {
        for node in 0..NODE_COUNT {
            if let Some(req) = requires(node) {
                assert!(req < NODE_COUNT);
                assert_ne!(req, node);
                // A prerequisite is either the tier below (same family) or a
                // tier of another family -- never something circular.
                if req == ROOT {
                    assert_eq!(tier_of(node), 1, "the root only gates entry nodes");
                } else if family_of(req) == family_of(node) {
                    assert_eq!(tier_of(req) + 1, tier_of(node));
                } else {
                    assert_eq!(tier_of(node), 1, "cross links only gate entry nodes");
                    assert!(tier_of(req) > 1);
                }
            } else {
                assert!(is_root(node), "only the root may be free-standing");
            }
        }
    }

    #[test]
    fn chains_only_end_at_the_last_tier() {
        for f in 0..FAMILIES.len() {
            for t in 2..=TIERS {
                assert!(requires(node_id(f, t)).is_some());
            }
            assert!(requires(node_id(f, TIERS)).is_some());
        }
    }

    #[test]
    fn keystones_reference_real_families() {
        for f in FAMILIES.iter() {
            if let Some((other, tiers)) = f.unlock {
                assert!((other as usize) < FAMILIES.len());
                assert!(tiers >= 1 && tiers <= TIERS);
            }
        }
        // At least a handful of cross links, or it is not a tree.
        let keystones = (0..NODE_COUNT).filter(|n| is_keystone(*n)).count();
        assert!(keystones >= 8, "only {} keystone nodes", keystones);
    }

    #[test]
    fn costs_grow_with_every_tier() {
        for f in 0..FAMILIES.len() {
            let mut prev = 0;
            for owned in 0..TIERS {
                let c = cost(f, owned, 1, 0.0);
                assert!(c > prev, "family {} tier {} did not get dearer", f, owned);
                prev = c;
            }
        }
    }

    #[test]
    fn discounts_reduce_costs_and_never_reach_zero() {
        for f in 0..FAMILIES.len() {
            let full = cost(f, 0, 1, 0.0);
            let cheap = cost(f, 0, 1, 0.5);
            assert!(cheap < full);
            assert!(cost(f, 0, 1, 5.0) >= 1, "cost must never be free or negative");
        }
    }

    #[test]
    fn every_family_hangs_off_the_root_or_a_keystone() {
        for f in 0..FAMILIES.len() {
            let entry = node_id(f, 1);
            assert!(requires(entry).is_some());
            if FAMILIES[f].unlock.is_none() {
                assert_eq!(requires(entry), Some(ROOT));
            }
        }
        assert!(requires(ROOT).is_none());
    }

    #[test]
    fn the_root_sits_on_the_trunk_row() {
        let layout = TreeLayout::new(Vec2::ZERO, 900.0, 400.0, Vec2::ZERO, 120.0);
        let (col, row) = layout.grid(ROOT);
        assert_eq!(col, 0.0);
        assert!((row - (FAMILIES.len() / 2) as f32).abs() < 0.5);
        // Every family's first tier is one column to the right of the root.
        for f in 0..FAMILIES.len() {
            let (c, _) = layout.grid(node_id(f, 1));
            assert_eq!(c, 1.0);
        }
    }

    #[test]
    fn labels_are_generated_without_overflow() {
        for f in 0..FAMILIES.len() {
            let l = NodeLabel::<40>::new(f, 8);
            assert!(l.as_str().contains(FAMILIES[f].name));
            assert!(!l.as_str().is_empty());
        }
    }

    #[test]
    fn a_click_lands_on_the_node_it_was_drawn_on() {
        // A viewport big enough to contain the whole tree, so every node is in
        // view and the click mapping can be checked without panning.
        let probe = TreeLayout::new(Vec2::ZERO, 4000.0, 8000.0, Vec2::ZERO, 120.0);
        let size = probe.content_size();
        let layout = TreeLayout::new(Vec2::ZERO, size.x + 200.0, size.y + 200.0,
                                     Vec2::ZERO, 120.0);
        for node in [ROOT, node_id(0, 1), node_id(0, 4), node_id(7, 8), node_id(34, 3)] {
            let rect = layout.node_rect(node).expect("every node has a cell");
            assert_eq!(layout.node_at(rect.center()), Some(node),
                       "click at {:?} should hit node {}", rect.center(), node);
        }

        // A cell straddling the edge is drawn but cannot be hit outside the
        // interactive area, so nothing invisible can be bought.
        // Centre left of the viewport: drawn (it overlaps the edge), but not
        // clickable, so a hidden node can never be bought.
        let edge = Rect::new(layout.origin.x - 60.0, layout.origin.y + 10.0, 60.0, 60.0);
        assert!(layout.intersects_view(edge), "edge cells must still be drawn");
        assert!(!layout.clickable(edge), "but not clickable outside the view");
        // And once it has scrolled fully clear, it stops being drawn at all.
        let gone = Rect::new(layout.origin.x - 900.0, layout.origin.y, 60.0, 60.0);
        assert!(!layout.intersects_view(gone));
    }

    #[test]
    fn panning_is_clamped_to_the_hive() {
        let layout = TreeLayout::new(Vec2::ZERO, 400.0, 200.0, Vec2::ZERO, 120.0);
        let far = layout.clamp_pan(Vec2::new(9999.0, 9999.0));
        let content = layout.content_size();
        assert!(far.x <= (content.x - 400.0) + 0.01);
        assert!(far.y <= (content.y - 200.0) + 0.01);
        let negative = layout.clamp_pan(Vec2::new(-50.0, -50.0));
        assert_eq!(negative.x, 0.0);
        assert_eq!(negative.y, 0.0);
    }

    #[test]
    fn every_family_describes_itself() {
        for f in FAMILIES.iter() {
            assert!(!f.name.is_empty());
            assert!(!f.blurb.is_empty());
            assert!(f.per_tier > 0.0);
            assert!(f.cost > 0 && f.cost_growth > 1.0);
        }
    }
}
