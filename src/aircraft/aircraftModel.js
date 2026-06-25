import * as THREE from 'three';

const white = () => new THREE.MeshStandardMaterial({ color: 0xf2f4f8, roughness: 0.55, metalness: 0.1 });
const blue = () => new THREE.MeshStandardMaterial({ color: 0x2f6fd0, roughness: 0.5, metalness: 0.15 });
const dark = () => new THREE.MeshStandardMaterial({ color: 0x1c1f24, roughness: 0.6 });
const glass = () => new THREE.MeshStandardMaterial({ color: 0x0e1c28, roughness: 0.15, metalness: 0.6, transparent: true, opacity: 0.7 });

function castAll(obj) {
  obj.traverse((o) => { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
}

// Builds a high-wing single-engine light aircraft. Nose points down -Z.
// Returns the group plus handles to the animated parts.
export function createAircraftModel() {
  const group = new THREE.Group();
  group.name = 'aircraft';

  // Fuselage (cylinder along Z) + nose cone + tail taper.
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.72, 0.5, 6.4, 14), white());
  body.rotation.x = Math.PI / 2;
  group.add(body);

  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.5, 1.3, 14), blue());
  nose.rotation.x = -Math.PI / 2;
  nose.position.z = -3.7;
  group.add(nose);

  // Cabin / windscreen.
  const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.25, 0.95, 2.2), glass());
  cabin.position.set(0, 0.55, -0.7);
  group.add(cabin);

  // High wing with a slight dihedral.
  const wing = new THREE.Mesh(new THREE.BoxGeometry(11, 0.16, 1.7), white());
  wing.position.set(0, 0.78, -0.4);
  const wingStripe = new THREE.Mesh(new THREE.BoxGeometry(11, 0.02, 0.35), blue());
  wingStripe.position.set(0, 0.87, -0.9);
  group.add(wing, wingStripe);
  // Wing struts.
  for (const sx of [-1, 1]) {
    const strut = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.9, 0.1), dark());
    strut.position.set(sx * 2.4, 0.35, -0.4);
    strut.rotation.z = sx * 0.5;
    group.add(strut);
  }

  // Ailerons (outer trailing edge), hinge at leading edge so they pivot cleanly.
  const ailGeo = new THREE.BoxGeometry(2.4, 0.12, 0.5);
  ailGeo.translate(0, 0, 0.25);
  const aileronL = new THREE.Mesh(ailGeo, white());
  aileronL.position.set(-3.6, 0.78, 0.45);
  const aileronR = new THREE.Mesh(ailGeo.clone(), white());
  aileronR.position.set(3.6, 0.78, 0.45);
  group.add(aileronL, aileronR);

  // Empennage.
  const hStab = new THREE.Mesh(new THREE.BoxGeometry(4.2, 0.12, 0.9), white());
  hStab.position.set(0, 0.35, 3.0);
  group.add(hStab);

  const elevGeo = new THREE.BoxGeometry(4.2, 0.1, 0.6);
  elevGeo.translate(0, 0, 0.3);
  const elevator = new THREE.Mesh(elevGeo, white());
  elevator.position.set(0, 0.35, 3.45);
  group.add(elevator);

  const vStab = new THREE.Mesh(new THREE.BoxGeometry(0.12, 1.5, 1.1), blue());
  vStab.position.set(0, 1.0, 3.05);
  group.add(vStab);

  const rudGeo = new THREE.BoxGeometry(0.1, 1.4, 0.7);
  rudGeo.translate(0, 0, 0.35);
  const rudder = new THREE.Mesh(rudGeo, blue());
  rudder.position.set(0, 1.0, 3.55);
  group.add(rudder);

  // Propeller + spinner at the nose.
  const propHub = new THREE.Group();
  propHub.position.z = -4.35;
  const spinner = new THREE.Mesh(new THREE.ConeGeometry(0.22, 0.5, 10), dark());
  spinner.rotation.x = -Math.PI / 2;
  propHub.add(spinner);
  for (let i = 0; i < 2; i++) {
    const blade = new THREE.Mesh(new THREE.BoxGeometry(0.16, 3.0, 0.05), dark());
    blade.rotation.z = i * Math.PI / 2;
    propHub.add(blade);
  }
  group.add(propHub);

  // Landing gear (tricycle).
  const gear = new THREE.Group();
  const wheelGeo = new THREE.CylinderGeometry(0.34, 0.34, 0.22, 12);
  const wheelMat = dark();
  const mkWheel = (x, y, z) => {
    const w = new THREE.Mesh(wheelGeo, wheelMat);
    w.rotation.z = Math.PI / 2;
    w.position.set(x, y, z);
    const strut = new THREE.Mesh(new THREE.BoxGeometry(0.1, Math.abs(y), 0.1), dark());
    strut.position.set(x, y / 2 + 0.1, z);
    gear.add(w, strut);
  };
  mkWheel(-1.5, -1.05, -0.2);
  mkWheel(1.5, -1.05, -0.2);
  mkWheel(0, -1.0, -3.2); // nose wheel
  group.add(gear);

  castAll(group);

  return {
    group,
    parts: { prop: propHub, aileronL, aileronR, elevator, rudder, gear },
  };
}
