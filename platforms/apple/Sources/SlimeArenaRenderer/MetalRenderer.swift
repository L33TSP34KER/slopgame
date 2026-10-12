//
//  MetalRenderer.swift
//  SlimeArenaRenderer
//
//  The whole GPU side of the Apple renderer, shared verbatim by macOS and iOS.
//
//  DESIGN
//  ------
//  * One vertex format (position, uv, rgba) and one shader pair.  We do *not*
//    rotate on the GPU: every quad is baked into a pixel-space triangle list on
//    the CPU while we walk the core's command buffer, so the vertex shader only
//    has to map pixels -> NDC.
//  * One pipeline per blend mode: normal (srcAlpha / oneMinusSrcAlpha) and
//    additive (srcAlpha / one) for GC_FLAG_FLASH.  Same shaders, different
//    MTLRenderPipelineColorAttachmentDescriptor.
//  * GC_FLAG_SHADOW needs no pipeline: while batching we emit an offset, dark,
//    translucent copy of the quad *before* the real one.  Both land in the same
//    normal-blend batch whenever the texture matches, so a shadow costs 6 extra
//    vertices and zero extra draw calls in the common case.
//  * Batching: consecutive commands that share (texture, blend mode) become one
//    draw call.  GC_CMD_RECT uses a 1x1 white texture, so rects and sprites and
//    glyphs all flow through the same pipeline and shader.  The core's command
//    list is already in painter's order, so batches are simply recorded in order
//    and replayed in the same order.
//  * No per-command allocation, ever: the command buffer is read straight out of
//    the C-owned UnsafeBufferPointer, the Swift vertex array keeps its capacity
//    between frames, and the MTLBuffer is only re-allocated when the frame
//    genuinely needs more room than the current buffer in that ring slot.
//  * Triple buffering: 3 vertex buffers + 3-deep semaphore, so the CPU never
//    overwrites a buffer the GPU is still reading.
//
//  Coordinate maths (y-down, virtual -> pixel):
//      pixel = (center + rotate(localCorner) + shadowOffsetVirtual) * viewScale
//      rotation clockwise in y-down space == the standard
//      (x*cos - y*sin, x*sin + y*cos) matrix with a positive angle.
//

import Foundation
import Metal
import QuartzCore
import CGameCore

/// One vertex of the single vertex format.  `MetalRenderer.init` reads the
/// field offsets from `MemoryLayout` and builds the vertex descriptor from
/// them, so this struct and the MSL `VertexIn` cannot drift apart silently.
struct GCVertex {
    var position: SIMD2<Float>
    var uv: SIMD2<Float>
    var color: SIMD4<Float>
}

/// A run of vertices sharing one texture and one blend mode.
private struct GCDrawBatch {
    var start: Int
    var count: Int
    var texture: MTLTexture
    var additive: Bool
}

public final class MetalRenderer {

    // MARK: Constants

    /// The drawable format.  Deliberately NOT `_srgb`; see the colour-space note
    /// in TextureStore.swift before changing this.
    public static let pixelFormat: MTLPixelFormat = .bgra8Unorm
    /// Vertex buffers in flight (and the semaphore depth).
    public static let maxFramesInFlight = 3

