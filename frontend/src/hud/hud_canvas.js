/**
 * 60 FPS Minimalist HUD Canvas Engine.
 * Renders Pitch Ladder, Artificial Horizon, Heading Ribbon, Target Reticle,
 * and Calipers with a clean, monotonous monochrome aesthetic.
 */

export class HudCanvasEngine {
  constructor(canvasElement) {
    this.canvas = canvasElement;
    this.ctx = this.canvas.getContext('2d');
    this.animationFrameId = null;

    // Telemetry & Tracking state references
    this.telemetry = {
      pitch_deg: 0,
      roll_deg: 0,
      yaw_deg: 0,
      altitude_cm: 0,
      speed_z: 0
    };
    this.tracking = null;
    this.autonomousActive = false;

    // Resize handling
    this.resize();
    window.addEventListener('resize', () => this.resize());
    this.start();
  }

  resize() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width;
    this.canvas.height = rect.height;
    this.width = this.canvas.width;
    this.height = this.canvas.height;
  }

  updateState(telemetry, tracking, autonomousActive) {
    if (telemetry) this.telemetry = telemetry;
    if (tracking) this.tracking = tracking;
    this.autonomousActive = !!autonomousActive;
  }

  start() {
    const loop = () => {
      this.render();
      this.animationFrameId = requestAnimationFrame(loop);
    };
    this.animationFrameId = requestAnimationFrame(loop);
  }

  stop() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
  }

  render() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    ctx.clearRect(0, 0, w, h);

    if (w === 0 || h === 0) return;

    // 1. Draw Top Heading Compass Ribbon
    this._drawCompassRibbon(ctx, w, h);

    // 2. Draw Center Aircraft Reticle & Artificial Horizon Pitch Ladder
    this._drawPitchLadder(ctx, w, h);

    // 3. Draw Target Lock Brackets & Biometric Calipers
    this._drawTargetLock(ctx, w, h);

    // 4. Draw Altitude & Speed Tapes
    this._drawAltitudeTape(ctx, w, h);
  }

  _drawCompassRibbon(ctx, w, h) {
    const yaw = (this.telemetry.yaw_deg || 0) % 360;
    const normalizedYaw = yaw < 0 ? yaw + 360 : yaw;
    const ribbonY = 22;
    const ribbonW = Math.min(280, w * 0.45);
    const startX = (w - ribbonW) / 2;

    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(startX, ribbonY);
    ctx.lineTo(startX + ribbonW, ribbonY);
    ctx.stroke();

    // Center caret
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.moveTo(w / 2, ribbonY + 4);
    ctx.lineTo(w / 2 - 4, ribbonY + 9);
    ctx.lineTo(w / 2 + 4, ribbonY + 9);
    ctx.closePath();
    ctx.fill();

    // Heading markings
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.6)';

    for (let deg = -40; deg <= 40; deg += 10) {
      const currentDeg = Math.round((normalizedYaw + deg + 360) % 360);
      const px = w / 2 + (deg * (ribbonW / 80));

      if (px >= startX && px <= startX + ribbonW) {
        ctx.beginPath();
        ctx.moveTo(px, ribbonY);
        ctx.lineTo(px, ribbonY - (deg % 30 === 0 ? 6 : 3));
        ctx.stroke();

        let label = `${currentDeg}°`;
        if (currentDeg === 0 || currentDeg === 360) label = 'N';
        else if (currentDeg === 90) label = 'E';
        else if (currentDeg === 180) label = 'S';
        else if (currentDeg === 270) label = 'W';

        if (deg % 20 === 0) {
          ctx.fillText(label, px, ribbonY - 10);
        }
      }
    }
    ctx.restore();
  }

  _drawPitchLadder(ctx, w, h) {
    const cx = w / 2;
    const cy = h * 0.48;
    const pitch = this.telemetry.pitch_deg || 0;
    const rollRad = ((this.telemetry.roll_deg || 0) * Math.PI) / 180;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-rollRad);

    // Center Bore Sight Aircraft Reticle (Minimal White)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.85)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    // Left wing
    ctx.moveTo(-24, 0);
    ctx.lineTo(-8, 0);
    ctx.lineTo(-8, 4);
    // Right wing
    ctx.moveTo(24, 0);
    ctx.lineTo(8, 0);
    ctx.lineTo(8, 4);
    // Center pip
    ctx.arc(0, 0, 2, 0, Math.PI * 2);
    ctx.stroke();

    // Pitch ladder rungs (+10, -10 degrees)
    const pitchScale = 3.2;
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.textAlign = 'right';

    for (let p = -20; p <= 20; p += 10) {
      if (p === 0) continue;
      const rungY = - (p - pitch) * pitchScale;
      if (Math.abs(rungY) < 130) {
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        // Left rung
        ctx.moveTo(-45, rungY);
        ctx.lineTo(-16, rungY);
        ctx.lineTo(-16, rungY + (p > 0 ? 4 : -4));
        // Right rung
        ctx.moveTo(16, rungY);
        ctx.lineTo(45, rungY);
        ctx.lineTo(16, rungY + (p > 0 ? 4 : -4));
        ctx.stroke();

        ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
        ctx.fillText(`${Math.abs(p)}`, -50, rungY + 3);
      }
    }
    ctx.restore();
  }

  _drawTargetLock(ctx, w, h) {
    if (!this.tracking || !this.tracking.target_detected) return;

    const bboxNorm = this.tracking.bbox_normalized;
    if (!bboxNorm) return;

    const bx = bboxNorm[0] * w;
    const by = bboxNorm[1] * h;
    const bw = bboxNorm[2] * w;
    const bh = bboxNorm[3] * h;

    const isMatched = this.tracking.target_matched;
    const conf = Math.round((this.tracking.confidence || 0) * 100);
    const color = isMatched ? '#ffffff' : 'rgba(255, 255, 255, 0.6)';

    ctx.save();

    // 1. Bracket Corners (Minimalist Monochrome)
    const bracketLen = Math.min(20, bw * 0.22, bh * 0.22);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;

    // Top Left
    ctx.beginPath();
    ctx.moveTo(bx, by + bracketLen);
    ctx.lineTo(bx, by);
    ctx.lineTo(bx + bracketLen, by);
    ctx.stroke();

    // Top Right
    ctx.beginPath();
    ctx.moveTo(bx + bw - bracketLen, by);
    ctx.lineTo(bx + bw, by);
    ctx.lineTo(bx + bw, by + bracketLen);
    ctx.stroke();

    // Bottom Left
    ctx.beginPath();
    ctx.moveTo(bx, by + bh - bracketLen);
    ctx.lineTo(bx, by + bh);
    ctx.lineTo(bx + bracketLen, by + bh);
    ctx.stroke();

    // Bottom Right
    ctx.beginPath();
    ctx.moveTo(bx + bw - bracketLen, by + bh);
    ctx.lineTo(bx + bw, by + bh);
    ctx.lineTo(bx + bw, by + bh - bracketLen);
    ctx.stroke();

    // 2. Subtle target center cross
    const tcx = bx + bw / 2;
    const tcy = by + bh / 2;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(tcx - 6, tcy);
    ctx.lineTo(tcx + 6, tcy);
    ctx.moveTo(tcx, tcy - 6);
    ctx.lineTo(tcx, tcy + 6);
    ctx.stroke();

    // 3. Lead Vector
    if (this.autonomousActive) {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(w / 2, h * 0.48);
      ctx.lineTo(tcx, tcy);
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // 4. Floating HUD Tag Badges
    const orient = this.tracking.orientation || 'FRONT';
    const dist = (this.tracking.estimated_distance_m || 2.0).toFixed(1);

    // Top Badge
    ctx.fillStyle = 'rgba(15, 17, 23, 0.9)';
    ctx.fillRect(bx, Math.max(10, by - 20), Math.max(130, bw * 0.55), 18);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.strokeRect(bx, Math.max(10, by - 20), Math.max(130, bw * 0.55), 18);

    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'left';
    ctx.fillText(`TARGET [${orient}]`, bx + 5, Math.max(10, by - 20) + 12);

    // Bottom Badge
    const botY = by + bh + 4;
    if (botY < h - 18) {
      ctx.fillStyle = 'rgba(15, 17, 23, 0.9)';
      ctx.fillRect(bx, botY, 100, 16);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
      ctx.strokeRect(bx, botY, 100, 16);

      ctx.font = '8px "JetBrains Mono", monospace';
      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.fillText(`DIST: ${dist}m (${conf}%)`, bx + 5, botY + 11);
    }

    ctx.restore();
  }

  _drawAltitudeTape(ctx, w, h) {
    const altCm = this.telemetry.altitude_cm || 0;
    const altM = (altCm / 100.0).toFixed(1);
    const tapeX = w - 42;
    const tapeY = h / 2 - 70;

    ctx.save();
    ctx.fillStyle = 'rgba(15, 17, 23, 0.7)';
    ctx.fillRect(tapeX - 16, tapeY, 48, 140);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.strokeRect(tapeX - 16, tapeY, 48, 140);

    // Active altitude readout box
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(tapeX - 20, h / 2 - 10, 56, 20);
    ctx.fillStyle = '#000000';
    ctx.font = 'bold 10px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText(`${altM}m`, tapeX + 8, h / 2 + 4);

    ctx.font = '8px "JetBrains Mono", monospace';
    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.fillText('ALT', tapeX + 8, tapeY + 10);
    ctx.restore();
  }
}
