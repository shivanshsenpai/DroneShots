/**
 * Main Application Orchestrator for Aero-Follow 3D (Pro Edition).
 * Connects WebSocket telemetry, HUD canvas, 3D hologram viewport, audio FX,
 * snapshot capture, live follow parameter sliders, and profile quick-switching.
 */
import { HudCanvasEngine } from './hud/hud_canvas.js';
import { Hologram3DView } from './three/hologram_view.js';
import { FlightControlDock } from './controls/flight_dock.js';
import { ScanModalWizard } from './registration/scan_modal.js';
import { soundFX } from './audio/sound_fx.js';

class AeroFollowApp {
  constructor() {
    this.ws = null;
    this.hudCanvas = null;
    this.sidebarHologram = null;
    this.flightDock = null;
    this.scanWizard = null;
    
    this.currentMode = 'SIMULATOR';
    this.isPreferPhysical = false;
    this.wasTargetMatched = false;

    this._initUI();
    this._connectWebSocket();
    this._loadProfiles();
  }

  _initUI() {
    // 1. HUD Canvas Engine
    const canvasEl = document.getElementById('hud-canvas');
    if (canvasEl) {
      this.hudCanvas = new HudCanvasEngine(canvasEl);
    }

    // 2. Sidebar 3D Hologram Viewport
    const holoEl = document.getElementById('three-hologram-container');
    if (holoEl) {
      this.sidebarHologram = new Hologram3DView(holoEl);
    }

    // 3. Flight Controls Dock
    const dockEl = document.getElementById('flight-dock');
    if (dockEl) {
      this.flightDock = new FlightControlDock(dockEl, (state) => {});
    }

    // 4. 3D Scan & Registration Modal Wizard
    const modalEl = document.getElementById('scan-modal');
    if (modalEl) {
      this.scanWizard = new ScanModalWizard(modalEl, (lockedProfile) => {
        soundFX.playLock();
        this._onTargetLocked(lockedProfile);
        this._loadProfiles();
      });
    }

    // Modal Trigger Button
    const scanBtn = document.getElementById('btn-open-scan-modal');
    if (scanBtn) {
      scanBtn.addEventListener('click', () => {
        soundFX.playClick();
        if (this.scanWizard) this.scanWizard.open();
      });
    }

    // Engine Mode Switcher (Physical Tello vs Simulator)
    const modePill = document.getElementById('mode-switcher-pill');
    if (modePill) {
      modePill.addEventListener('click', () => {
        soundFX.playClick();
        this.toggleEngineMode();
      });
    }

    // Snapshot Capture Tool
    const snapBtn = document.getElementById('btn-capture-snapshot');
    if (snapBtn) {
      snapBtn.addEventListener('click', () => this.captureSnapshot());
    }

    // Audio Mute / Unmute Button
    const audioBtn = document.getElementById('btn-toggle-audio');
    if (audioBtn) {
      this._updateAudioIcon();
      audioBtn.addEventListener('click', () => {
        const isMuted = soundFX.toggleMute();
        this._updateAudioIcon();
        if (!isMuted) soundFX.playLock();
      });
    }

    // Follow Parameters Range Sliders
    this._initFollowSliders();

    // Video stream image error handler (retry if stream dropped)
    const videoEl = document.getElementById('video-stream-el');
    if (videoEl) {
      videoEl.onerror = () => {
        setTimeout(() => {
          videoEl.src = `/api/video_feed?t=${Date.now()}`;
        }, 1000);
      };
    }
  }

  _updateAudioIcon() {
    const unmuted = document.getElementById('audio-icon-unmuted');
    const muted = document.getElementById('audio-icon-muted');
    if (unmuted && muted) {
      if (soundFX.isMuted()) {
        unmuted.style.display = 'none';
        muted.style.display = 'block';
      } else {
        unmuted.style.display = 'block';
        muted.style.display = 'none';
      }
    }
  }