    /// Metal Shading Language source, embedded so the build has no resource
    /// phase to wire up and the shader cannot go missing from a bundle.
    public static let shaderSource = """
    #include <metal_stdlib>
    using namespace metal;

    struct VertexIn {
        float2 position [[attribute(0)]];   // framebuffer pixels, y-down
        float2 uv       [[attribute(1)]];   // normalized, origin top-left
        float4 color    [[attribute(2)]];   // straight (non-premultiplied) alpha
    };

    struct VertexOut {
        float4 position [[position]];
        float2 uv;
        float4 color;
    };

    // Pixels (y-down, origin top-left) -> normalized device coordinates.
    vertex VertexOut slime_vertex(VertexIn in [[stage_in]],
                                  constant float2 &viewportPixels [[buffer(1)]])
    {
        VertexOut out;
        float2 ndc = float2((in.position.x / viewportPixels.x) * 2.0 - 1.0,
                            1.0 - (in.position.y / viewportPixels.y) * 2.0);
        out.position = float4(ndc, 0.0, 1.0);
        out.uv = in.uv;
        out.color = in.color;
        return out;
    }

    // Bilinear + clamp to edge, no mipmaps.  Straight alpha: the texture value
    // is modulated by the vertex colour and the *blend state* applies the
    // source alpha, so nothing is premultiplied twice.
    fragment float4 slime_fragment(VertexOut in [[stage_in]],
                                   texture2d<float> tex [[texture(0)]])
    {
        constexpr sampler s(filter::linear, address::clamp_to_edge);
        return tex.sample(s, in.uv) * in.color;
    }
    """

    // MARK: Errors

    public enum Failure: Error, CustomStringConvertible {
        case noDevice
        case libraryCompilationFailed(String)
        case functionMissing(String)
        case pipelineCreationFailed(String)
        case vertexBufferAllocationFailed(Int)

        public var description: String {
            switch self {
            case .noDevice:
                return "MTLCreateSystemDefaultDevice() returned nil; this Mac/device has no Metal device."
            case let .libraryCompilationFailed(message):
                return "Metal could not compile the embedded shader source:\n\(message)"
            case let .functionMissing(name):
                return "The compiled Metal library has no function named '\(name)'."
            case let .pipelineCreationFailed(message):
                return "Metal could not create a render pipeline state:\n\(message)"
            case let .vertexBufferAllocationFailed(bytes):
                return "Could not allocate a \(bytes)-byte shared vertex buffer."
            }
        }
    }

    // MARK: State

    public let device: MTLDevice
    private let commandQueue: MTLCommandQueue
    private let normalPipeline: MTLRenderPipelineState
    private let additivePipeline: MTLRenderPipelineState

    /// Reused each frame; only the drawable texture changes.
    private let passDescriptor = MTLRenderPassDescriptor()

    /// Ring of vertex buffers, one per in-flight frame.
    private var vertexBuffers: [MTLBuffer?]
    private var nextSlot = 0
    private let inFlightSemaphore = DispatchSemaphore(value: MetalRenderer.maxFramesInFlight)

    /// CPU-side staging for the frame's triangles.  Keeps capacity across
    /// frames, so a steady-state frame performs zero heap allocations here.
    private var vertices: [GCVertex] = []
    private var batches: [GCDrawBatch] = []

    /// Open (still accumulating) batch.
    private var openTexture: MTLTexture?
    private var openAdditive = false
    private var openBatchStart = 0

    /// Background colour the pass clears to.
    public var clearColor = MTLClearColor(red: 0.043, green: 0.055, blue: 0.078, alpha: 1.0)
    /// Shadow offset in VIRTUAL units (down-right), scaled to pixels at use.
    public var shadowOffsetVirtual = SIMD2<Float>(2, 2)
    /// Opacity of the dark copy emitted for GC_FLAG_SHADOW.
    public var shadowAlpha: Float = 0.45

    // MARK: Init

    /// Builds device-independent GPU state on the system default device:
    /// command queue, shader library, both pipelines.
    public convenience init() throws {
        guard let device = MTLCreateSystemDefaultDevice() else { throw Failure.noDevice }
        try self.init(device: device)
    }

