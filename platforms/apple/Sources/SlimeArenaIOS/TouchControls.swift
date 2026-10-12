//
//  TouchControls.swift
//  SlimeArenaIOS
//
//  The two on-screen controls: a round DASH button (a real UIButton, so it
//  consumes its own touches and the game view never sees them) and a
//  non-interactive overlay that draws the two floating sticks so the player can
//  see where a stick began and how far it is pushed.
//
//  The stick *maths* is not here: it lives in SlimeArenaRenderer/Input.swift
//  (VirtualJoystick) so macOS, iOS and any future shell share one
//  implementation.
//

import UIKit
import SlimeArenaRenderer

// MARK: - DASH button

/// Circular DASH button sized by its constraints; the highlight states are
/// explicit because a plain UIButton on a dark Metal background is invisible.
final class DashButton: UIButton {

    override init(frame: CGRect) {
        super.init(frame: frame)
        configure()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        configure()
    }

    private func configure() {
        setTitle("DASH", for: .normal)
        titleLabel?.font = .systemFont(ofSize: 15, weight: .heavy)
        setTitleColor(.white, for: .normal)
        setTitleColor(UIColor(white: 1, alpha: 0.6), for: .highlighted)
        backgroundColor = UIColor(white: 1, alpha: 0.14)
        layer.borderWidth = 2
        layer.borderColor = UIColor(white: 1, alpha: 0.38).cgColor
        layer.masksToBounds = true
        // The button is sized by Auto Layout (84x84) and the title is centred by
        // UIButton itself, so no content insets are needed.
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        layer.cornerRadius = bounds.height / 2
    }

    override var isHighlighted: Bool {
        didSet {
            backgroundColor = UIColor(white: 1, alpha: isHighlighted ? 0.32 : 0.14)
        }
    }
}

// MARK: - Stick overlay

/// Where one stick currently is, in view points.
struct StickVisualState {
    /// nil when the stick is idle.
    var origin: SIMD2<Float>?
    /// Current knob position in view points.
    var knob: SIMD2<Float> = .zero
    /// Stick radius in view points.
    var radius: Float = 0
}

/// Draws the two floating sticks.  Never interactive: touches must reach
/// MetalView underneath.
final class StickOverlay: UIView {

    private let moveRing = CAShapeLayer()
    private let moveKnob = CAShapeLayer()
    private let aimRing = CAShapeLayer()
    private let aimKnob = CAShapeLayer()

    override init(frame: CGRect) {
        super.init(frame: frame)
        isUserInteractionEnabled = false
        isOpaque = false
        backgroundColor = .clear

        configure(shape: moveRing)
        configure(shape: aimRing)
        configure(shape: moveKnob)
        configure(shape: aimKnob)

        // Movement stick reads cool, aim stick reads warm: the two halves of the
        // screen are otherwise indistinguishable in a screenshot.
        moveRing.strokeColor = UIColor(red: 0.45, green: 0.85, blue: 1, alpha: 0.45).cgColor
        moveKnob.fillColor = UIColor(red: 0.45, green: 0.85, blue: 1, alpha: 0.35).cgColor
        aimRing.strokeColor = UIColor(red: 1, green: 0.72, blue: 0.35, alpha: 0.45).cgColor
        aimKnob.fillColor = UIColor(red: 1, green: 0.72, blue: 0.35, alpha: 0.35).cgColor
    }

    required init?(coder: NSCoder) {
        // Created in code by GameViewController; there is no nib.
        fatalError("StickOverlay is created in code; init(coder:) is unreachable")
    }

    private func configure(shape: CAShapeLayer) {
        shape.fillColor = UIColor.clear.cgColor
        shape.strokeColor = UIColor(white: 1, alpha: 0.25).cgColor
        shape.lineWidth = 2
        shape.isHidden = true
        layer.addSublayer(shape)
    }

    /// Called every frame from the display link.  Deliberately not called
    /// `update(...)`: a name that cannot collide with a UIView method.
    func updateSticks(move: StickVisualState, aim: StickVisualState) {
        // CALayer geometry changes must not be animated implicitly.
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        apply(state: move, ring: moveRing, knob: moveKnob)
        apply(state: aim, ring: aimRing, knob: aimKnob)
        CATransaction.commit()
    }

    private func apply(state: StickVisualState, ring: CAShapeLayer, knob: CAShapeLayer) {
        guard let origin = state.origin, state.radius > 0 else {
            ring.isHidden = true
            knob.isHidden = true
            return
        }
        ring.isHidden = false
        knob.isHidden = false

        let originPoint = CGPoint(x: CGFloat(origin.x), y: CGFloat(origin.y))
        let radius = CGFloat(state.radius)
        ring.path = UIBezierPath(
            arcCenter: originPoint,
            radius: radius,
            startAngle: 0,
            endAngle: .pi * 2,
            clockwise: true).cgPath
        ring.lineWidth = 2

        // Knob: clamp the visual to the ring so it cannot escape the circle even
        // if the finger travels further than the radius.
        var offset = CGPoint(x: CGFloat(state.knob.x) - originPoint.x,
                             y: CGFloat(state.knob.y) - originPoint.y)
        let distance = (offset.x * offset.x + offset.y * offset.y).squareRoot()
        if distance > radius, distance > 0 {
            offset.x *= radius / distance
            offset.y *= radius / distance
        }
        let knobRadius = max(10, radius * 0.28)
        let knobCenter = CGPoint(x: originPoint.x + offset.x, y: originPoint.y + offset.y)
        knob.path = UIBezierPath(
            arcCenter: knobCenter,
            radius: knobRadius,
            startAngle: 0,
            endAngle: .pi * 2,
            clockwise: true).cgPath
    }
}
