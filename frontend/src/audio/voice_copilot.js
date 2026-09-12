/**
 * Synthetic Aerospace Voice Avionics Copilot ("JARVIS / BETTY").
 * Provides spoken flight announcements, tactical target acquisition callouts,
 * gesture confirmation, and safety warnings using the Web Speech Synthesis API.
 */

class VoiceCopilot {
  constructor() {
    this.synth = window.speechSynthesis || null;
    this.isMuted = false;
    this.selectedVoice = null;
    this.lastSpokenCategoryTime = {};
    this.lastSpokenText = '';

    if (this.synth) {
      this._loadVoices();
      if (this.synth.onvoiceschanged !== undefined) {
        this.synth.onvoiceschanged = () => this._loadVoices();
      }
    }
  }

  _loadVoices() {
    if (!this.synth) return;
    const voices = this.synth.getVoices();
    if (!voices || voices.length === 0) return;

    // Prefer high-quality English natural voices (e.g. Google, Microsoft, Samantha, Daniel)
    const preferred = voices.find(v => 
      v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google') || v.name.includes('Samantha') || v.name.includes('David') || v.name.includes('Daniel'))
    ) || voices.find(v => v.lang.startsWith('en')) || voices[0];

    this.selectedVoice = preferred;
  }

  toggleMute() {
    this.isMuted = !this.isMuted;
    if (this.isMuted && this.synth) {
      this.synth.cancel();
    } else {
      this.speak("Voice copilot active", "SYSTEM", 1.0);
    }
    return this.isMuted;
  }

  speak(text, category = "GENERAL", cooldownSec = 2.5) {
    if (this.isMuted || !this.synth) return;

    const now = Date.now() / 1000.0;
    const lastTime = this.lastSpokenCategoryTime[category] || 0;
    if (now - lastTime < cooldownSec && text === this.lastSpokenText) {
      return;
    }

    this.lastSpokenCategoryTime[category] = now;
    this.lastSpokenText = text;

    try {
      // Avoid queue backlog
      this.synth.cancel();

      const utter = new SpeechSynthesisUtterance(text);
      if (this.selectedVoice) utter.voice = this.selectedVoice;
      utter.rate = 1.08;
      utter.pitch = 0.96;
      utter.volume = 0.90;
      this.synth.speak(utter);
    } catch (e) {
      console.warn("Speech synthesis error:", e);
    }
  }

  // Pre-configured Tactical Avionics Callouts
  targetLocked(name = "Subject Alpha") {
    this.speak(`Target lock confirmed: ${name}`, "TARGET_LOCK", 4.0);
  }

  targetLost() {
    this.speak("Target lost. Predictive search initiated.", "TARGET_LOST", 5.0);
  }

  followEngaged(mode = "LEAD") {
    const modeClean = mode.replace('_', ' ').toLowerCase();
    this.speak(`Autonomous follow engaged. ${modeClean} mode.`, "FOLLOW_STATE", 3.5);
  }

  followDisengaged() {
    this.speak("Autonomous follow suspended. Holding hover.", "FOLLOW_STATE", 3.0);
  }

  gestureRecognized(gestureName) {
    this.speak(`Gesture confirmed: ${gestureName}`, "GESTURE", 3.5);
  }

  quickshotStarted(maneuver) {
    this.speak(`QuickShot ${maneuver} sequence initiated.`, "CINEMATIC", 4.0);
  }

  quickshotCompleted(maneuver) {
    this.speak(`QuickShot ${maneuver} maneuver complete.`, "CINEMATIC", 4.0);
  }

  snapshotCaptured() {
    this.speak("Snapshot captured.", "SNAPSHOT", 3.0);
  }

  takeoff() {
    this.speak("Systems armed. Takeoff initiated.", "FLIGHT", 4.0);
  }

  landing() {
    this.speak("Controlled landing protocol engaged.", "FLIGHT", 4.0);
  }

  proximityWarning() {
    this.speak("Caution: minimum distance boundary.", "SAFETY", 4.0);
  }

  batteryWarning(pct) {
    this.speak(`Warning: battery low. ${pct} percent remaining.`, "BATTERY", 15.0);
  }
}

export const voiceCopilot = new VoiceCopilot();