    public init(device: MTLDevice) throws {
        self.device = device

        guard let queue = device.makeCommandQueue() else {
            throw Failure.pipelineCreationFailed("makeCommandQueue() returned nil")
        }
        queue.label = "SlimeArena command queue"
        self.commandQueue = queue

        // Compile the embedded MSL.  No .metal file, no build phase to wire up.
        let library: MTLLibrary
        do {
            library = try device.makeLibrary(source: MetalRenderer.shaderSource, options: nil)
        } catch {
            throw Failure.libraryCompilationFailed(String(describing: error))
        }

        guard let vertexFunction = library.makeFunction(name: "slime_vertex") else {
            throw Failure.functionMissing("slime_vertex")
        }
        guard let fragmentFunction = library.makeFunction(name: "slime_fragment") else {
            throw Failure.functionMissing("slime_fragment")
        }
        vertexFunction.label = "slime_vertex"
        fragmentFunction.label = "slime_fragment"

        // Vertex descriptor derived from the Swift struct's real layout.
        let vertexDescriptor = MTLVertexDescriptor()
        let positionOffset = MemoryLayout<GCVertex>.offset(of: \.position) ?? 0
        let uvOffset = MemoryLayout<GCVertex>.offset(of: \.uv) ?? 8
        let colorOffset = MemoryLayout<GCVertex>.offset(of: \.color) ?? 16

        vertexDescriptor.attributes[0].format = .float2
        vertexDescriptor.attributes[0].offset = positionOffset
        vertexDescriptor.attributes[0].bufferIndex = 0
        vertexDescriptor.attributes[1].format = .float2
        vertexDescriptor.attributes[1].offset = uvOffset
        vertexDescriptor.attributes[1].bufferIndex = 0
        vertexDescriptor.attributes[2].format = .float4
        vertexDescriptor.attributes[2].offset = colorOffset
        vertexDescriptor.attributes[2].bufferIndex = 0
        vertexDescriptor.layouts[0].stride = MemoryLayout<GCVertex>.stride
        vertexDescriptor.layouts[0].stepFunction = .perVertex

        self.normalPipeline = try MetalRenderer.makePipeline(
            device: device,
            vertexFunction: vertexFunction,
            fragmentFunction: fragmentFunction,
            vertexDescriptor: vertexDescriptor,
            additive: false)
        self.additivePipeline = try MetalRenderer.makePipeline(
            device: device,
            vertexFunction: vertexFunction,
            fragmentFunction: fragmentFunction,
            vertexDescriptor: vertexDescriptor,
            additive: true)

        self.vertexBuffers = Array(repeating: nil, count: MetalRenderer.maxFramesInFlight)

        passDescriptor.colorAttachments[0].loadAction = .clear
        passDescriptor.colorAttachments[0].storeAction = .store
        passDescriptor.colorAttachments[0].clearColor = clearColor
    }

    private static func makePipeline(
        device: MTLDevice,
        vertexFunction: MTLFunction,
        fragmentFunction: MTLFunction,
        vertexDescriptor: MTLVertexDescriptor,
        additive: Bool
    ) throws -> MTLRenderPipelineState {
        let descriptor = MTLRenderPipelineDescriptor()
        descriptor.label = additive ? "sprite/additive" : "sprite/normal"
        descriptor.vertexFunction = vertexFunction
        descriptor.fragmentFunction = fragmentFunction
        descriptor.vertexDescriptor = vertexDescriptor

        // Subscripted directly (never bound to a local): the Metal subscript is
        // imported as an implicitly-unwrapped optional, and member access through
        // it works whether the SDK annotates it as optional or not.
        descriptor.colorAttachments[0].pixelFormat = MetalRenderer.pixelFormat
        descriptor.colorAttachments[0].isBlendingEnabled = true
        descriptor.colorAttachments[0].rgbBlendOperation = .add
        descriptor.colorAttachments[0].alphaBlendOperation = .add
        // Straight alpha: the fragment shader returns un-premultiplied colour,
        // so the source has to be multiplied by its own alpha here.
        descriptor.colorAttachments[0].sourceRGBBlendFactor = .sourceAlpha
        descriptor.colorAttachments[0].sourceAlphaBlendFactor = .sourceAlpha
        if additive {
            // Muzzle flashes, sparks, glows.
            descriptor.colorAttachments[0].destinationRGBBlendFactor = .one
            descriptor.colorAttachments[0].destinationAlphaBlendFactor = .one
        } else {
            descriptor.colorAttachments[0].destinationRGBBlendFactor = .oneMinusSourceAlpha
            descriptor.colorAttachments[0].destinationAlphaBlendFactor = .oneMinusSourceAlpha
        }

        do {
            return try device.makeRenderPipelineState(descriptor: descriptor)
        } catch {
            throw Failure.pipelineCreationFailed(String(describing: error))
        }
    }

