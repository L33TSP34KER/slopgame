//! HUD, menus and the clickable layout.
//!
//! `UiLayout::compute` is the single source of truth for where every clickable
//! element is.  The input handling in `World::handle_input` and the drawing code
//! below both consume it, so a rect can never drift away from what the player
//! sees (and the automated tests can query the same rects through the C ABI).

use crate::ffi::{GC_FLAG_NONE, GC_FLAG_SHADOW};
use crate::math::{clamp, Vec2};
use crate::render::{color, fade, Rect, Renderer, View};
use crate::sprite::SpriteId;
use crate::systems::danger_fade;
use crate::world::*;

/// Upper bound on clickable cells in one state: the honeycomb can show
/// 7 columns x 4 rows on a wide screen.
pub const MAX_SLOTS: usize = 32;

/// Font sizes derived from the view, so the HUD scales from a phone to a
/// desktop window without a second layout pass.
#[derive(Copy, Clone, Debug)]
pub struct Theme {
    pub scale: f32,
    pub h1: f32,
    pub h2: f32,
    pub h3: f32,
    pub body: f32,
    pub small: f32,
    pub tiny: f32,
}

impl Theme {
    pub fn from_view(view: &View) -> Theme {
        let content = view.content_rect();
        let scale = (content.w / 1280.0).clamp(0.55, 1.30);
        Theme {
            scale,
            h1: 56.0 * scale,
            h2: 34.0 * scale,
            h3: 25.0 * scale,
            body: 20.0 * scale,
            small: 16.0 * scale,
            tiny: 13.0 * scale,
        }
    }

    pub fn gap(&self) -> f32 {
        10.0 * self.scale
    }
}

#[derive(Clone, Debug)]
pub struct UiLayout {
    pub slots: [Rect; MAX_SLOTS],
    pub slot_count: usize,
    /// Unused by the tree; kept for the level-up card flow.
    pub prev_button: Rect,
    pub next_page_button: Rect,
    /// The hive for the between-round tree.
    pub tree: Option<crate::tree::TreeLayout>,
    /// The detail strip under the hive (shared so drawing and layout agree).
    pub strip: Rect,
    /// Opens the options screen (title and pause screens).
    pub options_button: Rect,
    /// Opens the Market from the Hive.
    pub market_button: Rect,
    /// Rows of the open Market, and its close button.
    pub market_rows: [Rect; crate::market::ITEMS],
    pub market_close: Rect,
    /// The panel the Market rows sit in.
    pub market_panel: Rect,
    /// Rows of the options screen.
    pub option_rows: [Rect; crate::settings::ROWS],
    /// The panel the rows sit in.
    pub options_panel: Rect,
    /// Big primary button: start / resume / play again.
    pub start_button: Rect,
    /// Shop's "next wave" button.
    pub next_button: Rect,
    /// Small always-visible pause button (touch friendly).
    pub pause_button: Rect,
}

impl Default for UiLayout {
    fn default() -> Self {
        UiLayout {
            slots: [Rect::default(); MAX_SLOTS],
            slot_count: 0,
            prev_button: Rect::default(),
            next_page_button: Rect::default(),
            tree: None,
            strip: Rect::default(),
            options_button: Rect::default(),
            market_button: Rect::default(),
            market_rows: [Rect::default(); crate::market::ITEMS],
            market_close: Rect::default(),
            market_panel: Rect::default(),
            option_rows: [Rect::default(); crate::settings::ROWS],
            options_panel: Rect::default(),
            start_button: Rect::default(),
            next_button: Rect::default(),
            pause_button: Rect::default(),
        }
    }
}

impl UiLayout {
    /// Screen rectangle of options row `i`, if the overlay is laid out.
    pub fn option_row(&self, i: usize) -> Option<Rect> {
        self.option_rows.get(i).copied().filter(|r| r.w > 0.0)
    }

    /// Screen rectangle of Market row `i`, if the panel is laid out.
    pub fn market_row_rect(&self, i: usize) -> Option<Rect> {
        self.market_rows.get(i).copied().filter(|r| r.w > 0.0)
    }

    pub fn slot(&self, i: usize) -> Rect {
        if i < MAX_SLOTS {
            self.slots[i]
        } else {
            Rect::default()
        }
    }

    pub fn compute(view: &View, w: &World) -> UiLayout {
        let content = view.content_rect();
        let theme = Theme::from_view(view);
        let gap = theme.gap();
        let mut layout = UiLayout::default();

        let button_h = (62.0 * theme.scale).max(46.0);
        let button_w = (content.w * 0.44).clamp(200.0, 420.0);

        // Primary button sits low-centre: start / resume / play again.
        layout.start_button = Rect::new(
            content.x + (content.w - button_w) * 0.5,
            content.y + content.h * 0.66,
            button_w,
            button_h,
        );

        // Pause button, top-right inside the safe area.
        let pb = (46.0 * theme.scale).max(34.0);
        layout.pause_button = Rect::new(
            content.x + content.w - pb - gap,
            content.y + gap,
            pb,
            pb,
        );

        // The options button hangs under the primary button on the screens that
        // offer it (title and pause).
        if matches!(w.state, State::Title | State::Paused) {
            let ow = (button_w * 0.6).max(150.0);
            layout.options_button = Rect::new(
                content.x + (content.w - ow) * 0.5,
                layout.start_button.y + button_h + gap * 1.6,
                ow,
                button_h * 0.72,
            );
        }

        // Market rows: laid out whenever the Hive is up, so the rects the
        // renderer draws are the ones input hit-tests.
        if w.state == State::Shop {
            let row_h = (theme.body * 3.0).max(30.0);
            let close_h = (30.0 * theme.scale).max(24.0);
            let panel_w = (content.w * 0.62).clamp(300.0, 640.0);
            // The header block (title + interest line) is measured first, so the
            // rows start below it rather than through it, and the panel is tall
            // enough that CLOSE sits under the last row instead of on top of it.
            let header = theme.h2 * 1.1 + theme.tiny * 1.6 + gap * 1.6;
            let panel_h = header + row_h * crate::market::ITEMS as f32 + close_h + gap * 2.6;
            let panel_x = content.x + (content.w - panel_w) * 0.5;
            let panel_y = content.y + (content.h - panel_h) * 0.5;
            layout.market_panel = Rect::new(panel_x, panel_y, panel_w, panel_h);
            let rows_top = panel_y + header;
            for i in 0..crate::market::ITEMS {
                layout.market_rows[i] = Rect::new(
                    panel_x + gap * 0.8,
                    rows_top + i as f32 * row_h,
                    panel_w - gap * 1.6,
                    row_h - gap * 0.5,
                );
            }
            layout.market_close = Rect::new(
                panel_x + (panel_w - 180.0) * 0.5,
                panel_y + panel_h - close_h - gap * 0.8,
                180.0,
                close_h,
            );
        }

        // Options rows: laid out on any screen that can open the overlay, so
        // the rects the renderer draws are the same ones input hit-tests.
        if matches!(w.state, State::Title | State::Paused) {
            let row_h = (theme.body * 2.6).max(24.0);
            let panel_w = (content.w * 0.66).clamp(300.0, 640.0);
            let panel_h = row_h * crate::settings::ROWS as f32 + gap * 3.4;
            let panel_x = content.x + (content.w - panel_w) * 0.5;
            let panel_y = content.y + (content.h - panel_h) * 0.5;
            layout.options_panel = Rect::new(panel_x, panel_y, panel_w, panel_h);
            let rows_top = panel_y + gap * 2.4;
            for i in 0..crate::settings::ROWS {
                layout.option_rows[i] = Rect::new(
                    panel_x + gap * 0.7,
                    rows_top + i as f32 * row_h,
                    panel_w - gap * 1.4,
                    row_h - gap * 0.3,
                );
            }
        }

        match w.state {
            State::LevelUp => {
                let n = 3usize;
                layout.slot_count = n;
                if content.w >= 860.0 {
                    let card_w = (content.w / 3.6).min(300.0 * theme.scale);
                    let card_h = (content.h * 0.28).clamp(120.0, 230.0 * theme.scale);
                    let total = card_w * n as f32 + gap * (n as f32 - 1.0);
                    let x0 = content.x + (content.w - total) * 0.5;
                    let y0 = content.y + content.h * 0.36;
                    for i in 0..n {
                        layout.slots[i] = Rect::new(x0 + i as f32 * (card_w + gap), y0, card_w, card_h);
                    }
                } else {
                    // Portrait phones: stack the cards.
                    let card_h = ((content.h * 0.60) / n as f32 - gap).clamp(56.0, 130.0);
                    let card_w = content.w - 2.0 * gap;
                    let total = card_h * n as f32 + gap * (n as f32 - 1.0);
                    let y0 = content.y + (content.h - total) * 0.5;
                    for i in 0..n {
                        layout.slots[i] = Rect::new(content.x + gap, y0 + i as f32 * (card_h + gap),
                                                    card_w, card_h);
                    }
                }
            }
            State::Shop => {
                // A pannable hive: 35 families x 8 tiers, one branch at a time.
                // The hive gets the lion's share of the screen: a slim header,
                // then cells from 13% down to 79%, then the strip and button.
                let top = content.y + content.h * 0.13;
                let bottom = content.y + content.h * 0.79;
                let area_h = (bottom - top).max(80.0);
                // Size the cells so the whole 9-wide tree fits across the
                // screen whenever there is room: no horizontal panning, and the
                // rows are short enough to fling through.
                let columns = crate::tree::TIERS as f32 + 1.0;
                let fit = (content.w - gap * (columns + 1.0)) / columns;
                let hex_w = fit.clamp(46.0, 112.0);
                layout.tree = Some(crate::tree::TreeLayout::new(
                    Vec2::new(content.x + gap, top),
                    (content.w - gap * 2.0).max(40.0),
                    area_h,
                    w.tree.pan,
                    hex_w,
                ));

                layout.market_button = Rect::new(
                    content.x + gap,
                    bottom + gap * 0.5 + theme.small * 3.2 + gap * 0.8,
                    (content.w * 0.22).clamp(150.0, 260.0),
                    button_h * 0.8,
                );

                layout.strip = Rect::new(
                    content.x + gap,
                    bottom + gap * 0.5,
                    content.w - gap * 2.0,
                    theme.small * 3.2,
                );

                let arrow_w = button_h;
                let row_y = layout.strip.y + layout.strip.h + gap * 0.8;
                layout.next_button = Rect::new(
                    content.x + (content.w - button_w) * 0.5,
                    row_y,
                    button_w,
                    button_h,
                );
                layout.prev_button = Rect::new(
                    layout.next_button.x - arrow_w - gap * 2.0,
                    row_y,
                    arrow_w,
                    button_h,
                );
                layout.next_page_button = Rect::new(
                    layout.next_button.x + button_w + gap * 2.0,
                    row_y,
                    arrow_w,
                    button_h,
                );
            }
            _ => {}
        }
        layout
    }
}

