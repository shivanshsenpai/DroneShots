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

### 3. Tactical Minimalist HUD Canvas Overlay
- **Artificial Horizon & Pitch Ladder**: Dynamic bank angle arc, roll tilt, and pitch rungs.
- **Velocity Lead Vector**: Proportional predictive vector arrow indicating target direction and real-time metric speed ($m/s$).
- **Trajectory Breadcrumbs**: Real-time dotted motion history path showing recent path of travel.
- **Range & Proximity Safety Arc**: Visual status ring alerting when target is optimal vs within critical proximity.

### 4. Interactive Cockpit & Controls
- **Virtual Dual Flight Sticks (Mode 2)**: On-screen touch/mouse joysticks (Left stick: Throttle/Yaw, Right stick: Pitch/Roll) for intuitive manual override.
- **Live Follow Tuning Sliders**: Adjust target follow distance ($1.0m - 4.0m$) and target altitude ($0.8m - 2.2m$) on the fly with live PID setpoint adjustment.
- **Target Profile Fast-Switcher**: Switch between registered subjects with 1 click without rescanning.
- **Snapshot Capture**: Capture high-res screenshots with timecode and target distance watermarked.
- **Native Web Audio Synthesizer**: Zero-dependency procedural avionics sound effects (Target Lock chirp, Follow Engaged harmonic sweep, Caution beep, Shutter sound) with mute toggle.

### 5. 4-Axis Smooth PID Follow Modes
- **`LEAD (Front)`**: Drone stays ahead of the moving subject at eye/chest level.
- **`CHASE (Back)`**: Drone trails behind the subject (relying on hair + body ReID + 3D pose).
- **`FLANK L / R (Side)`**: Drone tracks from the left or right 90° lateral profile.
- **`ORBIT (360°)`**: Drone dynamically circles around the subject in real-time.
- **Predictive Search Maneuver**: If target is temporarily lost, drone executes a gentle predictive yaw scan in the last known direction before entering stable hover.

### 6. Dual Flight Engine (Physical Tello & Virtual Simulator)
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

