//! libpng "simplified API" bindings, used to decode the sprite textures and to
//! write PNG screenshots.
//!
//! Using libpng directly (rather than SDL_image) keeps the dependency list to
//! exactly one library that is present on any desktop Linux install.

#![allow(non_camel_case_types)]
#![allow(dead_code)]

use core::ffi::{c_char, c_int, c_void, CStr};
use std::ffi::CString;

/// PNG_IMAGE_VERSION
const PNG_IMAGE_VERSION: u32 = 1;
const PNG_FORMAT_RGBA: u32 = 0x03;

#[repr(C)]
struct PngImage {
    opaque: *mut c_void,
    version: u32,
    width: u32,
    height: u32,
    format: u32,
    flags: u32,
    colormap_entries: u32,
    warning_or_error: u32,
    message: [c_char; 64],
}

impl PngImage {
    fn new() -> PngImage {
        PngImage {
            opaque: core::ptr::null_mut(),
            version: PNG_IMAGE_VERSION,
            width: 0,
            height: 0,
            format: PNG_FORMAT_RGBA,
            flags: 0,
            colormap_entries: 0,
            warning_or_error: 0,
            message: [0; 64],
        }
    }

    fn message(&self) -> String {
        unsafe { CStr::from_ptr(self.message.as_ptr()) }.to_string_lossy().into_owned()
    }
}

#[link(name = "png16")]
extern "C" {
    fn png_image_begin_read_from_file(image: *mut PngImage, file_name: *const c_char) -> c_int;
    fn png_image_finish_read(image: *mut PngImage, background: *const c_void,
                             buffer: *mut c_void, row_stride: i32,
                             colormap: *mut c_void) -> c_int;
    fn png_image_free(image: *mut PngImage);
    fn png_image_write_to_file(image: *mut PngImage, file: *const c_char,
                               convert_to_8bit: c_int, buffer: *const c_void,
                               row_stride: i32, colormap: *const c_void) -> c_int;
}

/// An RGBA8 image in memory.
pub struct Image {
    pub width: u32,
    pub height: u32,
    /// R,G,B,A per pixel, tightly packed.
    pub pixels: Vec<u8>,
}

impl Image {
    pub fn row_stride(&self) -> u32 {
        self.width * 4
    }
}

/// Decodes a PNG into straight (non-premultiplied) RGBA8.
pub fn load_rgba(path: &str) -> Result<Image, String> {
    let c_path = CString::new(path).map_err(|_| "path contains a NUL byte".to_string())?;
    let mut image = PngImage::new();
    unsafe {
        if png_image_begin_read_from_file(&mut image, c_path.as_ptr()) == 0 {
            let msg = image.message();
            png_image_free(&mut image);
            return Err(format!("{}: {}", path, msg));
        }
        let (w, h) = (image.width, image.height);
        if w == 0 || h == 0 || w > 8192 || h > 8192 {
            png_image_free(&mut image);
            return Err(format!("{}: implausible size {}x{}", path, w, h));
        }
        let mut pixels = vec![0u8; (w as usize) * (h as usize) * 4];
        if png_image_finish_read(&mut image, core::ptr::null(), pixels.as_mut_ptr() as *mut c_void,
                                 0, core::ptr::null_mut()) == 0 {
            let msg = image.message();
            png_image_free(&mut image);
            return Err(format!("{}: {}", path, msg));
        }
        png_image_free(&mut image);
        Ok(Image { width: w, height: h, pixels })
    }
}

/// Writes a tightly packed RGBA8 buffer out as a PNG.
pub fn write_rgba(path: &str, width: u32, height: u32, pixels: &[u8]) -> Result<(), String> {
    let c_path = CString::new(path).map_err(|_| "path contains a NUL byte".to_string())?;
    let mut image = PngImage::new();
    image.width = width;
    image.height = height;
    unsafe {
        if png_image_write_to_file(&mut image, c_path.as_ptr(), 0,
                                   pixels.as_ptr() as *const c_void, 0,
                                   core::ptr::null()) == 0 {
            return Err(format!("{}: {}", path, image.message()));
        }
    }
    Ok(())
}
