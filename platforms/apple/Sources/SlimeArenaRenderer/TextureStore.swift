//
//  TextureStore.swift
//  SlimeArenaRenderer
//
//  Loads every PNG the core asks for, keyed by gc_sprite_id, plus the font
//  atlas and the 1x1 white texture that every GC_CMD_RECT draws with.
//
//  Colour space decision
//  --------------------
//  The drawable is `.bgra8Unorm` (NOT `_srgb`) and textures are loaded with
//  `MTKTextureLoader.Option.SRGB = false`.  Blending therefore happens on the
//  stored, sRGB-encoded values, which is the convention every 2D sprite
//  compositor uses and which keeps the 8-bit `rgba` values the core emits
//  (`0xAARRGGBB`, straight alpha) landing on screen exactly as authored.
//  If you ever switch the layer to `.bgra8Unorm_srgb` for correct *physical*
//  linear blending, flip `srgbTextures` to true here at the same time or the
//  images will be double-converted (washed out).
//
//  Filtering: bilinear, clamp to edge, no mipmaps — the core is documented to
//  expect bilinear sampling of tight-trimmed RGBA PNGs.
//

import Foundation
import Metal
import MetalKit

public final class TextureStore {
    public enum Failure: Error, CustomStringConvertible {
        /// The bundle does not contain a folder with the sprite PNGs.
        case assetDirectoryNotFound([String])
        /// One or more files named by the core are absent.
        case missingAssets(directory: String, names: [String])
        case textureLoadFailed(name: String, underlying: Error)
        case whiteTextureCreationFailed

        public var description: String {
            switch self {
            case let .assetDirectoryNotFound(tried):
                return """
                Could not find the sprite folder in the app bundle. Tried:
                  \(tried.joined(separator: "\n  "))
                The PNGs must be bundled as a *folder reference* (blue folder) \
                named Assets, or copied into Contents/Resources/Assets by \
                build_macos.sh.
                """
            case let .missingAssets(directory, names):
                return """
                These assets named by game_core are missing from \(directory):
                  \(names.joined(separator: "\n  "))
                """
            case let .textureLoadFailed(name, underlying):
                return "MTKTextureLoader failed for \(name): \(underlying)"
            case .whiteTextureCreationFailed:
                return "Could not create the 1x1 white texture used for GC_CMD_RECT."
            }
        }
    }

    /// Directory the PNGs were loaded from (for diagnostics and the title bar).
    public let assetDirectory: URL
    /// Indexed by `gc_sprite_id`; nil for ids the core did not name.
    private var spriteTextures: [MTLTexture?]
    /// The white-on-transparent glyph atlas bound for `GC_CMD_GLYPH`.
    public private(set) var fontAtlas: MTLTexture?
    /// Pixel size reported by `gc_font_atlas` (may differ from the PNG size if
    /// the asset pipeline scales it; we warn instead of failing).
    public private(set) var atlasReportedPixelSize: (width: Int, height: Int)?
    /// Non-fatal problems found while loading, worth printing once at startup.
    public private(set) var warnings: [String] = []
    /// 1x1 opaque white: lets every GC_CMD_RECT share the sprite pipeline.
    public let whiteTexture: MTLTexture

