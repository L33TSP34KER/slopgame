//! The renderer: turns the simulation into the flat, pre-sorted, screen-space
//! command list that the platform shells blit.
//!
//! Everything the shells would otherwise have to do -- camera transform, screen
//! shake, text layout, glyph lookup, bars, outlines, hit-testable rectangles --
//! happens here, so a shell is only a texture blitter.

// Some of this module is internal API used by tests or by other
// platforms' renderers, so unused-in-this-build items are expected.
#![allow(dead_code)]

use crate::ffi::*;
use crate::generated::font_metrics as fm;
use crate::math::{clamp, Vec2};
use crate::sprite::{weapon_rotation_for, SpriteId};

/// Upper bound on commands per frame; extra commands are dropped rather than
/// growing the buffer without bound on a pathological frame.
pub const MAX_CMDS: usize = 16384;

// ---------------------------------------------------------------------------
// colours (0xAARRGGBB, straight alpha, matching include/game_core.h)
// ---------------------------------------------------------------------------

pub mod color {
    pub const fn rgb(r: u8, g: u8, b: u8) -> u32 {
        rgba(r, g, b, 255)
    }

    pub const fn rgba(r: u8, g: u8, b: u8, a: u8) -> u32 {
        ((a as u32) << 24) | ((r as u32) << 16) | ((g as u32) << 8) | (b as u32)
    }

    pub const WHITE: u32 = rgb(255, 255, 255);
    pub const BLACK: u32 = rgb(0, 0, 0);

    // Player / art palette, sampled from the source sheet.
    pub const INK: u32 = rgb(0x25, 0x25, 0x2b);
    pub const INK_SOFT: u32 = rgb(0x2c, 0x2c, 0x33);
    pub const SLIME: u32 = rgb(0xad, 0x3a, 0x84);
    pub const SLIME_HOT: u32 = rgb(0xed, 0x1e, 0x79);
    pub const BLUSH: u32 = rgb(0xd9, 0x9b, 0x9b);
    pub const XP_BLUE: u32 = rgb(0x29, 0xab, 0xe2);
    pub const MONEY_GREEN: u32 = rgb(0x39, 0xb5, 0x4a);

    pub const BG_DEEP: u32 = rgb(0x12, 0x12, 0x18);
    pub const BG_FLOOR: u32 = rgb(0x1b, 0x1b, 0x23);
    pub const GRID: u32 = rgb(0x23, 0x23, 0x2e);
    pub const ARENA_EDGE: u32 = rgb(0x3a, 0x3a, 0x4d);

    pub const HP: u32 = rgb(0xe5, 0x4b, 0x5b);
    pub const HP_BG: u32 = rgb(0x3a, 0x1f, 0x27);
    pub const XP: u32 = rgb(0x35, 0xc8, 0xff);
    pub const XP_BG: u32 = rgb(0x1b, 0x2c, 0x3d);
    pub const GOLD: u32 = rgb(0xff, 0xd1, 0x66);
    pub const PANEL: u32 = rgb(0x1a, 0x1a, 0x24);
    pub const PANEL_EDGE: u32 = rgb(0x4a, 0x4a, 0x66);
    pub const CARD: u32 = rgb(0x22, 0x22, 0x30);
    pub const CARD_HOVER: u32 = rgb(0x33, 0x33, 0x4a);
    pub const CARD_EDGE: u32 = rgb(0x6c, 0x6c, 0x94);
    pub const DIM: u32 = rgb(0x0a, 0x0a, 0x0f);
    pub const WARN: u32 = rgb(0xff, 0x6b, 0x6b);
}

/// Linear blend between two packed colours (alpha taken from `a`).
pub fn mix_colour(a: u32, b: u32, t: f32) -> u32 {
    let t = clamp(t, 0.0, 1.0);
    let ch = |shift: u32| {
        let ca = ((a >> shift) & 0xff) as f32;
        let cb = ((b >> shift) & 0xff) as f32;
        (ca + (cb - ca) * t).round().clamp(0.0, 255.0) as u32
    };
    (ch(24) << 24) | (ch(16) << 16) | (ch(8) << 8) | ch(0)
}

