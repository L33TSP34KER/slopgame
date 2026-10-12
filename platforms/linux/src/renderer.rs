//! The Linux renderer: loads the textures, then blits the command list the
//! shared library produces.
//!
//! Every command is either a textured quad (a sprite, or one glyph from the font
//! atlas) or a solid rectangle.  Positions arrive in *virtual units*; the only
//! transform this renderer applies is a uniform scale to physical pixels.

use crate::core_api::Api;
use crate::png;
use crate::sdl::*;
use game_core::{gc_cmd, GC_CMD_GLYPH, GC_CMD_RECT, GC_CMD_SPRITE, GC_FLAG_FLASH, GC_FLAG_SHADOW};
use std::path::{Path, PathBuf};

pub struct Renderer {
    raw: *mut SdlRenderer,
    /// One texture per `gc_sprite_id`, plus the font atlas and a 1x1 white.
    sprites: Vec<*mut SdlTexture>,
    atlas: *mut SdlTexture,
    atlas_w: f32,
    atlas_h: f32,
    white: *mut SdlTexture,
    /// Pixels per virtual unit, straight from `gc_view_scale`.
    pub scale: f32,
    pub draws: u32,
}

impl Renderer {
    pub fn new(raw: *mut SdlRenderer) -> Renderer {
        Renderer {
            raw,
            sprites: Vec::new(),
            atlas: core::ptr::null_mut(),
            atlas_w: 1.0,
            atlas_h: 1.0,
            white: core::ptr::null_mut(),
            scale: 1.0,
            draws: 0,
        }
    }

    #[allow(dead_code)]
    pub fn raw(&self) -> *mut SdlRenderer {
        self.raw
    }

    fn create_texture(&mut self, image: &png::Image) -> Result<*mut SdlTexture, String> {
        unsafe {
            let tex = SDL_CreateTexture(self.raw, SDL_PIXELFORMAT_ABGR8888,
                                        SDL_TEXTUREACCESS_STATIC,
                                        image.width as i32, image.height as i32);
            if tex.is_null() {
                return Err(format!("SDL_CreateTexture: {}", last_error()));
            }
            if SDL_UpdateTexture(tex, core::ptr::null(), image.pixels.as_ptr() as *const _,
                                 image.row_stride() as i32) != 0 {
                return Err(format!("SDL_UpdateTexture: {}", last_error()));
            }
            SDL_SetTextureBlendMode(tex, SDL_BLENDMODE_BLEND);
            Ok(tex)
        }
    }

    pub fn load_assets(&mut self, api: &Api, handle: *mut game_core::Handle,
                       dir: &Path) -> Result<(), String> {
        // Sprites, in gc_sprite_id order.
        for i in 0..game_core::SPRITE_COUNT as i32 {
            let name = unsafe { Api::cstr((api.sprite_file)(i)) };
            if name.is_empty() {
                return Err(format!("gc_sprite_file({}) returned nothing", i));
            }
            let path = dir.join(&name);
            let image = png::load_rgba(&path.to_string_lossy())?;
            if std::env::var("SLIME_ARENA_VERBOSE").is_ok() {
                println!("slime_arena: sprite {} = {} ({}x{})", i, name, image.width, image.height);
            }
            let tex = self.create_texture(&image)?;
            self.sprites.push(tex);
        }

        // Font atlas.
        let mut file: *const core::ffi::c_char = core::ptr::null();
        let mut w = 0i32;
        let mut h = 0i32;
        unsafe { (api.font_atlas)(&mut file, &mut w, &mut h) };
        let name = unsafe { Api::cstr(file) };
        let path = dir.join(&name);
        let image = png::load_rgba(&path.to_string_lossy())?;
        self.atlas = self.create_texture(&image)?;
        self.atlas_w = w.max(1) as f32;
        self.atlas_h = h.max(1) as f32;
        if image.width as i32 != w || image.height as i32 != h {
            return Err(format!(
                "font atlas mismatch: library says {}x{}, {} is {}x{}",
                w, h, name, image.width, image.height));
        }

        // 1x1 white texture: lets solid rectangles share the textured pipeline.
        let white = png::Image { width: 1, height: 1, pixels: vec![255, 255, 255, 255] };
        self.white = self.create_texture(&white)?;

        let _ = handle;
        Ok(())
    }

