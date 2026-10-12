//
//  GameCore.swift
//  SlimeArenaRenderer
//
//  Thin, safe Swift wrapper over the frozen C ABI in include/game_core.h.
//
//  ABI NOTES (read this before changing anything here)
//  ---------------------------------------------------
//  gc_cmd     == 56 bytes: kind(0) sprite(4) x(8) y(12) w(16) h(20) rot(24)
//                          rgba(28) u0(32) v0(36) u1(40) v1(44) flags(48) _pad(52)
//  gc_input   == 28 bytes: move_x(0) move_y(4) aim_x(8) aim_y(12)
//                          pointer_active(16) pointer_down(20) buttons(24)
//  gc_event   == 16 bytes: type(0) x(4) y(8) value(12)
//  gc_status  == 40 bytes: wave(0) level(4) kills(8) money(12) score(16)
//                          best_score(20) state(24) player_hp(28)
//                          player_hp_max(32) time_alive(36)
//
//  The command buffer is *never* copied into a Swift array: `withCommands`
//  hands the caller an UnsafeBufferPointer that points straight at
//  library-owned memory, which stays valid until the next gc_update().  That is
//  the only way to keep the per-frame cost allocation-free.
//
//  This wrapper does not call the `static inline` helpers at the bottom of
//  game_core.h (Clang does not reliably import static inline functions into
//  Swift); `pixelsToVirtual` re-implements gc_pixels_to_virtual with exactly the
//  same maths, including the s <= 0 guard.
//
//  Linking: against libgame_core.dylib (no dlopen).  Package.swift passes
//  -L <core/target/release> -lgame_core; the app bundle ships the dylib in
//  Contents/Frameworks (macOS) or .app/Frameworks (iOS) with an
//  @rpath/libgame_core.dylib install name.
//
//  THREAD AFFINITY: the ABI is thread-affine to the thread that called
//  gc_create().  Create, update and destroy the GameCore on the same thread
//  (both sample apps use the main thread).
//

import Foundation
import CGameCore

// MARK: - Constants mirrored from game_core.h

/// Values mirrored from include/game_core.h.
///
/// They are spelled out in Swift instead of relying on the Clang importer
/// picking up the `#define`s, so the public API does not change shape if the
/// header is re-parsed by a different toolchain.  `shim.c` static-asserts that
/// the C side agrees with each of them at compile time, and the Xcode project /
/// build_macos.sh check `GC_ABI_VERSION` too.
public enum GCABI {
    /// Must equal `GC_ABI_VERSION` in include/game_core.h.
    public static let version: UInt32 = 1
    /// Must equal `GC_DESIGN_HEIGHT` in include/game_core.h.
    public static let designHeight: Float = 720.0
}

/// `gc_cmd_kind`.
public enum GCCmdKind: Int32, Sendable {
    case sprite = 1
    case rect = 2
    case glyph = 3
}

/// `GC_FLAG_*`.
public struct GCCmdFlags: OptionSet, Sendable {
    public let rawValue: UInt32
    public init(rawValue: UInt32) { self.rawValue = rawValue }

    /// Additive blend (muzzle flashes, sparks).
    public static let flash = GCCmdFlags(rawValue: 1 << 0)
    /// Draw a soft dark offset copy first (HUD readability).
    public static let shadow = GCCmdFlags(rawValue: 1 << 1)
}

/// `GC_BTN_*`.
public struct GCButtons: OptionSet, Sendable {
    public let rawValue: UInt32
    public init(rawValue: UInt32) { self.rawValue = rawValue }

    public static let dash = GCButtons(rawValue: 1 << 0)
    public static let pause = GCButtons(rawValue: 1 << 1)
    public static let restart = GCButtons(rawValue: 1 << 2)
}

/// Sprite table indices (`gc_sprite_id`).
public enum GCSprite: Int32, CaseIterable, Sendable {
    case player = 0
    case enemyA = 1
    case enemyB = 2
    case gun = 3
    case bow = 4
    case sword = 5
    case money = 6
    case xp = 7

    /// `GC_SPR_COUNT`.
    public static let count = 8
}

/// `gc_game_state`.
public enum GCGameState: Int32, Sendable {
    case title = 0
    case playing = 1
    case levelUp = 2
    case shop = 3
    case paused = 4
    case gameOver = 5

    public static func from(_ raw: Int32) -> GCGameState {
        GCGameState(rawValue: raw) ?? .playing
    }
}

/// `gc_debug_cmd`.
public enum GCDebugCommand: Int32, Sendable {
    case giveMoney = 1
    case setWave = 2
    case skipWave = 3
    case levelUp = 4
    case killPlayer = 5
    case giveWeapon = 6
    case invulnerable = 7
    case setTime = 8
}

