# AERO-FOLLOW 3D (DroneShots) | Autonomous DJI Ryze Tello Avionics Platform

An aerospace-grade, multi-angle 3D person-following autonomous drone platform built for the **DJI Ryze Tello**, featuring a **minimalist cyber-tactical HUD dashboard**, **360° Multi-Angle Biometric Registration & 3D Point-Cloud Hologram Engine**, and an intelligent **4-axis PID Follow Engine** (Front, Side, Back, Overhead views).

---

## 🌟 Pro Features & Architecture

### 1. 360° Omni-Angle 3D Person Tracking (Front, Side, Back, Overhead)
Unlike standard trackers that lose target lock as soon as the person turns their back or walks away:
- **Facial Biometrics**: 128-dimensional Deep ResNet Face Embeddings for frontal & 45° angle lock.
- **Hair & Scalp Geometry**: Top-of-head color signature for tracking from behind and elevated/overhead angles.
- **Multi-Segment Appearance ReID**: Upper torso (shirt/jacket) and lower body (pants) 3D HSV color histograms for continuous identification even when the face is occluded.
- **Scale-Invariant 3D Anatomical Proportions**: MediaPipe 33-point 3D world landmarks (shoulder-to-hip ratio, torso-to-leg ratio, metric height).
- **Dynamic Profile Learning**: Auto-enriches color signatures during flight as lighting changes, preventing tracking degradation.

### 2. Pro 3D Holographic Viewport (Three.js)
- **Fluid Lerp Interpolation**: 60 FPS silky smooth joint transitions with zero sensor jitter.
- **3D Anatomical Geometry**: Wireframe head volume, torso plane, and 3D Gaze / Forward Orientation Vector.
- **Concentric Metric Floor Grid**: 1m, 2m, and 3m distance rings on the ground with dynamic subject shadow projection ring.

### 3. AI Vision Gesture Control (Hands-Free Pilot)
Pilot and direct the aircraft purely through natural optical gestures:
- ✋ **Open Palm Raised (`HOLD_HOVER`)**: Immediately freezes autonomous pursuit and locks drone into stable stationary hover.
- ✌️ **Peace Sign (`PEACE_SNAP`)**: Triggers a 3-second animated circular countdown ring on the HUD followed by an automated HD snapshot.
- 👍 **Thumbs Up (`THUMBS_LOCK`)**: Re-engages autonomous 3D tracking lock onto the subject.
- 🙅 **Crossed Arms (`CROSSED_LAND`)**: Initiates emergency hands-free aircraft landing sequence.
- 👉 **Pointing Left / Right (`FLANK_LEFT` / `FLANK_RIGHT`)**: Commands the drone to dynamically reposition into a 90° lateral flank perspective.

### 4. Cinematic QuickShot Flight Director
Executes automated, movie-grade aerial choreography with real-time HUD progress tracking, progressive easing, and emergency one-click abort:
- 🎬 **`DRONIE`**: Climbs backward and upward at a 30° incline while keeping the target centered, then returns smoothly to base.
- 🚀 **`ROCKET`**: Ascends vertically with pitch tilted downward to maintain a dynamic top-down lock.
- 🌀 **`HELIX`**: Ascends in an expanding 360° helical spiral while keeping camera locked on the subject.
- 🪃 **`BOOMERANG`**: Sweeps around the target in an elliptical arc, climbing to an apex before returning to initial hover.

### 5. Tactical Radar (HSI) & Predictive Motion HUD
- **Tactical Radar / HSI Mini-Map**: Top-down situational indicator with 1m–4m concentric distance rings, aircraft heading needle, target bearing blip, and red proximity warning zones.
- **Aviation Airspeed & Altitude Tapes**: Left and right vertical scrolling instruments with calibrated tick ladders and real-time metric readings ($m/s$, $m$).
- **Predictive Trajectory & Interception Vector**: Calculates $t+1\text{s}$ and $t+2\text{s}$ future position vectors with diamond target lead indicator (`INTCP T+1s`).
- **Occlusion Ghost-Box**: Renders a predictive dashed bounding box when the subject is temporarily obstructed to prevent loss of tracking.

### 6. Synthetic Voice Avionics Copilot ("JARVIS / BETTY")
Native Web Speech Synthesis providing zero-latency tactical callouts:
- Target lock confirmations ("Target Locked: Commander Prime")
- Gesture acknowledgments ("Hold gesture confirmed. Hovering.")
- Flight state changes ("Takeoff sequence initiated", "Landing engaged")
- Safety alerts ("Warning: Proximity alert", "Battery level critical")
- QuickShot routine progress announcements ("QuickShot Dronie initiated", "Maneuver completed")

### 7. Flight Missions Archive & Telemetry Analytics (SQLite)
- Built-in SQLite flight database (`data/flight_history.db`) recording mission runs, durations, battery consumption, average/peak speeds, altitude profiles, and lock rates.
- Interactive historical modal with responsive Chart.js velocity/altitude scrubbers and telemetry inspections.

