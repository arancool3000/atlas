import * as THREE from 'three';
import { mulberry32, clamp } from '../core/math.js';

// Runway 36/18 markings drawn to a canvas texture.
function runwayTexture() {
  const W = 256, H = 2048;
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const g = cv.getContext('2d');
  g.fillStyle = '#2b2e33';
  g.fillRect(0, 0, W, H);

  // Side edge lines.
  g.fillStyle = '#e8e8e8';
  g.fillRect(20, 0, 6, H);
  g.fillRect(W - 26, 0, 6, H);

  // Threshold "piano key" bars at both ends.
  for (let i = 0; i < 6; i++) {
    const x = 40 + i * 30;
    g.fillRect(x, 40, 16, 150);
    g.fillRect(x, H - 190, 16, 150);
  }

  // Dashed centreline.
  g.fillStyle = '#f4f4f4';
  for (let y = 260; y < H - 260; y += 120) g.fillRect(W / 2 - 5, y, 10, 70);

  // Runway designators.
  g.fillStyle = '#f4f4f4';
  g.font = 'bold 120px sans-serif';
  g.textAlign = 'center';
  g.save(); g.translate(W / 2, 250); g.fillText('36', 0, 0); g.restore();
  g.save(); g.translate(W / 2, H - 160); g.rotate(Math.PI); g.fillText('18', 0, 0); g.restore();

  const tex = new THREE.CanvasTexture(cv);
  tex.anisotropy = 8;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function makeTrees(height, rand) {
  const dummy = new THREE.Object3D();
  const placements = [];
  const RANGE = 6500;
  for (let i = 0; i < 9000 && placements.length < 4200; i++) {
    const x = (rand() * 2 - 1) * RANGE;
    const z = (rand() * 2 - 1) * RANGE;
    if (Math.abs(x) < 70 && z > -900 && z < 900) continue; // keep off the runway
    if (Math.hypot(x, z) < 360) continue;
    const y = height(x, z);
    if (y < 6 || y > 250) continue;
    const e = 8;
    const slope = Math.hypot(height(x + e, z) - height(x - e, z), height(x, z + e) - height(x, z - e)) / (2 * e);
    if (slope > 0.55) continue;
    placements.push({ x, y, z, s: 0.7 + rand() * 1.0, r: rand() * Math.PI });
  }

  const trunkGeo = new THREE.CylinderGeometry(0.3, 0.45, 3, 5);
  const trunkMat = new THREE.MeshStandardMaterial({ color: 0x5a3f2a, roughness: 1 });
  const foliageGeo = new THREE.ConeGeometry(2.2, 7, 6);
  const foliageMat = new THREE.MeshStandardMaterial({ color: 0x2f5a2a, roughness: 1 });

  const trunks = new THREE.InstancedMesh(trunkGeo, trunkMat, placements.length);
  const foliage = new THREE.InstancedMesh(foliageGeo, foliageMat, placements.length);
  placements.forEach((p, i) => {
    dummy.position.set(p.x, p.y + 1.5 * p.s, p.z);
    dummy.rotation.set(0, p.r, 0);
    dummy.scale.setScalar(p.s);
    dummy.updateMatrix();
    trunks.setMatrixAt(i, dummy.matrix);
    dummy.position.set(p.x, p.y + 5 * p.s, p.z);
    dummy.updateMatrix();
    foliage.setMatrixAt(i, dummy.matrix);
  });
  trunks.instanceMatrix.needsUpdate = true;
  foliage.instanceMatrix.needsUpdate = true;
  const group = new THREE.Group();
  group.add(trunks, foliage);
  return group;
}

// Builds the airfield: runway, a hangar, a control tower and forests.
export function createEnvironment({ height, seed = 1337 } = {}) {
  const group = new THREE.Group();
  group.name = 'environment';
  const rand = mulberry32(seed ^ 0x9e3779b9);

  // Runway (length along Z, ~1500m x 46m).
  const rwMat = new THREE.MeshStandardMaterial({
    map: runwayTexture(),
    roughness: 0.9,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
  });
  const runway = new THREE.Mesh(new THREE.PlaneGeometry(46, 1500), rwMat);
  runway.rotation.x = -Math.PI / 2;
  runway.position.y = 0.12;
  runway.receiveShadow = true;
  runway.name = 'runway';
  group.add(runway);

  // Hangar.
  const hangarMat = new THREE.MeshStandardMaterial({ color: 0x8a9099, roughness: 0.8, metalness: 0.2 });
  const hangar = new THREE.Mesh(new THREE.BoxGeometry(40, 14, 30), hangarMat);
  hangar.position.set(-70, 7, 250);
  hangar.castShadow = true; hangar.receiveShadow = true;
  group.add(hangar);

  // Control tower.
  const towerMat = new THREE.MeshStandardMaterial({ color: 0xcfd4da, roughness: 0.7 });
  const tower = new THREE.Mesh(new THREE.CylinderGeometry(4, 5, 26, 12), towerMat);
  tower.position.set(60, 13, 120);
  tower.castShadow = true;
  const cab = new THREE.Mesh(
    new THREE.BoxGeometry(11, 5, 11),
    new THREE.MeshStandardMaterial({ color: 0x223040, roughness: 0.3, metalness: 0.4 })
  );
  cab.position.set(60, 28, 120);
  cab.castShadow = true;
  group.add(tower, cab);

  group.add(makeTrees(height, rand));
  return { group, runwayHeading: 360, runwayLength: 1500 };
}