// MARK: - Swift models of the C value types

/// Swift model of `gc_input` (28 bytes on the C side).
public struct GCInput: Equatable, Sendable {
    /// Movement axis, -1..1.  Analogue stick or raw WASD.
    public var moveX: Float = 0
    public var moveY: Float = 0
    /// Pointer position in VIRTUAL units (y-down, origin top-left).
    public var aimX: Float = 0
    public var aimY: Float = 0
    /// True when a pointer is known (mouse present, or a finger has touched).
    public var pointerActive = false
    /// True while the primary button / finger is held.
    public var pointerDown = false
    /// Held buttons; the library edge-detects internally.
    public var buttons: GCButtons = []

    public init() {}

    /// Marshals to the C struct.  Field-by-field assignment (rather than the
    /// imported memberwise init) keeps this compiling even if the importer
    /// renames the generated initialiser.
    public var cValue: gc_input {
        var c = gc_input()
        c.move_x = moveX
        c.move_y = moveY
        c.aim_x = aimX
        c.aim_y = aimY
        c.pointer_active = pointerActive ? 1 : 0
        c.pointer_down = pointerDown ? 1 : 0
        c.buttons = buttons.rawValue
        return c
    }
}

/// Swift model of `gc_event` (16 bytes on the C side).
public struct GCEvent: Equatable, Sendable {
    public enum Kind: Int32, Sendable {
        case shoot = 1
        case hit = 2
        case enemyDie = 3
        case playerHurt = 4
        case pickupXP = 5
        case pickupMoney = 6
        case levelUp = 7
        case buy = 8
        case buyFail = 9
        case waveStart = 10
        case waveClear = 11
        case gameOver = 12
        case uiClick = 13
        case dash = 14

        /// Human-readable name, for logs and for the audio mapping table.
        public var name: String {
            switch self {
            case .shoot: return "shoot"
            case .hit: return "hit"
            case .enemyDie: return "enemy_die"
            case .playerHurt: return "player_hurt"
            case .pickupXP: return "pickup_xp"
            case .pickupMoney: return "pickup_money"
            case .levelUp: return "level_up"
            case .buy: return "buy"
            case .buyFail: return "buy_fail"
            case .waveStart: return "wave_start"
            case .waveClear: return "wave_clear"
            case .gameOver: return "game_over"
            case .uiClick: return "ui_click"
            case .dash: return "dash"
            }
        }
    }

    /// Unknown event types are dropped by the dispatcher, never fatal.
    public let kind: Kind?
    public let rawType: Int32
    /// Virtual units (meaning depends on the event).
    public let x: Float
    public let y: Float
    /// Meaning depends on the event type.
    public let value: Float

    public init(_ c: gc_event) {
        self.rawType = c.type
        self.kind = Kind(rawValue: c.type)
        self.x = c.x
        self.y = c.y
        self.value = c.value
    }
}

/// Swift model of `gc_status` (40 bytes on the C side).
public struct GCStatus: Equatable, Sendable {
    public var wave: Int32 = 0
    public var level: Int32 = 0
    public var kills: Int32 = 0
    public var money: Int32 = 0
    public var score: Int32 = 0
    public var bestScore: Int32 = 0
    public var state: GCGameState = .title
    public var playerHP: Float = 0
    public var playerHPMax: Float = 0
    public var timeAlive: Float = 0

    public init() {}

    public init(_ c: gc_status) {
        wave = c.wave
        level = c.level
        kills = c.kills
        money = c.money
        score = c.score
        bestScore = c.best_score
        state = GCGameState.from(c.state)
        playerHP = c.player_hp
        playerHPMax = c.player_hp_max
        timeAlive = c.time_alive
    }

    /// e.g. "Slime Arena — Wave 4 · Lv 7 · Score 12040 · HP 82/100"
    public var windowTitle: String {
        let hp = Int(playerHP.rounded())
        let hpMax = Int(playerHPMax.rounded())
        return "Slime Arena — Wave \(wave) · Lv \(level) · Score \(score) · HP \(hp)/\(hpMax) · Best \(bestScore)"
    }
}

extension gc_cmd {
    /// `nil` for unknown kinds (forward compatibility: skip the command).
    public var cmdKind: GCCmdKind? { GCCmdKind(rawValue: kind) }
    /// The C field is `int32_t`; the flag bits live in the low bits.
    public var cmdFlags: GCCmdFlags { GCCmdFlags(rawValue: UInt32(bitPattern: flags)) }
    public var isAdditive: Bool { cmdFlags.contains(.flash) }
    public var wantsShadow: Bool { cmdFlags.contains(.shadow) }
}

// MARK: - GameCore