/// Applies a 0..=1 alpha multiplier to a packed colour.
pub fn fade(c: u32, alpha: f32) -> u32 {
    let a = (c >> 24) & 0xff;
    let scaled = (a as f32 * clamp(alpha, 0.0, 1.0)) as u32;
    (c & 0x00ff_ffff) | (scaled << 24)
}

// ---------------------------------------------------------------------------
// view / camera
// ---------------------------------------------------------------------------

/// Framebuffer geometry plus the safe-area insets, in *virtual* units.
#[derive(Clone, Debug)]
pub struct View {
    pub fb_w: f32,
    pub fb_h: f32,
    /// pixels per virtual unit
    pub scale: f32,
    pub virt_w: f32,
    pub virt_h: f32,
    /// left, top, right, bottom insets in virtual units
    pub safe: [f32; 4],
}

/// The world area we always try to keep visible.  Keeping a minimum visible
/// extent (instead of a fixed zoom) is what lets the same build look right on a
/// 16:9 desktop window and on a tall phone screen.
const TARGET_VIEW_W: f32 = 1180.0;
const TARGET_VIEW_H: f32 = 760.0;
const MIN_ZOOM: f32 = 0.50;
const MAX_ZOOM: f32 = 1.45;

impl View {
    pub fn new(fb_w: i32, fb_h: i32, safe_px: [f32; 4]) -> View {
        let mut view = View {
            fb_w: 1.0,
            fb_h: 1.0,
            scale: 1.0,
            virt_w: GC_DESIGN_HEIGHT,
            virt_h: GC_DESIGN_HEIGHT,
            safe: [0.0; 4],
        };
        view.resize(fb_w, fb_h, safe_px);
        view
    }

    pub fn resize(&mut self, fb_w: i32, fb_h: i32, safe_px: [f32; 4]) {
        self.fb_w = fb_w.max(1) as f32;
        self.fb_h = fb_h.max(1) as f32;
        // Design height is fixed, so the scale follows from the framebuffer.
        self.scale = self.fb_h / GC_DESIGN_HEIGHT;
        if !self.scale.is_finite() || self.scale <= 0.0 {
            self.scale = 1.0;
        }
        self.virt_w = self.fb_w / self.scale;
        self.virt_h = self.fb_h / self.scale;
        for i in 0..4 {
            self.safe[i] = (safe_px[i].max(0.0)) / self.scale;
        }
    }

    pub fn center(&self) -> Vec2 {
        Vec2::new(self.virt_w * 0.5, self.virt_h * 0.5)
    }

    /// Zoom that keeps at least TARGET_VIEW_W x TARGET_VIEW_H world units visible.
    pub fn fit_zoom(&self) -> f32 {
        let z = (self.virt_w / TARGET_VIEW_W).min(self.virt_h / TARGET_VIEW_H);
        clamp(z, MIN_ZOOM, MAX_ZOOM)
    }

    /// Playable rectangle, i.e. the view minus the safe-area insets.
    pub fn content_rect(&self) -> Rect {
        Rect {
            x: self.safe[0],
            y: self.safe[1],
            w: (self.virt_w - self.safe[0] - self.safe[2]).max(1.0),
            h: (self.virt_h - self.safe[1] - self.safe[3]).max(1.0),
        }
    }
}

// ---------------------------------------------------------------------------
// rectangles (used for UI layout + hit testing, top-left based)
// ---------------------------------------------------------------------------

#[derive(Copy, Clone, Debug, Default, PartialEq)]
pub struct Rect {
    pub x: f32,
    pub y: f32,
    pub w: f32,
    pub h: f32,
}

impl Rect {
    pub fn new(x: f32, y: f32, w: f32, h: f32) -> Rect {
        Rect { x, y, w, h }
    }

    pub fn center(&self) -> Vec2 {
        Vec2::new(self.x + self.w * 0.5, self.y + self.h * 0.5)
    }

    pub fn contains(&self, p: Vec2) -> bool {
        p.x >= self.x && p.x <= self.x + self.w && p.y >= self.y && p.y <= self.y + self.h
    }

    pub fn inset(&self, by: f32) -> Rect {
        Rect { x: self.x + by, y: self.y + by, w: (self.w - 2.0 * by).max(0.0), h: (self.h - 2.0 * by).max(0.0) }
    }
}

