/**
 * Main Application Orchestrator for Aero-Follow 3D (Pro Edition).
 * Connects WebSocket telemetry, HUD canvas, 3D hologram viewport, audio FX,
 * snapshot capture, live follow parameter sliders, and profile quick-switching.
 */
import { HudCanvasEngine } from './hud/hud_canvas.js';
import { Hologram3DView } from './three/hologram_view.js';
import { FlightControlDock } from './controls/flight_dock.js';
import { ScanModalWizard } from './registration/scan_modal.js';
import { RunsModal } from './analytics/runs_modal.js';
import { voiceCopilot } from './audio/voice_copilot.js';
import { soundFX } from './audio/sound_fx.js';

class AeroFollowApp {
  constructor() {
    this.ws = null;
    this.hudCanvas = null;
    this.sidebarHologram = null;
    this.flightDock = null;
    this.scanWizard = null;
    this.runsModal = null;
    
    this.currentMode = 'SIMULATOR';
    this.isPreferPhysical = false;
    this.wasTargetMatched = false;
    this.lastSpokenGesture = 'NONE';
    this.lockedTargetName = 'Commander Prime';
    this.wasCinematicActive = false;

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

    // 5. Missions Archive & Telemetry Analytics Modal
    const runsModalEl = document.getElementById('runs-modal');
    if (runsModalEl) {
      this.runsModal = new RunsModal(runsModalEl);
      this.runsModal.loadRuns();
    }

    const openRunsBtn = document.getElementById('btn-open-runs-modal');
    if (openRunsBtn) {
      openRunsBtn.addEventListener('click', () => {
        soundFX.playClick();
        if (this.runsModal) this.runsModal.open();
      });
    }

    // Dual-Source Selector (Webcam vs DJI Tello Wi-Fi)
    this._initSourceSelector();

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

    // Voice Avionics Copilot (JARVIS / BETTY) Toggle Button
    const voiceBtn = document.getElementById('btn-toggle-voice');
    if (voiceBtn) {
      voiceBtn.classList.add('active');
      voiceBtn.addEventListener('click', () => {
        soundFX.playClick();
        const isMuted = voiceCopilot.toggleMute();
        if (isMuted) voiceBtn.classList.remove('active');
        else voiceBtn.classList.add('active');
      });
    }

    // Cinematic QuickShot Buttons (Dronie, Rocket, Helix, Boomerang)
    const qsBtns = document.querySelectorAll('.quickshot-btn');
    qsBtns.forEach(btn => {
      btn.addEventListener('click', async () => {
        const maneuver = btn.dataset.shot;
        soundFX.playClick();
        qsBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        try {
          const res = await fetch('/api/cinematic/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ maneuver })
          });
          const data = await res.json();
          if (data.status === 'started') {
            voiceCopilot.quickshotStarted(maneuver);
          }
        } catch (e) {
          console.error("Failed to trigger QuickShot:", e);
        }
      });
    });

    const abortQsBtn = document.getElementById('btn-abort-quickshot');
    if (abortQsBtn) {
      abortQsBtn.addEventListener('click', async () => {
        soundFX.playWarning();
        qsBtns.forEach(b => b.classList.remove('active'));
        try {
          await fetch('/api/cinematic/abort', { method: 'POST' });
        } catch (e) {}
      });
    }

