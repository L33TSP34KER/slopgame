//
//  AppDelegate.swift
//  SlimeArenaIOS
//
//  Classic (non-scene) app lifecycle: the Info.plist deliberately has no
//  UIApplicationSceneManifest, so UIKit gives the app delegate a window to own.
//  That keeps the project free of a SceneDelegate and makes the background hook
//  below the single place where "the app went away" is handled.
//

import UIKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {

    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        let window = UIWindow(frame: UIScreen.main.bounds)
        window.rootViewController = GameViewController()
        window.makeKeyAndVisible()
        self.window = window
        return true
    }

    /// Required by the task: stop the display link and persist the save blob.
    /// The view controller owns both, so it observes this notification rather
    /// than being reached through the window hierarchy.
    func applicationDidEnterBackground(_ application: UIApplication) {
        NotificationCenter.default.post(name: .slimeArenaWillEnterBackground, object: nil)
    }

    func applicationWillEnterForeground(_ application: UIApplication) {
        NotificationCenter.default.post(name: .slimeArenaWillEnterForeground, object: nil)
    }

    /// Not always delivered, but if it is, the same "stop + save" path runs.
    func applicationWillTerminate(_ application: UIApplication) {
        NotificationCenter.default.post(name: .slimeArenaWillEnterBackground, object: nil)
    }
}

extension Notification.Name {
    /// Posted by AppDelegate when the app is backgrounded; GameViewController
    /// stops the CADisplayLink and calls gc_save.
    static let slimeArenaWillEnterBackground = Notification.Name("SlimeArena.willEnterBackground")
    /// Posted by AppDelegate when the app returns to the foreground.
    static let slimeArenaWillEnterForeground = Notification.Name("SlimeArena.willEnterForeground")
}
