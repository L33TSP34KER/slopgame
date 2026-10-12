//! Player settings: the options menu.
//!
//! Kept in the core, not the renderer, for two reasons.  The menu has to look
//! and behave the same on every platform (the layout is the library's job), and
//! most of these are *gameplay* switches -- screen shake, damage numbers,
//! particle density, reduced flashing, aim assist -- that only the simulation
//! can honour.  The renderer reads the ones it owns (volumes, fullscreen,
//! haptics) through `gc_settings_get()`.

/// How many rows the options screen has.
pub const ROWS: usize = 11;
/// Rows from here on are buttons rather than values.
pub const FIRST_ACTION: usize = 9;
pub const ROW_RESET: usize = 9;
pub const ROW_BACK: usize = 10;

/// What a row does, which decides how it is drawn and clicked.
#[derive(Copy, Clone, PartialEq, Eq, Debug)]
pub enum RowKind {
    /// 0..max, drawn as a bar with arrows.
    Slider(i32),
    /// Two-state switch.
    Toggle,
    /// Three-state switch with named values.
    Choice,
    /// A button.
    Action,
}

#[derive(Copy, Clone)]
pub struct Row {
    pub label: &'static str,
    /// One short line explaining the tradeoff, shown on the highlighted row.
    pub hint: &'static str,
    pub kind: RowKind,
}

pub const fn row(label: &'static str, hint: &'static str, kind: RowKind) -> Row {
    Row { label, hint, kind }
}