// ---------------------------------------------------------------------------
// HUD
// ---------------------------------------------------------------------------

pub fn draw_ui(w: &World, r: &mut Renderer) {
    let theme = Theme::from_view(&r.view);
    let layout = UiLayout::compute(&r.view, w);
    draw_hud(w, r, &theme, &layout);
    if w.state != State::Shop {
        draw_banner(w, r, &theme);
    }
    match w.state {
        State::Title => draw_title(w, r, &theme, &layout),
        State::LevelUp => draw_level_up(w, r, &theme, &layout),
        State::Shop => draw_shop(w, r, &theme, &layout),
        State::Paused => draw_paused(w, r, &theme, &layout),
        State::GameOver => draw_game_over(w, r, &theme, &layout),
        State::Playing => {}
    }

    // The options overlay sits on top of whatever screen opened it.
    if w.options_open {
        draw_options(w, r, &theme, &layout);
    }
    // And the Market sits on top of the Hive that opened it.
    if w.market_open {
        draw_market(w, r, &theme, &layout);
    }
}

/// The Market: repeatable economy upgrades, priced on a geometric curve.
fn draw_market(w: &World, r: &mut Renderer, theme: &Theme, layout: &UiLayout) {
    dim(r, 0.74);
    let panel = layout.market_panel;
    if panel.w <= 0.0 {
        return;
    }
    let gap = theme.gap();
    r.rect(panel, fade(color::PANEL, 0.97), 0);
    r.rect(Rect::new(panel.x, panel.y, panel.w, panel.h * 0.08), fade(color::WHITE, 0.05), 0);
    r.outline(panel, 2.0, fade(color::GOLD, 0.45));
    let title_y = panel.y + gap * 0.6;
    r.text_center("THE MARKET", panel.center().x, title_y, theme.h2,
                  color::GOLD, GC_FLAG_SHADOW);

    // The number that matters: what the purse pays every wave.
    let interest = crate::buf_format!(48, "INTEREST {:.0}%  -  PAID ON YOUR PURSE EVERY WAVE",
                                      w.player.stats.interest * 100.0);
    // Directly under the title, never through it.
    r.text_center(interest.as_str(), panel.center().x, title_y + theme.h2 * 1.1, theme.tiny,
                  fade(color::WHITE, 0.75), GC_FLAG_SHADOW);

    for (i, item) in crate::market::MARKET.iter().enumerate() {
        let Some(rect) = layout.market_row_rect(i) else { continue };
        let price = w.market.price(i);
        let affordable = w.market.can_afford(w.player.money, i);
        let selected = i == w.market_row;
        r.rect(rect, if selected { fade(color::GOLD, 0.14) } else { fade(color::BLACK, 0.30) }, 0);
        r.rect(Rect::new(rect.x, rect.y, rect.w, rect.h * 0.4), fade(color::WHITE, 0.04), 0);
        r.outline(rect, if selected { 2.0 } else { 1.0 },
                  if selected { color::GOLD } else { fade(color::WHITE, 0.12) });
        r.text(item.name, rect.x + gap * 0.8, rect.y + rect.h * 0.14, theme.body, 0.0,
               color::WHITE, GC_FLAG_SHADOW);
        r.text(item.blurb, rect.x + gap * 0.8, rect.y + rect.h * 0.14 + theme.body * 1.05,
               theme.tiny, 0.0, fade(color::WHITE, 0.62), GC_FLAG_SHADOW);
        // Level on the left of the price, so the two read as one column.
        let lvl = w.market.level_text(i);
        let lvl_str = market_text(&lvl);
        r.text(lvl_str, rect.x + rect.w - gap * 0.8, rect.y + rect.h * 0.16,
               theme.tiny, 1.0, fade(color::WHITE, 0.7), GC_FLAG_SHADOW);
        let price_text = crate::render::money_buf(price);
        r.text(price_text.as_str(), rect.x + rect.w - gap * 0.8,
               rect.y + rect.h * 0.16 + theme.tiny * 1.3, theme.h3, 1.0,
               if affordable { color::MONEY_GREEN } else { color::WARN }, GC_FLAG_SHADOW);
    }

    big_button(r, layout.market_close, "CLOSE", theme, true);
}

/// Reads a NUL-terminated market label.
fn market_text(bytes: &[u8]) -> &str {
    let end = bytes.iter().position(|b| *b == 0).unwrap_or(bytes.len());
    core::str::from_utf8(&bytes[..end]).unwrap_or("")
}