    // MARK: Frame

    /// Renders one frame's command list (in draw order) into `layer`.
    ///
    /// - Parameters:
    ///   - commands: library-owned command buffer, valid for the duration of
    ///     this call only.  Read once, copied into vertices, never retained.
    ///   - scale: `gc_view_scale()` — pixels per virtual unit.
    ///   - layer: the CAMetalLayer whose drawable we render into.
    ///   - textures: sprite/atlas/white textures.
    /// - Returns: false when there was nothing to present (no drawable, or a
    ///   zero-sized layer); the caller should simply skip the frame.
    @discardableResult
    public func render(
        commands: UnsafeBufferPointer<gc_cmd>,
        scale: Float,
        layer: CAMetalLayer,
        textures: TextureStore
    ) -> Bool {
        // 1. CPU: turn commands into a pixel-space triangle list.  This is the
        //    only place the C-owned pointer is read.
        buildVertices(commands: commands, scale: scale > 0 ? scale : 1, textures: textures)
        let vertexBytes = vertices.count * MemoryLayout<GCVertex>.stride

        // 2. Wait for a free ring slot *after* the CPU work so a stalled GPU
        //    cannot delay input handling, and *before* asking for a drawable so
        //    we never hold one while blocked.
        inFlightSemaphore.wait()
        guard let drawable = layer.nextDrawable() else {
            inFlightSemaphore.signal()
            return false
        }

        let slot = nextSlot
        nextSlot = (nextSlot + 1) % MetalRenderer.maxFramesInFlight
        let semaphore = inFlightSemaphore

        guard let commandBuffer = commandQueue.makeCommandBuffer() else {
            semaphore.signal()
            return false
        }
        commandBuffer.label = "SlimeArena frame"

        var vertexBufferForFrame: MTLBuffer?
        if vertexBytes > 0 {
            do {
                let buffer = try vertexBuffer(slot: slot, minimumBytes: vertexBytes)
                vertices.withUnsafeBytes { raw in
                    if let base = raw.baseAddress {
                        buffer.contents().copyMemory(from: base, byteCount: vertexBytes)
                    }
                }
                vertexBufferForFrame = buffer
            } catch {
                // A failed frame must not leak the semaphore or wedge the ring.
                NSLog("%@", "SlimeArenaRenderer: dropping frame: \(error)")
                semaphore.signal()
                return false
            }
        }

        encode(into: commandBuffer, drawable: drawable, vertexBuffer: vertexBufferForFrame)

        commandBuffer.addCompletedHandler { _ in semaphore.signal() }
        commandBuffer.present(drawable)
        commandBuffer.commit()
        return true
    }

    /// Encodes the cached batch list.  Batches are already in painter's order.
    private func encode(into commandBuffer: MTLCommandBuffer, drawable: CAMetalDrawable, vertexBuffer: MTLBuffer?) {
        passDescriptor.colorAttachments[0].texture = drawable.texture
        passDescriptor.colorAttachments[0].clearColor = clearColor

        guard let encoder = commandBuffer.makeRenderCommandEncoder(descriptor: passDescriptor) else {
            return
        }
        encoder.label = "SlimeArena pass"

        if let vertexBuffer = vertexBuffer, !batches.isEmpty {
            var viewport = SIMD2<Float>(Float(drawable.texture.width), Float(drawable.texture.height))
            encoder.setVertexBytes(&viewport, length: MemoryLayout<SIMD2<Float>>.stride, index: 1)
            encoder.setVertexBuffer(vertexBuffer, offset: 0, index: 0)

            var boundAdditive: Bool?
            var boundTexture: MTLTexture?
            for batch in batches {
                if boundAdditive != batch.additive {
                    encoder.setRenderPipelineState(batch.additive ? additivePipeline : normalPipeline)
                    boundAdditive = batch.additive
                }
                if boundTexture !== batch.texture {
                    encoder.setFragmentTexture(batch.texture, index: 0)
                    boundTexture = batch.texture
                }
                encoder.drawPrimitives(type: .triangle,
                                       vertexStart: batch.start,
                                       vertexCount: batch.count)
            }
        }

        encoder.endEncoding()
    }