/// The options, in order.
pub fn rows() -> [Row; ROWS] {
    use RowKind::*;
    [
        row("MUSIC VOLUME", "How loud the soundtrack is.", Slider(10)),
        row("SOUND EFFECTS", "Shots, hits, pickups and the rest.", Slider(10)),
        row("HAPTICS", "Vibration on phones and tablets.", Toggle),
        row("SCREEN SHAKE", "How hard the camera kicks. Zero is calmest.", Slider(10)),
        row("DAMAGE NUMBERS", "Floating numbers over everything you hit.", Toggle),
        row("PARTICLES", "Fewer sparks, more frames on weak hardware.", Choice),
        row("FLASHING", "Reduced keeps bright effects dimmer.", Choice),
        row("AIM ASSIST", "Nudges your aim toward the nearest enemy.", Toggle),
        row("FULLSCREEN", "Borderless or windowed, where supported.", Toggle),
        row("RESTORE DEFAULTS", "Puts every setting back as it ships.", Action),
        row("BACK", "Return to the previous screen.", Action),
    ]
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Settings {
    /// 0..=10, as a fraction of full scale.
    pub music: i32,
    pub sfx: i32,
    pub haptics: bool,
    pub shake: i32,
    pub damage_numbers: bool,
    /// 0 = low, 1 = medium, 2 = high.
    pub particles: i32,
    /// 0 = full flashing, 1 = reduced.
    pub flashing: i32,
    pub aim_assist: bool,
    pub fullscreen: bool,
}

impl Default for Settings {
    fn default() -> Settings {
        Settings {
            music: 6,
            sfx: 8,
            haptics: true,
            shake: 6,
            damage_numbers: true,
            particles: 2,
            flashing: 0,
            aim_assist: true,
            // Never start fullscreen: a first launch that takes over the screen
            // is worse than one the player can enlarge.
            fullscreen: false,
        }
    }
}

impl Settings {
    pub fn music_norm(&self) -> f32 {
        self.music.clamp(0, 10) as f32 / 10.0
    }

    pub fn sfx_norm(&self) -> f32 {
        self.sfx.clamp(0, 10) as f32 / 10.0
    }

    /// 0 disables shake entirely, 6 is the shipped default, 10 is punchier.
    pub fn shake_scale(&self) -> f32 {
        self.shake.clamp(0, 10) as f32 / 6.0
    }

    /// Multiplier applied to how many particles an effect spawns.
    pub fn particle_scale(&self) -> f32 {
        match self.particles.clamp(0, 2) {
            0 => 0.35,
            1 => 0.7,
            _ => 1.0,
        }
    }

    pub fn reduce_flash(&self) -> bool {
        self.flashing >= 1
    }

    /// The value of a row, as the menu shows it.
    pub fn value_text(&self, index: usize) -> [u8; 24] {
        let mut out = [0u8; 24];
        let text: &str = match index {
            0 => return number(&mut out, self.music),
            1 => return number(&mut out, self.sfx),
            2 => if self.haptics { "ON" } else { "OFF" },
            3 => return number(&mut out, self.shake),
            4 => if self.damage_numbers { "ON" } else { "OFF" },
            5 => match self.particles {
                0 => "LOW",
                1 => "MEDIUM",
                _ => "HIGH",
            },
            6 => if self.reduce_flash() { "REDUCED" } else { "FULL" },
            7 => if self.aim_assist { "ON" } else { "OFF" },
            8 => if self.fullscreen { "ON" } else { "OFF" },
            _ => "",
        };
        copy_into(&mut out, text);
        out
    }

    /// Nudges a row left (`dir < 0`) or right.
    pub fn adjust(&mut self, index: usize, dir: i32) {
        match index {
            0 => self.music = (self.music + dir).clamp(0, 10),
            1 => self.sfx = (self.sfx + dir).clamp(0, 10),
            2 => self.haptics = !self.haptics,
            3 => self.shake = (self.shake + dir).clamp(0, 10),
            4 => self.damage_numbers = !self.damage_numbers,
            5 => self.particles = (self.particles + dir).clamp(0, 2),
            6 => self.flashing = (self.flashing + dir).clamp(0, 1),
            7 => self.aim_assist = !self.aim_assist,
            8 => self.fullscreen = !self.fullscreen,
            _ => {}
        }
    }

    /// Sets a 0..=1 fraction on a slider row (used when dragging the bar).
    pub fn set_fraction(&mut self, index: usize, fraction: f32) {
        let f = fraction.clamp(0.0, 1.0);
        match index {
            0 => self.music = (f * 10.0).round() as i32,
            1 => self.sfx = (f * 10.0).round() as i32,
            3 => self.shake = (f * 10.0).round() as i32,
            _ => {}
        }
    }

    /// Fraction shown on a slider row.
    pub fn fraction(&self, index: usize) -> f32 {
        match index {
            0 => self.music as f32 / 10.0,
            1 => self.sfx as f32 / 10.0,
            3 => self.shake as f32 / 10.0,
            _ => 0.0,
        }
    }

    /// True for rows that are a value (slider/switch) rather than a button.
    pub fn is_value(index: usize) -> bool {
        index < FIRST_ACTION
    }

    /// Encodes into the tail of the save blob.
    pub fn encode(&self) -> [u8; 12] {
        let mut out = [0u8; 12];
        out[0] = self.music.clamp(0, 10) as u8;
        out[1] = self.sfx.clamp(0, 10) as u8;
        out[2] = self.haptics as u8;
        out[3] = self.shake.clamp(0, 10) as u8;
        out[4] = self.damage_numbers as u8;
        out[5] = self.particles.clamp(0, 2) as u8;
        out[6] = self.flashing.clamp(0, 1) as u8;
        out[7] = self.aim_assist as u8;
        out[8] = self.fullscreen as u8;
        out
    }

    /// Decodes the tail of a save blob, tolerating older/shorter saves.
    pub fn decode(bytes: &[u8]) -> Settings {
        let mut s = Settings::default();
        if bytes.len() < 12 {
            return s;
        }
        s.music = (bytes[0] as i32).min(10);
        s.sfx = (bytes[1] as i32).min(10);
        s.haptics = bytes[2] != 0;
        s.shake = (bytes[3] as i32).min(10);
        s.damage_numbers = bytes[4] != 0;
        s.particles = (bytes[5] as i32).min(2);
        s.flashing = (bytes[6] as i32).min(1);
        s.aim_assist = bytes[7] != 0;
        s.fullscreen = bytes[8] != 0;
        s
    }
}

fn copy_into(out: &mut [u8; 24], text: &str) {
    let bytes = text.as_bytes();
    let n = bytes.len().min(out.len() - 1);
    out[..n].copy_from_slice(&bytes[..n]);
    out[n] = 0;
}

fn number(out: &mut [u8; 24], value: i32) -> [u8; 24] {
    // Two digits at most, so this needs no formatter.
    let v = value.clamp(0, 99);
    let mut n = 0;
    if v >= 10 {
        out[n] = b'0' + (v / 10) as u8;
        n += 1;
    }
    out[n] = b'0' + (v % 10) as u8;
    n += 1;
    out[n] = 0;
    *out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_row_is_described_and_reachable() {
        let r = rows();
        assert_eq!(r.len(), ROWS);
        for (i, row) in r.iter().enumerate() {
            assert!(!row.label.is_empty(), "row {i} has no label");
            assert!(!row.hint.is_empty(), "row {i} has no hint");
            if Settings::is_value(i) {
                assert_ne!(row.kind, RowKind::Action, "row {i} is a value row");
            } else {
                assert_eq!(row.kind, RowKind::Action, "row {i} is an action row");
            }
        }
    }

    #[test]
    fn adjustments_stay_inside_their_range() {
        let mut s = Settings::default();
        // Sliders clamp instead of wrapping.
        for _ in 0..50 {
            s.adjust(0, -1);
            s.adjust(1, -1);
            s.adjust(3, -1);
            s.adjust(5, -1);
        }
        assert_eq!((s.music, s.sfx, s.shake, s.particles), (0, 0, 0, 0));
        for _ in 0..50 {
            s.adjust(0, 1);
            s.adjust(1, 1);
            s.adjust(3, 1);
            s.adjust(5, 1);
        }
        assert_eq!((s.music, s.sfx, s.shake, s.particles), (10, 10, 10, 2));
        // Toggles flip both ways and come back.
        let before = s.damage_numbers;
        s.adjust(4, 1);
        assert_ne!(s.damage_numbers, before);
        s.adjust(4, 1);
        assert_eq!(s.damage_numbers, before);
        // Actions do nothing at all.
        let snapshot = s;
        s.adjust(ROW_RESET, 1);
        s.adjust(ROW_BACK, -1);
        assert_eq!(s, snapshot);
    }

    #[test]
    fn fractions_map_to_slider_values() {
        let mut s = Settings::default();
        s.set_fraction(0, 0.0);
        assert_eq!(s.music, 0);
        s.set_fraction(0, 1.0);
        assert_eq!(s.music, 10);
        s.set_fraction(0, 0.55);
        assert_eq!(s.music, 6);
        // Out-of-range drags are clamped, not wrapped.
        s.set_fraction(3, -5.0);
        assert_eq!(s.shake, 0);
        assert!((Settings::default().fraction(0) - 0.6).abs() < 1e-6);
    }

    #[test]
    fn scaling_helpers_are_sane() {
        let d = Settings::default();
        assert!((d.particle_scale() - 1.0).abs() < 1e-6);
        assert!((d.shake_scale() - 1.0).abs() < 1e-6);
        let mut low = Settings::default();
        low.particles = 0;
        low.shake = 0;
        assert!(low.particle_scale() < d.particle_scale());
        assert_eq!(low.shake_scale(), 0.0, "zero shake must mean no shake");
        assert!(!d.reduce_flash());
        let mut calm = Settings::default();
        calm.flashing = 1;
        assert!(calm.reduce_flash());
    }

    #[test]
    fn settings_round_trip_through_the_save_blob() {
        let mut s = Settings::default();
        s.music = 3;
        s.sfx = 9;
        s.haptics = false;
        s.shake = 2;
        s.damage_numbers = false;
        s.particles = 1;
        s.flashing = 1;
        s.aim_assist = false;
        s.fullscreen = true;
        let encoded = s.encode();
        assert_eq!(Settings::decode(&encoded), s);
        // An old, shorter save keeps the shipped defaults.
        assert_eq!(Settings::decode(&[0u8; 4]), Settings::default());
        assert_eq!(Settings::decode(&[]), Settings::default());
        // And nonsense values cannot escape their range.
        let junk = [200u8; 12];
        let d = Settings::decode(&junk);
        assert!(d.music <= 10 && d.sfx <= 10 && d.shake <= 10 && d.particles <= 2);
    }

    #[test]
    fn value_text_is_null_terminated_ascii() {
        let s = Settings::default();
        for i in 0..ROWS {
            let text = s.value_text(i);
            let end = text.iter().position(|b| *b == 0).expect("unterminated");
            assert!(text[..end].iter().all(|b| b.is_ascii_graphic() || *b == b' '),
                    "row {i} has odd characters");
            if Settings::is_value(i) {
                assert!(end > 0, "row {i} shows nothing");
            }
        }
    }
}
