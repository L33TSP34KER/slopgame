//
//  GameViewController.swift
//  SlimeArenaIOS
//
//  Owns the game on iOS: core handle, Metal renderer, textures, the CADisplayLink
//  loop and all touch input.
//
//  TOUCH MAPPING (the design decision, written down once)
//  -----------------------------------------------------
//  * LEFT half of the screen  -> floating MOVEMENT stick.  The stick is born
//    where the finger lands; the axis is the offset from that point, dead-zoned
//    (~10% of the radius) and clamped to the radius.  It drives
//    GCInput.move_x/move_y.  Both UIKit and the library are y-down, so a finger
//    dragged down gives a positive move_y with no inversion.
//  * RIGHT half               -> floating AIM stick.  It sets
//    GCInput.pointer_active = 1 and the aim position in VIRTUAL units, taken
//    from the *current finger position* (absolute, exactly like a mouse cursor)
//    rather than from an origin+offset, because gc_input.aim_* is documented as
//    an absolute pointer position in virtual units.  pointer_down = 1 while the
//    finger is held.  The stick origin is still recorded so the overlay can show
//    where the aim began.
//  * DASH button (bottom right, inside the safe area) -> GC_BTN_DASH while held.
//    It is a real UIButton, so it swallows its own touches and the sticks never
//    see them.
//
//  Rotation: viewWillTransition + the per-frame size check both funnel into
//  updateFramebufferSize(), which pushes the PIXEL size and the safe-area insets
//  (also in pixels) to gc_resize and resizes the drawable.
//

import UIKit
import Metal
import QuartzCore
import SlimeArenaRenderer

/// Breaks the CADisplayLink -> target retain cycle: CADisplayLink keeps a strong
/// reference to its target, and the target here is the view controller.
final class DisplayLinkProxy: NSObject {
    weak var controller: GameViewController?

    @objc func step(_ link: CADisplayLink) {
        controller?.stepDisplayLink(link)
    }
}

final class GameViewController: UIViewController, MetalViewTouchDelegate {

    private static let saveKey = "com.slimearena.saveBlob"

    // Game objects ---------------------------------------------------------
    private let gameView = MetalView(frame: .zero)
    private let overlay = StickOverlay(frame: .zero)
    private var core: GameCore?
    private var renderer: MetalRenderer?
    private var textures: TextureStore?
    private var feedback: AudioHapticsDispatcher?

    // Loop -----------------------------------------------------------------
    private let displayLinkProxy = DisplayLinkProxy()
    private var displayLink: CADisplayLink?
    private var lastFrameTime: CFTimeInterval = 0
    private var lastFramebufferSize = CGSize.zero
    private var lastSafeAreaInsets = UIEdgeInsets.zero

    // Input ----------------------------------------------------------------
    private var inputState = GCInputState()
    private var moveStick = VirtualJoystick(radius: 96)
    private var aimStick = VirtualJoystick(radius: 96, deadZone: 0)
    private weak var moveTouch: UITouch?
    private weak var aimTouch: UITouch?
    private var dashButton: DashButton?

    // MARK: - Lifecycle

    override func loadView() {
        // The game view *is* the controller's view and fills the window; the
        // safe area is only reported to the core, never used to inset the
        // framebuffer (that would shift every command).
        view = gameView
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        gameView.touchDelegate = self
        gameView.backgroundColor = .black

        overlay.frame = gameView.bounds
        overlay.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        gameView.addSubview(overlay)
        installDashButton()

        do {
            try startGame()
        } catch {
            presentStartupFailure(error)
            return
        }

        registerLifecycleObservers()
        restoreFromUserDefaults()
        startDisplayLink()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        updateFramebufferSize()
    }

    override func viewWillTransition(to size: CGSize, with coordinator: UIViewControllerTransitionCoordinator) {
        super.viewWillTransition(to: size, with: coordinator)
        // Bounds and safe-area insets are only final after the rotation
        // animation, so resize once it completes as well.
        coordinator.animate(alongsideTransition: nil) { [weak self] _ in
            self?.updateFramebufferSize(force: true)
        }
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
        displayLink?.invalidate()
    }