    // MARK: Vertex buffer growth

    /// Returns a buffer of at least `minimumBytes`, re-allocating only when the
    /// slot's current buffer is too small.  Growth is amortised (next power of
    /// two, minimum 64 KiB) so a steady-state frame never allocates.
    private func vertexBuffer(slot: Int, minimumBytes: Int) throws -> MTLBuffer {
        if let existing = vertexBuffers[slot], existing.length >= minimumBytes {
            return existing
        }
        let target = max(64 * 1024, nextPowerOfTwo(minimumBytes))
        guard let buffer = device.makeBuffer(length: target, options: .storageModeShared) else {
            throw Failure.vertexBufferAllocationFailed(target)
        }
        buffer.label = "vertices[\(slot)] \(target) bytes"
        vertexBuffers[slot] = buffer
        return buffer
    }

    private func nextPowerOfTwo(_ value: Int) -> Int {
        guard value > 1 else { return 1 }
        return 1 << (Int.bitWidth - (value - 1).leadingZeroBits)
    }

    // MARK: Batching

    /// Walks the command list once, appending triangles.  No allocations when
    /// the previous frame already grew `vertices`/`batches` enough.
    private func buildVertices(commands: UnsafeBufferPointer<gc_cmd>, scale: Float, textures: TextureStore) {
        vertices.removeAll(keepingCapacity: true)
        batches.removeAll(keepingCapacity: true)
        openTexture = nil
        openBatchStart = 0

        if vertices.capacity < commands.count * 6 {
            vertices.reserveCapacity(commands.count * 6)
        }
        if batches.capacity < 8 {
            batches.reserveCapacity(8)
        }

        for index in 0..<commands.count {
            let command = commands[index]
            // Unknown kinds are skipped rather than fatal: a newer core must not
            // crash an older renderer.
            guard let kind = command.cmdKind else { continue }

            let texture = textures.texture(for: kind, spriteID: command.sprite)

            // GC_FLAG_SHADOW: dark offset copy first, normal blend, same
            // texture (so glyphs and sprites shadow their own silhouette).
            if command.wantsShadow {
                selectBatch(texture: texture, additive: false)
                let base = MetalRenderer.unpack(command.rgba)
                let shadowColor = SIMD4<Float>(0, 0, 0, base.w * shadowAlpha)
                appendQuad(command: command,
                           scale: scale,
                           color: shadowColor,
                           uv: uvRect(for: kind, command: command),
                           offsetVirtual: shadowOffsetVirtual)
            }

            selectBatch(texture: texture, additive: command.isAdditive)
            appendQuad(command: command,
                       scale: scale,
                       color: MetalRenderer.unpack(command.rgba),
                       uv: uvRect(for: kind, command: command))
        }

        closeOpenBatch()
    }

    /// Switches to (texture, blend) — closing the previous run first.  Two
    /// consecutive commands with the same pair stay in one draw call.
    private func selectBatch(texture: MTLTexture, additive: Bool) {
        if openTexture === texture, openAdditive == additive {
            return
        }
        closeOpenBatch()
        openTexture = texture
        openAdditive = additive
        openBatchStart = vertices.count
    }

    private func closeOpenBatch() {
        guard let texture = openTexture else { return }
        let count = vertices.count - openBatchStart
        if count > 0 {
            batches.append(GCDrawBatch(start: openBatchStart,
                                       count: count,
                                       texture: texture,
                                       additive: openAdditive))
        }
        openTexture = nil
    }

