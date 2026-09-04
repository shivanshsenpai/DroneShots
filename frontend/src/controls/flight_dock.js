/**
 * Flight Control Dock, Autonomous Director, Virtual Dual Joysticks, and Cockpit Engine.
 */
import { soundFX } from '../audio/sound_fx.js';

export class FlightControlDock {
  constructor(dockElement, onStateChange) {
    this.dock = dockElement;
    this.onStateChange = onStateChange;

    this.currentMode = 'LEAD';
    this.isAutonomousEngaged = false;
    this.isFlying = false;

    // Virtual Sticks State
    this.sticksVisible = false;
    this.leftStickActive = false;
    this.rightStickActive = false;
    this.stickRC = { roll: 0, pitch: 0, throttle: 0, yaw: 0 };
    this.stickInterval = null;

    this._bindElements();
    this._bindEvents();
    this._initKeyboardControls();
    this._initVirtualSticks();
  }

  _bindElements() {
    this.modeButtons = this.dock.querySelectorAll('.mode-btn');
    this.toggleFollowBtn = this.dock.querySelector('#btn-toggle-follow');
    this.takeoffBtn = this.dock.querySelector('#btn-takeoff');
    this.landBtn = this.dock.querySelector('#btn-land');
    this.emergencyBtn = this.dock.querySelector('#btn-emergency');
    this.toggleSticksBtn = this.dock.querySelector('#btn-toggle-sticks');
    this.cockpitOverlay = document.getElementById('virtual-cockpit');
  }