    // Voice Callout on Flight Actions
    const takeoffBtn = document.getElementById('btn-takeoff');
    if (takeoffBtn) {
      takeoffBtn.addEventListener('click', () => voiceCopilot.takeoff());
    }
    const landBtn = document.getElementById('btn-land');
    if (landBtn) {
      landBtn.addEventListener('click', () => voiceCopilot.landing());
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

  async _initSourceSelector() {
    const btnWebcam = document.getElementById('btn-source-webcam');
    const btnDrone = document.getElementById('btn-source-drone');
    const selectCam = document.getElementById('select-webcam-index');
    const telloModal = document.getElementById('tello-alert-modal');
    const closeTelloBtn = document.getElementById('modal-tello-close-btn');
    const fallbackWebcamBtn = document.getElementById('btn-tello-fallback-webcam');
    const retryDroneBtn = document.getElementById('btn-tello-retry-connect');

    // Populate available cameras
    try {
      const res = await fetch('/api/available_sources');
      const data = await res.json();
      if (selectCam && Array.isArray(data.cameras) && data.cameras.length > 0) {
        selectCam.innerHTML = '';
        data.cameras.forEach(cam => {
          const opt = document.createElement('option');
          opt.value = cam.index;
          opt.innerText = cam.name;
          selectCam.appendChild(opt);
        });
        if (data.camera_index !== undefined) {
          selectCam.value = data.camera_index;
        }
      }
    } catch (e) {}

    // Switch to Webcam
    if (btnWebcam) {
      btnWebcam.addEventListener('click', () => {
        soundFX.playClick();
        const camIdx = selectCam ? parseInt(selectCam.value, 10) : 0;
        this.setSource('WEBCAM', camIdx);
      });
    }

    // Camera index dropdown change
    if (selectCam) {
      selectCam.addEventListener('change', () => {
        soundFX.playClick();
        const camIdx = parseInt(selectCam.value, 10);
        this.setSource('WEBCAM', camIdx);
      });
    }

    // Switch to Physical DJI Tello Drone over Wi-Fi
    if (btnDrone) {
      btnDrone.addEventListener('click', () => {
        soundFX.playClick();
        this.setSource('DRONE_WIFI');
      });
    }

    // Modal buttons
    if (closeTelloBtn && telloModal) {
      closeTelloBtn.addEventListener('click', () => {
        telloModal.classList.remove('open');
      });
    }

    if (fallbackWebcamBtn && telloModal) {
      fallbackWebcamBtn.addEventListener('click', () => {
        soundFX.playClick();
        telloModal.classList.remove('open');
        const camIdx = selectCam ? parseInt(selectCam.value, 10) : 0;
        this.setSource('WEBCAM', camIdx);
      });
    }

    if (retryDroneBtn && telloModal) {
      retryDroneBtn.addEventListener('click', async () => {
        soundFX.playClick();
        retryDroneBtn.innerText = 'CONNECTING...';
        await this.setSource('DRONE_WIFI');
        retryDroneBtn.innerText = 'RETRY WI-FI CONNECT';
      });
    }
  }

  async setSource(sourceType, cameraIndex = 0) {
    const btnWebcam = document.getElementById('btn-source-webcam');
    const btnDrone = document.getElementById('btn-source-drone');
    const linkText = document.getElementById('link-status-text');
    const linkDot = document.getElementById('link-status-dot');
    const telloModal = document.getElementById('tello-alert-modal');
    const telloErrDetail = document.getElementById('tello-error-detail');

    if (linkText) {
      linkText.innerText = sourceType === 'DRONE_WIFI' ? 'CONNECTING TELLO...' : `CONNECTING CAM ${cameraIndex}...`;
    }

    try {
      const res = await fetch('/api/set_source', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: sourceType, camera_index: cameraIndex })
      });
      const data = await res.json();