/// The options screen: label on the left, control on the right, one hint line.
fn draw_options(w: &World, r: &mut Renderer, theme: &Theme, layout: &UiLayout) {
    dim(r, 0.72);
    let panel = layout.options_panel;
    if panel.w <= 0.0 {
        return;
    }
    let gap = theme.gap();
    r.rect(panel, fade(color::PANEL, 0.97), 0);
    r.rect(Rect::new(panel.x, panel.y, panel.w, panel.h * 0.10), fade(color::WHITE, 0.05), 0);
    r.outline(panel, 2.0, fade(color::GOLD, 0.45));

    let title = "OPTIONS";
    r.text_center(title, panel.center().x, panel.y + gap * 0.5, theme.h2, color::GOLD,
                  GC_FLAG_SHADOW);

    let rows = crate::settings::rows();
    for i in 0..crate::settings::ROWS {
        let row = rows[i];
        let Some(rect) = layout.option_row(i) else { continue };
        let is_action = !crate::settings::Settings::is_value(i);
        let selected = i == w.options_row;
        let fill = if is_action {
            color::CARD_HOVER
        } else if selected {
            fade(color::GOLD, 0.16)
        } else {
            fade(color::BLACK, 0.30)
        };
        r.rect(rect, fill, 0);
        r.rect(Rect::new(rect.x, rect.y, rect.w, rect.h * 0.4), fade(color::WHITE, 0.04), 0);
        r.outline(rect, if selected { 2.0 } else { 1.0 },
                  if selected { color::GOLD } else { fade(color::WHITE, 0.12) });

        let label_y = rect.y + rect.h * 0.16;
        r.text(row.label, rect.x + gap * 0.8, label_y, theme.body, 0.0,
               if is_action { color::GOLD } else { color::WHITE },
               GC_FLAG_SHADOW);

        match row.kind {
            crate::settings::RowKind::Slider(_) => {
                // A track with a fill, plus +/- zones so a tap alone can adjust.
                let track_x = rect.x + rect.w * 0.45;
                let track_w = rect.w * 0.5;
                let track = Rect::new(track_x, rect.y + rect.h * 0.44, track_w,
                                      (theme.tiny * 0.55).max(6.0));
                r.rect(track, fade(color::BLACK, 0.55), 0);
                let f = w.settings.fraction(i);
                r.rect(Rect::new(track.x, track.y, track.w * f, track.h),
                       color::GOLD, 0);
                r.outline(track, 1.0, fade(color::WHITE, 0.2));
                // Knob.
                r.rect_screen(Vec2::new(track.x + track.w * f, track.center().y),
                              (theme.tiny * 0.8).max(8.0), track.h + 6.0, 0.0,
                              color::WHITE, 0);
                let value = w.settings.value_text(i);
                r.text(value_str(&value), rect.x + rect.w - gap * 0.8, label_y,
                       theme.body, 1.0, color::GOLD, GC_FLAG_SHADOW);
            }
            crate::settings::RowKind::Action => {
                r.text(">", rect.x + rect.w - gap * 0.8, rect.y + rect.h * 0.22,
                       theme.body, 1.0, color::GOLD, GC_FLAG_SHADOW);
            }
            _ => {
                let value = w.settings.value_text(i);
                let text = value_str(&value);
                let on = matches!(text, "ON" | "HIGH" | "FULL");
                let pill_w = (rect.w * 0.26).max(70.0);
                let pill = Rect::new(rect.x + rect.w - pill_w - gap * 0.6,
                                     rect.y + rect.h * 0.16, pill_w, rect.h * 0.68);
                r.rect(pill, if on { fade(color::GOLD, 0.28) } else { fade(color::BLACK, 0.5) }, 0);
                r.outline(pill, 1.0, fade(color::WHITE, 0.22));
                r.text_in(text, pill, theme.small, 0.5, if on { color::GOLD } else { fade(color::WHITE, 0.75) },
                          GC_FLAG_SHADOW);
            }
        }
    }

    // Hint for the highlighted row.
    let hint = rows.get(w.options_row).map(|r| r.hint).unwrap_or("");
    r.text_center(hint, panel.center().x, panel.y + panel.h + gap * 0.4, theme.small,
                  fade(color::WHITE, 0.7), GC_FLAG_SHADOW);
}

/// Reads a NUL-terminated settings string.
fn value_str(bytes: &[u8]) -> &str {
    let end = bytes.iter().position(|b| *b == 0).unwrap_or(bytes.len());
    core::str::from_utf8(&bytes[..end]).unwrap_or("")
}

