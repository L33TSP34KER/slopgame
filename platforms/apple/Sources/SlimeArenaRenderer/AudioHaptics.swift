//
//  AudioHaptics.swift
//  SlimeArenaRenderer
//
//  Turns the core's `gc_event` stream into platform feedback.
//
//  Haptics are implemented for real on both platforms.  AUDIO IS DELIBERATELY A
//  NO-OP HOOK: the complete mapping from every `gc_event_type` to the sound it
//  should play is written out in `AudioMapping` below (with the intended
//  parameter), so dropping in AVAudioEngine / AudioToolbox later is a matter of
//  implementing one protocol method per sound and calling it from
//  `AudioHook.play`.  Nothing else in this file has to change.
//
//  Haptic throttling matters: the core emits GC_EVT_SHOOT once per shot and
//  GC_EVT_HIT once per damaging frame, which at 120 Hz would turn the Taptic
//  Engine into a continuous buzz.  Each event type therefore has a minimum
//  interval, and shoot/pickup-XP deliberately get no haptic at all.
//

import Foundation
import QuartzCore

#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

// MARK: - Audio mapping (the documented hook)

/// The noise each event should make, once an audio engine is dropped in.
///
/// Using this enum rather than a raw string keeps the mapping reviewable: every
/// `GCEvent.Kind` case has exactly one entry, and `AudioMapping.sound(for:)`
/// switches exhaustively, so adding an event type is a compile error until it is
/// mapped.
public enum GCSound: String, CaseIterable, Sendable {
    case pistolShot          // GC_EVT_SHOOT
    case bulletImpact        // GC_EVT_HIT
    case enemyDeath          // GC_EVT_ENEMY_DIE
    case playerHurt          // GC_EVT_PLAYER_HURT
    case xpPickup            // GC_EVT_PICKUP_XP
    case moneyPickup         // GC_EVT_PICKUP_MONEY
    case levelUpJingle       // GC_EVT_LEVEL_UP
    case purchaseSuccess     // GC_EVT_BUY
    case purchaseDenied      // GC_EVT_BUY_FAIL
    case waveStartSting      // GC_EVT_WAVE_START
    case waveClearJingle     // GC_EVT_WAVE_CLEAR
    case gameOverSting       // GC_EVT_GAME_OVER
    case uiClick             // GC_EVT_UI_CLICK
    case dashWhoosh          // GC_EVT_DASH
}

public enum AudioMapping {
    /// Sound for an event.  `nil` only for unknown/future event types.
    public static func sound(for event: GCEvent) -> GCSound? {
        guard let kind = event.kind else { return nil }
        switch kind {
        case .shoot: return .pistolShot
        case .hit: return .bulletImpact
        case .enemyDie: return .enemyDeath
        case .playerHurt: return .playerHurt
        case .pickupXP: return .xpPickup
        case .pickupMoney: return .moneyPickup
        case .levelUp: return .levelUpJingle
        case .buy: return .purchaseSuccess
        case .buyFail: return .purchaseDenied
        case .waveStart: return .waveStartSting
        case .waveClear: return .waveClearJingle
        case .gameOver: return .gameOverSting
        case .uiClick: return .uiClick
        case .dash: return .dashWhoosh
        }
    }

    /// Pan/attenuation hint: events carry virtual-space positions, so an audio
    /// engine can place them.  Normalised -1 (left) ... 1 (right) assuming a
    /// virtual width of `virtualWidth`; events with no meaningful position
    /// (UI, shop, game over) are centred.
    public static func stereoPan(for event: GCEvent, virtualWidth: Float) -> Float {
        guard virtualWidth > 0 else { return 0 }
        switch event.kind {
        case .some(.uiClick), .some(.buy), .some(.buyFail), .some(.levelUp),
             .some(.waveStart), .some(.waveClear), .some(.gameOver):
            return 0
        default:
            let normalised = (event.x / virtualWidth) * 2 - 1
            return min(max(normalised, -1), 1)
        }
    }
}

/// Implement this to add sound.  The renderer only ever calls `play`.
public protocol AudioHook: AnyObject {
    /// - Parameters:
    ///   - sound: which effect.
    ///   - pan: -1 (left) ... 1 (right).
    ///   - event: the original event (position in virtual units, `value`).
    func play(_ sound: GCSound, pan: Float, event: GCEvent)
}

/// The no-op hook installed by default.  Logs once per sound in debug builds so
/// it is obvious that the mapping is wired up.
public final class SilentAudioHook: AudioHook {
    public init() {}

    public func play(_ sound: GCSound, pan: Float, event: GCEvent) {
        #if DEBUG
        NSLog("SlimeArena audio (no engine installed): %@ pan=%.2f value=%.2f",
              sound.rawValue, pan, event.value)
        #endif
    }
}

// MARK: - Haptic mapping

/// What the Taptic Engine / Force Touch trackpad should do.
public enum GCHaptic {
    case none
    case lightImpact
    case mediumImpact
    case heavyImpact
    case selection
    case success
    case warning
    case error
}

