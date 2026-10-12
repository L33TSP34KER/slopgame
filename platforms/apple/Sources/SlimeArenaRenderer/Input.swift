//
//  Input.swift
//  SlimeArenaRenderer
//
//  Platform-neutral input state plus the two translation rules every shell
//  shares: pointer -> virtual units, and touches -> move axis / aim vector.
//
//  COORDINATE RULES (the whole reason this file exists)
//  ---------------------------------------------------
//  The library works in VIRTUAL units, y-DOWN, origin at the framebuffer's
//  top-left.  pixel = virtual * gc_view_scale().
//
//    * UIKit already reports touches in a y-DOWN coordinate system, so an iOS
//      touch only needs `point * displayScale / viewScale` — no flip.
//    * AppKit reports mouse positions in a y-UP coordinate system (points),
//      so macOS must flip: `py = (boundsHeight - point.y) * backingScaleFactor`
//      before dividing by `viewScale`.
//
//  The joystick maths lives here (not in the iOS target) so that it is one
//  implementation, testable from either platform, and so the DASH/PAUSE/RESTART
//  bitmask has exactly one definition.
//

import Foundation

// MARK: - Pixel / virtual conversion

public enum GCCoordinates {
    /// Pixels -> virtual units.  Mirrors the header's static inline
    /// `gc_pixels_to_virtual`, which Swift cannot import reliably.
    @inline(__always)
    public static func pixelsToVirtual(_ pixels: SIMD2<Float>, scale: Float) -> SIMD2<Float> {
        let s = scale > 0 ? scale : 1
        return pixels / s
    }

    /// Virtual units -> pixels.  Mirrors `gc_virtual_to_pixels`.
    @inline(__always)
    public static func virtualToPixels(_ virtual: SIMD2<Float>, scale: Float) -> SIMD2<Float> {
        virtual * (scale > 0 ? scale : 1)
    }

    /// AppKit (y-up points) -> framebuffer pixels (y-down), including the
    /// backing scale factor.  `viewPoint` must already be in the flipped-down
    /// view space (i.e. `convert(_:from: nil)` on an NSView with
    /// `isFlipped == false`).
    ///
    ///   px =  viewPoint.x            * backingScaleFactor
    ///   py = (viewHeight - viewPoint.y) * backingScaleFactor
    ///
    /// `viewHeight` is in points, which is why the flip happens before the
    /// scale is applied: both operations are linear and commute, but flipping
    /// in points keeps the arithmetic readable.
    @inline(__always)
    public static func appKitPointToPixels(
        _ viewPoint: CGPoint,
        viewHeightInPoints: CGFloat,
        backingScaleFactor: CGFloat
    ) -> SIMD2<Float> {
        let px = Float(viewPoint.x * backingScaleFactor)
        let py = Float((viewHeightInPoints - viewPoint.y) * backingScaleFactor)
        return SIMD2(px, py)
    }
}

// MARK: - Virtual joystick

/// Floating virtual stick: the origin is wherever the finger landed, and the
/// axis is the offset from that origin, dead-zoned and clamped.
///
/// The y axis is NOT inverted anywhere in this type: touch coordinates are
/// y-down and the library's virtual space is y-down, so a finger dragged down
/// produces a positive `moveY`.  If the game ever ships with an inverted
/// look/feel control, negate `moveY` at the call site — do not flip here.
public struct VirtualJoystick: Equatable {
    /// Radius in the same units as the points fed to `move(to:)` (points on
    /// iOS, view points on macOS).  Everything is normalised by this, so the
    /// result is resolution independent.
    public var radius: Float
    /// Fraction of the radius that is ignored, ~10%.
    public var deadZone: Float
    /// Where the finger first touched, or nil when the stick is idle.
    public private(set) var origin: SIMD2<Float>?
    /// Last normalised axis, -1...1 per component, magnitude <= 1.
    public private(set) var axis: SIMD2<Float> = .zero