fn draw_hud(w: &World, r: &mut Renderer, theme: &Theme, layout: &UiLayout) {
    let content = r.view.content_rect();
    let gap = theme.gap();
    let bar_w = (content.w * 0.30).clamp(150.0, 340.0);
    let bar_h = (18.0 * theme.scale).max(12.0);

    // -- health ------------------------------------------------------------
    let hp_rect = Rect::new(content.x + gap, content.y + gap, bar_w, bar_h);
    r.bar(hp_rect, hp_fraction(&w.player), color::HP_BG, color::HP, color::INK);
    if w.player.stats.lives > 0 {
        let lives = crate::buf_format!(16, "x{} UP", w.player.stats.lives);
        r.text(lives.as_str(), hp_rect.x + hp_rect.w + theme.small * 0.6, hp_rect.y,
               theme.small, 0.0, color::GOLD, GC_FLAG_SHADOW);
    }
    let hp_text = crate::buf_format!(24, "{}/{}", w.player.hp.ceil() as i32, w.player.hp_max() as i32);
    r.text(hp_text.as_str(), hp_rect.x + 6.0 * theme.scale,
           hp_rect.y - theme.tiny * 0.15, theme.small, 0.0, color::WHITE, GC_FLAG_SHADOW);

    // -- experience --------------------------------------------------------
    let xp_rect = Rect::new(hp_rect.x, hp_rect.y + bar_h + gap * 1.6, bar_w, bar_h * 0.8);
    r.bar(xp_rect, xp_fraction(&w.player), color::XP_BG, color::XP, color::INK);
    let lv_text = crate::buf_format!(16, "LV {}", w.player.level);
    r.text(lv_text.as_str(), xp_rect.x + 6.0 * theme.scale,
           xp_rect.y - theme.tiny * 0.2, theme.small, 0.0, color::WHITE, GC_FLAG_SHADOW);

    // -- the run's quota: total earned against the next checkpoint ----------
    let quota_rect = Rect::new(xp_rect.x, xp_rect.y + bar_h + gap * 1.6, bar_w, bar_h * 0.7);
    let goal = w.goal.max(1) as f32;
    let progress = (w.money_earned as f32 / goal).clamp(0.0, 1.0);
    let met = w.money_earned >= w.goal;
    r.bar(quota_rect, progress, color::XP_BG,
          if met { color::MONEY_GREEN } else { color::GOLD }, color::INK);
    let earned = crate::render::money_buf(w.money_earned);
    let goal_text = crate::render::money_buf(w.goal);
    // The last two waves before a checkpoint shout about it.
    let urgent = !met && w.wave >= w.goal_wave - 2;
    let shortfall = (w.goal - w.money_earned).max(0);
    let quota = if !met && w.wave >= w.goal_wave - 3 {
        // Close to a checkpoint: say exactly how much is still missing.
        let missing = crate::render::money_buf(shortfall);
        crate::buf_format!(64, "{} / {}   TAX DUE WAVE {}   NEED {}", earned.as_str(),
                           goal_text.as_str(), w.goal_wave, missing.as_str())
    } else {
        crate::buf_format!(64, "{} / {}   TAX DUE WAVE {}", earned.as_str(),
                           goal_text.as_str(), w.goal_wave)
    };
    r.text(quota.as_str(), quota_rect.x, quota_rect.y + quota_rect.h + theme.tiny * 0.15,
           theme.tiny, 0.0,
           if met {
               color::MONEY_GREEN
           } else if urgent {
               color::WARN
           } else {
               fade(color::WHITE, 0.8)
           },
           GC_FLAG_SHADOW);

    // -- wave / timer / kills ---------------------------------------------
    let wave_text = crate::buf_format!(24, "WAVE {}", w.wave);
    r.text(wave_text.as_str(), content.x + content.w * 0.5, content.y + gap,
           theme.h3, 0.5, color::WHITE, GC_FLAG_SHADOW);
    let alive = w.enemies.len() as i32 + w.spawn_left;
    let sub = crate::buf_format!(32, "{} LEFT", alive);
    r.text(sub.as_str(), content.x + content.w * 0.5, content.y + gap + theme.h3 * 1.15,
           theme.small, 0.5, fade(color::WHITE, 0.75), GC_FLAG_SHADOW);

    // -- boss bar ---------------------------------------------------------
    // Found live rather than tracked, so it can never drift out of sync.
    if let Some(boss) = w.enemies.iter().find(|e| e.boss) {
        let frac = (boss.hp / boss.hp_max).clamp(0.0, 1.0);
        let bw = (content.w * 0.34).clamp(220.0, 520.0);
        let bh = (10.0 * theme.scale).max(7.0);
        let bx = content.x + (content.w - bw) * 0.5;
        // Below the clock, not on top of it.
        let by = content.y + gap + theme.h3 * 1.15 + theme.small * 3.6;
        let label = crate::buf_format!(32, "BOSS");
        r.text_center(label.as_str(), content.center().x, by - theme.small * 1.25,
                      theme.small, color::HP, GC_FLAG_SHADOW);
        r.rect(Rect::new(bx, by, bw, bh), fade(color::BLACK, 0.55), 0);
        r.rect(Rect::new(bx, by, bw * frac, bh), color::HP, 0);
        r.outline(Rect::new(bx, by, bw, bh), 1.5, fade(color::WHITE, 0.35));
    }

    let mins = (w.time / 60.0).floor() as i32;
    let secs = (w.time % 60.0).floor() as i32;
    let clock = crate::buf_format!(16, "{}:{:02}", mins, secs);
    r.text(clock.as_str(), content.x + content.w * 0.5,
           content.y + gap + theme.h3 * 1.15 + theme.small * 1.3,
           theme.small, 0.5, fade(color::WHITE, 0.6), GC_FLAG_SHADOW);

    // -- money (left of the pause button) ---------------------------------
    let money = crate::render::money_buf(w.player.money);
    let money_right = layout.pause_button.x - gap;
    r.sprite_screen(SpriteId::Money,
                    Vec2::new(money_right - 70.0 * theme.scale, content.y + gap + bar_h * 0.5),
                    22.0 * theme.scale, 0.0, color::WHITE, GC_FLAG_NONE);
    r.text(money.as_str(), money_right, content.y + gap - theme.tiny * 0.1,
           theme.body, 1.0, color::MONEY_GREEN, GC_FLAG_SHADOW);

    // -- pause button ------------------------------------------------------
    r.panel(layout.pause_button, fade(color::PANEL, 0.75), color::PANEL_EDGE, 2.0);
    let bars = Rect::new(layout.pause_button.center().x - 7.0 * theme.scale,
                         layout.pause_button.center().y - 9.0 * theme.scale,
                         5.0 * theme.scale, 18.0 * theme.scale);
    r.rect(bars, color::WHITE, 0);
    r.rect(Rect::new(bars.x + 9.0 * theme.scale, bars.y, bars.w, bars.h), color::WHITE, 0);

    // -- dash cooldown -----------------------------------------------------
    let dash_w = 120.0 * theme.scale;
    let dash = Rect::new(content.x + content.w * 0.5 - dash_w * 0.5,
                         content.y + content.h - gap - 12.0 * theme.scale,
                         dash_w, 10.0 * theme.scale);
    let max_charges = w.player.dash_charge_max();
    let ready = if max_charges <= 1 {
        1.0 - (w.player.dash_recharge / w.player.dash_cooldown_max().max(0.01)).clamp(0.0, 1.0)
    } else {
        w.player.dash_charges as f32 / max_charges as f32
    };
    r.bar(dash, ready, fade(color::INK, 0.8),
          if ready >= 1.0 { color::GOLD } else { color::PANEL_EDGE }, color::INK);
    if max_charges > 1 {
        let charges = crate::buf_format!(16, "DASH {}/{}", w.player.dash_charges, max_charges);
        r.text(charges.as_str(), dash.x + dash.w * 0.5, dash.y - theme.tiny * 1.3,
               theme.tiny, 0.5, fade(color::WHITE, 0.7), GC_FLAG_SHADOW);
    }

    // The arena's mood, named, so the player can see the world changing.
    let palette = w.backdrop.palette();
    let mood = if palette.blend > 0.06 {
        crate::buf_format!(48, "{} > {}", palette.name, palette.next_name)
    } else {
        crate::buf_format!(48, "{}", palette.name)
    };
    r.text(mood.as_str(), content.x + content.w - gap,
           content.y + content.h - theme.small * 1.4, theme.small, 1.0,
           fade(palette.accent, 0.75), GC_FLAG_SHADOW);

    // -- kills / score -----------------------------------------------------
    let stats = crate::buf_format!(48, "KILLS {}   SCORE {}   TIER {}",
                                   w.player.kills, w.score(), w.tier);
    r.text(stats.as_str(), content.x + gap, content.y + content.h - theme.body * 1.4,
           theme.small, 0.0, fade(color::WHITE, 0.8), GC_FLAG_SHADOW);

    // -- low health vignette (only while actually playing) ----------------
    let danger = if w.state == State::Playing { danger_fade(hp_fraction(&w.player)) } else { 0.0 };
    if danger > 0.01 {
        let t = (content.h * 0.10).max(24.0);
        let v = fade(color::HP, danger);
        r.rect(Rect::new(content.x, content.y, content.w, t), v, 0);
        r.rect(Rect::new(content.x, content.y + content.h - t, content.w, t), v, 0);
        r.rect(Rect::new(content.x, content.y, t, content.h), v, 0);
        r.rect(Rect::new(content.x + content.w - t, content.y, t, content.h), v, 0);
    }
}

fn draw_banner(w: &World, r: &mut Renderer, theme: &Theme) {
    let Some(b) = &w.banner else { return };
    let content = r.view.content_rect();
    let t = (b.t / b.max).clamp(0.0, 1.0);
    // Pop in quickly, fade out at the end.
    let alpha = clamp((1.0 - t) * 4.0, 0.0, 1.0) * clamp(t * 3.0, 0.0, 1.0);
    let y = content.y + content.h * 0.22;
    match b.kind {
        BannerKind::WaveStart => {
            let text = crate::buf_format!(24, "WAVE {}", b.value);
            r.text_center(text.as_str(), content.center().x, y, theme.h1,
                          fade(color::WHITE, alpha), GC_FLAG_SHADOW);
        }
        BannerKind::BossWave => {
            r.text_center("BOSS WAVE", content.center().x, y, theme.h1,
                          fade(color::HP, alpha), GC_FLAG_SHADOW);
            let sub = crate::buf_format!(24, "ONE ENORMOUS ENEMY - WAVE {}", b.value);
            r.text_center(sub.as_str(), content.center().x, y + theme.h1 * 1.1, theme.h3,
                          fade(color::GOLD, alpha), GC_FLAG_SHADOW);
        }
        BannerKind::WaveCleared => {
            r.text_center("WAVE CLEARED", content.center().x, y, theme.h1,
                          fade(color::MONEY_GREEN, alpha), GC_FLAG_SHADOW);
            let bonus = crate::buf_format!(24, "+{} BONUS", crate::render::money_buf(b.value).as_str());
            r.text_center(bonus.as_str(), content.center().x, y + theme.h1 * 1.1, theme.h3,
                          fade(color::GOLD, alpha), GC_FLAG_SHADOW);
        }
        BannerKind::CheckpointPassed => {
            r.text_center("QUOTA MET", content.center().x, y, theme.h1,
                          fade(color::MONEY_GREEN, alpha), GC_FLAG_SHADOW);
            let line = crate::buf_format!(48, "TIER {}  -  NEXT GOAL ${} BY WAVE {}",
                                          w.tier, w.goal, w.goal_wave);
            r.text_center(line.as_str(), content.center().x, y + theme.h1 * 1.1, theme.body,
                          fade(color::GOLD, alpha), GC_FLAG_SHADOW);
        }
        BannerKind::CheckpointFailed => {
            r.text_center("QUOTA MISSED", content.center().x, y, theme.h1,
                          fade(color::WARN, alpha), GC_FLAG_SHADOW);
            let line = crate::buf_format!(48, "NEEDED {}", crate::render::money_buf(b.value).as_str());
            r.text_center(line.as_str(), content.center().x, y + theme.h1 * 1.1, theme.body,
                          fade(color::WARN, alpha), GC_FLAG_SHADOW);
        }
        BannerKind::Revived => {
            r.text_center("EXTRA LIFE!", content.center().x, y, theme.h1,
                          fade(color::GOLD, alpha), GC_FLAG_SHADOW);
            let line = crate::buf_format!(32, "{} LEFT", b.value);
            r.text_center(line.as_str(), content.center().x, y + theme.h1 * 1.1, theme.body,
                          fade(color::WHITE, alpha), GC_FLAG_SHADOW);
        }
        BannerKind::GameOver => {}
    }
}

