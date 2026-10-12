//
//  DisplayLinkDriver.swift
//  SlimeArenaMac
//
//  Drives one game tick per display refresh, on the MAIN thread.
//
//  Why CVDisplayLink and not the newer NSView.displayLink(target:selector:)?
//  The latter is macOS 14+, and this package deploys to macOS 13 with an SDK
//  that may predate it; CVDisplayLink compiles everywhere.  It is marked
//  deprecated in the macOS 15 SDK, which produces a warning (not an error).  To
//  move to CADisplayLink later, delete the callback plumbing below and use
//  `view.displayLink(target:selector:)` — the rest of GameView is unchanged.
//
//  Why the main-thread hop: the C ABI is thread-affine to the thread that called
//  gc_create(), and that is the main thread.  The CVDisplayLink output callback
//  runs on a CoreVideo-owned thread, so it only *schedules* work; a coalescing
//  flag guarantees at most one pending frame, so a slow frame can never build a
//  queue of stale frames.
//

import Foundation
import CoreVideo
import QuartzCore

final class DisplayLinkDriver {

    private let displayLink: CVDisplayLink
    private let onFrame: () -> Void

    /// Coalesces ticks while a frame is already queued on the main thread.
    private let pendingLock = NSLock()
    private var framePending = false

    /// Strong reference handed to CoreVideo, released exactly once in `stop()`.
    /// Using passRetained (rather than passUnretained) guarantees the driver
    /// outlives any callback that is in flight when the link is stopped.
    private var callbackContext: UnsafeMutableRawPointer?

    /// Returns nil when CoreVideo cannot create a link (no active displays).
    static func make(onFrame: @escaping () -> Void) -> DisplayLinkDriver? {
        var link: CVDisplayLink?
        guard CVDisplayLinkCreateWithActiveCGDisplays(&link) == kCVReturnSuccess,
              let created = link else {
            return nil
        }
        return DisplayLinkDriver(link: created, onFrame: onFrame)
    }

    private init(link: CVDisplayLink, onFrame: @escaping () -> Void) {
        self.displayLink = link
        self.onFrame = onFrame
        // All stored properties are initialised from here on, so `self` may be
        // handed to CoreVideo.
        let context = Unmanaged.passRetained(self).toOpaque()
        self.callbackContext = context
        _ = CVDisplayLinkSetOutputCallback(link, DisplayLinkDriver.callback, context)
    }

    deinit {
        stop()
    }

    func start() {
        if !CVDisplayLinkIsRunning(displayLink) {
            _ = CVDisplayLinkStart(displayLink)
        }
    }

    /// Safe to call repeatedly, and safe to call from deinit.
    func stop() {
        if CVDisplayLinkIsRunning(displayLink) {
            CVDisplayLinkStop(displayLink)
        }
        // Only release after the link is stopped, so no in-flight callback can
        // touch freed memory.
        if let context = callbackContext {
            Unmanaged<DisplayLinkDriver>.fromOpaque(context).release()
            self.callbackContext = nil
        }
    }

    /// C callback: no captures allowed, so the driver arrives via `context`.
    private static let callback: CVDisplayLinkOutputCallback = {
        _, _, _, _, _, context -> CVReturn in
        guard let context else { return kCVReturnError }
        let driver = Unmanaged<DisplayLinkDriver>.fromOpaque(context).takeUnretainedValue()
        driver.tick()
        return kCVReturnSuccess
    }

    private func tick() {
        pendingLock.lock()
        if framePending {
            pendingLock.unlock()
            return
        }
        framePending = true
        pendingLock.unlock()

        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.pendingLock.lock()
            self.framePending = false
            self.pendingLock.unlock()
            self.onFrame()
        }
    }
}
