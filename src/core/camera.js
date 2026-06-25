import * as THREE from 'three';
import { damp } from './math.js';

const MODES = ['chase', 'cockpit', 'orbit'];
const LABELS = { chase: 'CHASE', cockpit: 'COCKPIT', orbit: 'EXTERNAL' };

// Manages multiple view modes that follow the aircraft.
export class CameraRig {
  constructor(camera, target) {
    this.camera = camera;
    this.target = target; // THREE.Object3D (aircraft group)
    this.modeIndex = 0;
    this.orbitAngle = 0;

    this._fwd = new THREE.Vector3();
    this._desired = new THREE.Vector3();
    this._look = new THREE.Vector3();
    this._up = new THREE.Vector3(0, 1, 0);
    this._initialized = false;
  }

  get mode() { return MODES[this.modeIndex]; }
  get label() { return LABELS[this.mode]; }

  cycle() {
    this.modeIndex = (this.modeIndex + 1) % MODES.length;
    this._initialized = false; // snap instead of lerp on a mode switch
  }

  update(dt, speed = 0) {
    const t = this.target;
    // World-space forward (nose points down local -Z).
    this._fwd.set(0, 0, -1).applyQuaternion(t.quaternion).normalize();

    if (this.mode === 'cockpit') {
      // Rigidly attached just behind the nose at pilot eye height.
      this._desired.set(0, 0.55, 0.2).applyQuaternion(t.quaternion).add(t.position);
      this.camera.position.copy(this._desired);
      this.camera.quaternion.copy(t.quaternion);
      return;
    }

    if (this.mode === 'orbit') {
      this.orbitAngle += dt * 0.35;
      const R = 16;
      this._desired.set(
        t.position.x + Math.sin(this.orbitAngle) * R,
        t.position.y + 5,
        t.position.z + Math.cos(this.orbitAngle) * R
      );
      this.camera.position.copy(this._desired);
      this.camera.up.copy(this._up);
      this.camera.lookAt(t.position);
      return;
    }

    // Chase: trail behind & above, ignoring roll for comfort. A little
    // extra trail distance with speed gives a sense of acceleration.
    const dist = 12 + Math.min(speed * 0.06, 8);
    this._desired
      .copy(t.position)
      .addScaledVector(this._fwd, -dist)
      .add(new THREE.Vector3(0, 4.2, 0));

    if (!this._initialized) {
      this.camera.position.copy(this._desired);
      this._initialized = true;
    } else {
      this.camera.position.lerp(this._desired, damp(6, dt));
    }
    this._look.copy(t.position).addScaledVector(this._fwd, 6);
    this.camera.up.copy(this._up);
    this.camera.lookAt(this._look);
  }
}