### 8. Interactive Cockpit & Controls
- **Virtual Dual Flight Sticks (Mode 2)**: On-screen touch/mouse joysticks (Left stick: Throttle/Yaw, Right stick: Pitch/Roll) for intuitive manual override.
- **Live Follow Tuning Sliders**: Adjust target follow distance ($1.0m - 4.0m$) and target altitude ($0.8m - 2.2m$) on the fly with live PID setpoint adjustment.
- **Target Profile Fast-Switcher**: Switch between registered subjects with 1 click without rescanning.
- **Snapshot Capture**: Capture high-res screenshots with timecode and target distance watermarked.
- **Native Web Audio Synthesizer**: Zero-dependency procedural avionics sound effects (Target Lock chirp, Follow Engaged harmonic sweep, Caution beep, Shutter sound) with mute toggle.

### 9. 4-Axis Smooth PID Follow Modes
- **`LEAD (Front)`**: Drone stays ahead of the moving subject at eye/chest level.
- **`CHASE (Back)`**: Drone trails behind the subject (relying on hair + body ReID + 3D pose).
- **`FLANK L / R (Side)`**: Drone tracks from the left or right 90° lateral profile.
- **`ORBIT (360°)`**: Drone dynamically circles around the subject in real-time.
- **Predictive Search Maneuver**: If target is temporarily lost, drone executes a gentle predictive yaw scan in the last known direction before entering stable hover.

### 10. Dual Flight Engine (Physical Tello & Virtual Simulator)
- Direct Wi-Fi UDP stream & RC control for the physical **DJI Ryze Tello**.
- Built-in **Virtual Drone Simulator / Webcam Mode** for instant indoor desk testing without draining drone battery.

---

## 🚀 Quick Start

Run the one-click launcher from the project root:
```bash
python start.py
```
This starts the FastAPI server and automatically opens the dashboard at:
👉 **`http://localhost:8000`**

---

## 🎮 Controls & Shortcuts

| Action | Shortcut / UI Button | Description |
|---|---|---|
| **Takeoff** | `Spacebar` / `TAKEOFF` | Autonomous takeoff to 1.2m hover |
| **Land** | `L` / `LAND` | Safe landing procedure |
| **Emergency Stop** | `Escape` / `KILL` | Immediate motor cutoff |
| **Engage 3D Follow** | `ENGAGE 3D FOLLOW` | Activates 4-axis autonomous target tracking |
| **Virtual Flight Sticks** | `STICKS` button | Toggle Mode 2 on-screen dual joysticks |
| **Capture Snapshot** | Camera Icon | Captures watermarked HD photo to `data/snapshots/` |
| **Toggle Audio** | Speaker Icon | Mute / Unmute procedural avionics sound FX |
| **Throttle (Up / Down)**| `W` / `S` | Manual altitude adjust (Manual Mode) |
| **Yaw (Turn Left / Right)** | `A` / `D` | Manual rotation (Manual Mode) |
| **Pitch (Forward / Back)** | `Arrow Up` / `Arrow Down` | Manual forward/backward (Manual Mode) |
| **Roll (Strafe Left / Right)**| `Arrow Left` / `Arrow Right` | Manual lateral strafe (Manual Mode) |

---

## 📡 Dual-Source Mode: System Webcam vs. Physical DJI Tello

The dashboard features an explicit **Avionics Source Selector** in the top header:

### Option 1: System Webcam Mode (Desk Simulation)
- **Active by default**: Allows complete end-to-end testing of 3D facial/pose scanning, biometric registration, 4-axis PID tracking, virtual flight physics, and telemetry matrix directly from your desk without needing the drone powered on or disconnecting your PC from home/office Wi-Fi.
- **Multiple Camera Support**: Use the camera dropdown in the top bar to switch between your integrated webcam and secondary USB/external webcams seamlessly.

### Option 2: Physical DJI Ryze Tello (Wi-Fi)
1. Turn ON your DJI Ryze Tello drone (wait ~10s for the status LED to flash).
2. On your computer, open your Wi-Fi settings and connect to **`TELLO-XXXXXX`**.
3. In the top bar of the dashboard, click **`DJI TELLO (WI-FI)`**.
4. The system automatically connects via high-speed UDP, initialises the 720p 30fps hardware stream, and binds real-time battery and flight telemetry.
5. *Safety Guard*: If your PC is not connected to the drone's Wi-Fi, the dashboard will display a connection guide modal with troubleshooting instructions and let you instantly continue testing in Webcam Mode with a single click.

---

## 👨‍💻 Author & Contact

- **Created & Developed by**: **Shivansh Sharma**
- **Email**: [shaivanshsharma6000@gmail.com](mailto:shaivanshsharma6000@gmail.com)
- **GitHub**: [@shivanshsenpai](https://github.com/shivanshsenpai)
- **Repository**: [https://github.com/shivanshsenpai/DroneShots](https://github.com/shivanshsenpai/DroneShots)