/// Owns one simulation (`gc_handle`) and exposes it to the platform shells.
public final class GameCore {
    public enum Failure: Error, CustomStringConvertible {
        case abiMismatch(expected: UInt32, actual: UInt32)
        case creationFailed
        case structLayoutMismatch(String)
        case fontAtlasUnavailable

        public var description: String {
            switch self {
            case let .abiMismatch(expected, actual):
                return """
                game_core ABI mismatch: this renderer was built for ABI \(expected) \
                but libgame_core reports ABI \(actual). Rebuild the core \
                (`cargo build --release` in core/) or update the renderer; running \
                anyway would read the command buffer with the wrong struct layout.
                """
            case .creationFailed:
                return "gc_create() returned NULL — the core refused to start a run."
            case let .structLayoutMismatch(detail):
                return "Swift/C struct layout mismatch: \(detail)"
            case .fontAtlasUnavailable:
                return "gc_font_atlas() returned no file name; the glyph atlas cannot be loaded."
            }
        }
    }

    /// Runtime-checked ABI agreement.  Called automatically by `init(seed:)`;
    /// exposed so a shell can fail before creating any GPU resources.
    public static func verifyABI() throws {
        let runtime = gc_abi_version()
        guard runtime == GCABI.version else {
            throw Failure.abiMismatch(expected: GCABI.version, actual: runtime)
        }
    }

    /// Checks the Swift-side assumptions about the imported C structs.  Cheap;
    /// runs once in `init`.  shim.c performs the same checks at C compile time.
    public static func verifyStructLayout() throws {
        func check(_ name: String, _ actual: Int, _ expected: Int) throws {
            guard actual == expected else {
                throw Failure.structLayoutMismatch("\(name) is \(actual) bytes, expected \(expected)")
            }
        }
        try check("gc_cmd", MemoryLayout<gc_cmd>.size, 56)
        try check("gc_input", MemoryLayout<gc_input>.size, 28)
        try check("gc_event", MemoryLayout<gc_event>.size, 16)
        try check("gc_status", MemoryLayout<gc_status>.size, 40)
    }

    private var handle: OpaquePointer?
    /// Thread the handle was created on; every ABI call must come from here.
    private let ownerThread: Thread

    /// Creates a run.  `seed` makes the whole simulation deterministic.
    public init(seed: UInt32 = UInt32.random(in: 1...UInt32.max)) throws {
        try GameCore.verifyABI()
        try GameCore.verifyStructLayout()
        guard let handle = gc_create(seed) else { throw Failure.creationFailed }
        self.handle = handle
        self.ownerThread = Thread.current
    }

    deinit {
        if let handle = handle {
            // The ABI is thread-affine; releasing off-thread is a programming
            // error we can only report, not fix.
            assert(Thread.current === ownerThread,
                   "GameCore released on a different thread than gc_create()")
            gc_destroy(handle)
        }
    }

    /// Traps if the caller uses the handle from a foreign thread.  Compiled out
    /// in release builds (`-O`), where the assertion costs nothing.
    @inline(__always)
    private func checked(_ h: OpaquePointer) -> OpaquePointer {
        assert(Thread.current === ownerThread,
               "game_core is thread-affine; call it from the thread that ran gc_create()")
        return h
    }

    /// True once a run exists.  In practice always true after a successful
    /// `init`; the accessor exists for shells that hold an optional handle.
    public var isValid: Bool { handle != nil }

    // MARK: Framebuffer

    /// Framebuffer size in PIXELS plus safe-area insets in PIXELS.
    /// Call at startup and after every resize / rotation.
    public func resize(
        framebufferWidth: Int,
        framebufferHeight: Int,
        safeLeft: Float = 0,
        safeTop: Float = 0,
        safeRight: Float = 0,
        safeBottom: Float = 0
    ) {
        guard let handle = handle else { return }
        gc_resize(checked(handle),
                  Int32(max(1, framebufferWidth)),
                  Int32(max(1, framebufferHeight)),
                  safeLeft, safeTop, safeRight, safeBottom)
    }

    /// Pixels per virtual unit (`gc_view_scale`), always > 0.
    public var viewScale: Float {
        guard let handle = handle else { return 1 }
        let s = gc_view_scale(checked(handle))
        return s > 0 ? s : 1
    }

    /// Virtual size of the current framebuffer.
    public var virtualSize: (width: Float, height: Float) {
        guard let handle = handle else { return (0, 0) }
        var w: Float = 0
        var h: Float = 0
        gc_virtual_size(checked(handle), &w, &h)
        return (w, h)
    }

    /// Pixels -> virtual units.  Mirrors the header's `gc_pixels_to_virtual`
    /// (including its `s <= 0` guard) because the C helper is `static inline`
    /// and therefore not reliably importable.
    public func pixelsToVirtual(x: Float, y: Float) -> (x: Float, y: Float) {
        let s = viewScale
        let scale = s > 0 ? s : 1
        return (x / scale, y / scale)
    }

