import * as THREE from 'three';

// Owns the WebGL renderer, scene, camera and global lighting.
export class Engine {
  constructor(canvas) {
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      powerPreference: 'high-performance',
      logarithmicDepthBuffer: true, // tame z-fighting across the huge view range
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    this.scene = new THREE.Scene();

    this.camera = new THREE.PerspectiveCamera(
      62,
      window.innerWidth / window.innerHeight,
      0.5,
      45000
    );
    this.camera.position.set(0, 20, 30);

    // Sun direction (mid-morning), shared with the sky shader.
    this.sunDir = new THREE.Vector3(0.45, 0.55, 0.7).normalize();

    const horizon = new THREE.Color(0x9fc4e8);
    this.scene.fog = new THREE.FogExp2(horizon, 0.000042);

    // Hemisphere fill (sky/ground bounce) + warm key sun.
    const hemi = new THREE.HemisphereLight(0xbcd7ff, 0x5a6647, 0.75);
    this.scene.add(hemi);

    const sun = new THREE.DirectionalLight(0xfff2e0, 2.4);
    sun.position.copy(this.sunDir).multiplyScalar(800);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 600;
    const s = 70; // tight shadow frustum that travels with the aircraft
    Object.assign(sun.shadow.camera, { left: -s, right: s, top: s, bottom: -s });
    sun.shadow.bias = -0.0004;
    this.scene.add(sun);
    this.scene.add(sun.target);
    this.sun = sun;

    this._onResize = this._onResize.bind(this);
    window.addEventListener('resize', this._onResize);
  }

  add(obj) { this.scene.add(obj); }

  // Keep the shadow frustum centred on the aircraft so it always casts.
  trackShadow(pos) {
    this.sun.position.copy(pos).addScaledVector(this.sunDir, 400);
    this.sun.target.position.copy(pos);
  }

  _onResize() {
    const w = window.innerWidth, h = window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h);
  }

  resize() { this._onResize(); }

  render() {
    this.renderer.render(this.scene, this.camera);
  }
}
