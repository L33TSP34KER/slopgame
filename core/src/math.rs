//! Minimal vector maths and a small deterministic RNG.
//!
//! The simulation is dependency free on purpose (it has to cross compile to
//! every platform), so this replaces what would otherwise be glam + rand.

// Some of this module is internal API used by tests or by other
// platforms' renderers, so unused-in-this-build items are expected.
#![allow(dead_code)]

use core::ops::{Add, AddAssign, Div, Mul, MulAssign, Neg, Sub, SubAssign};

pub const TAU: f32 = core::f32::consts::TAU;
pub const PI: f32 = core::f32::consts::PI;

#[derive(Copy, Clone, Debug, Default, PartialEq)]
pub struct Vec2 {
    pub x: f32,
    pub y: f32,
}

pub const fn vec2(x: f32, y: f32) -> Vec2 {
    Vec2 { x, y }
}

impl Vec2 {
    pub const ZERO: Vec2 = Vec2 { x: 0.0, y: 0.0 };
    pub const X: Vec2 = Vec2 { x: 1.0, y: 0.0 };
    pub const Y: Vec2 = Vec2 { x: 0.0, y: 1.0 };

    pub const fn new(x: f32, y: f32) -> Vec2 {
        Vec2 { x, y }
    }

    pub const fn splat(v: f32) -> Vec2 {
        Vec2 { x: v, y: v }
    }

    pub fn from_angle(a: f32) -> Vec2 {
        Vec2 { x: a.cos(), y: a.sin() }
    }

    pub fn length(self) -> f32 {
        (self.x * self.x + self.y * self.y).sqrt()
    }

    pub fn length_sq(self) -> f32 {
        self.x * self.x + self.y * self.y
    }

    pub fn distance(self, other: Vec2) -> f32 {
        (self - other).length()
    }

    pub fn distance_sq(self, other: Vec2) -> f32 {
        (self - other).length_sq()
    }

    pub fn dot(self, other: Vec2) -> f32 {
        self.x * other.x + self.y * other.y
    }

    /// 90 degrees counter clockwise in a y-down space.
    pub fn perp(self) -> Vec2 {
        Vec2 { x: -self.y, y: self.x }
    }

    pub fn normalize_or_zero(self) -> Vec2 {
        let len = self.length();
        if len > 1e-6 {
            self / len
        } else {
            Vec2::ZERO
        }
    }

    pub fn angle(self) -> f32 {
        self.y.atan2(self.x)
    }

    pub fn rotate(self, radians: f32) -> Vec2 {
        let (s, c) = radians.sin_cos();
        Vec2 { x: self.x * c - self.y * s, y: self.x * s + self.y * c }
    }

    pub fn clamp_length(self, max: f32) -> Vec2 {
        let len = self.length();
        if !len.is_finite() {
            // A NaN length would otherwise propagate into every position.
            return Vec2::ZERO;
        }
        if len > max && len > 1e-6 {
            self * (max / len)
        } else {
            self
        }
    }

    pub fn lerp(self, other: Vec2, t: f32) -> Vec2 {
        self + (other - self) * t
    }

    pub fn is_finite(self) -> bool {
        self.x.is_finite() && self.y.is_finite()
    }
}

impl Add for Vec2 {
    type Output = Vec2;
    fn add(self, rhs: Vec2) -> Vec2 {
        Vec2 { x: self.x + rhs.x, y: self.y + rhs.y }
    }
}

impl AddAssign for Vec2 {
    fn add_assign(&mut self, rhs: Vec2) {
        self.x += rhs.x;
        self.y += rhs.y;
    }
}

impl Sub for Vec2 {
    type Output = Vec2;
    fn sub(self, rhs: Vec2) -> Vec2 {
        Vec2 { x: self.x - rhs.x, y: self.y - rhs.y }
    }
}

impl SubAssign for Vec2 {
    fn sub_assign(&mut self, rhs: Vec2) {
        self.x -= rhs.x;
        self.y -= rhs.y;
    }
}