// ---------------------------------------------------------------------------
// renderer
// ---------------------------------------------------------------------------

pub struct Renderer {
    pub cmds: Vec<gc_cmd>,
    pub view: View,
    /// World position shown at the centre of the screen.
    pub camera: Vec2,
    pub zoom: f32,
    /// Screen shake, in virtual units.
    pub shake: Vec2,
    dropped: u32,
}

impl Renderer {
    pub fn new(view: View) -> Renderer {
        Renderer {
            cmds: Vec::with_capacity(4096),
            camera: Vec2::ZERO,
            zoom: 1.0,
            shake: Vec2::ZERO,
            dropped: 0,
            view,
        }
    }

    pub fn begin(&mut self, camera: Vec2, zoom: f32, shake: Vec2) {
        self.cmds.clear();
        self.dropped = 0;
        self.camera = camera;
        self.zoom = zoom;
        self.shake = shake;
    }

    pub fn dropped_commands(&self) -> u32 {
        self.dropped
    }

    pub fn world_to_screen(&self, world: Vec2) -> Vec2 {
        (world - self.camera) * self.zoom + self.view.center() + self.shake
    }

    pub fn screen_to_world(&self, screen: Vec2) -> Vec2 {
        (screen - self.view.center() - self.shake) / self.zoom + self.camera
    }

    fn push(&mut self, cmd: gc_cmd) {
        if self.cmds.len() < MAX_CMDS {
            self.cmds.push(cmd);
        } else {
            self.dropped += 1;
        }
    }

    // -- primitives ---------------------------------------------------------

    pub fn rect_screen(&mut self, center: Vec2, w: f32, h: f32, rot: f32, rgba: u32, flags: i32) {
        self.push(gc_cmd {
            kind: GC_CMD_RECT,
            sprite: -1,
            x: center.x,
            y: center.y,
            w,
            h,
            rot,
            rgba,
            flags,
            ..Default::default()
        });
    }

    pub fn rect(&mut self, r: Rect, rgba: u32, flags: i32) {
        self.rect_screen(r.center(), r.w, r.h, 0.0, rgba, flags);
    }

    pub fn rect_world(&mut self, center: Vec2, w: f32, h: f32, rot: f32, rgba: u32, flags: i32) {
        let p = self.world_to_screen(center);
        self.rect_screen(p, w * self.zoom, h * self.zoom, rot, rgba, flags);
    }

    /// A 1px-ish outline drawn as four rects (renderers have no line primitive).
    pub fn outline(&mut self, r: Rect, thickness: f32, rgba: u32) {
        let t = thickness.max(1.0);
        self.rect_screen(Vec2::new(r.x + r.w * 0.5, r.y + t * 0.5), r.w, t, 0.0, rgba, 0);
        self.rect_screen(Vec2::new(r.x + r.w * 0.5, r.y + r.h - t * 0.5), r.w, t, 0.0, rgba, 0);
        self.rect_screen(Vec2::new(r.x + t * 0.5, r.y + r.h * 0.5), t, r.h, 0.0, rgba, 0);
        self.rect_screen(Vec2::new(r.x + r.w - t * 0.5, r.y + r.h * 0.5), t, r.h, 0.0, rgba, 0);
    }

    /// A filled panel: background plus outline.
    pub fn panel(&mut self, r: Rect, fill: u32, edge: u32, thickness: f32) {
        self.rect(r, fill, 0);
        self.outline(r, thickness, edge);
    }

    /// A line between two *world* points, thickness in world units.
    pub fn line_world(&mut self, a: Vec2, b: Vec2, thickness: f32, rgba: u32) {
        let d = b - a;
        let len = d.length();
        if len < 1e-3 {
            return;
        }
        self.rect_world((a + b) * 0.5, len, thickness, d.angle(), rgba, 0);
    }

    pub fn line(&mut self, a: Vec2, b: Vec2, thickness: f32, rgba: u32) {
        let d = b - a;
        let len = d.length();
        if len < 1e-4 {
            return;
        }
        let mid = (a + b) * 0.5;
        self.rect_screen(mid, len, thickness, d.angle(), rgba, 0);
    }