  _initFollowSliders() {
    const distSlider = document.getElementById('slider-target-distance');
    const distVal = document.getElementById('val-target-distance');
    const altSlider = document.getElementById('slider-target-altitude');
    const altVal = document.getElementById('val-target-altitude');

    if (distSlider && distVal) {
      distSlider.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value);
        distVal.innerText = `${v.toFixed(1)}m`;
        fetch('/api/settings/follow', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_distance_m: v })
        }).catch(() => {});
      });
    }

    if (altSlider && altVal) {
      altSlider.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value);
        altVal.innerText = `${v.toFixed(1)}m`;
        fetch('/api/settings/follow', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_altitude_m: v })
        }).catch(() => {});
      });
    }
  }

  async captureSnapshot() {
    soundFX.playShutter();
    const flashEl = document.getElementById('shutter-flash-overlay');
    if (flashEl) {
      flashEl.classList.add('active');
      setTimeout(() => flashEl.classList.remove('active'), 120);
    }

    try {
      const res = await fetch('/api/flight/snapshot', { method: 'POST' });
      const data = await res.json();
      if (data.status === 'captured') {
        console.log(`[SNAPSHOT] Saved: ${data.url}`);
      }
    } catch (e) {}
  }

  async toggleEngineMode() {
    this.isPreferPhysical = !this.isPreferPhysical;
    const modeLabel = document.getElementById('engine-mode-text');
    if (modeLabel) {
      modeLabel.innerText = this.isPreferPhysical ? 'CONNECTING...' : 'SIMULATOR';
    }

    try {
      const res = await fetch('/api/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prefer_physical: this.isPreferPhysical })
      });
      const data = await res.json();
      this.currentMode = data.mode || (this.isPreferPhysical ? 'PHYSICAL_TELLO' : 'SIMULATOR');
      if (modeLabel) {
        modeLabel.innerText = this.currentMode === 'PHYSICAL_TELLO' ? 'DJI TELLO (WI-FI)' : 'SIMULATOR';
      }
    } catch (e) {
      if (modeLabel) modeLabel.innerText = 'SIMULATOR';
    }
  }

  async _loadProfiles() {
    try {
      const res = await fetch('/api/profiles');
      const profiles = await res.json();
      const listEl = document.getElementById('sidebar-profiles-list');
      if (!listEl || !Array.isArray(profiles)) return;

      listEl.innerHTML = '';
      profiles.forEach(prof => {
        const item = document.createElement('div');
        item.className = 'profile-pill-item';
        item.innerHTML = `
          <span style="font-weight:600; color:#fff;">${prof.name}</span>
          <span style="color:var(--text-muted); font-size:9px;">${prof.orientation}</span>
        `;
        item.addEventListener('click', async () => {
          soundFX.playClick();
          try {
            const lockRes = await fetch(`/api/lock_target/${prof.id}`, { method: 'POST' });
            if (lockRes.ok) {
              soundFX.playLock();
              this._onTargetLocked(prof);
              document.querySelectorAll('.profile-pill-item').forEach(el => el.classList.remove('active'));
              item.classList.add('active');
            }
          } catch (e) {}
        });
        listEl.appendChild(item);
      });
    } catch (e) {}
  }

  _connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      const dot = document.getElementById('link-status-dot');
      const txt = document.getElementById('link-status-text');
      if (dot) dot.className = 'status-indicator';
      if (txt) txt.innerText = 'LINK: ONLINE';
    };

    this.ws.onclose = () => {
      const dot = document.getElementById('link-status-dot');
      const txt = document.getElementById('link-status-text');
      if (dot) dot.className = 'status-indicator danger';
      if (txt) txt.innerText = 'LINK: OFFLINE';
      setTimeout(() => this._connectWebSocket(), 1500);
    };

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        this._updateDashboard(payload);
      } catch (e) {}
    };
  }

  _updateDashboard(payload) {
    const { telemetry, tracking, rc_commands, autonomous_active, follow_mode } = payload;

    // 1. Update Minimalist HUD Canvas
    if (this.hudCanvas) {
      this.hudCanvas.updateState(telemetry, tracking, autonomous_active);
    }

    // 2. Update 3D Hologram Viewport
    if (this.sidebarHologram && tracking && tracking.landmarks_3d_world) {
      this.sidebarHologram.updateFromLandmarks(tracking.landmarks_3d_world, tracking.yaw_deg || 0);
    }

    // 3. Audio Chime on Target Lock Transition
    if (tracking) {
      const isMatched = tracking.target_matched;
      if (isMatched && !this.wasTargetMatched) {
        soundFX.playLock();
      }
      this.wasTargetMatched = isMatched;
    }

    // 4. Update Top Header Telemetry
    if (telemetry) {
      const ft = telemetry.flight_time_sec || 0;
      const mins = String(Math.floor(ft / 60)).padStart(2, '0');
      const secs = String(ft % 60).padStart(2, '0');
      const ftEl = document.getElementById('top-flight-time');
      if (ftEl) ftEl.innerText = `${mins}:${secs}`;

      const bat = telemetry.battery || 90;
      const batValEl = document.getElementById('top-battery-val');
      const batBarEl = document.getElementById('battery-fill-bar');
      if (batValEl) batValEl.innerText = `${bat}%`;
      if (batBarEl) batBarEl.style.width = `${bat}%`;

      const altEl = document.getElementById('telem-alt');
      if (altEl) altEl.innerHTML = `${((telemetry.altitude_cm || 0) / 100.0).toFixed(1)} <span class="telem-unit">m</span>`;

      const tempEl = document.getElementById('telem-temp');
      if (tempEl) tempEl.innerHTML = `${telemetry.temp_c || 36} <span class="telem-unit">°C</span>`;

      const attEl = document.getElementById('telem-att');
      if (attEl) attEl.innerText = `${telemetry.pitch_deg || 0}° / ${telemetry.roll_deg || 0}°`;
    }

    // 5. Update Target Tracking & Biometrics Sidebar
    if (tracking) {
      const isMatched = tracking.target_matched;
      const conf = Math.round((tracking.confidence || 0) * 100);
      const orient = tracking.orientation || 'FRONT';

      const pfdTarget = document.getElementById('pfd-target-status');
      if (pfdTarget) {
        pfdTarget.className = `lock-status-badge ${isMatched ? 'locked' : ''}`;
        pfdTarget.innerText = isMatched ? `TARGET: ${orient} (${conf}%)` : `SCANNING [${orient}]`;
      }

      const viewEl = document.getElementById('sidebar-target-view');
      if (viewEl) viewEl.innerText = `${orient} (${isMatched ? 'LOCKED' : 'DETECTED'})`;

      const confPill = document.getElementById('target-conf-pill');
      if (confPill) {
        confPill.innerText = `LOCK: ${conf}%`;
        confPill.style.color = '#ffffff';
      }

      const distEl = document.getElementById('telem-dist');
      if (distEl) distEl.innerHTML = `${(tracking.estimated_distance_m || 2.0).toFixed(1)} <span class="telem-unit">m</span>`;

      const speedEl = document.getElementById('telem-speed');
      if (speedEl) {
        const spd = tracking.velocity ? tracking.velocity.speed_mps.toFixed(1) : '0.0';
        speedEl.innerHTML = `${spd} <span class="telem-unit">m/s</span>`;
      }

      if (tracking.color_palette) {
        const hSw = document.getElementById('sb-hair-swatch');
        const tSw = document.getElementById('sb-torso-swatch');
        const lSw = document.getElementById('sb-legs-swatch');
        if (hSw) hSw.style.backgroundColor = tracking.color_palette.hair_hex || '#1e293b';
        if (tSw) tSw.style.backgroundColor = tracking.color_palette.torso_hex || '#e2e8f0';
        if (lSw) lSw.style.backgroundColor = tracking.color_palette.legs_hex || '#0f172a';
      }

      const holoYaw = document.getElementById('holo-yaw-readout');
      if (holoYaw) holoYaw.innerText = `YAW: ${(tracking.yaw_deg || 0).toFixed(1)}° [${orient}]`;
    }

    // 6. Update PID Command Readout
    if (rc_commands) {
      const rcEl = document.getElementById('telem-rc');
      if (rcEl) {
        rcEl.innerText = `R${rc_commands.roll} P${rc_commands.pitch} T${rc_commands.throttle} Y${rc_commands.yaw}`;
      }
    }
  }

  _onTargetLocked(profile) {
    const nameEl = document.getElementById('sidebar-target-name');
    if (nameEl) nameEl.innerText = profile.name || 'Subject Alpha';

    const pfdTarget = document.getElementById('pfd-target-status');
    if (pfdTarget) {
      pfdTarget.className = 'lock-status-badge locked';
      pfdTarget.innerText = `LOCKED: ${profile.name}`;
    }
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.app = new AeroFollowApp();
});
