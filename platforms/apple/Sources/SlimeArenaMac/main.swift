//
//  main.swift
//  SlimeArenaMac
//
//  Top-level code: NSApplication is created in code, so there is no
//  MainMenu.xib, no @NSApplicationMain and no storyboard.
//
//  `swift build` treats this file as the executable target's entry point
//  because it is literally named main.swift.
//
//  NOTE: NSApplication holds its delegate *weakly*.  `appDelegate` below is a
//  top-level binding, i.e. a global, so it stays alive for the whole process —
//  holding it in a local would deallocate it immediately.
//

import AppKit

let application = NSApplication.shared
let appDelegate = AppDelegate()
application.delegate = appDelegate
// .regular = Dock icon + menu bar, i.e. a normal windowed app.
_ = application.setActivationPolicy(.regular)
application.run()