    /// Horizontal progress bar with a background.
    pub fn bar(&mut self, r: Rect, frac: f32, bg: u32, fg: u32, edge: u32) {
        self.rect(r, bg, 0);
        let f = clamp(frac, 0.0, 1.0);
        if f > 0.0 {
            let filled = Rect::new(r.x, r.y, (r.w * f).max(1.0), r.h);
            self.rect(filled, fg, 0);
            // A lighter sliver along the top reads as a highlight at any size.
            let mut hi = Rect::new(filled.x, filled.y, filled.w, (r.h * 0.28).max(1.0));
            hi.h = hi.h.min(filled.h);
            self.rect(hi, fade(color::WHITE, 0.18), 0);
        }
        self.outline(r, 1.0, edge);
    }

    pub fn sprite_screen(&mut self, id: SpriteId, center: Vec2, height: f32, rot: f32,
                         rgba: u32, flags: i32) {
        let w = height * id.aspect();
        self.push(gc_cmd {
            kind: GC_CMD_SPRITE,
            sprite: id.index(),
            x: center.x,
            y: center.y,
            w,
            h: height,
            rot,
            rgba,
            flags,
            ..Default::default()
        });
    }

    pub fn sprite(&mut self, id: SpriteId, world: Vec2, height: f32, rot: f32,
                  rgba: u32, flags: i32) {
        let p = self.world_to_screen(world);
        self.sprite_screen(id, p, height * self.zoom, rot, rgba, flags);
    }

    /// Draws a weapon sprite so that it points at `aim`, offset from the holder.
    pub fn weapon(&mut self, id: SpriteId, world: Vec2, aim: f32, reach: f32,
                  scale: f32, rgba: u32) {
        let dir = Vec2::from_angle(aim);
        let pos = world + dir * reach;
        self.sprite(id, pos, id.design_height() * scale, weapon_rotation_for(aim), rgba, GC_FLAG_NONE);
    }

    // -- text ---------------------------------------------------------------

    pub fn glyph(cp: u32) -> Option<(u16, u16, u16, u16, i16, i16, f32)> {
        if cp < fm::FIRST_CHAR || cp >= fm::FIRST_CHAR + fm::GLYPH_COUNT as u32 {
            return None;
        }
        let (_, x, y, w, h, dx, dy, adv) = fm::GLYPHS[(cp - fm::FIRST_CHAR) as usize];
        Some((x, y, w, h, dx, dy, adv))
    }

    /// Width of a string drawn at `size` (em units), in virtual units.
    pub fn text_width(&self, text: &str, size: f32) -> f32 {
        let s = size / fm::EM_SIZE;
        let mut w = 0.0;
        for ch in text.chars() {
            match Self::glyph(ch as u32) {
                Some((_, _, _, _, _, _, adv)) => w += adv * s,
                None => w += 0.5 * size,
            }
        }
        w
    }

    pub fn line_height(&self, size: f32) -> f32 {
        fm::LINE_HEIGHT * (size / fm::EM_SIZE)
    }

    /// Draws `text` with its top edge at `y`.  `align` is 0 = left, 0.5 = centre,
    /// 1 = right, and `x` is the corresponding anchor.
    ///
    /// Returns the pen position after the last glyph.
    pub fn text(&mut self, text: &str, x: f32, y: f32, size: f32, align: f32,
                rgba: u32, flags: i32) -> f32 {
        let s = size / fm::EM_SIZE;
        let width = self.text_width(text, size);
        let mut pen = x - width * align;
        let baseline = y + fm::ASCENT * s;
        let u_scale = 1.0 / fm::ATLAS_W as f32;
        let v_scale = 1.0 / fm::ATLAS_H as f32;

        for ch in text.chars() {
            match Self::glyph(ch as u32) {
                Some((gx, gy, gw, gh, dx, dy, adv)) => {
                    if gw > 0 && gh > 0 {
                        let w = gw as f32 * s;
                        let h = gh as f32 * s;
                        let left = pen + dx as f32 * s;
                        let top = baseline + dy as f32 * s;
                        self.push(gc_cmd {
                            kind: GC_CMD_GLYPH,
                            sprite: -1,
                            x: left + w * 0.5,
                            y: top + h * 0.5,
                            w,
                            h,
                            rot: 0.0,
                            rgba,
                            u0: gx as f32 * u_scale,
                            v0: gy as f32 * v_scale,
                            u1: (gx as f32 + gw as f32) * u_scale,
                            v1: (gy as f32 + gh as f32) * v_scale,
                            flags,
                            _pad: 0,
                        });
                    }
                    pen += adv * s;
                }
                None => pen += 0.5 * size,
            }
        }
        pen
    }