    /// Loads every sprite in `0..<spriteCount` plus the glyph atlas.
    ///
    /// - Parameters:
    ///   - device: Metal device that will sample the textures.
    ///   - assetDirectory: folder containing the PNGs named by the core.
    ///   - spriteCount: `GC_SPR_COUNT`, overridable for tests.
    public init(device: MTLDevice, assetDirectory: URL, spriteCount: Int = GCSprite.count) throws {
        // --- Phase 1: every stored property must be set before `self` is used.
        self.assetDirectory = assetDirectory
        self.spriteTextures = Array(repeating: nil, count: max(0, spriteCount))

        // 1x1 white texture: created first so that a failure here cannot leave
        // a half-loaded store behind.  It lets every GC_CMD_RECT share the
        // sprite pipeline and shader.
        let whiteDescriptor = MTLTextureDescriptor.texture2DDescriptor(
            pixelFormat: .rgba8Unorm, width: 1, height: 1, mipmapped: false)
        whiteDescriptor.usage = .shaderRead
        whiteDescriptor.storageMode = .shared
        guard let white = device.makeTexture(descriptor: whiteDescriptor) else {
            throw Failure.whiteTextureCreationFailed
        }
        white.label = "white 1x1"
        let whitePixel: [UInt8] = [255, 255, 255, 255]
        whitePixel.withUnsafeBytes { bytes in
            white.replace(
                region: MTLRegionMake2D(0, 0, 1, 1),
                mipmapLevel: 0,
                withBytes: bytes.baseAddress!,
                bytesPerRow: 4)
        }
        self.whiteTexture = white

        // --- Phase 2: safe to touch `self` from here on.
        let loader = MTKTextureLoader(device: device)
        // See the colour-space note at the top of the file.
        let options: [MTKTextureLoader.Option: Any] = [
            .SRGB: false,
            .generateMipmaps: false,
            .textureUsage: MTLTextureUsage.shaderRead.rawValue,
            // Pin the origin explicitly: UV (0,0) is the top-left texel, which
            // is what the core's normalised glyph rects assume (v grows down).
            .origin: MTKTextureLoader.Origin.topLeft.rawValue,
        ]

        var missing: [String] = []

        for id in 0..<spriteCount {
            guard let name = GameCore.spriteFileName(id: Int32(id)) else {
                warnings.append("game_core named no file for sprite id \(id); skipping.")
                continue
            }
            let url = assetDirectory.appendingPathComponent(name)
            guard FileManager.default.fileExists(atPath: url.path) else {
                missing.append(name)
                continue
            }
            do {
                spriteTextures[id] = try loader.newTexture(URL: url, options: options)
            } catch {
                throw Failure.textureLoadFailed(name: name, underlying: error)
            }
        }

        // Font atlas -------------------------------------------------------
        if let info = try? GameCore.fontAtlasInfo() {
            atlasReportedPixelSize = (info.width, info.height)
            let url = assetDirectory.appendingPathComponent(info.file)
            if FileManager.default.fileExists(atPath: url.path) {
                do {
                    let texture = try loader.newTexture(URL: url, options: options)
                    fontAtlas = texture
                    if info.width > 0, info.height > 0,
                       Int(texture.width) != info.width || Int(texture.height) != info.height {
                        warnings.append(
                            "font atlas \(info.file) is \(texture.width)x\(texture.height) on disk "
                            + "but game_core reports \(info.width)x\(info.height). "
                            + "Glyph UVs come from the core, so the texture must match.")
                    }
                } catch {
                    throw Failure.textureLoadFailed(name: info.file, underlying: error)
                }
            } else {
                missing.append(info.file)
            }
        } else {
            warnings.append("game_core reported no font atlas; GC_CMD_GLYPH will draw as untextured quads.")
        }

        guard missing.isEmpty else {
            throw Failure.missingAssets(directory: assetDirectory.path, names: missing)
        }
    }

    // MARK: Lookup

    /// Texture for a `gc_sprite_id`, or nil when the core never named it.
    public func sprite(_ id: Int32) -> MTLTexture? {
        guard id >= 0, Int(id) < spriteTextures.count else { return nil }
        return spriteTextures[Int(id)]
    }

    /// Texture the renderer must bind for a command.  Falls back to the white
    /// texture (untextured quads) rather than dropping the draw.
    public func texture(for kind: GCCmdKind, spriteID: Int32) -> MTLTexture {
        switch kind {
        case .sprite: return sprite(spriteID) ?? whiteTexture
        case .glyph: return fontAtlas ?? whiteTexture
        case .rect: return whiteTexture
        }
    }

    // MARK: Bundle lookup

    /// Finds the sprite folder inside a bundle.
    ///
    /// `build_macos.sh` copies the PNGs to `Contents/Resources/Assets`.  The
    /// Xcode target bundles `assets/dist` as a *folder reference*; Xcode copies
    /// it under the folder's on-disk name, which is not necessarily "Assets",
    /// so the on-disk names are probed as well.  The probe is "does this folder
    /// contain player.png", not a hard-coded path, so renaming the reference in
    /// Xcode cannot break the loader.
    public static func locateAssets(in bundle: Bundle = .main) -> URL? {
        let fileManager = FileManager.default
        // The file the core always names; used only as a probe.
        let probe = GameCore.spriteFileName(.player) ?? "player.png"

        var candidates: [URL] = []
        let resource = bundle.resourceURL
        let bundleRoot = bundle.bundleURL
        for root in [resource, bundleRoot].compactMap({ $0 }) {
            candidates.append(root.appendingPathComponent("Assets"))
            candidates.append(root.appendingPathComponent("assets"))
            candidates.append(root.appendingPathComponent("dist"))
            candidates.append(root.appendingPathComponent("sprites"))
            candidates.append(root)
        }

        for candidate in candidates {
            var isDirectory: ObjCBool = false
            guard fileManager.fileExists(atPath: candidate.path, isDirectory: &isDirectory),
                  isDirectory.boolValue else { continue }
            let probeURL = candidate.appendingPathComponent(probe)
            if fileManager.fileExists(atPath: probeURL.path) {
                return candidate
            }
        }
        return nil
    }

    /// Convenience: locate the assets and load them, or throw with the list of
    /// directories that were tried.
    public static func loadFromBundle(device: MTLDevice, bundle: Bundle = .main) throws -> TextureStore {
        guard let directory = locateAssets(in: bundle) else {
            let tried = [bundle.resourceURL?.path, bundle.bundleURL.path].compactMap { $0 }
            throw Failure.assetDirectoryNotFound(tried)
        }
        return try TextureStore(device: device, assetDirectory: directory)
    }
}