// ---------------------------------------------------------------------------
// overlays
// ---------------------------------------------------------------------------

fn dim(r: &mut Renderer, alpha: f32) {
    let content = r.view.content_rect();
    r.rect(Rect::new(-20.0, -20.0, r.view.virt_w + 40.0, r.view.virt_h + 40.0),
           fade(color::DIM, alpha), 0);
    let _ = content;
}

fn big_button(r: &mut Renderer, rect: Rect, label: &str, theme: &Theme, enabled: bool) {
    // Bottom shadow, body, top sheen, then a two-tone border: cheap, and it
    // reads as a real button rather than a rectangle.
    let shadow = Rect::new(rect.x, rect.y + 3.0 * theme.scale, rect.w, rect.h);
    r.rect(shadow, fade(color::BLACK, 0.45), 0);
    let fill = if enabled { color::CARD_HOVER } else { color::CARD };
    r.rect(rect, fill, 0);
    r.rect(Rect::new(rect.x, rect.y, rect.w, rect.h * 0.42),
           fade(color::WHITE, if enabled { 0.10 } else { 0.04 }), 0);
    r.rect(Rect::new(rect.x, rect.y + rect.h * 0.78, rect.w, rect.h * 0.22),
           fade(color::BLACK, 0.22), 0);
    r.outline(rect, 3.0, if enabled { color::GOLD } else { color::PANEL_EDGE });
    if enabled {
        r.outline(rect.inset(3.0), 1.0, fade(color::WHITE, 0.18));
    }
    r.text_in(label, rect, theme.h3, 0.5,
              if enabled { color::WHITE } else { fade(color::WHITE, 0.4) }, GC_FLAG_SHADOW);
}

fn draw_title(w: &World, r: &mut Renderer, theme: &Theme, layout: &UiLayout) {
    dim(r, 0.78);
    let content = r.view.content_rect();
    let cx = content.center().x;

    r.text_center("SLIME ARENA", cx, content.y + content.h * 0.10, theme.h1 * 1.25,
                  color::WHITE, GC_FLAG_SHADOW);
    r.text_center("SURVIVE THE WAVES. COLLECT. UPGRADE.", cx,
                  content.y + content.h * 0.10 + theme.h1 * 1.5, theme.small,
                  fade(color::WHITE, 0.7), GC_FLAG_SHADOW);

    // Cast line-up: the player flanked by both enemy types.
    let stage_y = content.y + content.h * 0.32;
    let s = 1.15;
    r.sprite_screen(SpriteId::Player, Vec2::new(cx - content.w * 0.20, stage_y),
                    SpriteId::Player.design_height() * s, 0.0, color::WHITE, GC_FLAG_NONE);
    r.sprite_screen(SpriteId::EnemyA, Vec2::new(cx, stage_y),
                    SpriteId::EnemyA.design_height() * s, 0.0, color::WHITE, GC_FLAG_NONE);
    r.sprite_screen(SpriteId::EnemyB, Vec2::new(cx + content.w * 0.20, stage_y),
                    SpriteId::EnemyB.design_height() * s, 0.0, color::WHITE, GC_FLAG_NONE);

    // Weapon row.
    let wy = stage_y + 78.0 * theme.scale;
    let names = [("GUN", SpriteId::Gun), ("BOW", SpriteId::Bow), ("SWORD", SpriteId::Sword)];
    for (i, (name, sprite)) in names.iter().enumerate() {
        let x = cx + (i as f32 - 1.0) * content.w * 0.16;
        r.sprite_screen(*sprite, Vec2::new(x, wy), sprite.design_height() * 0.85, 0.0,
                        color::WHITE, GC_FLAG_NONE);
        r.text_center(name, x, wy + 34.0 * theme.scale, theme.tiny, fade(color::WHITE, 0.7),
                      GC_FLAG_SHADOW);
    }

    let best = crate::buf_format!(32, "BEST {}", crate::render::money_buf(w.best_score).as_str());
    r.text_center(best.as_str(), cx, layout.start_button.y - theme.body * 2.2, theme.small,
                  color::GOLD, GC_FLAG_SHADOW);

    big_button(r, layout.start_button, "TAP TO START", theme, true);
    if layout.options_button.w > 0.0 {
        big_button(r, layout.options_button, "OPTIONS", theme, true);
    }
    r.text_center("MOVE: WASD / LEFT STICK     DASH: SPACE / BUTTON     PAUSE: ESC",
                  cx, layout.start_button.y + layout.start_button.h + theme.gap() * 1.6,
                  theme.tiny, fade(color::WHITE, 0.55), GC_FLAG_SHADOW);
}

fn draw_level_up(w: &World, r: &mut Renderer, theme: &Theme, layout: &UiLayout) {
    dim(r, 0.86);
    let content = r.view.content_rect();
    r.text_center("LEVEL UP!", content.center().x, content.y + content.h * 0.11,
                  theme.h1, color::XP, GC_FLAG_SHADOW);
    let hint = crate::buf_format!(32, "CHOOSE ONE  -  LEVEL {}", w.player.level);
    r.text_center(hint.as_str(), content.center().x, content.y + content.h * 0.11 + theme.h1 * 1.1,
                  theme.small, fade(color::WHITE, 0.75), GC_FLAG_SHADOW);

    for i in 0..layout.slot_count.min(w.cards_shown.max(3)) {
        let rect = layout.slot(i);
        let perk = w.cards[i];
        r.panel(rect, color::CARD, color::CARD_EDGE, 3.0);
        let accent = Rect::new(rect.x, rect.y, rect.w, 6.0 * theme.scale);
        r.rect(accent, color::XP, 0);

        let title_size = theme.h3;
        let inner = rect.inset(theme.gap());
        r.text_in(perk.title(), Rect::new(inner.x, inner.y + inner.h * 0.20, inner.w, title_size * 1.4),
                  title_size, 0.5, color::WHITE, GC_FLAG_SHADOW);
        // Divider between the name and the effect.
        r.rect(Rect::new(inner.x + inner.w * 0.15, inner.y + inner.h * 0.44,
                         inner.w * 0.70, 1.5), fade(color::WHITE, 0.18), 0);
        r.text_in(perk.describe(),
                  Rect::new(inner.x, inner.y + inner.h * 0.56, inner.w, theme.body * 1.6),
                  theme.body, 0.5, fade(color::WHITE, 0.85), GC_FLAG_SHADOW);
    }
}

