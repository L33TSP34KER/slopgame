//
//  AppDelegate.swift
//  SlimeArenaMac
//
//  Programmatic AppKit application: no storyboard, no nib, no .xcodeproj needed.
//  main.swift creates NSApplication, installs this delegate and runs.
//

import AppKit
import SlimeArenaRenderer

final class AppDelegate: NSObject, NSApplicationDelegate {

    private var window: NSWindow?
    private var gameView: GameView?

    // MARK: Launch

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMainMenu()

        let contentRect = NSRect(x: 0, y: 0, width: 1280, height: 720)
        do {
            let view = try GameView.make(frame: contentRect)
            let window = NSWindow(
                contentRect: contentRect,
                styleMask: [.titled, .closable, .miniaturizable, .resizable],
                backing: .buffered,
                defer: false)
            window.title = "Slime Arena"
            window.minSize = NSSize(width: 640, height: 360)
            // ARC also owns this window; without this AppKit would release it a
            // second time when the user closes it.
            window.isReleasedWhenClosed = false
            window.contentView = view
            window.center()
            window.makeKeyAndOrderFront(nil)
            window.makeFirstResponder(view)

            // Best score survives because the core's blob lives in UserDefaults.
            view.restoreFromUserDefaults()

            view.onStatusChange = { [weak window] status in
                window?.title = status.windowTitle
            }
            view.onRestartRequested = { [weak view] in
                // Persist at the moment of a restart: the core has already
                // folded the finished run into best_score.
                view?.saveToUserDefaults()
            }
            view.onStatusChange?(view.core.status())

            view.startRendering()

            self.window = window
            self.gameView = view
        } catch {
            presentFatal(error)
            return
        }

        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: Termination

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        gameView?.shutdown()
    }

    // MARK: Menu

    /// Minimal menu bar: without one, ⌘Q does not work in a programmatic app.
    private func installMainMenu() {
        let appName = ProcessInfo.processInfo.processName

        let mainMenu = NSMenu()

        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(
            withTitle: "Hide \(appName)",
            action: #selector(NSApplication.hide(_:)),
            keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(
            withTitle: "Quit \(appName)",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q")
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        NSApp.mainMenu = mainMenu
    }

    // MARK: Failure reporting

    /// Anything that stops the app from starting is reported once, clearly,
    /// instead of crashing on a force-unwrap.
    private func presentFatal(_ error: Error) {
        NSLog("SlimeArenaMac: fatal startup error: %@", String(describing: error))

        let alert = NSAlert()
        alert.alertStyle = .critical
        alert.messageText = "Slime Arena could not start"
        alert.informativeText = """
        \(String(describing: error))

        If this mentions libgame_core or a missing sprite, run build_macos.sh: it
        builds the Rust core, runs swift build, and assembles SlimeArena.app with
        the dylib and the PNGs in the right places.
        """
        alert.addButton(withTitle: "Quit")
        alert.runModal()
        NSApp.terminate(nil)
    }
}
