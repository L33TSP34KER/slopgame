//
//  MetalView.swift
//  SlimeArenaIOS
//
//  A UIView whose backing layer is a CAMetalLayer.
//
//  Coordinate facts that matter for everything downstream:
//    * UIKit touch coordinates are y-DOWN points, origin TOP-LEFT of the view.
//    * The library's virtual space is y-DOWN, origin top-left of the
//      framebuffer.  So the iOS conversion has NO y flip, unlike AppKit:
//          pixels  = point * displayScale
//          virtual = pixels / gc_view_scale()
//    * The view deliberately fills the whole window (it is the controller's
//      `view` and is NOT constrained to the safe area), so the framebuffer
//      origin is the screen's top-left and the simple conversion above is
//      correct.  The safe-area insets are passed to gc_resize separately.
//
//  Touch handling itself lives in GameViewController (it owns the game state);
//  this view just forwards the raw touch sets.
//

import UIKit
import Metal
import QuartzCore
import SlimeArenaRenderer

protocol MetalViewTouchDelegate: AnyObject {
    func metalView(_ view: MetalView, touchesBegan touches: Set<UITouch>, event: UIEvent?)
    func metalView(_ view: MetalView, touchesMoved touches: Set<UITouch>, event: UIEvent?)
    func metalView(_ view: MetalView, touchesEnded touches: Set<UITouch>, event: UIEvent?)
    func metalView(_ view: MetalView, touchesCancelled touches: Set<UITouch>, event: UIEvent?)
}

final class MetalView: UIView {

    weak var touchDelegate: MetalViewTouchDelegate?

    /// The view's backing layer is always a CAMetalLayer (see `layerClass`), so
    /// this cast cannot fail.
    var metalLayer: CAMetalLayer {
        guard let metalLayer = layer as? CAMetalLayer else {
            // Unreachable: `layerClass` is CAMetalLayer and UIKit never swaps a
            // view's backing layer class at runtime.
            fatalError("MetalView.layer is not a CAMetalLayer")
        }
        return metalLayer
    }

    override class var layerClass: AnyClass { CAMetalLayer.self }

    override init(frame: CGRect) {
        super.init(frame: frame)
        // Two thumbs at once: a movement stick and an aim stick.
        isMultipleTouchEnabled = true
        isExclusiveTouch = false
        isOpaque = true
        backgroundColor = .black
        contentScaleFactor = displayScale

        let layer = metalLayer
        layer.pixelFormat = MetalRenderer.pixelFormat
        layer.framebufferOnly = true
        layer.isOpaque = true
        layer.allowsNextDrawableTimeout = true
        layer.contentsScale = displayScale
    }

    required init?(coder: NSCoder) {
        // The app builds every view in code, so there is no nib to decode.
        fatalError("MetalView is created in code; init(coder:) is unreachable")
    }

    /// `renderer` is attached after construction because the Metal device only
    /// exists once the renderer has been created.
    func attach(device: MTLDevice) {
        metalLayer.device = device
    }

    private var displayScale: CGFloat {
        let scale = traitCollection.displayScale
        return scale > 0 ? scale : 1
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        // Screen changes (external display, Stage Manager) can change the scale.
        contentScaleFactor = displayScale
        metalLayer.contentsScale = displayScale
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        // The drawableSize itself is pushed by GameViewController, together with
        // gc_resize(), so the layer and the core can never disagree.
        metalLayer.contentsScale = displayScale
    }

    // MARK: Touch forwarding

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        touchDelegate?.metalView(self, touchesBegan: touches, event: event)
    }

    override func touchesMoved(_ touches: Set<UITouch>, with event: UIEvent?) {
        touchDelegate?.metalView(self, touchesMoved: touches, event: event)
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        touchDelegate?.metalView(self, touchesEnded: touches, event: event)
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        touchDelegate?.metalView(self, touchesCancelled: touches, event: event)
    }
}
