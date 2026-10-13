//! The Market: repeatable economy upgrades, sold in the Hive between waves.
//!
//! The upgrade *tree* is finite (313 nodes), and the tax is not: by wave 50 it
//! asks for millions.  Once the tree is bought out there is nothing left to
//! spend money on, and nothing that lets income grow fast enough to matter.
//!
//! The Market fills that hole.  Its four items have no level cap and their
//! prices grow geometrically, so they stay a real decision at every point in a
//! run while giving money somewhere to go that *multiplies money*.  Compound
//! Interest is the important one: the tax compounds at ~1.25x per wave, and
//! Interest is the only income source that can keep up, because it pays a cut of
//! the whole purse every wave rather than a cut of the enemies you kill.

use crate::entities::Stats;

/// How many items the Market sells.
pub const ITEMS: usize = 4;

/// What buying a level does.
#[derive(Copy, Clone, PartialEq, Eq, Debug)]
pub enum Effect {
    /// Interest paid on the purse at the end of every wave.
    Interest,
    /// Value of every coin an enemy drops.
    CoinValue,
    /// The wave-cleared bounty.
    Bounty,
    /// A standing discount on every future checkpoint.
    TaxRebate,
}

pub struct Item {
    pub name: &'static str,
    pub blurb: &'static str,
    pub effect: Effect,
    /// Price of the first level.
    pub base: f64,
    /// Price multiplier per level bought.
    pub growth: f64,
    /// Effect per level.
    pub step: f32,
}

pub const MARKET: [Item; ITEMS] = [
    Item {
        name: "COMPOUND INTEREST",
        blurb: "+2% interest, paid on your whole purse every wave",
        effect: Effect::Interest,
        base: 600.0,
        growth: 1.75,
        step: 0.02,
    },
    Item {
        name: "COIN MINT",
        blurb: "+15% value on every coin an enemy drops",
        effect: Effect::CoinValue,
        base: 500.0,
        growth: 1.70,
        step: 0.15,
    },
    Item {
        name: "BOUNTY BOARD",
        blurb: "+12% wave-cleared bounty",
        effect: Effect::Bounty,
        base: 500.0,
        growth: 1.70,
        step: 0.12,
    },
    Item {
        name: "TAX REBATE",
        blurb: "-3% on every future checkpoint (never below 40%)",
        effect: Effect::TaxRebate,
        base: 1200.0,
        growth: 2.00,
        step: 0.03,
    },
];

/// The lowest the tax can be talked down to, however many rebates you buy.
pub const REBATE_FLOOR: f64 = 0.40;

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Market {
    /// Levels bought, one per item.
    pub levels: [i32; ITEMS],
}

impl Market {
    pub fn level(&self, item: usize) -> i32 {
        self.levels.get(item).copied().unwrap_or(0)
    }

    /// Price of the *next* level.  Grows geometrically, so the fifth Compound
    /// Interest costs about twice the third.
    pub fn price(&self, item: usize) -> i32 {
        let Some(def) = MARKET.get(item) else { return i32::MAX };
        let raw = def.base * def.growth.powi(self.level(item));
        raw.round().min(2.0e9) as i32
    }

    pub fn can_afford(&self, money: i32, item: usize) -> bool {
        money >= self.price(item)
    }

    /// Buys one level, spending the money and applying the effect.
    pub fn buy(&mut self, item: usize, money: &mut i32, stats: &mut Stats) -> bool {
        if item >= ITEMS {
            return false;
        }
        let price = self.price(item);
        if *money < price {
            return false;
        }
        *money -= price;
        self.levels[item] += 1;
        self.apply(item, stats);
        true
    }

    /// Applies the effect of one level of `item`.
    pub fn apply(&self, item: usize, stats: &mut Stats) {
        let Some(def) = MARKET.get(item) else { return };
        match def.effect {
            Effect::Interest => stats.interest += def.step,
            Effect::CoinValue => stats.money_mult += def.step,
            Effect::Bounty => stats.wave_bonus += def.step,
            // Read from `rebate_mult`, not from a stat.
            Effect::TaxRebate => {}
        }
    }

    /// Re-applies every level bought so far.  Used when loading a save, where
    /// the levels are restored before the stats they feed.
    pub fn reapply_all(&self, stats: &mut Stats) {
        for item in 0..ITEMS {
            let levels = self.level(item);
            for _ in 0..levels {
                self.apply(item, stats);
            }
        }
    }

    /// Multiplier applied to every future checkpoint.
    pub fn rebate_mult(&self) -> f64 {
        let bought = self.level(3).max(0); // TAX REBATE
        (0.97f64.powi(bought)).max(REBATE_FLOOR)
    }