    // MARK: - Startup

    /// Creates the core, the renderer and the textures.  Throws so the failure
    /// can be shown on screen instead of crashing an app the user cannot fix.
    private func startGame() throws {
        let core = try GameCore()
        self.core = core

        let renderer = try MetalRenderer()
        self.renderer = renderer
        gameView.attach(device: renderer.device)

        let textures = try TextureStore.loadFromBundle(device: renderer.device)
        self.textures = textures
        for warning in textures.warnings {
            NSLog("SlimeArenaRenderer: %@", warning)
        }

        let feedback = AudioHapticsDispatcher()
        self.feedback = feedback

        updateFramebufferSize(force: true)
    }

    private func presentStartupFailure(_ error: Error) {
        NSLog("SlimeArenaIOS: fatal startup error: %@", String(describing: error))

        let label = UILabel()
        label.numberOfLines = 0
        label.textAlignment = .center
        label.textColor = .white
        label.font = .monospacedSystemFont(ofSize: 13, weight: .regular)
        label.text = """
        Slime Arena could not start.

        \(String(describing: error))

        On iOS this normally means the app bundle is missing
        libgame_core.dylib (run build_ios_core.sh and check the
        Embed Frameworks phase) or the Assets folder reference.
        """
        label.translatesAutoresizingMaskIntoConstraints = false
        gameView.addSubview(label)
        NSLayoutConstraint.activate([
            label.leadingAnchor.constraint(equalTo: gameView.safeAreaLayoutGuide.leadingAnchor, constant: 20),
            label.trailingAnchor.constraint(equalTo: gameView.safeAreaLayoutGuide.trailingAnchor, constant: -20),
            label.centerYAnchor.constraint(equalTo: gameView.centerYAnchor),
        ])
    }

