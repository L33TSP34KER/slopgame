//
//  GameView.swift
//  SlimeArenaMac
//
//  The AppKit view that owns the whole macOS renderer: the core handle, the
//  Metal layer, the textures, the frame loop and all input state.
//
//  COORDINATE CONVERSION (the part that is easy to get wrong)
//  ---------------------------------------------------------
//  AppKit view coordinates are y-UP, origin bottom-left of the view, measured in
//  POINTS.  The library wants virtual units, y-DOWN, origin top-left of the
//  framebuffer, where
//
//      scale   = framebuffer_height_px / GC_DESIGN_HEIGHT
//      pixel   = virtual * scale
//
//  so one mouse event becomes:
//
//      point            = convert(event.locationInWindow, from: nil)   // y-up points
//      px               = point.x * window.backingScaleFactor
//      py               = (bounds.height - point.y) * window.backingScaleFactor
//      virtual          = (px, py) / gc_view_scale()
//
//  `bounds.height` is in points: the flip and the scale commute, but flipping in
//  points keeps the expression readable and guarantees the y reference is the
//  view's own top edge, not the screen's.
//
//  `NSEvent.mouseLocation` (a class property) is *screen* coordinates, y-UP,
//  origin bottom-left of the PRIMARY screen; it is only used when no
//  locationInWindow exists (mouse outside the view), and it must be routed
//  through the window first — see `refreshAimFromScreenMouseLocation()`.
//

import AppKit
import Metal
import QuartzCore
import SlimeArenaRenderer

final class GameView: NSView {

    static let saveKey = "com.slimearena.saveBlob"

    // MARK: Owned state

    let core: GameCore
    let renderer: MetalRenderer
    let textures: TextureStore
    private let feedback: AudioHapticsDispatcher

    private var frameDriver: DisplayLinkDriver?
    private var inputState = GCInputState()
    private var translator = KeyboardTranslator()
    private var lastFrameTime: CFTimeInterval = 0
    private var secondsSinceTitleUpdate: CFTimeInterval = 0
    private var lastFramebufferSize = CGSize.zero

    /// Called ~4x a second with a fresh status snapshot (window title).
    var onStatusChange: ((GCStatus) -> Void)?
    /// Called once per R press (edge-detected here, because the core consumes
    /// the held-state bitmask and never reports edges back to the shell).
    var onRestartRequested: (() -> Void)?
    private var previousRestartState = false

    /// Layer-backed by `makeBackingLayer()`; AppKit keeps its frame in sync.
    private lazy var metalLayer: CAMetalLayer = {
        let layer = CAMetalLayer()
        layer.device = renderer.device
        layer.pixelFormat = MetalRenderer.pixelFormat
        layer.framebufferOnly = true
        layer.isOpaque = true
        layer.allowsNextDrawableTimeout = true
        return layer
    }()

    // MARK: Construction

    /// Builds the game: core, GPU state and textures.  Everything that can fail
    /// happens here, so the app delegate can present one clear alert.
    static func make(frame: NSRect) throws -> GameView {
        let core = try GameCore()
        let renderer = try MetalRenderer()
        let textures = try TextureStore.loadFromBundle(device: renderer.device)
        for warning in textures.warnings {
            NSLog("SlimeArenaRenderer: %@", warning)
        }
        return GameView(frame: frame, core: core, renderer: renderer, textures: textures)
    }

    init(frame frameRect: NSRect, core: GameCore, renderer: MetalRenderer, textures: TextureStore) {
        self.core = core
        self.renderer = renderer
        self.textures = textures
        self.feedback = AudioHapticsDispatcher()
        super.init(frame: frameRect)
        wantsLayer = true
        autoresizingMask = [.width, .height]
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        // Programmatic app: there is no nib or storyboard to decode.
        fatalError("GameView is created in code; init(coder:) is unreachable")
    }

    override var acceptsFirstResponder: Bool { true }
    override var isOpaque: Bool { true }

    /// AppKit asks for the backing layer; returning a CAMetalLayer makes the
    /// whole view a Metal drawable with no extra NSView subclassing.
    override func makeBackingLayer() -> CALayer {
        return metalLayer
    }