impl Mul<f32> for Vec2 {
    type Output = Vec2;
    fn mul(self, rhs: f32) -> Vec2 {
        Vec2 { x: self.x * rhs, y: self.y * rhs }
    }
}

impl Mul<Vec2> for f32 {
    type Output = Vec2;
    fn mul(self, rhs: Vec2) -> Vec2 {
        rhs * self
    }
}

impl MulAssign<f32> for Vec2 {
    fn mul_assign(&mut self, rhs: f32) {
        self.x *= rhs;
        self.y *= rhs;
    }
}

impl Div<f32> for Vec2 {
    type Output = Vec2;
    fn div(self, rhs: f32) -> Vec2 {
        Vec2 { x: self.x / rhs, y: self.y / rhs }
    }
}

impl Neg for Vec2 {
    type Output = Vec2;
    fn neg(self) -> Vec2 {
        Vec2 { x: -self.x, y: -self.y }
    }
}

pub fn clamp(v: f32, lo: f32, hi: f32) -> f32 {
    if v < lo {
        lo
    } else if v > hi {
        hi
    } else {
        v
    }
}

pub fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// Frame-rate independent exponential smoothing.
pub fn damp(current: f32, target: f32, rate: f32, dt: f32) -> f32 {
    lerp(current, target, 1.0 - (-rate * dt).exp())
}

pub fn damp_vec(current: Vec2, target: Vec2, rate: f32, dt: f32) -> Vec2 {
    current.lerp(target, 1.0 - (-rate * dt).exp())
}

/// Shortest signed difference between two angles, in (-PI, PI].
pub fn angle_delta(from: f32, to: f32) -> f32 {
    let mut d = (to - from) % TAU;
    if d > PI {
        d -= TAU;
    } else if d < -PI {
        d += TAU;
    }
    d
}

/// xorshift64* -- small, fast, and deterministic across platforms.  Determinism
/// matters because `gc_create(seed)` is documented to reproduce a run exactly.
#[derive(Clone, Debug)]
pub struct Rng {
    state: u64,
}

impl Rng {
    pub fn new(seed: u32) -> Rng {
        // Avoid the all-zero state.
        Rng { state: 0x9E37_79B9_7F4A_7C15 ^ (seed as u64).wrapping_mul(0x2545_F491_4F6C_DD1D) | 1 }
    }

    pub fn next_u64(&mut self) -> u64 {
        let mut x = self.state;
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        self.state = x;
        x.wrapping_mul(0x2545_F491_4F6C_DD1D)
    }

    pub fn next_u32(&mut self) -> u32 {
        (self.next_u64() >> 32) as u32
    }

    /// Uniform in [0, 1).
    pub fn next_f32(&mut self) -> f32 {
        (self.next_u32() >> 8) as f32 / (1u32 << 24) as f32
    }

    /// Uniform in [lo, hi).
    pub fn range(&mut self, lo: f32, hi: f32) -> f32 {
        lo + self.next_f32() * (hi - lo)
    }

    /// Uniform in [lo, hi].
    pub fn range_i(&mut self, lo: i32, hi: i32) -> i32 {
        if hi <= lo {
            return lo;
        }
        lo + (self.next_u32() % ((hi - lo + 1) as u32)) as i32
    }

    pub fn chance(&mut self, p: f32) -> bool {
        self.next_f32() < p
    }

    pub fn angle(&mut self) -> f32 {
        self.next_f32() * TAU
    }

    pub fn sign(&mut self) -> f32 {
        if self.next_u32() & 1 == 0 {
            1.0
        } else {
            -1.0
        }
    }

    /// Unit vector with a uniformly distributed direction.
    pub fn unit_vec(&mut self) -> Vec2 {
        Vec2::from_angle(self.angle())
    }

    /// Picks one element, or None for an empty slice.
    pub fn choose<'a, T>(&mut self, items: &'a [T]) -> Option<&'a T> {
        if items.is_empty() {
            None
        } else {
            Some(&items[self.next_u32() as usize % items.len()])
        }
    }
}