    private func installDashButton() {
        let button = DashButton(type: .custom)
        button.translatesAutoresizingMaskIntoConstraints = false
        button.addTarget(self, action: #selector(dashPressed), for: [.touchDown, .touchDragEnter])
        button.addTarget(self, action: #selector(dashReleased),
                         for: [.touchUpInside, .touchUpOutside, .touchCancel, .touchDragExit])
        gameView.addSubview(button)
        NSLayoutConstraint.activate([
            button.widthAnchor.constraint(equalToConstant: 84),
            button.heightAnchor.constraint(equalToConstant: 84),
            button.trailingAnchor.constraint(equalTo: gameView.safeAreaLayoutGuide.trailingAnchor, constant: -18),
            button.bottomAnchor.constraint(equalTo: gameView.safeAreaLayoutGuide.bottomAnchor, constant: -28),
        ])
        dashButton = button
    }

    @objc private func dashPressed() {
        inputState.press(.dash)
    }

    @objc private func dashReleased() {
        inputState.release(.dash)
    }

    // MARK: - Frame loop

    private func startDisplayLink() {
        guard displayLink == nil else { return }
        displayLinkProxy.controller = self
        let link = CADisplayLink(target: displayLinkProxy, selector: #selector(DisplayLinkProxy.step(_:)))
        // .common keeps it ticking during scroll/gesture tracking modes.
        link.add(to: .main, forMode: .common)
        displayLink = link
        lastFrameTime = CACurrentMediaTime()
    }

    private func stopDisplayLink() {
        displayLink?.invalidate()
        displayLink = nil
    }

    /// Called by DisplayLinkProxy on the main run loop.
    func stepDisplayLink(_ link: CADisplayLink) {
        guard let core = core, let renderer = renderer, let textures = textures else { return }

        // CADisplayLink.timestamp shares the CACurrentMediaTime() time base.
        let now = link.timestamp
        var dt = Float(now - lastFrameTime)
        lastFrameTime = now
        if !(dt > 0) { dt = 1.0 / 60.0 }
        dt = min(dt, 1.0 / 15.0)

        core.update(input: inputState.input, dt: dt)
        core.withEvents { events in
            self.feedback?.handle(events: events)
        }

        // Cheap, and it catches safe-area changes that do not come from a
        // rotation (Stage Manager, call status bar, ...).
        updateFramebufferSize()

        overlay.updateSticks(move: moveVisualState(), aim: aimVisualState())

        let scale = core.viewScale
        core.withCommands { commands in
            renderer.render(commands: commands, scale: scale, layer: gameView.metalLayer, textures: textures)
        }
    }

    // MARK: - Framebuffer / rotation

    /// Pushes pixel size + pixel safe-area insets into the core and resizes the
    /// drawable.  Idempotent:
    /// the guard keeps the (relatively expensive) gc_resize out of every frame.
    private func updateFramebufferSize(force: Bool = false) {
        guard let core = core else { return }
        let scale = displayScale
        let pixelWidth = max(1, Int((gameView.bounds.width * scale).rounded()))
        let pixelHeight = max(1, Int((gameView.bounds.height * scale).rounded()))
        let insets = gameView.safeAreaInsets

        if !force,
           CGSize(width: pixelWidth, height: pixelHeight) == lastFramebufferSize,
           insets == lastSafeAreaInsets {
            return
        }
        lastFramebufferSize = CGSize(width: pixelWidth, height: pixelHeight)
        lastSafeAreaInsets = insets

        let layer = gameView.metalLayer
        layer.contentsScale = scale
        layer.drawableSize = CGSize(width: pixelWidth, height: pixelHeight)

        // gc_resize wants PIXELS for the insets too, never points.
        core.resize(
            framebufferWidth: pixelWidth,
            framebufferHeight: pixelHeight,
            safeLeft: Float(insets.left * scale),
            safeTop: Float(insets.top * scale),
            safeRight: Float(insets.right * scale),
            safeBottom: Float(insets.bottom * scale))

        feedback?.virtualWidth = core.virtualSize.width

        // Stick radius: ~18% of the short edge, so the stick feels the same on
        // an iPhone SE and an iPad.
        let radius = Float(min(gameView.bounds.width, gameView.bounds.height)) * 0.18
        moveStick.radius = max(48, radius)
        aimStick.radius = max(48, radius)
    }

    private var displayScale: CGFloat {
        let scale = gameView.traitCollection.displayScale
        return scale > 0 ? scale : 1
    }

    // MARK: - Touch handling

    func metalView(_ view: MetalView, touchesBegan touches: Set<UITouch>, event: UIEvent?) {
        for touch in touches {
            let point = touchPoint(touch, in: view)
            if point.x < Float(view.bounds.midX) {
                guard moveTouch == nil else { continue }
                moveTouch = touch
                moveStick.begin(at: point)
                inputState.setMoveAxis(x: 0, y: 0)
            } else {
                guard aimTouch == nil else { continue }
                aimTouch = touch
                aimStick.begin(at: point)
                inputState.setPointerDown(true)
                updateAim(from: point)
            }
        }
    }

    func metalView(_ view: MetalView, touchesMoved touches: Set<UITouch>, event: UIEvent?) {
        for touch in touches {
            let point = touchPoint(touch, in: view)
            if touch === moveTouch {
                let axis = moveStick.move(to: point)
                inputState.setMoveAxis(x: axis.x, y: axis.y)
            } else if touch === aimTouch {
                aimStick.move(to: point)
                updateAim(from: point)
            }
        }
    }

    func metalView(_ view: MetalView, touchesEnded touches: Set<UITouch>, event: UIEvent?) {
        end(touches: touches)
    }

    func metalView(_ view: MetalView, touchesCancelled touches: Set<UITouch>, event: UIEvent?) {
        end(touches: touches)
    }

    private func end(touches: Set<UITouch>) {
        for touch in touches {
            if touch === moveTouch {
                moveTouch = nil
                moveStick.end()
                inputState.clearMoveAxis()
            } else if touch === aimTouch {
                aimTouch = nil
                aimStick.end()
                // pointer_active deliberately stays 1 with the last known aim:
                // the core treats it as "a pointer is known", not "is held".
                inputState.setPointerDown(false)
            }
        }
    }

    /// Touch -> view points, as a SIMD2 so the shared stick maths can use it.
    private func touchPoint(_ touch: UITouch, in view: UIView) -> SIMD2<Float> {
        let location = touch.location(in: view)
        return SIMD2(Float(location.x), Float(location.y))
    }

    /// Aim: absolute finger position -> virtual units.
    ///  * points * displayScale = framebuffer pixels (no y flip: UIKit is y-down)
    ///  * pixels / gc_view_scale() = virtual units
    private func updateAim(from point: SIMD2<Float>) {
        guard let core = core else { return }
        let pixels = point * Float(displayScale)
        let virtual = GCCoordinates.pixelsToVirtual(pixels, scale: core.viewScale)
        inputState.setAimVirtual(x: virtual.x, y: virtual.y)
    }

    // MARK: - Overlay state

    private func moveVisualState() -> StickVisualState {
        let axis = moveStick.axis
        guard let origin = moveStick.origin else { return StickVisualState() }
        let clamped = axis.clampedToUnitLength()
        return StickVisualState(origin: origin,
                                knob: origin + clamped * moveStick.radius,
                                radius: moveStick.radius)
    }

    private func aimVisualState() -> StickVisualState {
        guard let origin = aimStick.origin else { return StickVisualState() }
        return StickVisualState(origin: origin, knob: origin + aimStick.axis * aimStick.radius, radius: aimStick.radius)
    }

    // MARK: - Lifecycle notifications

    private func registerLifecycleObservers() {
        let center = NotificationCenter.default
        // Posted by AppDelegate (applicationDidEnterBackground), which is the
        // hook the task requires; the UIKit notifications cover the paths that
        // do not go through the app delegate (e.g. a scene-less app on older
        // iOS, or a background refresh).
        center.addObserver(self, selector: #selector(handleEnterBackground),
                           name: .slimeArenaWillEnterBackground, object: nil)
        center.addObserver(self, selector: #selector(handleEnterForeground),
                           name: .slimeArenaWillEnterForeground, object: nil)
        center.addObserver(self, selector: #selector(handleEnterBackground),
                           name: UIApplication.didEnterBackgroundNotification, object: nil)
        center.addObserver(self, selector: #selector(handleEnterForeground),
                           name: UIApplication.willEnterForegroundNotification, object: nil)
    }

    @objc private func handleEnterBackground() {
        // Stop the loop FIRST: an invalidated CADisplayLink stops the GPU work
        // immediately, so the save below cannot race a frame.
        stopDisplayLink()
        releaseAllTouches()
        saveToUserDefaults()
    }

    @objc private func handleEnterForeground() {
        // The framebuffer may have changed while we were suspended.
        updateFramebufferSize(force: true)
        startDisplayLink()
    }

    /// iOS cancels touches when the app is backgrounded, but the sticks and the
    /// button bitmask must be cleared explicitly so the player does not return to
    /// a stuck dash or a frozen movement axis.
    private func releaseAllTouches() {
        // Clear the button's visual state too: UIKit cancels the touch without
        // sending touchUpInside when the app is backgrounded.
        dashButton?.isHighlighted = false
        moveTouch = nil
        aimTouch = nil
        moveStick.end()
        aimStick.end()
        inputState.clearMoveAxis()
        inputState.setPointerDown(false)
        inputState.release(.dash)
        inputState.release(.pause)
        inputState.release(.restart)
    }

    // MARK: - Persistence

    /// `gc_save` -> UserDefaults.  This is what keeps the best score.
    func saveToUserDefaults(defaults: UserDefaults = .standard) {
        guard let core = core, let blob = core.save() else { return }
        defaults.set(blob, forKey: GameViewController.saveKey)
    }

    private func restoreFromUserDefaults(defaults: UserDefaults = .standard) {
        guard let core = core, let blob = defaults.data(forKey: GameViewController.saveKey) else { return }
        if !core.load(blob) {
            NSLog("SlimeArenaIOS: stored save blob was rejected by gc_load; ignoring it.")
        }
    }

    // MARK: - Presentation

    override var prefersStatusBarHidden: Bool { true }
    override var prefersHomeIndicatorAutoHidden: Bool { true }
    override var supportedInterfaceOrientations: UIInterfaceOrientationMask { .allButUpsideDown }
}