    pub fn text_center(&mut self, text: &str, cx: f32, y: f32, size: f32, rgba: u32,
                       flags: i32) -> f32 {
        self.text(text, cx, y, size, 0.5, rgba, flags)
    }

    /// Convenience: vertically centres a line of `size` inside `r`.
    pub fn text_in(&mut self, text: &str, r: Rect, size: f32, align: f32, rgba: u32,
                   flags: i32) -> f32 {
        let lh = self.line_height(size);
        let y = r.y + (r.h - lh) * 0.5;
        let x = match align {
            a if a <= 0.0 => r.x,
            a if a >= 1.0 => r.x + r.w,
            _ => r.x + r.w * 0.5,
        };
        self.text(text, x, y, size, align, rgba, flags)
    }
}

// ---------------------------------------------------------------------------
// allocation-free string formatting for HUD text
// ---------------------------------------------------------------------------

/// A tiny fixed-capacity string buffer so that HUD/damage text never allocates.
pub struct Buf<const N: usize> {
    bytes: [u8; N],
    len: usize,
}

impl<const N: usize> Buf<N> {
    pub fn new() -> Buf<N> {
        Buf { bytes: [0; N], len: 0 }
    }

    pub fn as_str(&self) -> &str {
        core::str::from_utf8(&self.bytes[..self.len]).unwrap_or("")
    }
}

impl<const N: usize> core::fmt::Write for Buf<N> {
    fn write_str(&mut self, s: &str) -> core::fmt::Result {
        for b in s.as_bytes() {
            if self.len >= N {
                return Err(core::fmt::Error);
            }
            self.bytes[self.len] = *b;
            self.len += 1;
        }
        Ok(())
    }
}

/// Formats money compactly: $950, $12.4K, $3.1M, $1.2B.  The quota grows
/// exponentially, so the HUD has to stay readable at a glance.
pub fn money_buf(amount: i32) -> Buf<16> {
    use core::fmt::Write as _;
    let mut b = Buf::<16>::new();
    let a = amount.max(0) as f64;
    let _ = if a < 10_000.0 {
        write!(b, "${}", amount.max(0))
    } else if a < 1_000_000.0 {
        write!(b, "${:.1}K", a / 1_000.0)
    } else if a < 1_000_000_000.0 {
        write!(b, "${:.1}M", a / 1_000_000.0)
    } else {
        write!(b, "${:.1}B", a / 1_000_000_000.0)
    };
    b
}

