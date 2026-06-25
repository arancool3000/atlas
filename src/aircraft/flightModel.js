import * as THREE from 'three';
import { clamp, lerp, smoothstep, RAD, DEG } from '../core/math.js';

// A light-aircraft (Cessna-172-class) flight model.
//
// State is integrated in world space (position, velocity, orientation
// quaternion) plus a body-frame angular velocity. Aerodynamic forces and
// moments are built from coefficients each step, so the aircraft genuinely
// stalls, trims, weathercocks and responds to air density with altitude.
//
// Axes (local/body): +X right, +Y up, -Z forward (nose). This matches the
// model and three.js' convention so cameras "look" down -Z naturally.
export class FlightModel {
  constructor() {
    // Mass & geometry
    this.mass = 1100;          // kg
    this.S = 16.2;             // wing area, m^2
    this.b = 11.0;             // span, m
    this.chord = this.S / this.b;
    this.AR = (this.b * this.b) / this.S;
    this.inertia = new THREE.Vector3(1800, 2800, 1300); // about body X,Y,Z (pitch,yaw,roll)

    // Aerodynamic coefficients
    this.Cl_alpha = 5.7;       // per rad
    this.Cl0 = 0.25;
    this.alphaStallDeg = 16;
    this.Cd0 = 0.028;
    this.oswald = 0.8;

    // Control & stability derivatives
    this.Cm_de = 0.35;         // elevator power (full pull ~ stall AoA)
    this.Cm_alpha = -1.1;      // pitch static stability (restoring)
    this.Cl_da = 0.18;         // aileron roll power
    this.Cn_dr = 0.12;         // rudder yaw power
    this.Cn_beta = 0.12;       // weathercock stability
    // Aerodynamic rate-damping magnitudes (|Cmq|, |Clp|, |Cnr|).
    this.Cmq = 20;
    this.Clp = 0.5;
    this.Cnr = 0.25;

    // Propulsion
    this.maxThrust = 3300;     // N (static)

    this.g = 9.81;
    this.rho0 = 1.225;

    // State
    this.position = new THREE.Vector3();
    this.velocity = new THREE.Vector3();
    this.quaternion = new THREE.Quaternion();
    this.omega = new THREE.Vector3(); // body-frame angular velocity (rad/s)

    // Controls
    this.controls = { pitch: 0, roll: 0, yaw: 0, throttle: 0, brakes: 0, flapsDeg: 0, gearDown: true };

    // Telemetry (filled each update)
    this.tel = {
      airspeed: 0, alpha: 0, beta: 0, gLoad: 1, heading: 0,
      vsi: 0, altitude: 0, onGround: true, stalled: false, throttle: 0,
    };

    // scratch
    this._q = new THREE.Quaternion();
    this._vb = new THREE.Vector3();
    this._fb = new THREE.Vector3();
    this._tmp = new THREE.Vector3();

    this.reset(new THREE.Vector3(0, 1.4, 600), 0);
  }