public enum HapticMapping {
    public static func haptic(for kind: GCEvent.Kind) -> GCHaptic {
        switch kind {
        case .shoot:
            // Once per bullet: haptics here would be a constant rattle.
            return .none
        case .hit: return .lightImpact
        case .enemyDie: return .mediumImpact
        case .playerHurt: return .heavyImpact
        case .pickupXP:
            // Extremely frequent; the money pickup carries the feedback.
            return .none
        case .pickupMoney: return .lightImpact
        case .levelUp: return .success
        case .buy: return .lightImpact
        case .buyFail: return .error
        case .waveStart: return .none
        case .waveClear: return .success
        case .gameOver: return .error
        case .uiClick: return .selection
        case .dash: return .lightImpact
        }
    }

    /// Minimum seconds between two haptics of the same event type.
    public static func minimumInterval(for kind: GCEvent.Kind) -> CFTimeInterval {
        switch kind {
        case .hit, .pickupMoney, .uiClick, .dash:
            return 0.06
        case .enemyDie, .buy, .buyFail:
            return 0.08
        default:
            return 0.10
        }
    }
}

// MARK: - Dispatcher

/// Consumes the frame's events: haptics immediately, audio through the hook.
public final class AudioHapticsDispatcher {
    public var audio: AudioHook
    /// Virtual width used for stereo pan; updated from `gc_virtual_size`.
    public var virtualWidth: Float = 1280
    /// Set to false to silence haptics (e.g. a settings toggle).
    public var hapticsEnabled = true

    private var lastHapticTime: [Int32: CFTimeInterval] = [:]

    public init(audio: AudioHook = SilentAudioHook()) {
        self.audio = audio
        prepareGenerators()
    }

    /// Handles one frame's events.  Must be called on the main thread (both
    /// UIKit and AppKit feedback generators require it).
    public func handle(events: UnsafeBufferPointer<gc_event>) {
        guard !events.isEmpty else { return }
        let now = CACurrentMediaTime()
        for index in 0..<events.count {
            let event = GCEvent(events[index])
            guard let kind = event.kind else {
                // Unknown type (a newer core): ignore it rather than guessing.
                continue
            }
            if let sound = AudioMapping.sound(for: event) {
                audio.play(sound,
                           pan: AudioMapping.stereoPan(for: event, virtualWidth: virtualWidth),
                           event: event)
            }
            guard hapticsEnabled else { continue }
            let haptic = HapticMapping.haptic(for: kind)
            guard haptic != .none else { continue }
            let interval = HapticMapping.minimumInterval(for: kind)
            if let last = lastHapticTime[event.rawType], now - last < interval { continue }
            lastHapticTime[event.rawType] = now
            fire(haptic)
        }
    }

    // MARK: Platform haptics

    #if canImport(UIKit)

    private lazy var lightImpact = UIImpactFeedbackGenerator(style: .light)
    private lazy var mediumImpact = UIImpactFeedbackGenerator(style: .medium)
    private lazy var heavyImpact = UIImpactFeedbackGenerator(style: .heavy)
    private lazy var notification = UINotificationFeedbackGenerator()
    private lazy var selection = UISelectionFeedbackGenerator()

    /// `prepare()` warms the Taptic Engine so the first event is not late.
    private func prepareGenerators() {
        lightImpact.prepare()
        mediumImpact.prepare()
        heavyImpact.prepare()
        notification.prepare()
        selection.prepare()
    }

    private func fire(_ haptic: GCHaptic) {
        switch haptic {
        case .none: break
        case .lightImpact:
            lightImpact.impactOccurred()
            lightImpact.prepare()          // re-arm for the next one
        case .mediumImpact:
            mediumImpact.impactOccurred()
            mediumImpact.prepare()
        case .heavyImpact:
            heavyImpact.impactOccurred()
            heavyImpact.prepare()
        case .selection:
            selection.selectionChanged()
            selection.prepare()
        case .success:
            notification.notificationOccurred(.success)
            notification.prepare()
        case .warning:
            notification.notificationOccurred(.warning)
            notification.prepare()
        case .error:
            notification.notificationOccurred(.error)
            notification.prepare()
        }
    }

    #elseif canImport(AppKit)

    /// macOS has no Taptic Engine API surface as rich as UIKit's: the Force
    /// Touch trackpad only exposes three patterns, so the mapping collapses.
    private let performer = NSHapticFeedbackManager.defaultPerformer

    private func prepareGenerators() {
        // Nothing to warm up on macOS; kept so both branches have the same shape.
    }

    private func fire(_ haptic: GCHaptic) {
        switch haptic {
        case .none:
            break
        case .lightImpact, .selection:
            performer.perform(.alignment, performanceTime: .now)
        case .mediumImpact, .warning:
            performer.perform(.levelChange, performanceTime: .now)
        case .heavyImpact, .error, .success:
            performer.perform(.generic, performanceTime: .now)
        }
    }

    #else

    private func prepareGenerators() {}
    private func fire(_ haptic: GCHaptic) {}

    #endif
}