    // MARK: Lifecycle

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        // Needed for mouseMoved(with:) to be delivered at all.
        window?.acceptsMouseMovedEvents = true
        window?.makeFirstResponder(self)
        // viewDidMoveToWindow can fire more than once (e.g. re-parenting), so
        // drop any previous registration before adding a new one.
        NotificationCenter.default.removeObserver(
            self, name: NSWindow.didResignKeyNotification, object: nil)
        if let window = window {
            NotificationCenter.default.addObserver(
                self,
                selector: #selector(windowDidResignKey),
                name: NSWindow.didResignKeyNotification,
                object: window)
        }
        updateFramebufferSize()
    }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        updateFramebufferSize()
    }

    override func viewDidChangeBackingProperties() {
        // Fires when the window moves to a display with a different
        // backingScaleFactor (Retina <-> non-Retina).
        super.viewDidChangeBackingProperties()
        updateFramebufferSize()
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
        frameDriver?.stop()
    }

    /// Stops the frame loop and persists the save blob.  Called on terminate.
    func shutdown() {
        frameDriver?.stop()
        frameDriver = nil
        saveToUserDefaults()
    }

    // MARK: Framebuffer

    /// Pushes the pixel size and (zero) safe-area insets into the core and sizes
    /// the drawable.  macOS has no safe area, so the insets are 0.
    func updateFramebufferSize() {
        let backingScale = window?.backingScaleFactor ?? 2
        let pixelWidth = max(1, Int((bounds.width * backingScale).rounded()))
        let pixelHeight = max(1, Int((bounds.height * backingScale).rounded()))
        let size = CGSize(width: pixelWidth, height: pixelHeight)
        guard size != lastFramebufferSize else { return }
        lastFramebufferSize = size

        metalLayer.contentsScale = backingScale
        metalLayer.drawableSize = size
        core.resize(framebufferWidth: pixelWidth, framebufferHeight: pixelHeight)
        feedback.virtualWidth = core.virtualSize.width
    }

    // MARK: Frame loop

    func startRendering() {
        guard frameDriver == nil else { return }
        guard let driver = DisplayLinkDriver.make(onFrame: { [weak self] in self?.step() }) else {
            NSLog("SlimeArenaMac: could not create a CVDisplayLink; the window will not animate.")
            return
        }
        frameDriver = driver
        lastFrameTime = CACurrentMediaTime()
        driver.start()
    }

    func stopRendering() {
        frameDriver?.stop()
        frameDriver = nil
    }

    /// One simulation step + one frame, always on the main thread.
    private func step() {
        let now = CACurrentMediaTime()
        var dt = Float(now - lastFrameTime)
        lastFrameTime = now
        if !(dt > 0) { dt = 1.0 / 60.0 }        // first frame, or a clock hiccup
        dt = min(dt, 1.0 / 15.0)                // never simulate a long stall

        // Held key state -> movement axis and button bitmask.  The library
        // edge-detects, so we only ever pass *held* state.
        translator.apply(to: &inputState)
        handleRestartEdge()

        core.update(input: inputState.input, dt: dt)
        core.withEvents { feedback.handle(events: $0) }

        let scale = core.viewScale
        core.withCommands { renderer.render(commands: $0, scale: scale, layer: metalLayer, textures: textures) }

        secondsSinceTitleUpdate += Double(dt)
        if secondsSinceTitleUpdate >= 0.25 {
            secondsSinceTitleUpdate = 0
            onStatusChange?(core.status())
        }
    }

    private func handleRestartEdge() {
        let restart = inputState.isPressed(.restart)
        if restart && !previousRestartState {
            onRestartRequested?()
        }
        previousRestartState = restart
    }

    // MARK: Keyboard

    override func keyDown(with event: NSEvent) {
        // Key repeat carries no new information: the key is already held.
        guard !event.isARepeat else { return }
        translator.keyDown(keyCode: event.keyCode, characters: event.charactersIgnoringModifiers)
        // Deliberately no super call: unhandled keys would make AppKit beep.
        // Command-key equivalents (⌘Q, ⌘H) never reach keyDown — the menu
        // handles them through performKeyEquivalent first.
    }

    override func keyUp(with event: NSEvent) {
        translator.keyUp(keyCode: event.keyCode, characters: event.charactersIgnoringModifiers)
    }

    override func resignFirstResponder() -> Bool {
        // Never leave a key "stuck down" while another view has focus.
        releaseAllInput()
        return super.resignFirstResponder()
    }

    @objc private func windowDidResignKey() {
        releaseAllInput()
    }

    private func releaseAllInput() {
        translator.releaseAll()
        inputState.clearMoveAxis()
        inputState.setPointerDown(false)
        inputState.release(.dash)
        inputState.release(.pause)
        inputState.release(.restart)
        previousRestartState = false
    }

    // MARK: Mouse

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        for area in trackingAreas {
            removeTrackingArea(area)
        }
        // .inVisibleRect keeps the area correct through resizes.
        addTrackingArea(NSTrackingArea(
            rect: .zero,
            options: [.mouseMoved, .mouseEnteredAndExited, .activeInKeyWindow, .inVisibleRect],
            owner: self,
            userInfo: nil))
    }

    override func mouseDown(with event: NSEvent) {
        updateAim(from: event)
        inputState.setPointerDown(true)
    }

    override func mouseUp(with event: NSEvent) {
        updateAim(from: event)
        inputState.setPointerDown(false)
    }

    override func mouseDragged(with event: NSEvent) {
        updateAim(from: event)
    }

    override func mouseMoved(with event: NSEvent) {
        updateAim(from: event)
    }

    override func mouseEntered(with event: NSEvent) {
        refreshAimFromScreenMouseLocation()
    }

    override func mouseExited(with event: NSEvent) {
        // Keep the last aim; a pointer outside the window is still "known" on a
        // desktop, which is what GCInputState.pointerActive means.
        inputState.setPointerDown(false)
    }

    /// Mouse event -> virtual units.  See the file header for the derivation.
    private func updateAim(from event: NSEvent) {
        let pointInView = convert(event.locationInWindow, from: nil)
        applyAim(viewPoint: pointInView)
    }

    /// Same conversion, but starting from `NSEvent.mouseLocation` (screen
    /// coordinates, y-up, origin bottom-left of the primary screen).  The window
    /// converts it into window coordinates (still y-up), after which the flip
    /// and scale are identical.  Used when no locationInWindow is available.
    private func refreshAimFromScreenMouseLocation() {
        guard let window = window else { return }
        let pointInWindow = window.convertPoint(fromScreen: NSEvent.mouseLocation)
        let pointInView = convert(pointInWindow, from: nil)
        applyAim(viewPoint: pointInView)
    }

    private func applyAim(viewPoint: NSPoint) {
        let backingScale = window?.backingScaleFactor ?? 2
        let pixels = GCCoordinates.appKitPointToPixels(
            viewPoint,
            viewHeightInPoints: bounds.height,
            backingScaleFactor: backingScale)
        inputState.setAim(pixelPosition: pixels, scale: core.viewScale)
    }

    // MARK: Persistence

    /// `gc_save` -> UserDefaults.  This is what keeps the best score.
    func saveToUserDefaults(defaults: UserDefaults = .standard) {
        guard let blob = core.save() else { return }
        defaults.set(blob, forKey: GameView.saveKey)
    }

    /// Restores the blob written by `saveToUserDefaults` (call once at launch,
    /// after gc_create).
    func restoreFromUserDefaults(defaults: UserDefaults = .standard) {
        guard let blob = defaults.data(forKey: GameView.saveKey) else { return }
        if !core.load(blob) {
            NSLog("SlimeArenaMac: stored save blob was rejected by gc_load; ignoring it.")
        }
    }

    // MARK: Diagnostics

    /// One-line summary for the title bar's tooltip.
    var diagnostics: String {
        "draws \(renderer.lastDrawCallCount) · verts \(renderer.lastVertexCount) · scale \(core.viewScale)"
    }
}