    pub fn clear(&mut self) {
        unsafe {
            SDL_SetRenderDrawBlendMode(self.raw, SDL_BLENDMODE_NONE);
            SDL_SetRenderDrawColor(self.raw, 8, 8, 12, 255);
            SDL_RenderClear(self.raw);
        }
    }

    pub fn present(&mut self) {
        unsafe { SDL_RenderPresent(self.raw) };
    }

    /// Draws the command list.  Commands are already sorted back-to-front.
    pub fn draw(&mut self, cmds: &[gc_cmd]) {
        let s = self.scale;
        self.draws = 0;
        for cmd in cmds {
            match cmd.kind {
                GC_CMD_SPRITE => {
                    if (cmd.sprite as usize) < self.sprites.len() {
                        let tex = self.sprites[cmd.sprite as usize];
                        self.blit(tex, cmd, s, None);
                    }
                }
                GC_CMD_RECT => {
                    // Solid colour via the 1x1 white texture rather than
                    // SDL_RenderFillRectF: the fill call cannot rotate, and the
                    // command list uses rotation for lines, hexagon edges and
                    // bullets.  This also keeps rects on the same blend path as
                    // sprites (BLEND vs ADD for GC_FLAG_FLASH).
                    if !self.white.is_null() {
                        self.blit(self.white, cmd, s, None);
                    }
                }
                GC_CMD_GLYPH => {
                    if self.atlas.is_null() {
                        continue;
                    }
                    // NOTE: SDL_RenderCopy*F takes an *integer* source rect even
                    // in its float variant -- only the destination is float.
                    let src = SdlRect {
                        x: (cmd.u0 * self.atlas_w).round() as i32,
                        y: (cmd.v0 * self.atlas_h).round() as i32,
                        w: ((cmd.u1 - cmd.u0) * self.atlas_w).round().max(1.0) as i32,
                        h: ((cmd.v1 - cmd.v0) * self.atlas_h).round().max(1.0) as i32,
                    };
                    let tex = self.atlas;
                    self.blit(tex, cmd, s, Some(src));
                }
                _ => {}
            }
        }
    }

    fn blit(&mut self, tex: *mut SdlTexture, cmd: &gc_cmd, s: f32, src: Option<SdlRect>) {
        let (r, g, b, a) = unpack(cmd.rgba);
        let additive = cmd.flags & GC_FLAG_FLASH != 0;
        unsafe {
            SDL_SetTextureBlendMode(tex, if additive { SDL_BLENDMODE_ADD } else { SDL_BLENDMODE_BLEND });
            SDL_SetTextureColorMod(tex, r, g, b);
            SDL_SetTextureAlphaMod(tex, a);

            if cmd.flags & GC_FLAG_SHADOW != 0 {
                SDL_SetTextureColorMod(tex, 0, 0, 0);
                SDL_SetTextureAlphaMod(tex, (a as f32 * 0.55) as u8);
                let shadow = rect_of(cmd, s, 0.0, 2.0);
                let center = center_of(cmd, s);
                SDL_RenderCopyExF(self.raw, tex, src_ptr(&src), &shadow,
                                  (cmd.rot as f64).to_degrees(), &center, SDL_FLIP_NONE);
                SDL_SetTextureColorMod(tex, r, g, b);
                SDL_SetTextureAlphaMod(tex, a);
            }

            let dst = rect_of(cmd, s, 0.0, 0.0);
            let center = center_of(cmd, s);
            let rc = SDL_RenderCopyExF(self.raw, tex, src_ptr(&src), &dst,
                                       (cmd.rot as f64).to_degrees(), &center, SDL_FLIP_NONE);
            if rc != 0 {
                eprintln!("slime_arena: SDL_RenderCopyExF: {}", last_error());
            }
            self.draws += 1;
        }
    }

