/**
 * Mission History & Telemetry Analytics Modal.
 * Renders flight session archives, aggregate summary metrics, and an interactive
 * HTML5 Canvas multi-curve time-series telemetry chart.
 */
import { soundFX } from '../audio/sound_fx.js';

export class RunsModal {
  constructor(modalEl, onRunAction = null) {
    this.modalEl = modalEl;
    this.onRunAction = onRunAction;
    this.runs = [];
    this.summary = null;
    this.selectedRun = null;
    this.chartMetric = 'ALL'; // 'ALL', 'ALT', 'DIST', 'SPEED'

    this.chartCanvas = null;
    this.chartCtx = null;

    this._initDOMElements();
  }

  _initDOMElements() {
    this.closeBtn = this.modalEl.querySelector('#modal-runs-close-btn');
    this.runsListEl = this.modalEl.querySelector('#runs-history-list');
    this.summaryTotalMissions = this.modalEl.querySelector('#summary-total-missions');
    this.summaryTotalAirtime = this.modalEl.querySelector('#summary-total-airtime');
    this.summaryAvgLock = this.modalEl.querySelector('#summary-avg-lock');
    this.summaryPeakSpeed = this.modalEl.querySelector('#summary-peak-speed');
    this.btnClearAll = this.modalEl.querySelector('#btn-clear-runs-history');
    this.btnRefresh = this.modalEl.querySelector('#btn-refresh-runs');
    this.chartCanvas = this.modalEl.querySelector('#run-telemetry-chart');
    if (this.chartCanvas) {
      this.chartCtx = this.chartCanvas.getContext('2d');
    }

    this.detailTitle = this.modalEl.querySelector('#run-detail-title');
    this.detailMeta = this.modalEl.querySelector('#run-detail-meta');
    this.detailMetrics = this.modalEl.querySelector('#run-detail-metrics');

    // Chart metric filter buttons
    const filterBtns = this.modalEl.querySelectorAll('.chart-filter-btn');
    filterBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        filterBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.chartMetric = btn.dataset.metric || 'ALL';
        soundFX.playClick();
        if (this.selectedRun) {
          this._renderChart(this.selectedRun);
        }
      });
    });

    if (this.closeBtn) {
      this.closeBtn.addEventListener('click', () => this.close());
    }

    if (this.btnRefresh) {
      this.btnRefresh.addEventListener('click', () => {
        soundFX.playClick();
        this.loadRuns();
      });
    }

    if (this.btnClearAll) {
      this.btnClearAll.addEventListener('click', async () => {
        soundFX.playWarning();
        if (confirm('Are you sure you want to clear all historical flight mission logs?')) {
          await this._clearAllRuns();
        }
      });
    }

    // Close on backdrop click outside card
    this.modalEl.addEventListener('click', (e) => {
      if (e.target === this.modalEl) {
        this.close();
      }
    });

    // Handle ESC key
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this.modalEl.classList.contains('open')) {
        this.close();
      }
    });

    // Chart interactive hover tooltip
    if (this.chartCanvas) {
      this.chartCanvas.addEventListener('mousemove', (e) => this._onChartMouseMove(e));
      this.chartCanvas.addEventListener('mouseleave', () => this._onChartMouseLeave());
    }
  }

  open() {
    this.modalEl.classList.add('open');
    soundFX.playClick();
    this.loadRuns();
  }

  close() {
    this.modalEl.classList.remove('open');
    soundFX.playClick();
  }

  async loadRuns() {
    try {
      const res = await fetch('/api/db/runs');
      if (!res.ok) return;
      const data = await res.json();
      this.runs = data.runs || [];
      this.summary = data.summary || {};
      this.activeRun = data.active_run || null;

      this._renderSummaryCards();
      this._renderRunsList();

      // Auto-select first or active run
      if (this.runs.length > 0) {
        const targetRun = this.runs[0];
        const targetId = targetRun.id || targetRun.run_id;
        this.selectRun(targetId);
      } else {
        this._renderEmptyDetail();
      }

      // Update external badges
      this._updateExternalBadges();
    } catch (e) {
      console.error('Failed to load mission runs:', e);
    }
  }

  _renderSummaryCards() {
    if (!this.summary) return;

    if (this.summaryTotalMissions) {
      this.summaryTotalMissions.innerText = this.summary.total_missions ?? this.summary.total_runs ?? 0;
    }

    if (this.summaryTotalAirtime) {
      const totalSec = Math.round(this.summary.total_flight_sec ?? this.summary.total_flight_time_sec ?? 0);
      const m = Math.floor(totalSec / 60);
      const s = totalSec % 60;
      this.summaryTotalAirtime.innerText = `${m}m ${s}s`;
    }

    if (this.summaryAvgLock) {
      const lockPct = Number(this.summary.avg_lock_rate ?? this.summary.avg_target_lock_pct ?? 0).toFixed(1);
      this.summaryAvgLock.innerText = `${lockPct}%`;
    }

    if (this.summaryPeakSpeed) {
      const peakSpd = Number(this.summary.peak_speed_mps ?? 0).toFixed(1);
      this.summaryPeakSpeed.innerText = `${peakSpd} m/s`;
    }
  }

  _renderRunsList() {
    if (!this.runsListEl) return;
    this.runsListEl.innerHTML = '';

    if (this.runs.length === 0) {
      this.runsListEl.innerHTML = `
        <div class="runs-empty-state">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>
          <div>NO MISSION FLIGHT LOGS YET</div>
          <span style="font-size:10px; color:var(--text-muted);">Takeoff or toggle Autonomous Follow to record flight sessions.</span>
        </div>
      `;
      return;
    }

    this.runs.forEach((run) => {
      const runId = run.id || run.run_id || 'unknown';
      const isSelected = this.selectedRun && (this.selectedRun.id === runId || this.selectedRun.run_id === runId);

      const itemEl = document.createElement('div');
      itemEl.className = `run-item-card ${isSelected ? 'active' : ''}`;
      itemEl.dataset.runId = runId;

      const durSec = Math.round(run.duration_sec || 0);
      const mins = Math.floor(durSec / 60);
      const secs = durSec % 60;
      const durStr = `${mins}:${String(secs).padStart(2, '0')}`;

      const dateStr = run.start_time ? new Date(run.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : 'UNKNOWN';
      const statusClass = run.status === 'COMPLETED' ? 'badge-success' : run.status === 'RECORDING' ? 'badge-recording' : run.status === 'EMERGENCY' ? 'badge-danger' : 'badge-neutral';

      const lockPct = Math.round(run.lock_rate_pct ?? run.target_lock_rate_pct ?? 0);
      const snaps = run.snapshots_count ?? run.snapshots_taken ?? 0;

      itemEl.innerHTML = `
        <div class="run-item-header">
          <span class="run-item-id">#${runId.slice(-6)}</span>
          <span class="run-status-badge ${statusClass}">${run.status}</span>
        </div>
        <div class="run-item-body">
          <div class="run-item-detail">
            <span class="run-label">MODE / SRC:</span>
            <span class="run-val">${run.mode} // ${run.source === 'DRONE_WIFI' ? 'TELLO' : 'WEBCAM'}</span>
          </div>
          <div class="run-item-detail">
            <span class="run-label">TIME / DUR:</span>
            <span class="run-val">${dateStr} (${durStr})</span>
          </div>
          <div class="run-item-detail">
            <span class="run-label">LOCK RATE:</span>
            <div class="run-lock-progress-wrap">
              <div class="run-lock-progress-bar" style="width: ${lockPct}%"></div>
              <span class="run-val" style="margin-left:6px; font-size:10px;">${lockPct}%</span>
            </div>
          </div>
        </div>
        <div class="run-item-footer">
          <span style="font-size:10px; color:var(--text-muted);">${snaps} Snaps</span>
          <button class="btn-delete-run" title="Delete mission record" data-id="${runId}">✕</button>
        </div>
      `;

      // Select click
      itemEl.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-delete-run')) return;
        soundFX.playClick();
        this.selectRun(runId);
      });

      // Delete click
      const delBtn = itemEl.querySelector('.btn-delete-run');
      if (delBtn) {
        delBtn.addEventListener('click', async (e) => {
          e.stopPropagation();
          soundFX.playClick();
          await this._deleteRun(runId);
        });
      }

      this.runsListEl.appendChild(itemEl);
    });
  }

  async selectRun(runId) {
    try {
      const res = await fetch(`/api/db/runs/${runId}`);
      if (!res.ok) return;
      const run = await res.json();
      this.selectedRun = run;

      // Update active styling in list
      const items = this.modalEl.querySelectorAll('.run-item-card');
      items.forEach(el => {
        if (el.dataset.runId === runId) el.classList.add('active');
        else el.classList.remove('active');
      });

      this._renderRunDetail(run);
      this._renderChart(run);
    } catch (e) {
      console.error('Failed to select run:', e);
    }
  }

  _renderRunDetail(run) {
    const runId = run.id || run.run_id || 'UNKNOWN';

    if (this.detailTitle) {
      this.detailTitle.innerText = run.name || `MISSION ${runId}`;
    }

    if (this.detailMeta) {
      const startTime = run.start_time ? new Date(run.start_time).toLocaleString() : 'N/A';
      this.detailMeta.innerHTML = `
        <span>SOURCE: <strong style="color:#fff;">${run.source}</strong></span>
        <span>MODE: <strong style="color:#fff;">${run.mode}</strong></span>
        <span>STARTED: <strong style="color:#fff;">${startTime}</strong></span>
        <span>STATUS: <strong style="color:#fff;">${run.status}</strong></span>
      `;
    }

    if (this.detailMetrics) {
      const durSec = Math.round(run.duration_sec || 0);
      const mins = Math.floor(durSec / 60);
      const secs = durSec % 60;
      const durStr = `${mins}m ${secs}s`;

      const maxAlt = run.max_altitude_m !== undefined ? run.max_altitude_m : ((run.max_altitude_cm || 0) / 100.0);
      const lockRate = Number(run.lock_rate_pct ?? run.target_lock_rate_pct ?? 0).toFixed(1);
      const batUsed = run.battery_used ?? (run.start_battery ? (run.start_battery - (run.end_battery || run.start_battery)) : 0);

      this.detailMetrics.innerHTML = `
        <div class="run-stat-card">
          <span class="stat-card-label">DURATION</span>
          <span class="stat-card-val">${durStr}</span>
        </div>
        <div class="run-stat-card">
          <span class="stat-card-label">TARGET LOCK RATE</span>
          <span class="stat-card-val">${lockRate}%</span>
        </div>
        <div class="run-stat-card">
          <span class="stat-card-label">MAX ALTITUDE</span>
          <span class="stat-card-val">${Number(maxAlt).toFixed(2)} m</span>
        </div>
        <div class="run-stat-card">
          <span class="stat-card-label">MAX AIRSPEED</span>
          <span class="stat-card-val">${Number(run.max_speed_mps || 0).toFixed(1)} m/s</span>
        </div>
        <div class="run-stat-card">
          <span class="stat-card-label">AVG DISTANCE</span>
          <span class="stat-card-val">${Number(run.avg_distance_m || 0).toFixed(2)} m</span>
        </div>
        <div class="run-stat-card">
          <span class="stat-card-label">BATTERY CONSUMED</span>
          <span class="stat-card-val">${batUsed}%</span>
        </div>
      `;
    }
  }

  _renderEmptyDetail() {
    if (this.detailTitle) this.detailTitle.innerText = 'MISSION TELEMETRY ANALYTICS';
    if (this.detailMeta) this.detailMeta.innerHTML = '<span>Select a flight mission to view detailed avionics.</span>';
    if (this.detailMetrics) this.detailMetrics.innerHTML = '';
    if (this.chartCtx && this.chartCanvas) {
      this.chartCtx.clearRect(0, 0, this.chartCanvas.width, this.chartCanvas.height);
      this._drawEmptyChart('NO RUN SELECTED');
    }
  }

  _renderChart(run) {
    if (!this.chartCanvas || !this.chartCtx) return;
    const ctx = this.chartCtx;
    const w = this.chartCanvas.width;
    const h = this.chartCanvas.height;

    ctx.clearRect(0, 0, w, h);

    const rawSamples = run.telemetry || run.samples || [];
    if (rawSamples.length < 2) {
      this._drawEmptyChart('INSUFFICIENT TELEMETRY SAMPLES RECORDED FOR THIS RUN');
      return;
    }

    // Normalize sample objects
    const samples = rawSamples.map(s => ({
      t: Number(s.t !== undefined ? s.t : (s.rel_time_sec || 0)),
      alt: Number(s.alt !== undefined ? s.alt : ((s.alt_cm || 0) / 100.0)),
      dist: Number(s.dist !== undefined ? s.dist : (s.dist_m || 0)),
      spd: Number(s.spd !== undefined ? s.spd : (s.spd_mps || 0)),
      lock: Boolean(s.lock !== undefined ? s.lock > 50 : (s.locked || false)),
      bat: Number(s.bat !== undefined ? s.bat : 100)
    }));

    const padding = { top: 25, right: 30, bottom: 30, left: 45 };
    const chartW = w - padding.left - padding.right;
    const chartH = h - padding.top - padding.bottom;

    // Background Grid lines
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(w - padding.right, y);
      ctx.stroke();
    }
    for (let i = 0; i <= 5; i++) {
      const x = padding.left + (chartW / 5) * i;
      ctx.beginPath();
      ctx.moveTo(x, padding.top);
      ctx.lineTo(x, h - padding.bottom);
      ctx.stroke();
    }

    // Time domain
    const totalTime = Math.max(1, samples[samples.length - 1].t || 1);

    // Compute scales
    const maxAlt = Math.max(2.5, ...samples.map(s => s.alt));
    const maxDist = Math.max(4.0, ...samples.map(s => s.dist));
    const maxSpd = Math.max(2.0, ...samples.map(s => s.spd));

    // Time axis labels
    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    for (let i = 0; i <= 5; i++) {
      const t = (totalTime / 5) * i;
      const x = padding.left + (chartW / 5) * i;
      ctx.fillText(`${t.toFixed(0)}s`, x, h - 12);
    }

    // Y Axis label
    ctx.textAlign = 'right';
    ctx.fillText('SCALE', padding.left - 8, padding.top - 10);

    // Draw lines based on active metric filter
    if (this.chartMetric === 'ALL' || this.chartMetric === 'ALT') {
      this._drawLine(samples, s => s.alt, maxAlt, '#ffffff', totalTime, chartW, chartH, padding);
    }
    if (this.chartMetric === 'ALL' || this.chartMetric === 'DIST') {
      this._drawLine(samples, s => s.dist, maxDist, 'rgba(255, 255, 255, 0.55)', totalTime, chartW, chartH, padding, [4, 4]);
    }
    if (this.chartMetric === 'ALL' || this.chartMetric === 'SPEED') {
      this._drawLine(samples, s => s.spd, maxSpd, 'rgba(255, 255, 255, 0.85)', totalTime, chartW, chartH, padding);
    }

    // Target lock indicator points (small white pings where target was matched)
    samples.forEach(s => {
      if (s.lock) {
        const x = padding.left + (s.t / totalTime) * chartW;
        ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.fillRect(x - 1, h - padding.bottom - 4, 2, 4);
      }
    });

    // Legend
    this._drawLegend(padding);
  }

  _drawLine(samples, valFn, maxVal, color, totalTime, chartW, chartH, padding, dash = []) {
    const ctx = this.chartCtx;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.8;
    ctx.setLineDash(dash);
    ctx.beginPath();

    samples.forEach((s, idx) => {
      const x = padding.left + (s.t / totalTime) * chartW;
      const val = Math.max(0, valFn(s));
      const y = padding.top + chartH - (val / maxVal) * chartH;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.stroke();
    ctx.restore();
  }

  _drawLegend(padding) {
    const ctx = this.chartCtx;
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.textAlign = 'left';

    let curX = padding.left;
    const y = 14;

    if (this.chartMetric === 'ALL' || this.chartMetric === 'ALT') {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(curX, y - 7, 12, 3);
      ctx.fillText('ALTITUDE (m)', curX + 16, y);
      curX += 120;
    }

    if (this.chartMetric === 'ALL' || this.chartMetric === 'DIST') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.55)';
      ctx.fillRect(curX, y - 7, 12, 3);
      ctx.fillText('TARGET DIST (m)', curX + 16, y);
      curX += 135;
    }

    if (this.chartMetric === 'ALL' || this.chartMetric === 'SPEED') {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.85)';
      ctx.fillRect(curX, y - 7, 12, 3);
      ctx.fillText('AIRSPEED (m/s)', curX + 16, y);
      curX += 130;
    }
  }

  _drawEmptyChart(message) {
    const ctx = this.chartCtx;
    const w = this.chartCanvas.width;
    const h = this.chartCanvas.height;
    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.font = '11px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText(message, w / 2, h / 2);
  }

  _onChartMouseMove(e) {
    const rawSamples = this.selectedRun ? (this.selectedRun.telemetry || this.selectedRun.samples || []) : [];
    if (rawSamples.length < 2) return;

    const rect = this.chartCanvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const padding = { top: 25, right: 30, bottom: 30, left: 45 };
    const chartW = this.chartCanvas.width - padding.left - padding.right;

    if (mouseX < padding.left || mouseX > this.chartCanvas.width - padding.right) return;

    const samples = rawSamples.map(s => ({
      t: Number(s.t !== undefined ? s.t : (s.rel_time_sec || 0)),
      alt: Number(s.alt !== undefined ? s.alt : ((s.alt_cm || 0) / 100.0)),
      dist: Number(s.dist !== undefined ? s.dist : (s.dist_m || 0)),
      spd: Number(s.spd !== undefined ? s.spd : (s.spd_mps || 0)),
      lock: Boolean(s.lock !== undefined ? s.lock > 50 : (s.locked || false)),
      bat: Number(s.bat !== undefined ? s.bat : 100)
    }));

    const totalTime = Math.max(1, samples[samples.length - 1].t || 1);
    const hoverTime = ((mouseX - padding.left) / chartW) * totalTime;

    // Find closest sample
    let closest = samples[0];
    let minDiff = Math.abs(closest.t - hoverTime);
    for (let i = 1; i < samples.length; i++) {
      const diff = Math.abs(samples[i].t - hoverTime);
      if (diff < minDiff) {
        minDiff = diff;
        closest = samples[i];
      }
    }

    // Redraw and overlay crosshair scrubber
    this._renderChart(this.selectedRun);

    const ctx = this.chartCtx;
    const x = padding.left + (closest.t / totalTime) * chartW;

    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
    ctx.setLineDash([2, 2]);
    ctx.beginPath();
    ctx.moveTo(x, padding.top);
    ctx.lineTo(x, this.chartCanvas.height - padding.bottom);
    ctx.stroke();

    // Readout box
    const altM = closest.alt.toFixed(2);
    const distM = closest.dist.toFixed(2);
    const spdM = closest.spd.toFixed(1);
    const tooltipText = `T+${closest.t.toFixed(1)}s | ALT: ${altM}m | DIST: ${distM}m | SPD: ${spdM}m/s`;

    ctx.fillStyle = '#090a0c';
    ctx.fillRect(x - 100, padding.top - 20, 200, 18);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.strokeRect(x - 100, padding.top - 20, 200, 18);

    ctx.fillStyle = '#ffffff';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText(tooltipText, x, padding.top - 8);
    ctx.restore();
  }

  _onChartMouseLeave() {
    if (this.selectedRun) {
      this._renderChart(this.selectedRun);
    }
  }

  async _deleteRun(runId) {
    try {
      const res = await fetch(`/api/db/runs/${runId}`, { method: 'DELETE' });
      if (res.ok) {
        this.loadRuns();
      }
    } catch (e) {
      console.error('Failed to delete run:', e);
    }
  }

  async _clearAllRuns() {
    try {
      const res = await fetch('/api/db/runs/clear', { method: 'POST' });
      if (res.ok) {
        this.loadRuns();
      }
    } catch (e) {
      console.error('Failed to clear runs:', e);
    }
  }

  _updateExternalBadges() {
    const badgeEl = document.getElementById('header-mission-badge');
    if (badgeEl && this.summary) {
      badgeEl.innerText = this.summary.total_missions ?? this.summary.total_runs ?? 0;
    }
  }

  updateActiveRun(activeRun) {
    this.activeRun = activeRun;
    const pill = document.getElementById('live-mission-pill');
    const txt = document.getElementById('live-mission-text');

    if (activeRun && (activeRun.id || activeRun.run_id)) {
      if (pill) pill.style.display = 'inline-flex';
      if (txt) {
        const durSec = Math.round(activeRun.duration_sec || 0);
        const mins = String(Math.floor(durSec / 60)).padStart(2, '0');
        const secs = String(durSec % 60).padStart(2, '0');
        txt.innerText = `REC ${mins}:${secs}`;
      }
    } else {
      if (pill) pill.style.display = 'none';
    }
  }
}
