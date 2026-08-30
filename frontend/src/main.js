/**
 * Main Application Orchestrator for Aero-Follow 3D (Minimalist Monochrome Edition).
 * Connects WebSocket telemetry, HUD canvas, 3D hologram viewport, and controls.
 */
import { HudCanvasEngine } from './hud/hud_canvas.js';
import { Hologram3DView } from './three/hologram_view.js';
import { FlightControlDock } from './controls/flight_dock.js';
import { ScanModalWizard } from './registration/scan_modal.js';

class AeroFollowApp {
  constructor() {
    this.ws = null;
    this.hudCanvas = null;
    this.sidebarHologram = null;
    this.flightDock = null;
    this.scanWizard = null;
    
    this.currentMode = 'SIMULATOR';
    this.isPreferPhysical = false;

    this._initUI();
    this._connectWebSocket();
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
        this._onTargetLocked(lockedProfile);
      });
    }

    // Modal Trigger Button
    const scanBtn = document.getElementById('btn-open-scan-modal');
    if (scanBtn) {
      scanBtn.addEventListener('click', () => {
        if (this.scanWizard) this.scanWizard.open();
      });
    }

    // Engine Mode Switcher (Physical Tello vs Simulator)
    const modePill = document.getElementById('mode-switcher-pill');
    if (modePill) {
      modePill.addEventListener('click', () => this.toggleEngineMode());
    }

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

  async toggleEngineMode() {
    this.isPreferPhysical = !this.isPreferPhysical;
    const modeLabel = document.getElementById('engine-mode-text');
    if (modeLabel) {
      modeLabel.innerText = this.isPreferPhysical ? 'CONNECTING TELLO...' : 'SIMULATOR';
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
        modeLabel.innerText = this.currentMode === 'PHYSICAL_TELLO' ? 'DJI TELLO (WI-FI)' : 'SIMULATOR / CAM';
      }
    } catch (e) {
      if (modeLabel) modeLabel.innerText = 'SIMULATOR';
    }
  }

  _connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      const dot = document.getElementById('link-status-dot');
      const txt = document.getElementById('link-status-text');
      if (dot) {
        dot.className = 'status-indicator';
      }
      if (txt) {
        txt.innerText = 'LINK: ONLINE';
      }
    };

    this.ws.onclose = () => {
      const dot = document.getElementById('link-status-dot');
      const txt = document.getElementById('link-status-text');
      if (dot) {
        dot.className = 'status-indicator danger';
      }
      if (txt) {
        txt.innerText = 'LINK: OFFLINE';
      }
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

    // 3. Update Top Header Telemetry (Minimal Monotone)
    if (telemetry) {
      const ft = telemetry.flight_time_sec || 0;
      const mins = String(Math.floor(ft / 60)).padStart(2, '0');
      const secs = String(ft % 60).padStart(2, '0');
      const ftEl = document.getElementById('top-flight-time');
      if (ftEl) ftEl.innerText = `${mins}:${secs}`;

      const bat = telemetry.battery || 90;
      const batValEl = document.getElementById('top-battery-val');
      const batBarEl = document.getElementById('battery-fill-bar');
      if (batValEl) {
        batValEl.innerText = `${bat}%`;
        batValEl.className = 'metric-badge-val';
      }
      if (batBarEl) {
        batBarEl.style.width = `${bat}%`;
        batBarEl.style.background = '#ffffff';
      }

      const altEl = document.getElementById('telem-alt');
      if (altEl) altEl.innerHTML = `${((telemetry.altitude_cm || 0) / 100.0).toFixed(1)} <span class="telem-unit">m</span>`;

      const tempEl = document.getElementById('telem-temp');
      if (tempEl) tempEl.innerHTML = `${telemetry.temp_c || 36} <span class="telem-unit">°C</span>`;

      const baroEl = document.getElementById('telem-baro');
      if (baroEl) baroEl.innerHTML = `${(telemetry.barometer_m || 0.0).toFixed(1)} <span class="telem-unit">m</span>`;

      const attEl = document.getElementById('telem-att');
      if (attEl) attEl.innerText = `${telemetry.pitch_deg || 0}° / ${telemetry.roll_deg || 0}°`;
    }

    // 4. Update Target Tracking & Biometrics Sidebar
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

    // 5. Update PID Command Readout
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
