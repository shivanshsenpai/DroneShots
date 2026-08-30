/**
 * Flight Control Dock, Autonomous Director, and Manual Cockpit Engine.
 */

export class FlightControlDock {
  constructor(dockElement, onStateChange) {
    this.dock = dockElement;
    this.onStateChange = onStateChange;

    this.currentMode = 'LEAD';
    this.isAutonomousEngaged = false;
    this.isFlying = false;

    this._bindElements();
    this._bindEvents();
    this._initKeyboardControls();
  }

  _bindElements() {
    this.modeButtons = this.dock.querySelectorAll('.mode-btn');
    this.toggleFollowBtn = this.dock.querySelector('#btn-toggle-follow');
    this.takeoffBtn = this.dock.querySelector('#btn-takeoff');
    this.landBtn = this.dock.querySelector('#btn-land');
    this.emergencyBtn = this.dock.querySelector('#btn-emergency');
  }

  _bindEvents() {
    // Follow Mode buttons
    this.modeButtons.forEach(btn => {
      btn.addEventListener('click', () => {
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
      this.takeoffBtn.addEventListener('click', () => this.takeoff());
    }

    // Land
    if (this.landBtn) {
      this.landBtn.addEventListener('click', () => this.land());
    }

    // Emergency Cutoff
    if (this.emergencyBtn) {
      this.emergencyBtn.addEventListener('click', () => this.emergency());
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
        <span>AUTONOMOUS LOCK: ENGAGED</span>
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

  _initKeyboardControls() {
    const activeKeys = new Set();
    let keyInterval = null;

    const handleKeyRC = async () => {
      if (this.isAutonomousEngaged || activeKeys.size === 0) return;

      let roll = 0, pitch = 0, throttle = 0, yaw = 0;
      const speed = 40;

      // Throttle (W/S)
      if (activeKeys.has('KeyW')) throttle += speed;
      if (activeKeys.has('KeyS')) throttle -= speed;

      // Yaw (A/D)
      if (activeKeys.has('KeyA')) yaw -= speed;
      if (activeKeys.has('KeyD')) yaw += speed;

      // Pitch (ArrowUp / ArrowDown)
      if (activeKeys.has('ArrowUp')) pitch += speed;
      if (activeKeys.has('ArrowDown')) pitch -= speed;

      // Roll (ArrowLeft / ArrowRight)
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
        this.takeoff();
        return;
      }
      if (e.code === 'KeyL') {
        this.land();
        return;
      }
      if (e.code === 'Escape') {
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
        // Send zero stop
        fetch('/api/flight/manual_rc', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ roll: 0, pitch: 0, throttle: 0, yaw: 0 })
        }).catch(() => {});
      }
    });
  }
}
