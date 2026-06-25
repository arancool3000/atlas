import { KEYMAP } from '../core/input.js';

// Title / pause menu + the initial loading overlay.
export class Menu {
  constructor({ onFly } = {}) {
    this.root = document.getElementById('menu');
    this.loading = document.getElementById('loading');
    this.btn = document.getElementById('btn-fly');
    this.grid = document.getElementById('controls-grid');

    // Populate the control reference.
    for (const [key, desc] of KEYMAP) {
      const k = document.createElement('div');
      k.innerHTML = key
        .split(' / ')
        .map((s) => `<span class="k">${s}</span>`)
        .join(' / ');
      const d = document.createElement('div');
      d.textContent = desc;
      this.grid.append(k, d);
    }

    this.btn.addEventListener('click', () => onFly && onFly());
  }

  doneLoading() { this.loading.classList.add('hidden'); }
  open(paused = false) {
    this.root.classList.remove('hidden');
    this.btn.textContent = paused ? 'RESUME' : 'FLY NOW';
  }
  close() { this.root.classList.add('hidden'); }
}