fn draw_shop(w: &World, r: &mut Renderer, theme: &Theme, layout: &UiLayout) {
    dim(r, 0.90);
    let content = r.view.content_rect();
    let gap = theme.gap();
    let Some(tree) = layout.tree else { return };
    let view = Rect::new(tree.origin.x, tree.origin.y, tree.width, tree.height);
    let visible = |rect: Rect| tree.intersects_view(rect);

    // -- hive backdrop: faint lattice dots on the hex grid ------------------
    {
        let x_step = tree.x_step();
        let y_step = tree.y_step();
        for row in 0..(crate::tree::FAMILIES.len() + 1) {
            for col in 0..=(crate::tree::TIERS as i32) {
                let stagger = if row % 2 == 1 { x_step * 0.5 } else { 0.0 };
                let p = Vec2::new(
                    tree.origin.x + col as f32 * x_step + stagger - tree.pan.x + tree.hex_w * 0.5,
                    tree.origin.y + row as f32 * y_step - tree.pan.y + tree.hex_h * 0.5,
                );
                if p.x < view.x - 20.0 || p.x > view.x + view.w + 20.0
                    || p.y < view.y - 20.0 || p.y > view.y + view.h + 20.0
                {
                    continue;
                }
                r.rect_screen(p, 3.0, 3.0, 0.0, fade(color::WHITE, 0.05), 0);
            }
        }
    }

    // -- connections: a dark pipe with a bright core, glowing once powered ---
    for node in 0..crate::tree::NODE_COUNT {
        let Some(rect) = tree.node_rect(node) else { continue };
        if !visible(rect) || !w.node_visible(node) {
            continue;
        }
        let Some(req) = crate::tree::requires(node) else { continue };
        if !w.node_visible(req) {
            continue;
        }
        let Some(from) = tree.node_rect(req).filter(|r| visible(*r)) else { continue };
        let (a, b) = (from.center(), rect.center());
        let owned = w.node_owned(req);
        let accent = crate::tree::family(node).branch.color();
        r.line(a, b, 5.0, fade(color::BLACK, 0.55));
        if owned {
            r.line(a, b, 7.0, fade(accent, 0.15));
        }
        r.line(a, b, 1.8, if owned { accent } else { fade(color::WHITE, 0.18) });
    }

    let hovered = if w.pointer_active() { tree.node_at(w.pointer_pos()) } else { None };

    // -- cells -------------------------------------------------------------
    for node in 0..crate::tree::NODE_COUNT {
        let Some(rect) = tree.node_rect(node) else { continue };
        if !visible(rect) || !w.node_visible(node) {
            continue;
        }
        let family = crate::tree::family_of(node);
        let fam = &crate::tree::FAMILIES[family];
        let owned = w.node_owned(node);
        let available = w.node_available(node);
        let price = w.node_cost(node);
        let affordable = w.player.money >= price;
        let hover = hovered == Some(node);
        let root = crate::tree::is_root(node);
        let accent = fam.branch.color();

        // The hovered cell lifts slightly.
        let lift = if hover { rect.w * 0.035 } else { 0.0 };
        let cell = Rect::new(rect.x - lift, rect.y - lift,
                             rect.w + lift * 2.0, rect.h + lift * 2.0);

        let face = if owned {
            fade(accent, 0.34)
        } else if available {
            color::CARD_HOVER
        } else {
            fade(color::PANEL, 0.92)
        };
        let edge = if hover {
            color::WHITE
        } else if owned || (available && affordable) {
            color::GOLD
        } else if available {
            accent
        } else {
            fade(color::WHITE, 0.18)
        };
        hex_cell(r, cell, face, edge, if hover { 3.5 } else { 2.0 }, hover);
        if owned {
            hex_slabs(r, cell, fade(accent, 0.10), 8);
            hex_outline(r, cell.inset(cell.w * 0.10), 1.5, fade(accent, 0.55));
        }
        // Keystones are gated on a tier in another chain: mark them as links.
        if crate::tree::is_keystone(node) {
            let d = cell.w * 0.60;
            r.rect_screen(Vec2::new(cell.center().x, cell.center().y), d, d,
                          std::f32::consts::FRAC_PI_4, fade(color::WHITE, 0.10), 0);
            r.rect_screen(Vec2::new(cell.center().x, cell.center().y), d, 1.5,
                          std::f32::consts::FRAC_PI_4, fade(color::WHITE, 0.30), 0);
            r.rect_screen(Vec2::new(cell.center().x, cell.center().y), d, 1.5,
                          -std::f32::consts::FRAC_PI_4, fade(color::WHITE, 0.30), 0);
        }

        // Badge sprite, tier pips, label, price.
        // The root is "you"; everything else shows what it does.
        let icon_alpha = if owned { 0.95 } else if available { 0.82 } else { 0.38 };
        let icon_at = Vec2::new(cell.center().x, cell.center().y - cell.h * 0.02);
        if root {
            r.sprite_screen(crate::sprite::SpriteId::Player, icon_at, cell.w * 0.26, 0.0,
                            fade(color::WHITE, icon_alpha), GC_FLAG_NONE);
        } else if let Some(badge) = fam.badge() {
            r.sprite_screen(badge, icon_at, cell.w * 0.22, 0.0,
                            fade(color::WHITE, icon_alpha), GC_FLAG_NONE);
        } else {
            family_icon(r, fam.kind, icon_at, cell.w * 0.22,
                        fade(color::WHITE, icon_alpha));
        }

        let tier = crate::tree::tier_of(node);
        let pips = if root { 1 } else { tier as i32 };
        let owned_tiers = w.tree.tiers(family);
        let spacing = 4.6;
        let total = (pips as f32 - 1.0) * spacing;
        for k in 0..pips {
            let x = cell.center().x - total * 0.5 + k as f32 * spacing;
            let y = cell.y + cell.h * 0.815;
            let on = root || (k as u8) < owned_tiers;
            r.rect_screen(Vec2::new(x, y), 4.2, 4.2, 0.0,
                          fade(color::BLACK, 0.5), 0);
            r.rect_screen(Vec2::new(x, y), 3.0, 3.0, 0.0,
                          if on { accent } else { fade(color::WHITE, 0.3) }, 0);
        }

        let badge_label = if root {
            crate::buf_format!(16, "ROOT")
        } else {
            crate::buf_format!(16, "{}", crate::tree::tier_label(tier))
        };
        r.text_center(badge_label.as_str(), cell.center().x, cell.y + cell.h * 0.135,
                      theme.tiny,
                      fade(color::WHITE, if owned || available { 0.9 } else { 0.45 }),
                      GC_FLAG_SHADOW);

        let (text, colour) = if owned {
            (crate::buf_format!(16, "OWNED"), color::GOLD)
        } else if available && affordable {
            (crate::render::money_buf(price), color::MONEY_GREEN)
        } else if available {
            (crate::render::money_buf(price), color::WARN)
        } else {
            (crate::buf_format!(16, "LOCKED"), fade(color::WHITE, 0.38))
        };
        r.text_center(text.as_str(), cell.center().x, cell.y + cell.h * 0.90,
                      theme.tiny, colour, GC_FLAG_SHADOW);
    }

    // -- gradient edges: cells fade out instead of being cut off ------------
    {
        let steps = 5;
        let band_h = tree.hex_h * 0.34;
        for i in 0..steps {
            let t = i as f32 / steps as f32;
            let alpha = 0.10 + 0.16 * (1.0 - t);
            let h = band_h / steps as f32 * 1.6;
            r.rect(Rect::new(view.x, view.y + t * band_h, view.w, h),
                   fade(color::DIM, alpha), 0);
            r.rect(Rect::new(view.x, view.y + view.h - t * band_h - h, view.w, h),
                   fade(color::DIM, alpha), 0);
        }
        r.outline(view, 1.5, fade(color::GOLD, 0.22));
    }

    // -- scrollbars --------------------------------------------------------
    {
        let (tx, ty, vis_x, vis_y) = tree.scroll();
        let bar_w = 3.5 * theme.scale;
        if vis_y < 1.0 {
            let track = Rect::new(view.x + view.w - bar_w - 3.0 * theme.scale, view.y,
                                  bar_w, view.h);
            r.rect(track, fade(color::BLACK, 0.25), 0);
            let h = (track.h * vis_y).max(24.0);
            r.rect(Rect::new(track.x, track.y + (track.h - h) * ty, bar_w, h),
                   fade(color::WHITE, 0.32), 0);
        }
        if vis_x < 0.95 {
            let track = Rect::new(view.x, view.y + view.h - bar_w, view.w, bar_w);
            r.rect(track, fade(color::BLACK, 0.25), 0);
            let w = (track.w * vis_x).max(24.0);
            r.rect(Rect::new(track.x + (track.w - w) * tx, track.y, w, bar_w),
                   fade(color::WHITE, 0.32), 0);
        }
    }

    header_band(r, content, theme, w);

    // -- detail strip ------------------------------------------------------
    let strip = layout.strip;
    if let Some(node) = hovered {
        let root = crate::tree::is_root(node);
        let accent = if root {
            color::GOLD
        } else {
            crate::tree::family(node).branch.color()
        };
        let (title, blurb) = if root {
            (crate::buf_format!(40, "{}", crate::tree::ROOT_NAME),
             crate::buf_format!(48, "{}", crate::tree::ROOT_BLURB))
        } else {
            let family = crate::tree::family_of(node);
            let label = crate::tree::NodeLabel::<40>::new(family, crate::tree::tier_of(node));
            (crate::buf_format!(40, "{}", label.as_str()),
             crate::buf_format!(48, "{}", crate::tree::FAMILIES[family].blurb))
        };
        r.rect(strip, fade(color::PANEL, 0.96), 0);
        r.rect(Rect::new(strip.x, strip.y, strip.w, strip.h * 0.4),
               fade(color::WHITE, 0.05), 0);
        r.rect(Rect::new(strip.x, strip.y, 5.0 * theme.scale, strip.h), accent, 0);
        r.outline(strip, 1.5, fade(accent, 0.55));
        r.text(title.as_str(), strip.x + gap * 1.6, strip.y + strip.h * 0.10,
               theme.body, 0.0, color::WHITE, GC_FLAG_SHADOW);
        r.text(blurb.as_str(), strip.x + gap * 1.6,
               strip.y + strip.h * 0.10 + theme.body * 1.05,
               theme.small, 0.0, fade(color::WHITE, 0.72), GC_FLAG_SHADOW);
        let (state, colour) = if w.node_owned(node) {
            (crate::buf_format!(16, "OWNED"), color::GOLD)
        } else if w.node_available(node) {
            let price = w.node_cost(node);
            (crate::render::money_buf(price),
             if w.player.money >= price { color::MONEY_GREEN } else { color::WARN })
        } else {
            (crate::buf_format!(16, "LOCKED"), fade(color::WHITE, 0.5))
        };
        r.text(state.as_str(), strip.x + strip.w - gap, strip.y + strip.h * 0.26,
               theme.h3, 1.0, colour, GC_FLAG_SHADOW);
    } else {
        r.text_center("DRAG TO EXPLORE  -  TAP A NODE TO BUY  -  EACH NODE OPENS MORE",
                      strip.center().x, strip.y + strip.h * 0.22, theme.small,
                      fade(color::WHITE, 0.5), GC_FLAG_SHADOW);
    }

    if layout.market_button.w > 0.0 {
        big_button(r, layout.market_button, "MARKET", theme, true);
    }
    big_button(r, layout.next_button, "NEXT WAVE", theme, true);
}

