import * as THREE from 'three';

// Atmospheric gradient sky with a sun glow + disk, drawn behind everything.
export function createSky(sunDir) {
  const uniforms = {
    uSunDir: { value: sunDir.clone().normalize() },
    uTop: { value: new THREE.Color(0x2a6bd6) },
    uHorizon: { value: new THREE.Color(0xbcd8f2) },
    uGround: { value: new THREE.Color(0x6f7d72) },
    uSunColor: { value: new THREE.Color(0xfff4e0) },
  };

  const material = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthTest: false,
    depthWrite: false,
    fog: false,
    uniforms,
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec3 vDir;
      uniform vec3 uSunDir, uTop, uHorizon, uGround, uSunColor;
      void main() {
        vec3 dir = normalize(vDir);
        float h = dir.y;
        vec3 sky = mix(uHorizon, uTop, smoothstep(0.0, 0.55, h));
        sky = mix(sky, uGround, smoothstep(0.0, -0.18, h));
        float mu = max(dot(dir, normalize(uSunDir)), 0.0);
        float glow = pow(mu, 8.0) * 0.5 + pow(mu, 260.0) * 1.6;
        vec3 col = sky + uSunColor * glow;
        float disk = smoothstep(0.9994, 0.9998, mu);
        col += uSunColor * disk * 4.0;
        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });

  const mesh = new THREE.Mesh(new THREE.SphereGeometry(16000, 32, 16), material);
  mesh.renderOrder = -1;
  mesh.frustumCulled = false;
  mesh.name = 'sky';
  return { mesh, material };
}