/// `fmt::format`-like helper that writes into a fixed buffer.
#[macro_export]
macro_rules! buf_format {
    ($n:expr, $($arg:tt)*) => {{
        use core::fmt::Write as _;
        let mut b = $crate::render::Buf::<$n>::new();
        let _ = write!(b, $($arg)*);
        b
    }};
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::math::vec2;

    fn test_renderer() -> Renderer {
        Renderer::new(View::new(1280, 720, [0.0; 4]))
    }

    #[test]
    fn view_scale_and_virtual_size() {
        let v = View::new(1280, 720, [0.0; 4]);
        assert!((v.scale - 1.0).abs() < 1e-6);
        assert!((v.virt_w - 1280.0).abs() < 1e-3);
        assert!((v.virt_h - 720.0).abs() < 1e-3);

        // A 2x display keeps the same virtual size at double the pixel scale.
        let v2 = View::new(2560, 1440, [0.0; 4]);
        assert!((v2.scale - 2.0).abs() < 1e-6);
        assert!((v2.virt_w - 1280.0).abs() < 1e-3);
        assert!((v2.virt_h - 720.0).abs() < 1e-3);
    }

    #[test]
    fn safe_area_is_converted_to_virtual_units() {
        let v = View::new(1280, 720, [10.0, 20.0, 30.0, 40.0]);
        assert!((v.safe[0] - 10.0).abs() < 1e-3);
        assert!((v.safe[3] - 40.0).abs() < 1e-3);
        let c = v.content_rect();
        assert!((c.x - 10.0).abs() < 1e-3);
        assert!((c.h - (720.0 - 60.0)).abs() < 1e-3);
    }

    #[test]
    fn camera_maps_world_center_to_screen_center() {
        let mut r = test_renderer();
        r.begin(vec2(500.0, 400.0), 1.0, Vec2::ZERO);
        let p = r.world_to_screen(vec2(500.0, 400.0));
        assert!((p.x - 640.0).abs() < 1e-3);
        assert!((p.y - 360.0).abs() < 1e-3);
        // and back again
        let w = r.screen_to_world(p);
        assert!((w.x - 500.0).abs() < 1e-3);
        assert!((w.y - 400.0).abs() < 1e-3);
    }

    #[test]
    fn text_is_measured_and_split_into_glyphs() {
        let mut r = test_renderer();
        r.begin(Vec2::ZERO, 1.0, Vec2::ZERO);
        let w1 = r.text_width("A", 32.0);
        let w2 = r.text_width("AA", 32.0);
        assert!((w2 - 2.0 * w1).abs() < 0.5, "advances should be linear");
        r.text("AB", 100.0, 50.0, 32.0, 0.0, color::WHITE, 0);
        assert_eq!(r.cmds.len(), 2);
        assert!(r.cmds.iter().all(|c| c.kind == GC_CMD_GLYPH));
        // Glyph UVs must stay inside the atlas.
        for c in &r.cmds {
            assert!(c.u0 >= 0.0 && c.u1 <= 1.0 && c.v0 >= 0.0 && c.v1 <= 1.0);
            assert!(c.u1 > c.u0 && c.v1 > c.v0);
            assert!(c.w > 0.0 && c.h > 0.0);
        }
    }

    #[test]
    fn text_alignment_shifts_the_anchor() {
        let mut r = test_renderer();
        r.begin(Vec2::ZERO, 1.0, Vec2::ZERO);
        r.text("HELLO", 100.0, 0.0, 20.0, 0.0, color::WHITE, 0);
        let left_first = r.cmds[0].x;
        r.begin(Vec2::ZERO, 1.0, Vec2::ZERO);
        r.text("HELLO", 100.0, 0.0, 20.0, 0.5, color::WHITE, 0);
        let centre_first = r.cmds[0].x;
        assert!(centre_first < left_first, "centre alignment must shift left");
    }

    #[test]
    fn command_buffer_is_bounded() {
        let mut r = test_renderer();
        r.begin(Vec2::ZERO, 1.0, Vec2::ZERO);
        for _ in 0..(MAX_CMDS + 128) {
            r.rect(Rect::new(0.0, 0.0, 1.0, 1.0), color::WHITE, 0);
        }
        assert_eq!(r.cmds.len(), MAX_CMDS);
        assert_eq!(r.dropped_commands(), 128);
    }

    #[test]
    fn rect_hit_testing() {
        let r = Rect::new(10.0, 20.0, 100.0, 50.0);
        assert!(r.contains(vec2(10.0, 20.0)));
        assert!(r.contains(vec2(60.0, 45.0)));
        assert!(!r.contains(vec2(9.0, 45.0)));
        assert!(!r.contains(vec2(60.0, 71.0)));
    }

    #[test]
    fn money_reads_well_at_every_scale() {
        assert_eq!(money_buf(0).as_str(), "$0");
        assert_eq!(money_buf(950).as_str(), "$950");
        assert_eq!(money_buf(9_999).as_str(), "$9999");
        assert_eq!(money_buf(12_400).as_str(), "$12.4K");
        assert_eq!(money_buf(3_100_000).as_str(), "$3.1M");
        assert_eq!(money_buf(1_200_000_000).as_str(), "$1.2B");
        // Never longer than the buffer, whatever the value.
        assert!(money_buf(i32::MAX).as_str().len() <= 16);
    }

    #[test]
    fn buf_format_truncates_instead_of_growing() {
        let b = buf_format!(8, "score {}", 123456789);
        assert!(b.as_str().len() <= 8);
        let ok = buf_format!(16, "WAVE {}", 7);
        assert_eq!(ok.as_str(), "WAVE 7");
    }
}