    /// UV rectangle for a command.
    ///  * sprite: the whole texture, origin top-left.
    ///  * glyph:  the core's normalized atlas rect (v grows downwards).
    ///  * rect:   the middle of the 1x1 white texture, so clamping can never
    ///            blend in a neighbouring texel.
    @inline(__always)
    private func uvRect(for kind: GCCmdKind, command: gc_cmd) -> (u0: Float, v0: Float, u1: Float, v1: Float) {
        switch kind {
        case .sprite: return (0, 0, 1, 1)
        case .glyph: return (command.u0, command.v0, command.u1, command.v1)
        case .rect: return (0.5, 0.5, 0.5, 0.5)
        }
    }

    /// Emits two triangles for one command.
    ///
    /// `(x, y)` is the CENTER of the quad; `rot` is clockwise about that center.
    /// In a y-down space a clockwise rotation is the usual
    /// (x*cos - y*sin, x*sin + y*cos) matrix with a positive angle, so the
    /// corner order below is TL, TR, BR, BL as seen on screen.
    @inline(__always)
    private func appendQuad(
        command: gc_cmd,
        scale: Float,
        color: SIMD4<Float>,
        uv: (u0: Float, v0: Float, u1: Float, v1: Float),
        offsetVirtual: SIMD2<Float> = .zero
    ) {
        let halfWidth = command.w * 0.5
        let halfHeight = command.h * 0.5
        let angle = command.rot
        let cosA = cos(angle)
        let sinA = sin(angle)
        let center = SIMD2<Float>(command.x, command.y) + offsetVirtual

        func pixel(_ localX: Float, _ localY: Float) -> SIMD2<Float> {
            // Rotate the local corner offset, translate to the quad center,
            // then scale virtual units -> framebuffer pixels (y stays down).
            let rotated = SIMD2<Float>(localX * cosA - localY * sinA,
                                       localX * sinA + localY * cosA)
            return (center + rotated) * scale
        }

        let topLeft = pixel(-halfWidth, -halfHeight)
        let topRight = pixel(halfWidth, -halfHeight)
        let bottomRight = pixel(halfWidth, halfHeight)
        let bottomLeft = pixel(-halfWidth, halfHeight)

        let uvTopLeft = SIMD2<Float>(uv.u0, uv.v0)
        let uvTopRight = SIMD2<Float>(uv.u1, uv.v0)
        let uvBottomRight = SIMD2<Float>(uv.u1, uv.v1)
        let uvBottomLeft = SIMD2<Float>(uv.u0, uv.v1)

        appendVertex(topLeft, uvTopLeft, color)
        appendVertex(topRight, uvTopRight, color)
        appendVertex(bottomRight, uvBottomRight, color)
        appendVertex(topLeft, uvTopLeft, color)
        appendVertex(bottomRight, uvBottomRight, color)
        appendVertex(bottomLeft, uvBottomLeft, color)
    }

    @inline(__always)
    private func appendVertex(_ position: SIMD2<Float>, _ uv: SIMD2<Float>, _ color: SIMD4<Float>) {
        vertices.append(GCVertex(position: position, uv: uv, color: color))
    }

    // MARK: Colour unpacking

    /// `0xAARRGGBB` straight (non-premultiplied) alpha -> linear float4.
    /// The blend state applies the alpha; the shader does not.
    @inline(__always)
    public static func unpack(_ rgba: UInt32) -> SIMD4<Float> {
        let alpha = Float((rgba >> 24) & 0xFF) * (1.0 / 255.0)
        let red = Float((rgba >> 16) & 0xFF) * (1.0 / 255.0)
        let green = Float((rgba >> 8) & 0xFF) * (1.0 / 255.0)
        let blue = Float(rgba & 0xFF) * (1.0 / 255.0)
        return SIMD4<Float>(red, green, blue, alpha)
    }

    // MARK: Diagnostics

    /// Draw calls the last `render` produced (for the title bar / profiling).
    public var lastDrawCallCount: Int { batches.count }
    /// Vertices the last `render` produced.
    public var lastVertexCount: Int { vertices.count }
}
