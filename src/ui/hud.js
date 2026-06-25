import { DEG } from '../core/math.js';

const pad3 = (n) => String(n).padStart(3, '0');

// Heads-up display: artificial horizon, heading tape and a data block.
export class HUD {
  constructor() {
    this.root = document.getElementById('hud');
    this.att = document.getElementById('attitude');
    this.attCtx = this.att.getContext('2d');
    this.hdg = document.getElementById('heading');
    this.hdgCtx = this.hdg.getContext('2d');

    this.el = {
      airspeed: document.getElementById('hud-airspeed'),
      altitude: document.getElementById('hud-altitude'),
      throttle: document.getElementById('hud-throttle'),
      vsi: document.getElementById('hud-vsi'),
      heading: document.getElementById('hud-heading'),
      gload: document.getElementById('hud-gload'),
      aoa: document.getElementById('hud-aoa'),
      flaps: document.getElementById('hud-flaps'),
      gear: document.getElementById('hud-gear'),
      warn: document.getElementById('warn'),
      cam: document.getElementById('cam-label'),
    };
  }

  show() { this.root.classList.remove('hidden'); }
  hide() { this.root.classList.add('hidden'); }

  update(tel, controls, camLabel) {
    this._drawAttitude(tel.pitchAtt || 0, tel.bank || 0);
    this._drawHeading(tel.heading || 0);

    this.el.airspeed.textContent = Math.round(tel.airspeed * 1.94384); // m/s -> kt
    this.el.altitude.textContent = Math.round(tel.altitude * 3.28084); // m -> ft
    this.el.throttle.textContent = Math.round(controls.throttle * 100) + '%';
    this.el.vsi.textContent = Math.round(tel.vsi * 196.85); // m/s -> fpm
    const h = Math.round(tel.heading) % 360;
    this.el.heading.textContent = pad3(h === 0 ? 360 : h);
    this.el.gload.textContent = tel.gLoad.toFixed(1);
    this.el.aoa.textContent = Math.round(tel.alpha * (180 / Math.PI)) + '°';
    this.el.flaps.textContent = controls.flapsDeg + '°';
    this.el.gear.textContent = controls.gearDown ? 'DN' : 'UP';
    this.el.cam.textContent = camLabel;
    this.el.warn.classList.toggle('hidden', !tel.stalled);
  }

  _drawAttitude(pitchDeg, bankDeg) {
    const ctx = this.attCtx;
    const W = this.att.width, H = this.att.height;
    const cx = W / 2, cy = H / 2, R = W / 2 - 6;
    const ppd = 3.0;

    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();
    ctx.translate(cx, cy);
    ctx.rotate(-bankDeg * DEG);
    ctx.translate(0, pitchDeg * ppd);

    const big = 700;
    ctx.fillStyle = '#3b7bd1'; ctx.fillRect(-big, -big, 2 * big, big);
    ctx.fillStyle = '#6e4a2a'; ctx.fillRect(-big, 0, 2 * big, big);
    ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(-big, 0); ctx.lineTo(big, 0); ctx.stroke();

    ctx.fillStyle = '#fff'; ctx.font = '11px monospace'; ctx.textAlign = 'center';
    ctx.lineWidth = 1.5;
    for (let p = -60; p <= 60; p += 10) {
      if (p === 0) continue;
      const y = -p * ppd;
      const len = p % 20 === 0 ? 46 : 26;
      ctx.beginPath(); ctx.moveTo(-len, y); ctx.lineTo(len, y); ctx.stroke();
      if (p % 20 === 0) {
        ctx.fillText(String(Math.abs(p)), -len - 14, y + 4);
        ctx.fillText(String(Math.abs(p)), len + 14, y + 4);
      }
    }
    ctx.restore();

    // Fixed aircraft reference.
    ctx.strokeStyle = '#ffd23a'; ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(cx - 54, cy); ctx.lineTo(cx - 18, cy);
    ctx.moveTo(cx + 18, cy); ctx.lineTo(cx + 54, cy);
    ctx.moveTo(cx, cy - 8); ctx.lineTo(cx, cy); ctx.stroke();
    ctx.fillStyle = '#ffd23a';
    ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.fill();

    // Bezel + bank pointer.
    ctx.strokeStyle = 'rgba(65,255,154,0.6)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
    ctx.fillStyle = '#41ff9a';
    ctx.beginPath();
    ctx.moveTo(cx, cy - R + 2); ctx.lineTo(cx - 7, cy - R + 14); ctx.lineTo(cx + 7, cy - R + 14);
    ctx.closePath(); ctx.fill();
  }

  _drawHeading(hdg) {
    const ctx = this.hdgCtx;
    const W = this.hdg.width, H = this.hdg.height, cx = W / 2;
    const ppd = 4;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(0,12,7,0.45)'; ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(65,255,154,0.4)'; ctx.strokeRect(0.5, 0.5, W - 1, H - 1);

    ctx.textAlign = 'center';
    const cards = { 0: 'N', 90: 'E', 180: 'S', 270: 'W' };
    for (let d = Math.round(hdg) - 70; d <= Math.round(hdg) + 70; d++) {
      const dd = ((d % 360) + 360) % 360;
      const x = cx + (d - hdg) * ppd;
      if (dd % 10 !== 0) continue;
      const major = dd % 30 === 0;
      ctx.strokeStyle = '#41ff9a'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x, H); ctx.lineTo(x, H - (major ? 16 : 9)); ctx.stroke();
      if (major) {
        ctx.fillStyle = cards[dd] ? '#ffd23a' : '#9affc9';
        ctx.font = cards[dd] ? 'bold 16px monospace' : '13px monospace';
        ctx.fillText(cards[dd] || pad3(dd === 0 ? 360 : dd).slice(0, 2), x, 18);
      }
    }
  }
}