    /// The value text for a row: level, and what the next level does.
    pub fn level_text(&self, item: usize) -> [u8; 20] {
        let mut out = [0u8; 20];
        let n = self.level(item);
        let text = if n <= 0 { "NONE".to_string() } else { format!("LV {}", n) };
        let bytes = text.as_bytes();
        let len = bytes.len().min(out.len() - 1);
        out[..len].copy_from_slice(&bytes[..len]);
        out
    }

    /// Encodes for the save blob.
    pub fn encode(&self) -> [u8; 4] {
        let mut out = [0u8; 4];
        for (i, lvl) in self.levels.iter().enumerate() {
            out[i] = (*lvl).clamp(0, 255) as u8;
        }
        out
    }

    pub fn decode(bytes: &[u8]) -> Market {
        let mut m = Market::default();
        for i in 0..ITEMS {
            if let Some(b) = bytes.get(i) {
                m.levels[i] = *b as i32;
            }
        }
        m
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prices_grow_with_every_level() {
        let mut m = Market::default();
        let mut stats = Stats::default();
        let mut money = i32::MAX;
        let mut last = 0;
        for _ in 0..8 {
            let price = m.price(0);
            assert!(price > last, "price did not rise ({} -> {})", last, price);
            last = price;
            assert!(m.buy(0, &mut money, &mut stats));
        }
        assert_eq!(m.level(0), 8);
    }

    #[test]
    fn buying_needs_the_money_and_spends_exactly_the_price() {
        let mut m = Market::default();
        let mut stats = Stats::default();
        let price = m.price(0);
        let mut money = price - 1;
        assert!(!m.buy(0, &mut money, &mut stats), "bought without the money");
        assert_eq!(m.level(0), 0);
        assert_eq!(money, price - 1, "money moved on a failed purchase");

        let mut money = price + 250;
        assert!(m.buy(0, &mut money, &mut stats));
        assert_eq!(money, 250);
        assert_eq!(m.level(0), 1);
    }

    #[test]
    fn each_item_does_what_it_says() {
        let mut stats = Stats::default();
        let interest_before = stats.interest;
        let coins_before = stats.money_mult;
        let bounty_before = stats.wave_bonus;

        let mut m = Market::default();
        m.levels = [3, 2, 4, 1];
        m.reapply_all(&mut stats);

        assert!((stats.interest - interest_before - 0.06).abs() < 1e-6);
        assert!((stats.money_mult - coins_before - 0.30).abs() < 1e-6);
        assert!((stats.wave_bonus - bounty_before - 0.48).abs() < 1e-6);
        // The rebate is not a stat: it is read when the next tax is computed.
        assert!(m.rebate_mult() < 1.0);
    }

    #[test]
    fn the_rebate_has_a_floor() {
        let mut m = Market::default();
        m.levels[3] = 0;
        assert!((m.rebate_mult() - 1.0).abs() < 1e-9);
        m.levels[3] = 10;
        assert!(m.rebate_mult() > REBATE_FLOOR);
        m.levels[3] = 200;
        assert!((m.rebate_mult() - REBATE_FLOOR).abs() < 1e-9,
                "the rebate must not go below the floor");
    }

    #[test]
    fn the_market_makes_the_late_tax_reachable() {
        // The whole point of the feature, as arithmetic: bank the purse, let
        // interest compound, and check the cumulative earnings can actually
        // cover the wave-50 checkpoint that a linear economy could not.
        use crate::world::goal_for_tier;

        let mut stats = Stats::default();
        let mut m = Market::default();
        // A plausible maxed state: the tree's interest family plus a few perks
        // and a good number of Market levels bought with late-game money.
        stats.interest = 0.48 + 0.30; // tree + level-up cards
        m.levels[0] = 12; // compound interest
        m.reapply_all(&mut stats);

        let rate = stats.interest as f64;
        assert!(rate > 0.25, "interest must beat the tax's per-wave rate");

        // Simulate: start at wave 40 with a purse, bank everything, and see if
        // the earnings by wave 50 cover tier 4.
        let mut purse = 250_000.0f64;
        let mut earned = 0.0f64;
        for wave in 40..50 {
            // Interest on the purse, plus the wave bounty, times the rebate-free
            // coin income which is small next to this.
            let interest = purse * rate;
            let bounty = (12.0 + wave as f64 * 3.0) * (1.0 + wave as f64 * 0.05)
                * stats.money_mult as f64 * stats.wave_bonus as f64;
            earned += interest + bounty;
            purse += interest + bounty;
        }
        let goal = goal_for_tier(4) as f64 * m.rebate_mult();
        assert!(earned >= goal,
                "banking still cannot pay tier 4: earned {:.0} vs goal {:.0}", earned, goal);
    }
}