  reset(pos, headingDeg = 0) {
    this.position.copy(pos);
    this.velocity.set(0, 0, 0);
    this.omega.set(0, 0, 0);
    // Heading 0 = north (-Z); rotate about world up.
    this.quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), -headingDeg * DEG);
    this.controls.throttle = 0;
  }

  setControls(c) { Object.assign(this.controls, c); }

  airDensity(altitude) {
    return this.rho0 * Math.exp(-Math.max(0, altitude) / 8500);
  }

  // Lift coefficient curve including a soft stall.
  liftCoeff(alpha) {
    const aDeg = alpha * RAD;
    const linear = this.Cl0 + this.Cl_alpha * alpha;
    const stall = smoothstep(this.alphaStallDeg, this.alphaStallDeg + 7, Math.abs(aDeg));
    const post = 1.05 * Math.sin(2 * alpha); // flat-plate behaviour past the break
    return clamp(lerp(linear, post, stall), -1.6, 1.8);
  }

  update(dt, groundHeight = 0) {
    const c = this.controls;
    const m = this.mass;

    // --- Airflow in the body frame ---
    this._q.copy(this.quaternion).invert();
    this._vb.copy(this.velocity).applyQuaternion(this._q);
    const V = this.velocity.length();
    const Vsafe = Math.max(V, 1e-3);

    // Angle of attack & sideslip.
    const alpha = V > 0.5 ? Math.atan2(-this._vb.y, -this._vb.z) : 0;
    const beta = V > 1 ? Math.asin(clamp(this._vb.x / Vsafe, -1, 1)) : 0;

    const altitude = this.position.y;
    const rho = this.airDensity(altitude);
    const qbar = 0.5 * rho * V * V;

    // --- Coefficients ---
    const flapN = c.flapsDeg / 30; // 0..1
    const Cl = this.liftCoeff(alpha) + flapN * 0.5;
    const Cd =
      this.Cd0 +
      (Cl * Cl) / (Math.PI * this.oswald * this.AR) +
      flapN * 0.05 +
      (c.gearDown ? 0.02 : 0);

    const lift = qbar * this.S * Cl;
    const drag = qbar * this.S * Cd;
    const sideCy = -2.2 * beta;
    const side = qbar * this.S * sideCy;

    // --- Aerodynamic force in body frame ---
    // Drag opposes velocity; lift is perpendicular to velocity in the
    // vertical-ish plane (cross of body-right with the airflow).
    this._fb.set(0, 0, 0);
    if (V > 0.1) {
      const vbn = this._tmp.copy(this._vb).normalize();
      this._fb.addScaledVector(vbn, -drag); // drag
      const liftDir = new THREE.Vector3(1, 0, 0).cross(this._vb).normalize();
      this._fb.addScaledVector(liftDir, lift); // lift
      this._fb.x += side; // side force along body right
    }

    // Thrust along the nose (-Z), lapsing with airspeed.
    const lapse = Math.max(0.2, 1 - V / 95);
    const thrust = c.throttle * this.maxThrust * lapse;
    this._fb.z += -thrust;

    // Body-up component of non-gravity force -> sensed load factor.
    this.tel.gLoad = this._fb.y / (m * this.g);

    // --- To world, add gravity, integrate linear motion ---
    const fWorld = this._fb.clone().applyQuaternion(this.quaternion);
    fWorld.y -= m * this.g;
    const accel = fWorld.multiplyScalar(1 / m);
    this.velocity.addScaledVector(accel, dt);

    // --- Moments (body frame) ---
    // Control + static-stability moments, plus aerodynamic rate damping that
    // always opposes the body angular velocity (and scales with airspeed).
    const { inertia: I } = this;
    const Sb = qbar * this.S * this.b;
    const Sc = qbar * this.S * this.chord;
    const kPitch = (Sc * this.chord) / (2 * Vsafe) * this.Cmq;
    const kRoll = (Sb * this.b) / (2 * Vsafe) * this.Clp;
    const kYaw = (Sb * this.b) / (2 * Vsafe) * this.Cnr;

    // Pitch about +X (nose up positive).
    const Tx = Sc * (this.Cm_de * c.pitch + this.Cm_alpha * alpha) - kPitch * this.omega.x;
    // Roll: positive command rolls right -> torque about -Z.
    const Tz = -Sb * (this.Cl_da * c.roll) - kRoll * this.omega.z;
    // Yaw: positive command yaws right -> torque about -Y; weathercock on beta.
    const Ty = -Sb * (this.Cn_dr * c.yaw + this.Cn_beta * beta) - kYaw * this.omega.y;

    this.omega.x += (Tx / I.x) * dt;
    this.omega.y += (Ty / I.y) * dt;
    this.omega.z += (Tz / I.z) * dt;

    // --- Ground contact ---
    const clearance = c.gearDown ? 1.42 : 0.8;
    const agl = this.position.y - groundHeight;
    let onGround = false;
    if (agl <= clearance + 0.02) {
      onGround = true;
      this._groundHandling(dt, groundHeight, clearance);
    }
    this.tel.onGround = onGround;

    // --- Integrate orientation (right-multiply = body frame) ---
    const dq = new THREE.Quaternion(
      this.omega.x * dt * 0.5,
      this.omega.y * dt * 0.5,
      this.omega.z * dt * 0.5,
      1
    ).normalize();
    this.quaternion.multiply(dq).normalize();

    // --- Integrate position ---
    this.position.addScaledVector(this.velocity, dt);
    if (this.position.y < groundHeight + clearance) {
      this.position.y = groundHeight + clearance;
    }

    // --- Telemetry ---
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(this.quaternion);
    const upv = new THREE.Vector3(0, 1, 0).applyQuaternion(this.quaternion);
    const rightv = new THREE.Vector3(1, 0, 0).applyQuaternion(this.quaternion);
    let hdg = Math.atan2(fwd.x, -fwd.z) * RAD;
    if (hdg < 0) hdg += 360;
    this.tel.airspeed = V;
    this.tel.alpha = alpha;
    this.tel.beta = beta;
    this.tel.heading = hdg;
    this.tel.pitchAtt = Math.asin(clamp(fwd.y, -1, 1)) * RAD;
    this.tel.bank = Math.atan2(rightv.y, upv.y) * RAD;
    this.tel.vsi = this.velocity.y;
    this.tel.altitude = this.position.y;
    this.tel.throttle = c.throttle;
    this.tel.stalled = !onGround && V > 6 &&
      Math.abs(alpha * RAD) > this.alphaStallDeg + 1;
  }

  _groundHandling(dt, groundHeight, clearance) {
    const c = this.controls;
    // Don't sink through; cancel downward velocity (tiny bounce).
    this.position.y = Math.max(this.position.y, groundHeight + clearance);
    if (this.velocity.y < 0) this.velocity.y *= -0.08;

    // Wheel frame: roll along heading, scrub lateral velocity.
    const fwd = new THREE.Vector3(0, 0, -1).applyQuaternion(this.quaternion);
    fwd.y = 0; fwd.normalize();
    const right = new THREE.Vector3(1, 0, 0).applyQuaternion(this.quaternion);
    right.y = 0; right.normalize();

    let vF = this.velocity.dot(fwd);
    let vR = this.velocity.dot(right);
    vR *= 1 - Math.min(1, 7 * dt); // tyre lateral grip

    const fric = (0.03 + c.brakes * 0.7) * this.g; // rolling + brakes
    const sign = Math.sign(vF) || 1;
    vF -= sign * Math.min(Math.abs(vF), fric * dt);

    this.velocity.x = fwd.x * vF + right.x * vR;
    this.velocity.z = fwd.z * vF + right.z * vR;

    // Keep the aircraft planted & wings level; allow elevator to rotate.
    this.omega.multiplyScalar(1 - Math.min(1, 4 * dt));
    const rightUp = new THREE.Vector3(1, 0, 0).applyQuaternion(this.quaternion).y; // bank
    this.omega.z += rightUp * 2.5 * dt; // self-level roll
    // Low-speed nose-wheel steering from the rudder pedals.
    if (Math.abs(vF) < 30) this.omega.y += -c.yaw * 0.7 * dt * (1 - Math.abs(vF) / 30);
  }
}
