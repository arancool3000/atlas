import './styles.css';
import * as THREE from 'three';

import { Engine } from './engine/renderer.js';
import { createSky } from './world/sky.js';
import { createTerrain } from './world/terrain.js';
import { createEnvironment } from './world/environment.js';
import { Aircraft } from './aircraft/aircraft.js';
import { Input } from './core/input.js';
import { CameraRig } from './core/camera.js';
import { HUD } from './ui/hud.js';
import { Menu } from './ui/menu.js';

const SPAWN = new THREE.Vector3(0, 1.42, 700); // south threshold, facing north
const FLAP_STEPS = [0, 10, 20, 30];
const FIXED_DT = 1 / 120;

class Game {
  constructor() {
    const canvas = document.getElementById('scene');
    this.engine = new Engine(canvas);
    this.input = new Input();
    this.hud = new HUD();
    this.menu = new Menu({ onFly: () => this.start() });

    this.state = 'menu'; // 'menu' | 'flying' | 'paused'
    this.flapIndex = 0;
    this.gearDown = true;
    this.accumulator = 0;
    this.lastT = 0;

    this._loop = this._loop.bind(this);
  }

  async build() {
    const { mesh: sky } = createSky(this.engine.sunDir);
    this.sky = sky;
    this.engine.add(sky);

    const terrain = createTerrain({ seed: 1337 });
    this.terrain = terrain;
    this.engine.add(terrain.mesh);

    const { group } = createEnvironment({ height: terrain.height, seed: 1337 });
    this.engine.add(group);

    this.aircraft = new Aircraft();
    this.engine.add(this.aircraft.object);
    this.aircraft.reset(SPAWN, 0);

    this.rig = new CameraRig(this.engine.camera, this.aircraft.object);

    this.menu.doneLoading();
    this.menu.open(false);
    requestAnimationFrame(this._loop);
  }

  start() {
    this.menu.close();
    this.hud.show();
    this.state = 'flying';
  }

  pause() {
    this.state = 'paused';
    this.hud.hide();
    this.menu.open(true);
  }

  reset() {
    this.aircraft.reset(SPAWN, 0);
    this.input.throttle = 0;
    this.flapIndex = 0;
    this.gearDown = true;
  }

  _handleEvents() {
    const e = this.input.consumeEvents();
    if (e.pause) {
      if (this.state === 'flying') this.pause();
      else if (this.state === 'paused') this.start();
    }
    if (this.state !== 'flying') return;
    if (e.camera) this.rig.cycle();
    if (e.gear) this.gearDown = !this.gearDown;
    if (e.reset) this.reset();
    if (e.flapDown) this.flapIndex = Math.min(FLAP_STEPS.length - 1, this.flapIndex + 1);
    if (e.flapUp) this.flapIndex = Math.max(0, this.flapIndex - 1);
  }

  _loop(t) {
    requestAnimationFrame(this._loop);
    const now = t / 1000;
    let dt = this.lastT ? now - this.lastT : 0;
    this.lastT = now;
    dt = Math.min(dt, 0.1); // clamp after tab-out

    this.input.update(dt);
    this._handleEvents();

    if (this.state === 'flying') {
      this.aircraft.setControls({
        pitch: this.input.pitch,
        roll: this.input.roll,
        yaw: this.input.yaw,
        throttle: this.input.throttle,
        brakes: this.input.brakes,
        flapsDeg: FLAP_STEPS[this.flapIndex],
        gearDown: this.gearDown,
      });

      // Fixed-step physics for stability.
      this.accumulator += dt;
      let guard = 0;
      while (this.accumulator >= FIXED_DT && guard++ < 8) {
        const gh = this.terrain.height(this.aircraft.fm.position.x, this.aircraft.fm.position.z);
        this.aircraft.update(FIXED_DT, gh);
        this.accumulator -= FIXED_DT;
      }
    }

    const tel = this.aircraft.telemetry;
    this.rig.update(dt, tel.airspeed);
    this.engine.trackShadow(this.aircraft.object.position);
    this.sky.position.copy(this.engine.camera.position);

    if (this.state !== 'menu') {
      this.hud.update(tel, this.aircraft.controls, this.rig.label);
    }
    this.engine.render();
  }
}

const game = new Game();
window.SKYFORGE = game; // exposed for debugging / automated checks
// Defer the heavy world build a frame so the loading overlay can paint.
requestAnimationFrame(() => game.build());