/// Opaque band + chips for the hive, drawn *after* the cells so nothing the
/// player drags around can collide with the text.
fn header_band(r: &mut Renderer, content: Rect, theme: &Theme, w: &World) {
    let band = Rect::new(content.x, content.y, content.w, content.h * 0.145);
    r.rect(band, fade(color::DIM, 0.94), 0);
    r.rect(Rect::new(band.x, band.y + band.h - 2.0, band.w, 2.0),
           fade(color::GOLD, 0.28), 0);

    let gap = theme.gap();
    let title_size = theme.h1 * 0.72;
    r.text_center("THE HIVE", band.x + band.w * 0.5, band.y + title_size * 0.06,
                  title_size, color::GOLD, GC_FLAG_SHADOW);
    let rule_w = title_size * 4.2;
    r.rect(Rect::new(band.x + band.w * 0.5 - rule_w * 0.5, band.y + title_size * 1.02,
                     rule_w, 2.0), fade(color::GOLD, 0.45), 0);

    let chip_h = (30.0 * theme.scale).max(22.0);
    let y = band.y + band.h - chip_h - gap * 0.4;

    let money = crate::render::money_buf(w.player.money);
    let money_w = r.text_width(money.as_str(), theme.body) + gap * 2.4;
    let money_chip = Rect::new(band.x + gap, y, money_w, chip_h);
    chip(r, money_chip, fade(color::MONEY_GREEN, 0.6), theme);
    r.text_in(money.as_str(), money_chip, theme.body, 0.5, color::MONEY_GREEN, GC_FLAG_SHADOW);

    let nodes = crate::buf_format!(32, "{} / {} NODES", w.tree_tiers_owned(),
                                   crate::tree::NODE_COUNT as i32);
    let nodes_w = r.text_width(nodes.as_str(), theme.small) + gap * 2.4;
    let nodes_chip = Rect::new(band.x + band.w - gap - nodes_w, y, nodes_w, chip_h);
    chip(r, nodes_chip, fade(color::WHITE, 0.25), theme);
    r.text_in(nodes.as_str(), nodes_chip, theme.small, 0.5, fade(color::WHITE, 0.85),
              GC_FLAG_SHADOW);

    let goal_text = crate::render::money_buf(w.goal);
    let earned = crate::render::money_buf(w.money_earned);
    let met = w.money_earned >= w.goal;
    let urgent = !met && w.wave >= w.goal_wave - 2;
    let tax = crate::buf_format!(64, "TAX {} BY WAVE {}   -   EARNED {}",
                                 goal_text.as_str(), w.goal_wave, earned.as_str());
    r.text_center(tax.as_str(), band.x + band.w * 0.5, band.y + title_size * 1.18,
                  theme.small,
                  if met {
                      color::MONEY_GREEN
                  } else if urgent {
                      color::WARN
                  } else {
                      fade(color::WHITE, 0.8)
                  },
                  GC_FLAG_SHADOW);
}

/// Draws one honeycomb cell.
///
/// The command set has no polygons, so a cell is a stack of horizontal slabs
/// whose widths follow the hexagon profile.  On top of that it gets a drop
/// shadow, a top highlight and a bottom shade, which is what turns a flat
/// silhouette into something with depth.
fn hex_cell(r: &mut Renderer, rect: Rect, fill: u32, edge: u32, thickness: f32, hover: bool) {
    let half_h = rect.h * 0.5;
    let full_w = rect.w * 0.94;
    if full_w <= 2.0 || half_h <= 2.0 {
        return;
    }

    // Soft drop shadow: fewer, coarser bands are plenty for a blur.
    let shadow = Rect::new(rect.x, rect.y + rect.h * 0.055, rect.w, rect.h);
    hex_slabs(r, shadow, fade(color::BLACK, 0.35), 8);

    // The face.
    hex_slabs(r, rect, fill, 20);

    // Top highlight and bottom shade, clipped to the hexagon profile.
    hex_slabs(r, Rect::new(rect.x, rect.y, rect.w, rect.h * 0.30),
              fade(color::WHITE, if hover { 0.14 } else { 0.07 }), 4);
    hex_slabs(r, Rect::new(rect.x, rect.y + rect.h * 0.72, rect.w, rect.h * 0.28),
              fade(color::BLACK, 0.22), 4);

    hex_outline(r, rect, thickness, edge);

    if hover {
        // Lift the hovered cell: a bright ring just inside the edge.
        hex_outline(r, rect.inset(rect.w * 0.045), thickness * 0.8,
                    fade(color::WHITE, 0.55));
    }
}