    public init(radius: Float = 96, deadZone: Float = 0.10) {
        self.radius = max(1, radius)
        self.deadZone = min(max(deadZone, 0), 0.9)
    }

    public var isActive: Bool { origin != nil }

    /// First touch: the stick materialises under the finger.
    public mutating func begin(at point: SIMD2<Float>) {
        origin = point
        axis = .zero
    }

    /// Drag.  Returns the (dead-zoned, clamped) axis so the caller can feed it
    /// straight into GCInput.moveX / moveY.
    @discardableResult
    public mutating func move(to point: SIMD2<Float>) -> SIMD2<Float> {
        guard let origin = origin else { return axis }
        let delta = point - origin
        let distance = (delta * delta).sum().squareRoot()
        guard distance > 0.0001 else {
            axis = .zero
            return axis
        }
        // Normalise against the radius first: the dead zone is defined as a
        // fraction of the stick radius, not of the raw distance.
        let normalised = min(distance / radius, 1)
        guard normalised > deadZone else {
            axis = .zero
            return axis
        }
        // Re-map the live band [deadZone, 1] onto [0, 1] so control is
        // continuous at the dead-zone boundary (no jump from 0 to 0.1).
        let magnitude = (normalised - deadZone) / (1 - deadZone)
        axis = (delta / distance) * magnitude
        return axis
    }

    /// Lift the finger.  The stick forgets its origin and the axis zeroes.
    @discardableResult
    public mutating func end() -> SIMD2<Float> {
        origin = nil
        axis = .zero
        return axis
    }
}

// MARK: - Input state

/// Everything the shells hand to `gc_update`, built incrementally from events.
public struct GCInputState {
    public var input = GCInput()

    public init() {}

    // Movement axis ---------------------------------------------------------
    public mutating func setMoveAxis(x: Float, y: Float) {
        input.moveX = x.clampedToUnit()
        input.moveY = y.clampedToUnit()
    }

    public mutating func clearMoveAxis() {
        input.moveX = 0
        input.moveY = 0
    }

    /// WASD / arrow keys produce a raw digital axis; normalise so diagonals are
    /// not ~1.41x faster than a single key.
    public mutating func setDigitalMove(left: Bool, right: Bool, up: Bool, down: Bool) {
        var x: Float = 0
        var y: Float = 0
        if left { x -= 1 }
        if right { x += 1 }
        if up { y -= 1 }    // y-down: "up" is negative
        if down { y += 1 }
        let length = (x * x + y * y).squareRoot()
        if length > 1 {
            x /= length
            y /= length
        }
        setMoveAxis(x: x, y: y)
    }

    // Pointer ---------------------------------------------------------------
    /// `pixelPosition` is a framebuffer pixel coordinate (y-down).
    public mutating func setAim(pixelPosition: SIMD2<Float>, scale: Float) {
        let v = GCCoordinates.pixelsToVirtual(pixelPosition, scale: scale)
        input.aimX = v.x
        input.aimY = v.y
        input.pointerActive = true
    }

    /// Aim directly in virtual units (used by the iOS aim stick, which already
    /// knows the scale it converted with).
    public mutating func setAimVirtual(x: Float, y: Float) {
        input.aimX = x
        input.aimY = y
        input.pointerActive = true
    }

    public mutating func setPointerDown(_ down: Bool) {
        input.pointerDown = down
        if down { input.pointerActive = true }
    }

    // Buttons ---------------------------------------------------------------
    public mutating func press(_ button: GCButtons) { input.buttons.insert(button) }
    public mutating func release(_ button: GCButtons) { input.buttons.remove(button) }
    public mutating func set(_ button: GCButtons, pressed: Bool) {
        if pressed { press(button) } else { release(button) }
    }
    public func isPressed(_ button: GCButtons) -> Bool { input.buttons.contains(button) }
}

// MARK: - Keyboard translation

