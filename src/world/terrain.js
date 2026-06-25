import * as THREE from 'three';
import { Perlin, lerp, clamp, smoothstep } from '../core/math.js';

// Procedural terrain: rolling plains around the airfield rising to distant
// ridges. Exposes a height(x, z) sampler so the sim and scenery can sit on it.
export function createTerrain({ seed = 1337, size = 24000, segments = 400 } = {}) {
  const perlin = new Perlin(seed);

  function baseHeight(x, z) {
    const broad = perlin.fbm(x / 4200, z / 4200, 5); // continents of hills
    const medium = perlin.fbm(x / 950, z / 950, 4); // local relief
    let h = broad * 540 + medium * 70;
    const ridge = Math.pow(Math.max(0, broad), 1.6); // sharpen the highlands
    h += ridge * 760;
    return h;
  }

  // Flatten a generous bowl around the origin so the airfield is level.
  function height(x, z) {
    const d = Math.hypot(x, z);
    const blend = smoothstep(700, 2100, d);
    return lerp(0, baseHeight(x, z), blend);
  }

  const geo = new THREE.PlaneGeometry(size, size, segments, segments);
  geo.rotateX(-Math.PI / 2); // lie flat in the XZ plane

  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);

  const grass = new THREE.Color(0x46823a);
  const forest = new THREE.Color(0x2c5328);
  const rock = new THREE.Color(0x6d6051);
  const snow = new THREE.Color(0xeef3f7);
  const c = new THREE.Color();

  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const z = pos.getZ(i);
    const y = height(x, z);
    pos.setY(i, y);

    // Analytic slope from the height field for rock on steep faces.
    const e = 8;
    const hx = height(x + e, z) - height(x - e, z);
    const hz = height(x, z + e) - height(x, z - e);
    const slope = clamp(Math.hypot(hx, hz) / (2 * e), 0, 1);
    const steep = smoothstep(0.35, 1.1, slope);

    c.copy(grass);
    c.lerp(forest, smoothstep(40, 170, y));
    c.lerp(rock, smoothstep(230, 470, y));
    c.lerp(snow, smoothstep(540, 780, y));
    c.lerp(rock, steep * 0.8);
    // Slight variation so large fields aren't flat-shaded billiard tables.
    const tint = 0.94 + 0.12 * perlin.noise2D(x / 120, z / 120);
    colors[i * 3] = clamp(c.r * tint, 0, 1);
    colors[i * 3 + 1] = clamp(c.g * tint, 0, 1);
    colors[i * 3 + 2] = clamp(c.b * tint, 0, 1);
  }

  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.computeVertexNormals();

  const mat = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.97,
    metalness: 0.0,
  });

  const mesh = new THREE.Mesh(geo, mat);
  mesh.receiveShadow = true;
  mesh.name = 'terrain';

  return { mesh, height, perlin, size };
}
