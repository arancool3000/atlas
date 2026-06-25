import { clamp, damp } from './math.js';

// Human-readable control map (shown in the menu).
export const KEYMAP = [
  ['W / S', 'Throttle up / down'],
  ['↑ / ↓', 'Pitch (nose down / up)'],
  ['← / →', 'Roll left / right'],
  ['A / D', 'Rudder (yaw) left / right'],
  ['B', 'Wheel brakes (hold)'],
  ['F / V', 'Flaps extend / retract'],
  ['G', 'Landing gear toggle'],
  ['C', 'Cycle camera'],
  ['R', 'Reset to runway'],
  ['P / Esc', 'Pause'],
];

const CODE = {
  pitchUp: 'ArrowDown',
  pitchDown: 'ArrowUp',
  rollLeft: 'ArrowLeft',
  rollRight: 'ArrowRight',
  yawLeft: 'KeyA',
  yawRight: 'KeyD',
  thrUp: 'KeyW',
  thrDown: 'KeyS',
  brake: 'KeyB',
};

export class Input {
  constructor() {
    this.keys = new Set();
    // Smoothed analog command axes in [-1, 1].
    this.pitch = 0;
    this.roll = 0;
    this.yaw = 0;
    this.throttle = 0; // [0, 1]
    this.brakes = 0; // [0, 1]
    // One-shot edge events consumed by the sim each frame.
    this._events = { camera: false, gear: false, reset: false, pause: false, flapDown: false, flapUp: false };
    this._gpPrev = {};

    window.addEventListener('keydown', (e) => {
      // Don't hijack browser shortcuts / refresh.
      if (e.metaKey || e.ctrlKey) return;
      if (
        ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space'].includes(e.code)
      ) {
        e.preventDefault();
      }
      if (!this.keys.has(e.code)) this._onPress(e.code);
      this.keys.add(e.code);
    });
    window.addEventListener('keyup', (e) => this.keys.delete(e.code));
    window.addEventListener('blur', () => this.keys.clear());
  }

  _onPress(code) {
    switch (code) {
      case 'KeyC': this._events.camera = true; break;
      case 'KeyG': this._events.gear = true; break;
      case 'KeyR': this._events.reset = true; break;
      case 'KeyP':
      case 'Escape': this._events.pause = true; break;
      case 'KeyF': this._events.flapDown = true; break;
      case 'KeyV': this._events.flapUp = true; break;
    }
  }

  has(code) { return this.keys.has(code); }

  // Pull-and-clear edge events.
  consumeEvents() {
    const e = this._events;
    this._events = { camera: false, gear: false, reset: false, pause: false, flapDown: false, flapUp: false };
    return e;
  }

  update(dt) {
    // --- Keyboard target axes ---
    let pitchT = (this.has(CODE.pitchUp) ? 1 : 0) - (this.has(CODE.pitchDown) ? 1 : 0);
    let rollT = (this.has(CODE.rollRight) ? 1 : 0) - (this.has(CODE.rollLeft) ? 1 : 0);
    let yawT = (this.has(CODE.yawRight) ? 1 : 0) - (this.has(CODE.yawLeft) ? 1 : 0);
    let brakeT = this.has(CODE.brake) || this.has('Space') ? 1 : 0;
    let thrDelta = (this.has(CODE.thrUp) ? 1 : 0) - (this.has(CODE.thrDown) ? 1 : 0);
    let gamepadThrottle = null;

    // --- Gamepad overrides (analog) ---
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    const gp = [...pads].find((p) => p && p.connected);
    if (gp) {
      const dz = (v) => (Math.abs(v) < 0.08 ? 0 : v);
      const ax = gp.axes;
      if (ax.length >= 4) {
        rollT = dz(ax[2]);
        pitchT = dz(ax[3]);
        yawT = dz(ax[0]);
      }
      const rt = gp.buttons[7]?.value ?? 0;
      const lt = gp.buttons[6]?.value ?? 0;
      if (rt > 0.02 || lt > 0.02) gamepadThrottle = rt; // analog throttle on right trigger
      brakeT = Math.max(brakeT, lt > 0.5 ? 1 : 0);

      const edge = (i) => {
        const now = !!gp.buttons[i]?.pressed;
        const fired = now && !this._gpPrev[i];
        this._gpPrev[i] = now;
        return fired;
      };
      if (edge(3)) this._events.camera = true; // Y
      if (edge(0)) this._events.gear = true; // A
      if (edge(2)) this._events.flapDown = true; // X
      if (edge(9)) this._events.pause = true; // Start
    }

    // --- Smooth toward targets for a stick-like feel ---
    const kRate = 6; // control surface slew
    this.pitch += (pitchT - this.pitch) * damp(kRate, dt);
    this.roll += (rollT - this.roll) * damp(kRate, dt);
    this.yaw += (yawT - this.yaw) * damp(kRate, dt);
    this.brakes += (brakeT - this.brakes) * damp(12, dt);

    if (gamepadThrottle !== null) {
      this.throttle += (gamepadThrottle - this.throttle) * damp(8, dt);
    } else if (thrDelta !== 0) {
      this.throttle = clamp(this.throttle + thrDelta * 0.55 * dt, 0, 1);
    }
  }
}
