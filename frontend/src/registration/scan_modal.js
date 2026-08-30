/**
 * 3D Target Scan & Biometric Registration Wizard Modal.
 * Implements 360° feature acquisition, 3D point cloud rendering, and confirmation lock.
 */
import { Hologram3DView } from '../three/hologram_view.js';

export class ScanModalWizard {
  constructor(modalElement, onTargetLocked) {
    this.modal = modalElement;
    this.onTargetLocked = onTargetLocked;
    this.hologramView = null;
    this.currentScannedProfile = null;

    this._bindElements();
    this._bindEvents();
  }

  _bindElements() {
    this.closeBtn = this.modal.querySelector('#modal-close-btn');
    this.confirmBtn = this.modal.querySelector('#modal-confirm-lock-btn');
    this.rescanBtn = this.modal.querySelector('#modal-rescan-btn');
    this.threeContainer = this.modal.querySelector('#wizard-three-container');
    
    // Biometric labels
    this.orientLabel = this.modal.querySelector('#bio-orientation');
    this.faceStatusLabel = this.modal.querySelector('#bio-face-status');
    this.proportionsLabel = this.modal.querySelector('#bio-proportions');
    this.heightLabel = this.modal.querySelector('#bio-height');
    this.hairSwatch = this.modal.querySelector('#bio-hair-swatch');
    this.torsoSwatch = this.modal.querySelector('#bio-torso-swatch');
    this.legsSwatch = this.modal.querySelector('#bio-legs-swatch');
    this.nameInput = this.modal.querySelector('#target-name-input');
  }

  _bindEvents() {
    this.closeBtn.addEventListener('click', () => this.close());
    this.rescanBtn.addEventListener('click', () => this.executeScan());
    this.confirmBtn.addEventListener('click', () => this.confirmLock());
  }

  open() {
    this.modal.classList.add('open');
    if (!this.hologramView && this.threeContainer) {
      this.hologramView = new Hologram3DView(this.threeContainer);
    } else if (this.hologramView) {
      setTimeout(() => this.hologramView.resize(), 100);
    }
    this.executeScan();
  }

  close() {
    this.modal.classList.remove('open');
  }

  async executeScan() {
    const subjectName = (this.nameInput && this.nameInput.value.trim()) || 'Commander Prime';
    this.confirmBtn.disabled = true;
    this.confirmBtn.innerText = 'ACQUIRING 3D SCAN...';

    try {
      const response = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: subjectName })
      });

      if (!response.ok) {
        throw new Error('Scan failed. Ensure subject is visible in camera feed.');
      }

      const data = await response.json();
      this.currentScannedProfile = data.profile;
      this._populateBiometrics(data.profile);

      this.confirmBtn.disabled = false;
      this.confirmBtn.innerText = 'CONFIRM 3D TARGET LOCK';
    } catch (err) {
      alert(`3D Scan Alert: ${err.message}`);
      this.confirmBtn.innerText = 'RETRY 3D SCAN';
      this.confirmBtn.disabled = false;
    }
  }

  _populateBiometrics(profile) {
    if (!profile) return;

    // 1. Orientation
    if (this.orientLabel) {
      this.orientLabel.innerText = profile.orientation_at_scan || 'FRONT';
    }

    // 2. Face Biometrics
    if (this.faceStatusLabel) {
      this.faceStatusLabel.innerText = profile.face_detected ? '128D VECTOR ENCODED' : 'BACK / OCCLUDED (REID ACTIVE)';
      this.faceStatusLabel.style.color = '#ffffff';
    }

    // 3. Proportions
    if (this.proportionsLabel && profile.proportions) {
      const s2h = profile.proportions.shoulder_to_hip_ratio?.toFixed(2) || '1.12';
      const t2l = profile.proportions.torso_to_leg_ratio?.toFixed(2) || '0.65';
      this.proportionsLabel.innerText = `S/H: ${s2h} | T/L: ${t2l}`;
    }

    // 4. Height estimate
    if (this.heightLabel && profile.proportions) {
      const h = profile.proportions.total_height_metric?.toFixed(2) || '1.75';
      this.heightLabel.innerText = `${h}m (Est)`;
    }

    // 5. Color Swatches
    if (profile.color_palette) {
      if (this.hairSwatch) this.hairSwatch.style.backgroundColor = profile.color_palette.hair_hex || '#1e293b';
      if (this.torsoSwatch) this.torsoSwatch.style.backgroundColor = profile.color_palette.torso_hex || '#e2e8f0';
      if (this.legsSwatch) this.legsSwatch.style.backgroundColor = profile.color_palette.legs_hex || '#0f172a';
    }

    // 6. Update 3D Holographic view
    if (this.hologramView && profile.landmarks_3d_world) {
      this.hologramView.updateFromLandmarks(profile.landmarks_3d_world, profile.yaw_deg || 0);
    }
  }

  async confirmLock() {
    if (!this.currentScannedProfile) {
      await this.executeScan();
      return;
    }

    const subjectName = (this.nameInput && this.nameInput.value.trim()) || 'Commander Prime';
    this.currentScannedProfile.name = subjectName;

    try {
      const response = await fetch('/api/register_target', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile: this.currentScannedProfile,
          lock_immediately: true
        })
      });

      const res = await response.json();
      this.close();

      if (this.onTargetLocked) {
        this.onTargetLocked(this.currentScannedProfile);
      }
    } catch (err) {
      alert(`Registration error: ${err.message}`);
    }
  }
}