/// macOS virtual key codes (ANSI layout, `NSEvent.keyCode`).
///
/// These are *hardware position* codes, so they keep WASD under the same
/// physical keys on AZERTY/Dvorak.  `KeyboardTranslator` therefore also accepts
/// the produced character when the layout puts W/A/S/D elsewhere.
public enum GCKeyCode {
    public static let a: UInt16 = 0
    public static let s: UInt16 = 1
    public static let d: UInt16 = 2
    public static let w: UInt16 = 13
    public static let r: UInt16 = 15
    public static let space: UInt16 = 49
    public static let escape: UInt16 = 53
    public static let cursorLeft: UInt16 = 123
    public static let cursorRight: UInt16 = 124
    public static let cursorDown: UInt16 = 125
    public static let cursorUp: UInt16 = 126
}

/// Pure translation from held keys to a `GCInputState`.  Used by the AppKit
/// shell; kept here so the rules (and the diagonal normalisation) have one
/// definition and can be unit tested without a window.
public struct KeyboardTranslator {
    private var heldKeyCodes = Set<UInt16>()
    /// Keys activated by the character they produced (layout independent).
    private var heldCharacters = Set<Character>()

    public init() {}

    public mutating func keyDown(keyCode: UInt16, characters: String?) {
        heldKeyCodes.insert(keyCode)
        if let character = KeyboardTranslator.normalised(characters) {
            heldCharacters.insert(character)
        }
    }

    public mutating func keyUp(keyCode: UInt16, characters: String?) {
        heldKeyCodes.remove(keyCode)
        if let character = KeyboardTranslator.normalised(characters) {
            heldCharacters.remove(character)
        }
    }

    public mutating func releaseAll() {
        heldKeyCodes.removeAll()
        heldCharacters.removeAll()
    }

    /// Applies the held state to `state` (movement axis + held buttons).
    public func apply(to state: inout GCInputState) {
        let w = isHeld(keyCode: GCKeyCode.w, character: "w")
        let a = isHeld(keyCode: GCKeyCode.a, character: "a")
        let s = isHeld(keyCode: GCKeyCode.s, character: "s")
        let d = isHeld(keyCode: GCKeyCode.d, character: "d")
        let up = heldKeyCodes.contains(GCKeyCode.cursorUp)
        let down = heldKeyCodes.contains(GCKeyCode.cursorDown)
        let left = heldKeyCodes.contains(GCKeyCode.cursorLeft)
        let right = heldKeyCodes.contains(GCKeyCode.cursorRight)

        state.setDigitalMove(left: a || left, right: d || right, up: w || up, down: s || down)

        state.set(.dash, pressed: heldKeyCodes.contains(GCKeyCode.space))
        state.set(.pause, pressed: heldKeyCodes.contains(GCKeyCode.escape))
        state.set(.restart, pressed: isHeld(keyCode: GCKeyCode.r, character: "r"))
    }

    private func isHeld(keyCode: UInt16, character: Character) -> Bool {
        heldKeyCodes.contains(keyCode) || heldCharacters.contains(character)
    }

    private static func normalised(_ characters: String?) -> Character? {
        guard let characters, let first = characters.lowercased().first else { return nil }
        return first
    }
}

// MARK: - Small helpers

public extension Float {
    /// Clamps to -1...1, mapping NaN to 0 (a released touch can produce NaN if
    /// a caller divides by a zero length).
    @inline(__always)
    func clampedToUnit() -> Float {
        if isNaN { return 0 }
        return Swift.min(Swift.max(self, -1), 1)
    }
}

public extension SIMD2 where Scalar == Float {
    /// Euclidean length.  Named `vectorLength` rather than `length` to avoid
    /// colliding with anything the standard library may add to SIMD.
    @inline(__always)
    var vectorLength: Float { (self * self).sum().squareRoot() }

    /// Clamps the vector's magnitude to 1 without changing its direction.
    @inline(__always)
    func clampedToUnitLength() -> SIMD2<Float> {
        let l = vectorLength
        guard l > 1, l > 0 else { return self }
        return self / l
    }
}