      if (data.status === 'connected') {
        soundFX.playLock();
        this.currentMode = data.source;

        if (sourceType === 'DRONE_WIFI') {
          if (btnDrone) btnDrone.classList.add('active');
          if (btnWebcam) btnWebcam.classList.remove('active');
          if (linkText) linkText.innerText = 'SOURCE: DJI TELLO (WI-FI)';
          if (linkDot) linkDot.className = 'status-indicator';
          if (telloModal) telloModal.classList.remove('open');
        } else {
          if (btnWebcam) btnWebcam.classList.add('active');
          if (btnDrone) btnDrone.classList.remove('active');
          if (linkText) linkText.innerText = `SOURCE: WEBCAM ${cameraIndex}`;
          if (linkDot) linkDot.className = 'status-indicator';
        }

        // Refresh video stream
        const videoEl = document.getElementById('video-stream-el');
        if (videoEl) {
          videoEl.src = `/api/video_feed?t=${Date.now()}`;
        }
      } else {
        // Connection error (e.g. Drone Wi-Fi not reachable)
        soundFX.playWarning();
        if (telloErrDetail && data.message) {
          telloErrDetail.innerText = data.message;
        }
        if (telloModal) {
          telloModal.classList.add('open');
        }
        // Keep active button on Webcam
        if (btnWebcam) btnWebcam.classList.add('active');
        if (btnDrone) btnDrone.classList.remove('active');
        if (linkText) linkText.innerText = `SOURCE: WEBCAM ${cameraIndex}`;
      }
    } catch (err) {
      if (linkText) linkText.innerText = `ERROR: ${err.message}`;
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

    // 3. Audio Chime & Voice Callout on Target Lock Transition
    if (tracking) {
      const isMatched = tracking.target_matched;
      if (isMatched && !this.wasTargetMatched) {
        soundFX.playLock();
        voiceCopilot.targetLocked(this.lockedTargetName);
      }
      this.wasTargetMatched = isMatched;

      // Proximity Alert Voice Warning (< 0.95m)
      if (tracking.estimated_distance_m && tracking.estimated_distance_m < 0.95) {
        voiceCopilot.proximityWarning();
      }

      // Gesture Recognition Voice Callout
      if (tracking.gesture) {
        const gType = tracking.gesture.type;
        if (gType !== 'NONE' && gType !== this.lastSpokenGesture) {
          voiceCopilot.gestureRecognized(tracking.gesture.label);
          this.lastSpokenGesture = gType;
        } else if (gType === 'NONE') {
          this.lastSpokenGesture = 'NONE';
        }
      }
    }

    // 4. Update QuickShot Cinematic In-Flight Overlay
    const cinematic = payload.cinematic;
    const qsOverlay = document.getElementById('quickshot-hud-overlay');
    const qsFill = document.getElementById('quickshot-progress-fill');
    const qsName = document.getElementById('qs-hud-name');
    const qsPhase = document.getElementById('qs-hud-phase');
    const qsPct = document.getElementById('qs-hud-pct');
    const qsBtns = document.querySelectorAll('.quickshot-btn');

    if (cinematic && cinematic.active) {
      if (qsOverlay) qsOverlay.style.display = 'flex';
      if (qsName) qsName.innerText = `CINEMATIC: ${cinematic.maneuver}`;
      if (qsPhase) qsPhase.innerText = `PHASE: ${cinematic.phase}`;
      if (qsPct) qsPct.innerText = `${Math.round(cinematic.progress_pct)}%`;
      if (qsFill) qsFill.style.width = `${cinematic.progress_pct}%`;
      this.wasCinematicActive = true;
    } else {
      if (qsOverlay) qsOverlay.style.display = 'none';
      if (this.wasCinematicActive) {
        qsBtns.forEach(b => b.classList.remove('active'));
        voiceCopilot.quickshotCompleted(cinematic ? cinematic.maneuver : 'maneuver');
        this.wasCinematicActive = false;
      }
    }

    // 5. Update Top Header Telemetry
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

    // 7. Update Live Mission Active Run state
    if (this.runsModal && payload.active_run !== undefined) {
      this.runsModal.updateActiveRun(payload.active_run);
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

  captureSnapshot() {
    soundFX.playShutter();
    const pfd = document.querySelector('.pfd-viewport');
    if (pfd) {
      const flash = document.createElement('div');
      flash.style.position = 'absolute';
      flash.style.inset = '0';
      flash.style.backgroundColor = '#ffffff';
      flash.style.opacity = '0.8';
      flash.style.zIndex = '50';
      flash.style.pointerEvents = 'none';
      flash.style.transition = 'opacity 0.4s ease';
      pfd.appendChild(flash);
      requestAnimationFrame(() => {
        flash.style.opacity = '0';
        setTimeout(() => flash.remove(), 400);
      });
    }
    voiceCopilot.speak("Snapshot captured", "snapshot");
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.app = new AeroFollowApp();
});