/// Small icons drawn from rectangles for the body-stat families.  Six shapes
/// cover the whole set, and they read far better in a grid than one repeated
/// sprite would.
fn family_icon(r: &mut Renderer, kind: crate::tree::StatKind, c: Vec2, size: f32, colour: u32) {
    use crate::tree::StatKind as K;
    let s = size * 0.5;
    let thick = (size * 0.17).max(2.0);
    match kind {
        // Speed and dash charges: a chevron.
        K::Speed | K::DashCharges => {
            r.line(Vec2::new(c.x - s * 0.6, c.y - s), Vec2::new(c.x + s * 0.5, c.y), thick, colour);
            r.line(Vec2::new(c.x + s * 0.5, c.y), Vec2::new(c.x - s * 0.6, c.y + s), thick, colour);
        }
        // Cooldown / i-frames: a clock.
        K::DashCd | K::Iframes => {
            let tau = std::f32::consts::TAU;
            for k in 0..10 {
                let a0 = k as f32 * tau / 10.0;
                let a1 = (k + 1) as f32 * tau / 10.0;
                r.line(c + Vec2::from_angle(a0) * s, c + Vec2::from_angle(a1) * s,
                       thick * 0.8, colour);
            }
            r.line(c, Vec2::new(c.x, c.y - s * 0.65), thick * 0.8, colour);
            r.line(c, Vec2::new(c.x + s * 0.5, c.y), thick * 0.8, colour);
        }
        // Healing: a cross.
        K::Regen | K::Lifesteal | K::WaveHeal => {
            r.rect_screen(c, s * 1.7, thick, 0.0, colour, 0);
            r.rect_screen(c, thick, s * 1.7, 0.0, colour, 0);
        }
        // Armour and thorns: a shield.
        K::Armor | K::Thorns => {
            r.rect_screen(Vec2::new(c.x, c.y - s * 0.35), s * 1.5, s * 0.9, 0.0, colour, 0);
            r.rect_screen(Vec2::new(c.x, c.y + s * 0.22), s * 1.05, s * 0.42, 0.0, colour, 0);
            r.rect_screen(Vec2::new(c.x, c.y + s * 0.62), s * 0.55, s * 0.38, 0.0, colour, 0);
        }
        // Health and lives: a heart.
        K::MaxHp | K::Lives => {
            r.rect_screen(Vec2::new(c.x - s * 0.42, c.y - s * 0.42), s * 0.72, s * 0.72,
                          0.0, colour, 0);
            r.rect_screen(Vec2::new(c.x + s * 0.42, c.y - s * 0.42), s * 0.72, s * 0.72,
                          0.0, colour, 0);
            r.rect_screen(Vec2::new(c.x, c.y + s * 0.22), s * 1.28, s * 1.28,
                          std::f32::consts::FRAC_PI_4, colour, 0);
        }
        // Blazing dash: a flame.
        K::DashDamage => {
            r.rect_screen(Vec2::new(c.x, c.y + s * 0.25), s * 0.9, s * 1.1, 0.0, colour, 0);
            r.rect_screen(Vec2::new(c.x, c.y - s * 0.5), s * 0.55, s * 0.8,
                          std::f32::consts::FRAC_PI_4, colour, 0);
        }
        // Lightning: a bolt.
        K::Lightning => {
            r.line(Vec2::new(c.x + s * 0.45, c.y - s), Vec2::new(c.x - s * 0.25, c.y + s * 0.1),
                   thick * 1.1, colour);
            r.line(Vec2::new(c.x - s * 0.25, c.y + s * 0.1), Vec2::new(c.x + s * 0.3, c.y + s * 0.05),
                   thick * 1.1, colour);
            r.line(Vec2::new(c.x + s * 0.3, c.y + s * 0.05), Vec2::new(c.x - s * 0.45, c.y + s),
                   thick * 1.1, colour);
        }
        _ => {
            r.rect_screen(c, s, s, 0.0, colour, 0);
        }
    }
}

/// Horizontal slabs approximating a (stretched, pointy-top) hexagon.
fn hex_slabs(r: &mut Renderer, rect: Rect, colour: u32, bands: i32) {
    let c = rect.center();
    let half_h = rect.h * 0.5;
    let full_w = rect.w * 0.94;
    if full_w <= 1.0 || half_h <= 1.0 || colour >> 24 == 0 {
        return;
    }
    let band_h = (half_h * 2.0) / bands as f32;
    for k in 0..bands {
        let dy = -half_h + (k as f32 + 0.5) * band_h;
        let ny = (dy.abs() / half_h).min(1.0);
        let scale = if ny <= 0.5 { 1.0 } else { 2.0 * (1.0 - ny) };
        let w = full_w * scale;
        if w <= 1.0 {
            continue;
        }
        r.rect_screen(Vec2::new(c.x, c.y + dy), w, band_h + 1.0, 0.0, colour, 0);
    }
}

/// Six segments between the vertices of the cell.
fn hex_outline(r: &mut Renderer, rect: Rect, thickness: f32, colour: u32) {
    let vertex = |i: i32| {
        match i.rem_euclid(6) {
            0 => Vec2::new(rect.x + rect.w * 0.5, rect.y),
            1 => Vec2::new(rect.x + rect.w, rect.y + rect.h * 0.25),
            2 => Vec2::new(rect.x + rect.w, rect.y + rect.h * 0.75),
            3 => Vec2::new(rect.x + rect.w * 0.5, rect.y + rect.h),
            4 => Vec2::new(rect.x, rect.y + rect.h * 0.75),
            _ => Vec2::new(rect.x, rect.y + rect.h * 0.25),
        }
    };
    for i in 0..6 {
        r.line(vertex(i), vertex(i + 1), thickness, colour);
    }
}

/// A small inset panel used for header chips.
fn chip(r: &mut Renderer, rect: Rect, edge: u32, theme: &Theme) {
    r.rect(rect, fade(color::PANEL, 0.92), 0);
    r.rect(Rect::new(rect.x, rect.y, rect.w, rect.h * 0.45),
           fade(color::WHITE, 0.05), 0);
    r.outline(rect, (1.5 * theme.scale).max(1.0), edge);
}

fn draw_paused(w: &World, r: &mut Renderer, theme: &Theme, layout: &UiLayout) {
    dim(r, 0.7);
    let content = r.view.content_rect();
    let cx = content.center().x;
    r.text_center("PAUSED", cx, content.y + content.h * 0.26, theme.h1, color::WHITE,
                  GC_FLAG_SHADOW);
    let line = crate::buf_format!(64, "WAVE {}   LEVEL {}   KILLS {}", w.wave, w.player.level,
                                  w.player.kills);
    r.text_center(line.as_str(), cx, content.y + content.h * 0.26 + theme.h1 * 1.2,
                  theme.body, fade(color::WHITE, 0.8), GC_FLAG_SHADOW);
    let score = crate::buf_format!(32, "SCORE {}", w.score());
    r.text_center(score.as_str(), cx, content.y + content.h * 0.26 + theme.h1 * 1.2 + theme.body * 1.5,
                  theme.body, color::GOLD, GC_FLAG_SHADOW);
    big_button(r, layout.start_button, "RESUME", theme, true);
    if layout.options_button.w > 0.0 {
        big_button(r, layout.options_button, "OPTIONS", theme, true);
    }
    r.text_center("R RESTARTS THE RUN", cx,
                  layout.start_button.y + layout.start_button.h + theme.gap() * 1.5,
                  theme.tiny, fade(color::WHITE, 0.5), GC_FLAG_SHADOW);
}

fn draw_game_over(w: &World, r: &mut Renderer, theme: &Theme, layout: &UiLayout) {
    dim(r, 0.82);
    let content = r.view.content_rect();
    let cx = content.center().x;
    r.text_center("GAME OVER", cx, content.y + content.h * 0.16, theme.h1 * 1.1,
                  color::WARN, GC_FLAG_SHADOW);
    let score = crate::buf_format!(32, "SCORE {}", w.score());
    r.text_center(score.as_str(), cx, content.y + content.h * 0.16 + theme.h1 * 1.35,
                  theme.h2, color::WHITE, GC_FLAG_SHADOW);

    let best = if w.score() >= w.best_score {
        crate::buf_format!(32, "NEW BEST!")
    } else {
        crate::buf_format!(32, "BEST {}", w.best_score)
    };
    r.text_center(best.as_str(), cx, content.y + content.h * 0.16 + theme.h1 * 1.35 + theme.h2 * 1.3,
                  theme.body, color::GOLD, GC_FLAG_SHADOW);

    let rows = [
        crate::buf_format!(24, "WAVE {}", w.wave),
        crate::buf_format!(24, "LEVEL {}", w.player.level),
        crate::buf_format!(24, "KILLS {}", w.player.kills),
    ];
    let y = content.y + content.h * 0.44;
    for (i, row) in rows.iter().enumerate() {
        let x = cx + (i as f32 - 1.0) * content.w * 0.20;
        r.text_center(row.as_str(), x, y, theme.body, fade(color::WHITE, 0.85), GC_FLAG_SHADOW);
    }

    big_button(r, layout.start_button, "PLAY AGAIN", theme, true);
    r.text_center("PRESS R OR TAP TO RESTART", cx,
                  layout.start_button.y + layout.start_button.h + theme.gap() * 1.5,
                  theme.tiny, fade(color::WHITE, 0.5), GC_FLAG_SHADOW);
}

/// Reticle for pointer aiming; drawn last so it sits above everything.
pub fn draw_pointer(w: &World, r: &mut Renderer, pointer: Vec2) {
    if !matches!(w.state, State::Playing) {
        return;
    }
    let c = fade(color::WHITE, 0.35);
    let s = 9.0;
    r.rect_screen(pointer, s * 2.0, 1.5, 0.0, c, 0);
    r.rect_screen(pointer, 1.5, s * 2.0, 0.0, c, 0);
}