    /// Diagnostic: draws every texture at a known place with a test pattern, so
    /// the upload path can be verified independently of the game.
    pub fn diag_textures(&mut self, path: &Path, width: i32, height: i32) -> Result<(), String> {
        unsafe {
            SDL_SetRenderDrawBlendMode(self.raw, SDL_BLENDMODE_NONE);
            SDL_SetRenderDrawColor(self.raw, 0, 0, 0, 255);
            SDL_RenderClear(self.raw);
        }
        // Reference blocks: pure red, green, blue, white, 50% white.
        let refs = [(255u8, 0u8, 0u8, 255u8), (0, 255, 0, 255), (0, 0, 255, 255),
                    (255, 255, 255, 255), (255, 255, 255, 128)];
        unsafe {
            SDL_SetRenderDrawBlendMode(self.raw, SDL_BLENDMODE_BLEND);
            for (i, (r, g, b, a)) in refs.iter().enumerate() {
                SDL_SetRenderDrawColor(self.raw, *r, *g, *b, *a);
                let rect = SdlFRect { x: 20.0 + i as f32 * 90.0, y: 20.0, w: 80.0, h: 80.0 };
                SDL_RenderFillRectF(self.raw, &rect);
            }
        }
        // Every sprite, at 120 px tall, left to right.
        for (i, tex) in self.sprites.iter().enumerate() {
            let dst = SdlFRect { x: 30.0 + i as f32 * 140.0, y: 160.0, w: 120.0, h: 120.0 };
            unsafe {
                SDL_SetTextureBlendMode(*tex, SDL_BLENDMODE_BLEND);
                SDL_SetTextureColorMod(*tex, 255, 255, 255);
                SDL_SetTextureAlphaMod(*tex, 255);
                SDL_RenderCopyF(self.raw, *tex, core::ptr::null(), &dst);
            }
        }
        // The font atlas, full width, at the bottom.
        if !self.atlas.is_null() {
            let dst = SdlFRect { x: 20.0, y: 320.0, w: 1024.0, h: 208.0 };
            unsafe {
                SDL_SetTextureBlendMode(self.atlas, SDL_BLENDMODE_BLEND);
                SDL_SetTextureColorMod(self.atlas, 255, 255, 255);
                SDL_SetTextureAlphaMod(self.atlas, 255);
                SDL_RenderCopyF(self.raw, self.atlas, core::ptr::null(), &dst);
            }
        }
        self.capture(path, width, height)
    }

    /// Reads the rendered frame back and writes it as a PNG.
    pub fn capture(&self, path: &Path, width: i32, height: i32) -> Result<(), String> {
        let mut buf = vec![0u8; (width as usize) * (height as usize) * 4];
        unsafe {
            let rc = SDL_RenderReadPixels(self.raw, core::ptr::null(), SDL_PIXELFORMAT_ARGB8888,
                                          buf.as_mut_ptr() as *mut _, width * 4);
            if rc != 0 {
                return Err(format!("SDL_RenderReadPixels: {}", last_error()));
            }
        }
        // SDL_PIXELFORMAT_ARGB8888 is B,G,R,A in memory on little endian hosts;
        // PNG wants R,G,B,A.
        for px in buf.chunks_exact_mut(4) {
            px.swap(0, 2);
        }
        png::write_rgba(&path.to_string_lossy(), width as u32, height as u32, &buf)
    }
}

fn src_ptr(src: &Option<SdlRect>) -> *const SdlRect {
    match src {
        Some(r) => r as *const SdlRect,
        None => core::ptr::null(),
    }
}

/// Destination rectangle in physical pixels, optionally nudged for a shadow.
fn rect_of(cmd: &gc_cmd, s: f32, dx: f32, dy: f32) -> SdlFRect {
    SdlFRect {
        x: (cmd.x - cmd.w * 0.5) * s + dx * s,
        y: (cmd.y - cmd.h * 0.5) * s + dy * s,
        w: cmd.w * s,
        h: cmd.h * s,
    }
}

/// Rotation centre, relative to the destination rect (its own middle).
fn center_of(cmd: &gc_cmd, s: f32) -> SdlFPoint {
    SdlFPoint { x: cmd.w * s * 0.5, y: cmd.h * s * 0.5 }
}

fn unpack(rgba: u32) -> (u8, u8, u8, u8) {
    (
        ((rgba >> 16) & 0xff) as u8,
        ((rgba >> 8) & 0xff) as u8,
        (rgba & 0xff) as u8,
        ((rgba >> 24) & 0xff) as u8,
    )
}

/// Where to find `assets/dist`, most specific first.
pub fn asset_dir_candidates(explicit: Option<&str>) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Some(dir) = explicit {
        out.push(PathBuf::from(dir));
    }
    if let Ok(dir) = std::env::var("SLIME_ARENA_ASSETS") {
        out.push(PathBuf::from(dir));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            out.push(dir.join("assets/dist"));
            out.push(dir.join("assets"));
            if let Some(root) = dir.parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
                out.push(root.join("assets/dist"));
            }
        }
    }
    out.push(PathBuf::from("assets/dist"));
    out.push(PathBuf::from("../../assets/dist"));
    out
}
