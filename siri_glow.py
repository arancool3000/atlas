"""Siri-style "Golden Gate" glow — a flowing, breathing band of light that sweeps
around Ember's window edge while it's listening, thinking, or speaking.

A frameless, click-through QWidget overlay sized to cover the window. Its paintEvent
strokes a rounded-rect just inside the edges with a conical gradient (a warm-leaning
rainbow: gold → orange → red → magenta → violet → blue → teal) whose angle rotates
over time, drawn in several soft layers so it blooms like a glow. Overall intensity
breathes with a sine, and each state (listen / think / speak) tunes the speed and
brightness. A ~60fps QTimer drives it; everything is wrapped so a paint hiccup can
never take down the app.
"""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt, QRectF, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QConicalGradient, QPainterPath
from PyQt6.QtWidgets import QWidget


# Vibrant spectral flow in the spirit of Apple's 2019 "wonderful things" / "By
# innovation only" event — saturated, liquid, alive — but kept ember-warm at the
# seam (gold first AND last) so the conical loop is seamless.
_PALETTE_HEX = ["#ffd23f", "#ff8c1a", "#ff5e3a", "#ff2d55", "#ff375f",
                "#bf5af2", "#5e5ce6", "#0a84ff", "#32d0c6", "#ffd23f"]

# Per-state tuning: (rotation speed, breath speed, min alpha, max alpha, stroke px)
# Snappier + brighter than before so the band reads as energetic, not sleepy.
_STATES = {
    "listening": (0.022, 3.6, 0.50, 1.00, 3.4),
    "thinking":  (0.010, 1.8, 0.34, 0.70, 2.8),
    "speaking":  (0.016, 5.4, 0.52, 1.00, 3.8),
}

# How fast the whole glow fades in / out (per ~60fps frame). ~0.09 -> ≈190ms.
_FADE_STEP = 0.09


class SiriGlow(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._palette = [QColor(h) for h in _PALETTE_HEX]
        self._phase = 0.0          # rotation phase (0..1)
        self._t = 0.0              # time accumulator for breathing
        self._active = False
        self._intensity = 0.0      # current global opacity envelope (0..1) — drives the fade
        self._target = 0.0         # where the envelope is heading (1 = on, 0 = fading out)
        self._corner = 22
        self._inset = 5
        self._layers = 5
        self._speed, self._breath, self._min_a, self._max_a, self._stroke = _STATES["listening"]
        self._timer = QTimer(self)
        self._timer.setInterval(16)   # ~60fps
        self._timer.timeout.connect(self._tick)

    # -- lifecycle -------------------------------------------------------------
    def cover(self):
        """Resize to fully cover the parent and sit on top."""
        p = self.parent()
        if p is not None:
            self.setGeometry(0, 0, p.width(), p.height())
        self.raise_()

    def set_state(self, state: str):
        cfg = _STATES.get(state)
        if cfg:
            self._speed, self._breath, self._min_a, self._max_a, self._stroke = cfg

    def start(self, state: str = "listening"):
        self.set_state(state)
        self.cover()
        self._active = True
        self._target = 1.0          # fade up to full
        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start()

    def stop(self):
        # Don't pop off — fade out, then hide when the envelope reaches zero (in _tick).
        self._target = 0.0

    def _tick(self):
        # Ease the opacity envelope toward its target so the glow fades in/out.
        if self._intensity < self._target:
            self._intensity = min(self._target, self._intensity + _FADE_STEP)
        elif self._intensity > self._target:
            self._intensity = max(self._target, self._intensity - _FADE_STEP)
        # Fully faded out -> stop animating and hide to save CPU.
        if self._target == 0.0 and self._intensity <= 0.0:
            self._active = False
            if self._timer.isActive():
                self._timer.stop()
            self.hide()
            return
        self._phase = (self._phase + self._speed) % 1.0
        self._t += 0.016
        try:
            self.update()
        except Exception:
            pass

    # -- painting --------------------------------------------------------------
    def _ring_gradient(self, cx, cy, angle_deg, alpha):
        g = QConicalGradient(cx, cy, angle_deg % 360)
        n = len(self._palette)
        a = int(max(0, min(255, alpha)))
        for i, base in enumerate(self._palette):
            c = QColor(base)
            c.setAlpha(a)
            g.setColorAt(i / (n - 1) if n > 1 else 0.0, c)
        return g

    def paintEvent(self, _ev):
        if not self._active or self._intensity <= 0.0:
            return
        try:
            w, h = self.width(), self.height()
            if w < 24 or h < 24:
                return
            cx, cy = w / 2.0, h / 2.0
            angle = self._phase * 360.0
            breathe = 0.5 + 0.5 * math.sin(self._t * self._breath)
            # The global intensity envelope scales everything so the band fades in/out.
            base_alpha = (self._min_a + (self._max_a - self._min_a) * breathe) * 255.0 * self._intensity
            if base_alpha < 1.0:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            inset = self._inset
            rect = QRectF(inset, inset, w - 2 * inset, h - 2 * inset)
            path = QPainterPath()
            path.addRoundedRect(rect, self._corner, self._corner)
            # Widest + faintest layer first, brightest thin core last -> soft bloom.
            for layer in range(self._layers, 0, -1):
                width = self._stroke * (0.7 + layer)
                alpha = base_alpha * (0.85 / layer)
                pen = QPen(QBrush(self._ring_gradient(cx, cy, angle + layer * 6, alpha)), width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
            p.end()
        except Exception:
            pass


class ThinkingDots(QWidget):
    """A little cluster of glowing dots that pulse and gently rearrange (drift past each
    other) while Ember is thinking — an iOS-style 'alive' indicator. Self-animating at
    ~60fps; call start()/stop()."""

    def __init__(self, parent: QWidget = None, n: int = 4, dot: int = 7, gap: int = 15):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._n = n
        self._dot = dot          # base radius
        self._gap = gap          # spacing between dot centers
        self._t = 0.0
        self._amp = gap * 0.55   # how far dots drift (enough to cross / rearrange)
        self._palette = [QColor(h) for h in ("#ffd23f", "#ff5e3a", "#ff2d55", "#bf5af2")]
        pad = 14
        self.setFixedSize(int((n - 1) * gap + 2 * dot + 2 * self._amp + pad),
                          int(2 * dot + pad))
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def start(self):
        if not self._timer.isActive():
            self._timer.start()
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._t += 0.045
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, _ev):
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            cy = self.height() / 2.0
            left = self._dot + self._amp + 4
            for i in range(self._n):
                base_x = left + i * self._gap
                # Drift left/right out of phase so neighbours slide past each other.
                x = base_x + self._amp * math.sin(self._t * 1.6 + i * 1.5)
                # Staggered size + brightness pulse — a travelling wave across the dots.
                pulse = 0.5 + 0.5 * math.sin(self._t * 3.2 - i * 0.9)
                r = self._dot * (0.62 + 0.5 * pulse)
                col = self._palette[i % len(self._palette)]
                # Glow: a few concentric fills with falloff alpha.
                for ring in (2.4, 1.6, 1.0):
                    c = QColor(col)
                    c.setAlpha(int((40 if ring > 1.5 else 235) * (0.45 + 0.55 * pulse)))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QBrush(c))
                    rr = r * ring
                    p.drawEllipse(QRectF(x - rr, cy - rr, 2 * rr, 2 * rr))
            p.end()
        except Exception:
            pass