  _bindEvents() {
    // Follow Mode buttons
    this.modeButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        soundFX.playClick();
        const mode = btn.dataset.mode;
        this.setFollowMode(mode);
      });
    });

    // Autonomous Follow Toggle
    if (this.toggleFollowBtn) {
      this.toggleFollowBtn.addEventListener('click', () => this.toggleAutonomousFollow());
    }

    // Takeoff
    if (this.takeoffBtn) {
      this.takeoffBtn.addEventListener('click', () => {
        soundFX.playClick();
        this.takeoff();
      });
    }

    // Land
    if (this.landBtn) {
      this.landBtn.addEventListener('click', () => {
        soundFX.playClick();
        this.land();
      });
    }

    // Emergency Cutoff
    if (this.emergencyBtn) {
      this.emergencyBtn.addEventListener('click', () => {
        soundFX.playWarning();
        this.emergency();
      });
    }

    // Virtual Sticks Toggle
    if (this.toggleSticksBtn && this.cockpitOverlay) {
      this.toggleSticksBtn.addEventListener('click', () => {
        soundFX.playClick();
        this.sticksVisible = !this.sticksVisible;
        if (this.sticksVisible) {
          this.cockpitOverlay.classList.add('visible');
          this.toggleSticksBtn.style.background = '#ffffff';
          this.toggleSticksBtn.style.color = '#000000';
        } else {
          this.cockpitOverlay.classList.remove('visible');
          this.toggleSticksBtn.style.background = 'transparent';
          this.toggleSticksBtn.style.color = 'var(--text-secondary)';
        }
      });
    }
  }

  async setFollowMode(mode) {
    this.currentMode = mode;
    this.modeButtons.forEach(btn => {
      if (btn.dataset.mode === mode) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    try {
      await fetch('/api/follow_mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: this.currentMode })
      });
    } catch (e) {}
  }

  async toggleAutonomousFollow() {
    this.isAutonomousEngaged = !this.isAutonomousEngaged;
    this._updateFollowButtonUI();

    if (this.isAutonomousEngaged) {
      soundFX.playFollowEngaged();
    } else {
      soundFX.playClick();
    }

    try {
      await fetch('/api/tracking_toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active: this.isAutonomousEngaged })
      });
    } catch (e) {}
  }

  _updateFollowButtonUI() {
    if (!this.toggleFollowBtn) return;
    if (this.isAutonomousEngaged) {
      this.toggleFollowBtn.classList.add('engaged');
      this.toggleFollowBtn.innerHTML = `
        <span class="status-indicator"></span>
        <span>AUTONOMOUS ENGAGED</span>
      `;
    } else {
      this.toggleFollowBtn.classList.remove('engaged');
      this.toggleFollowBtn.innerHTML = `
        <span class="status-indicator amber"></span>
        <span>ENGAGE 3D FOLLOW</span>
      `;
    }
  }

  async takeoff() {
    try {
      await fetch('/api/flight/takeoff', { method: 'POST' });
    } catch (e) {}
  }

  async land() {
    this.isAutonomousEngaged = false;
    this._updateFollowButtonUI();
    try {
      await fetch('/api/flight/land', { method: 'POST' });
    } catch (e) {}
  }

  async emergency() {
    this.isAutonomousEngaged = false;
    this._updateFollowButtonUI();
    try {
      await fetch('/api/flight/emergency', { method: 'POST' });
    } catch (e) {}
  }

  _initVirtualSticks() {
    const leftHousing = document.getElementById('left-stick-housing');
    const leftKnob = document.getElementById('left-stick-knob');
    const rightHousing = document.getElementById('right-stick-housing');
    const rightKnob = document.getElementById('right-stick-knob');

    if (!leftHousing || !rightHousing || !leftKnob || !rightKnob) return;

    const maxRadius = 38;

    const setupStick = (housing, knob, onMove, onRelease) => {
      let isDragging = false;
      let center = { x: 0, y: 0 };

      const getCoords = (e) => {
        if (e.touches && e.touches.length > 0) {
          return { x: e.touches[0].clientX, y: e.touches[0].clientY };
        }
        return { x: e.clientX, y: e.clientY };
      };

      const onStart = (e) => {
        isDragging = true;
        const rect = housing.getBoundingClientRect();
        center = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        onPointerMove(e);
      };

      const onPointerMove = (e) => {
        if (!isDragging) return;
        const pos = getCoords(e);
        const dx = pos.x - center.x;
        const dy = pos.y - center.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const angle = Math.atan2(dy, dx);
        const clampedDist = Math.min(dist, maxRadius);

        const clampedX = clampedDist * Math.cos(angle);
        const clampedY = clampedDist * Math.sin(angle);

        knob.style.transform = `translate(${clampedX}px, ${clampedY}px)`;
        onMove(clampedX / maxRadius, clampedY / maxRadius);
      };

      const onEnd = () => {
        if (!isDragging) return;
        isDragging = false;
        knob.style.transform = `translate(0px, 0px)`;
        onRelease();
      };

      housing.addEventListener('mousedown', onStart);
      window.addEventListener('mousemove', onPointerMove);
      window.addEventListener('mouseup', onEnd);

      housing.addEventListener('touchstart', onStart, { passive: true });
      window.addEventListener('touchmove', onPointerMove, { passive: true });
      window.addEventListener('touchend', onEnd);
    };

    // Mode 2 Left Stick: X = Yaw, Y = Throttle (up = positive throttle)
    setupStick(
      leftHousing,
      leftKnob,
      (normX, normY) => {
        this.stickRC.yaw = Math.round(normX * 50);
        this.stickRC.throttle = Math.round(-normY * 50);
        this._startSendingStickRC();
      },
      () => {
        this.stickRC.yaw = 0;
        this.stickRC.throttle = 0;
        this._checkStopStickRC();
      }
    );

    // Mode 2 Right Stick: X = Roll, Y = Pitch (up = forward pitch)
    setupStick(
      rightHousing,
      rightKnob,
      (normX, normY) => {
        this.stickRC.roll = Math.round(normX * 50);
        this.stickRC.pitch = Math.round(-normY * 50);
        this._startSendingStickRC();
      },
      () => {
        this.stickRC.roll = 0;
        this.stickRC.pitch = 0;
        this._checkStopStickRC();
      }
    );
  }

  _startSendingStickRC() {
    if (!this.stickInterval) {
      this.stickInterval = setInterval(() => {
        if (this.isAutonomousEngaged) return;
        fetch('/api/flight/manual_rc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.stickRC)
        }).catch(() => {});
      }, 50);
    }
  }

  _checkStopStickRC() {
    const isZero = this.stickRC.roll === 0 && this.stickRC.pitch === 0 && 
                   this.stickRC.throttle === 0 && this.stickRC.yaw === 0;
    if (isZero && this.stickInterval) {
      clearInterval(this.stickInterval);
      this.stickInterval = null;
      fetch('/api/flight/manual_rc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ roll: 0, pitch: 0, throttle: 0, yaw: 0 })
      }).catch(() => {});
    }
  }

  _initKeyboardControls() {
    const activeKeys = new Set();
    let keyInterval = null;

    const handleKeyRC = async () => {
      if (this.isAutonomousEngaged || activeKeys.size === 0) return;

      let roll = 0, pitch = 0, throttle = 0, yaw = 0;
      const speed = 40;

      if (activeKeys.has('KeyW')) throttle += speed;
      if (activeKeys.has('KeyS')) throttle -= speed;
      if (activeKeys.has('KeyA')) yaw -= speed;
      if (activeKeys.has('KeyD')) yaw += speed;
      if (activeKeys.has('ArrowUp')) pitch += speed;
      if (activeKeys.has('ArrowDown')) pitch -= speed;
      if (activeKeys.has('ArrowLeft')) roll -= speed;
      if (activeKeys.has('ArrowRight')) roll += speed;

      try {
        await fetch('/api/flight/manual_rc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ roll, pitch, throttle, yaw })
        });
      } catch (e) {}
    };

    window.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'INPUT') return;

      if (e.code === 'Space') {
        e.preventDefault();
        soundFX.playClick();
        this.takeoff();
        return;
      }
      if (e.code === 'KeyL') {
        soundFX.playClick();
        this.land();
        return;
      }
      if (e.code === 'Escape') {
        soundFX.playWarning();
        this.emergency();
        return;
      }

      if (!activeKeys.has(e.code)) {
        activeKeys.add(e.code);
        if (!keyInterval) {
          keyInterval = setInterval(handleKeyRC, 50);
        }
      }
    });

    window.addEventListener('keyup', (e) => {
      activeKeys.delete(e.code);
      if (activeKeys.size === 0 && keyInterval) {
        clearInterval(keyInterval);
        keyInterval = null;
        fetch('/api/flight/manual_rc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ roll: 0, pitch: 0, throttle: 0, yaw: 0 })
        }).catch(() => {});
      }
    });
  }
}