    /// Virtual units -> pixels.  Mirrors `gc_virtual_to_pixels`.
    public func virtualToPixels(_ v: Float) -> Float { v * viewScale }

    // MARK: Frame

    /// Advances the simulation.  `dt` is seconds; the library runs its own
    /// fixed timestep, so a variable `dt` is fine (and clamped internally).
    public func update(input: GCInput, dt: Float) {
        guard let handle = handle else { return }
        var c = input.cValue
        gc_update(checked(handle), &c, dt)
    }

    /// The frame's command list, in draw order.
    ///
    /// The pointer is library-owned and only valid until the next `update`.
    /// No copy, no allocation: the renderer walks this buffer directly while
    /// filling its vertex buffer.
    @discardableResult
    public func withCommands<R>(_ body: (UnsafeBufferPointer<gc_cmd>) throws -> R) rethrows -> R {
        guard let handle = handle else {
            return try body(UnsafeBufferPointer(start: nil, count: 0))
        }
        var count: Int32 = 0
        guard let base = gc_cmds(checked(handle), &count), count > 0 else {
            return try body(UnsafeBufferPointer(start: nil, count: 0))
        }
        return try body(UnsafeBufferPointer(start: base, count: Int(count)))
    }

    /// The frame's events, for audio and haptics.
    @discardableResult
    public func withEvents<R>(_ body: (UnsafeBufferPointer<gc_event>) throws -> R) rethrows -> R {
        guard let handle = handle else {
            return try body(UnsafeBufferPointer(start: nil, count: 0))
        }
        var count: Int32 = 0
        guard let base = gc_events(checked(handle), &count), count > 0 else {
            return try body(UnsafeBufferPointer(start: nil, count: 0))
        }
        return try body(UnsafeBufferPointer(start: base, count: Int(count)))
    }

    /// Wave / level / score / hp snapshot for the window title and the save UI.
    public func status() -> GCStatus {
        guard let handle = handle else { return GCStatus() }
        var c = gc_status()
        gc_status_get(checked(handle), &c)
        return GCStatus(c)
    }

    // MARK: Persistence

    /// Opaque save blob (best score, settings) or `nil` when there is nothing
    /// to save.  Store it in `UserDefaults`; `gc_save` returns -1 when the
    /// buffer is too small, so we retry with a bigger one.
    public func save() -> Data? {
        guard let handle = handle else { return nil }
        var capacity = 4 * 1024
        while capacity <= 4 * 1024 * 1024 {
            var buffer = [UInt8](repeating: 0, count: capacity)
            let written = buffer.withUnsafeMutableBytes { raw -> Int32 in
                gc_save(checked(handle), raw.baseAddress, Int32(capacity))
            }
            if written > 0 {
                return Data(buffer[0..<Int(written)])
            }
            if written == 0 {
                return nil  // core has no state worth persisting
            }
            capacity *= 4
        }
        return nil
    }

    /// Restores a blob produced by `save()`.  Silently ignored when the blob is
    /// empty or the core rejects it (`gc_load` returns < 0).
    @discardableResult
    public func load(_ blob: Data) -> Bool {
        guard let handle = handle else { return false }
        guard !blob.isEmpty else { return false }
        let result = blob.withUnsafeBytes { raw -> Int32 in
            gc_load(checked(handle), raw.baseAddress, Int32(blob.count))
        }
        return result >= 0
    }

    // MARK: Test hooks

    /// Automated screenshot-test hooks.  Never needed by a shipping renderer.
    public func debug(_ command: GCDebugCommand, value: Float = 0) {
        guard let handle = handle else { return }
        gc_debug(checked(handle), command.rawValue, value)
    }

    // MARK: Asset descriptions

    /// File name (no directory) of a sprite, e.g. "player.png".
    /// `sprite` is a raw `gc_sprite_id`; unknown ids return nil.
    public static func spriteFileName(id: Int32) -> String? {
        guard let cString = gc_sprite_file(id) else { return nil }
        return String(cString: cString)
    }

    /// File name (no directory) of a sprite, e.g. "player.png".
    public static func spriteFileName(_ sprite: GCSprite) -> String? {
        spriteFileName(id: sprite.rawValue)
    }

    /// File name of the white-on-transparent glyph atlas plus its pixel size.
    public static func fontAtlasInfo() throws -> (file: String, width: Int, height: Int) {
        var file: UnsafePointer<CChar>?
        var width: Int32 = 0
        var height: Int32 = 0
        gc_font_atlas(&file, &width, &height)
        guard let file else { throw Failure.fontAtlasUnavailable }
        return (String(cString: file), Int(width), Int(height))
    }
}
