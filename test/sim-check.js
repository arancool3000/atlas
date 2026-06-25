// Headless sanity check for the flight model: full-throttle takeoff roll,
// rotate, climb. Verifies signs/integration are right and nothing goes NaN.
// Run with: node test/sim-check.js
import * as THREE from 'three';
import { FlightModel } from '../src/aircraft/flightModel.js';

const fm = new FlightModel();
fm.reset(new THREE.Vector3(0, 1.42, 0), 0);

const dt = 1 / 120;
const seconds = 45;
let liftoffT = null;
let maxAlt = 0;
const knots = (v) => v * 1.94384;
const feet = (m) => m * 3.28084;

console.log('  t(s)  speed(kt)  alt(ft)   vsi(fpm)  aoa  G    ground');
for (let i = 0; i <= seconds / dt; i++) {
  const t = i * dt;
  const spd = fm.tel.airspeed;
  // Throttle up; rotate once we have flying speed.
  fm.setControls({
    throttle: 1,
    pitch: spd > 30 ? 0.32 : 0,
    roll: 0,
    yaw: 0,
    brakes: 0,
    flapsDeg: 10,
    gearDown: true,
  });
  fm.update(dt, 0);

  if (!fm.tel.onGround && liftoffT === null && fm.position.y > 1.6) {
    liftoffT = t;
  }
  maxAlt = Math.max(maxAlt, fm.position.y);

  if (i % Math.round(1 / dt) === 0) {
    console.log(
      `${t.toFixed(0).padStart(5)} ${knots(fm.tel.airspeed).toFixed(1).padStart(9)} ` +
      `${feet(fm.position.y).toFixed(0).padStart(8)} ${(fm.tel.vsi * 196.85).toFixed(0).padStart(9)} ` +
      `${(fm.tel.alpha * 180 / Math.PI).toFixed(1).padStart(5)} ${fm.tel.gLoad.toFixed(2).padStart(4)}  ${fm.tel.onGround}`
    );
  }
}

const p = fm.position;
const finite = Number.isFinite(p.x) && Number.isFinite(p.y) && Number.isFinite(p.z);
console.log('\nResults:');
console.log('  finite state :', finite);
console.log('  lift-off at  :', liftoffT === null ? 'never' : liftoffT.toFixed(1) + ' s');
console.log('  max altitude :', feet(maxAlt).toFixed(0), 'ft');
console.log('  final speed  :', knots(fm.tel.airspeed).toFixed(1), 'kt');

const pass = finite && liftoffT !== null && liftoffT < 25 && maxAlt > 60;
console.log('\n' + (pass ? 'PASS ✅' : 'FAIL ❌'));
process.exit(pass ? 0 : 1);
