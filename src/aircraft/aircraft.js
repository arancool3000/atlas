import { FlightModel } from './flightModel.js';
import { createAircraftModel } from './aircraftModel.js';

// Couples the physics model to its 3D representation: syncs the transform,
// animates control surfaces / propeller and surfaces telemetry to the HUD.
export class Aircraft {
  constructor() {
    this.fm = new FlightModel();
    const { group, parts } = createAircraftModel();
    this.object = group;
    this.parts = parts;
    this._propAngle = 0;
  }

  get telemetry() { return this.fm.tel; }
  get controls() { return this.fm.controls; }

  reset(pos, headingDeg) { this.fm.reset(pos, headingDeg); }
  setControls(c) { this.fm.setControls(c); }

  update(dt, groundHeight) {
    this.fm.update(dt, groundHeight);

    this.object.position.copy(this.fm.position);
    this.object.quaternion.copy(this.fm.quaternion);

    // Visual control-surface deflections (radians).
    const c = this.fm.controls;
    this.parts.elevator.rotation.x = -c.pitch * 0.42;
    this.parts.aileronL.rotation.x = c.roll * 0.42;
    this.parts.aileronR.rotation.x = -c.roll * 0.42;
    this.parts.rudder.rotation.y = -c.yaw * 0.42;
    this.parts.gear.visible = c.gearDown;

    // Propeller spin scales with throttle (blur not modelled).
    this._propAngle += (8 + c.throttle * 80) * dt;
    this.parts.prop.rotation.z = this._propAngle;
  }
}
