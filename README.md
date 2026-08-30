# AERO-FOLLOW 3D | Autonomous DJI Ryze Tello Avionics Platform

An aerospace-grade, multi-angle 3D person-following autonomous drone platform built for the **DJI Ryze Tello**, featuring a **$10,000-tier minimalist cyber-tactical HUD dashboard**, **360° Multi-Angle Biometric Registration & 3D Point-Cloud Hologram Preview**, and an intelligent **4-axis PID Follow Engine** (Front, Side, Back, Overhead views).

---

## 🌟 Key Features

### 1. 360° Omni-Angle 3D Person Tracking (Front, Side, Back, Overhead)
Unlike standard trackers that lose target lock as soon as the person turns their back or walks sideways:
- **Facial Biometrics**: 128-dimensional Deep ResNet Face Embeddings for frontal & 45° angle lock.
- **Hair & Scalp Geometry**: Top-of-head color signature for tracking from behind and elevated/overhead angles.
- **Multi-Segment Appearance ReID**: Upper torso (shirt/jacket) and lower body (pants) 3D HSV color histograms for continuous identification even when the face is not visible.
- **Scale-Invariant 3D Anatomical Proportions**: MediaPipe 33-point 3D world landmarks (shoulder-to-hip ratio, torso-to-leg ratio, metric height).

### 2. 3D Scan & Registration Biometric Wizard
- Real-time 3D feature capture from the drone's camera stream.
- **Interactive Three.js 3D Holographic Point Cloud**: Inspect the scanned subject's 3D skeleton and orientation vector.
- Visual biometric summary cards displaying dominant color swatches, facial embedding status, and anatomical ratios.
- One-click **Confirm 3D Target Lock** button.

### 3. $10,000-Tier Luxury Aerospace HUD Dashboard
- Sleek obsidian glassmorphic UI with dynamic 60 FPS HTML5 Canvas HUD overlay (artificial horizon, pitch ladder, compass ribbon, target corner reticles, distance calipers, lock confidence arc gauge).
- 20Hz real-time WebSocket telemetry matrix: Battery %, Altitude (m/cm), Flight Time, Wi-Fi RSSI, Motor Temp (°C), Barometer, Attitude (Pitch/Roll/Yaw), and PID RC velocity output.

### 4. 4-Axis Smooth PID Follow Modes
- **`LEAD (Front)`**: Drone stays ahead of the moving subject at eye/chest level.
- **`CHASE (Back)`**: Drone trails behind the subject (relying on hair + body ReID + 3D pose).
- **`FLANK L / R (Side)`**: Drone tracks from the left or right 90° lateral profile.
- **`ORBIT (360°)`**: Drone dynamically circles around the subject in real-time.

### 5. Dual Flight Engine (Physical Tello & Virtual Simulator)
- Connects directly to the physical **DJI Ryze Tello** via Wi-Fi UDP stream.
- Includes a **Virtual Simulator / Webcam Mode** for instant desk testing and indoors simulation without draining drone battery.

---

## 🚀 Quick Start

### 1. Start Application
Run the one-click launcher from the project root:
```bash
python start.py
```
This starts the FastAPI server and automatically opens the dashboard at:
👉 `http://localhost:8000`

---

## 🎮 Flight Controls & Shortcuts

| Action | Shortcut / UI Button | Description |
|---|---|---|
| **Takeoff** | `Spacebar` / `TAKEOFF` | Autonomous takeoff to 1.2m hover |
| **Land** | `L` / `LAND` | Safe landing procedure |
| **Emergency Stop** | `Escape` / `KILL` | Immediate motor cutoff |
| **Engage 3D Follow** | `ENGAGE 3D FOLLOW` | Activates 4-axis autonomous target tracking |
| **Throttle (Up / Down)**| `W` / `S` | Manual altitude adjust (Manual Mode) |
| **Yaw (Turn Left / Right)** | `A` / `D` | Manual rotation (Manual Mode) |
| **Pitch (Forward / Back)** | `Arrow Up` / `Arrow Down` | Manual forward/backward (Manual Mode) |
| **Roll (Strafe Left / Right)**| `Arrow Left` / `Arrow Right` | Manual lateral strafe (Manual Mode) |

---

## 📡 Connecting to Physical DJI Ryze Tello

1. Turn on your DJI Ryze Tello drone.
2. On your computer, open Wi-Fi settings and connect to the drone's Wi-Fi network (e.g. `TELLO-XXXXXX`).
3. On the dashboard header, click **ENGINE: SIMULATOR** to switch to **DJI TELLO (WI-FI)**.
4. The live 720p 30fps camera feed and real-time battery/altitude telemetry will instantly populate the dashboard!

---

## 📂 Project Architecture

```
w:/Drone_Follow/
├── backend/
│   ├── app.py                   # FastAPI application & WebSocket server
│   ├── config.py                # Vision, PID, and server configurations
│   ├── tello_controller.py      # DJI Tello SDK wrapper with simulator failover
│   ├── vision/
│   │   ├── tracker_3d.py        # 3D Pose + Face + Multi-Segment ReID Engine
│   │   ├── face_reid.py         # Face embedding extraction & matching
│   │   ├── appearance_reid.py   # Multi-segment HSV appearance matcher
│   │   └── pose_estimator.py    # MediaPipe 33-point 3D Landmark processor
│   ├── navigation/
│   │   ├── pid_follower.py      # 4-Axis PID follow controller with safety limits
│   │   └── kalman_tracker.py    # Motion predictor & occlusion filter
│   └── profiles/
│       └── profile_store.py     # Target profile persistence
├── frontend/
│   ├── index.html               # Aerospace HUD entrypoint
│   ├── src/
│   │   ├── main.js              # Application orchestrator
│   │   ├── hud/hud_canvas.js    # 60fps HUD canvas overlay
│   │   ├── three/hologram_view.js # Three.js 3D Hologram point cloud viewport
│   │   ├── registration/scan_modal.js # 3D Scan & Registration wizard
│   │   ├── controls/flight_dock.js # Flight director & cockpit controls
│   │   └── styles/aerospace.css # $10,000-tier glassmorphic styling
├── start.py                     # One-click launcher
└── requirements.txt             # Dependencies
```
