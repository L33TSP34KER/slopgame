// swift-tools-version:5.9
//
//  Package.swift — Apple (macOS + iOS) renderer for Slime Arena.
//
//  Two targets are built here:
//
//    CGameCore            C module for the frozen ABI in include/game_core.h.
//                         No implementation: every gc_* symbol comes from
//                         libgame_core.dylib at link time.  The same module name
//                         is used by SlimeArena.xcodeproj (which puts
//                         Sources/CGameCore/include on SWIFT_INCLUDE_PATHS), so
//                         the shared Swift sources build unchanged in both.
//
//    SlimeArenaRenderer   The shared renderer: GameCore / MetalRenderer /
//                         TextureStore / Input / AudioHaptics.  This target is
//                         compiled on macOS AND — through the Xcode project,
//                         not through SwiftPM — on iOS.
//
//    SlimeArenaMac        AppKit executable (NSApplication in code, no storyboard).
//
//  WHY iOS IS NOT A SWIFTPM TARGET
//  ------------------------------
//  An iOS app needs an .app bundle, an Info.plist, a code signature and an
//  embedded framework; SwiftPM cannot produce that.  Sources/SlimeArenaIOS is
//  therefore an Xcode-only source set, compiled by the hand-written
//  SlimeArena.xcodeproj, which pulls in Sources/SlimeArenaRenderer directly.
//  Xcode ignores this package file, and SwiftPM ignores Sources/SlimeArenaIOS.
//
//  PREREQUISITE: build the core first ("core/" is a Rust crate producing
//  libgame_core.dylib).  build_macos.sh does both steps in the right order.
//

import PackageDescription
import Foundation

// ---------------------------------------------------------------------------
// Where libgame_core.dylib lives.
//
// Resolved from this file's own path, so it does not matter which directory
// `swift build` is invoked from.  A standalone crate writes to
// core/target/release; a cargo workspace writes to <root>/target/release.
// Both are probed at manifest-evaluation time.
// ---------------------------------------------------------------------------
let packageRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
let coreReleaseDirectory = packageRoot
    .appendingPathComponent("../../core/target/release")
    .standardizedFileURL
let workspaceReleaseDirectory = packageRoot
    .appendingPathComponent("../../target/release")
    .standardizedFileURL

let coreSearchDirectory = [coreReleaseDirectory, workspaceReleaseDirectory]
    .first { FileManager.default.fileExists(atPath: $0.appendingPathComponent("libgame_core.dylib").path) }?
    .path
    ?? coreReleaseDirectory.path

/// -L for the core's directory, the app-bundle rpath (Contents/Frameworks), and
/// an absolute rpath so an unbundled `swift run` also finds the dylib.
let coreLinkerFlags: [String] = [
    "-L\(coreSearchDirectory)",
    "-Xlinker", "-rpath", "-Xlinker", "@loader_path/../Frameworks",
    "-Xlinker", "-rpath", "-Xlinker", coreSearchDirectory,
]

let package = Package(
    name: "SlimeArena",
    platforms: [
        // macOS 13 covers every Metal feature used here (MTKTextureLoader
        // options, .storageModeShared buffers, Swift 5.9 concurrency).
        .macOS(.v13)
    ],
    products: [
        .library(name: "SlimeArenaRenderer", targets: ["SlimeArenaRenderer"]),
        .executable(name: "SlimeArenaMac", targets: ["SlimeArenaMac"]),
    ],
    targets: [
        // Frozen C ABI.  Header-only plus a translation unit full of
        // _Static_asserts that pin the struct layouts.
        .target(
            name: "CGameCore",
            path: "Sources/CGameCore",
            publicHeadersPath: "include"
        ),

        // Shared renderer, used by the macOS executable here and by the iOS app
        // through SlimeArena.xcodeproj.
        .target(
            name: "SlimeArenaRenderer",
            dependencies: ["CGameCore"],
            path: "Sources/SlimeArenaRenderer",
            linkerSettings: [
                // unsafeFlags because SwiftPM has no first-class way to say
                // "-L <dir> -lgame_core -rpath ...".  Harmless for a root package.
                .unsafeFlags(coreLinkerFlags),
                .linkedLibrary("game_core"),
            ]
        ),

        // AppKit shell.
        .executableTarget(
            name: "SlimeArenaMac",
            dependencies: ["SlimeArenaRenderer"],
            path: "Sources/SlimeArenaMac",
            linkerSettings: [
                .unsafeFlags(coreLinkerFlags),
                .linkedLibrary("game_core"),
            ]
        ),
    ]
)
