"""
One-Click Launcher for DJI Ryze Tello 3D Autonomous Follow System.
Launches FastAPI backend server and opens the $10,000-tier Aerospace HUD Dashboard.
"""
import os
import sys
import time
import webbrowser
import uvicorn

if __name__ == "__main__":
    print("=" * 70)
    print("  AERO-FOLLOW 3D | DJI RYZE TELLO AUTONOMOUS AVIONICS SYSTEM")
    print("  360° Multi-Angle Person Follow & Aerospace HUD Dashboard")
    print("=" * 70)
    print("\n[+] Starting FastAPI & Real-Time Telemetry WebSockets...")
    print("[+] Launching dashboard on http://localhost:8000\n")

    # Open browser automatically after a short delay
    def open_dashboard():
        time.sleep(1.2)
        webbrowser.open("http://localhost:8000")

    import threading
    threading.Thread(target=open_dashboard, daemon=True).start()

    # Run Uvicorn server
    uvicorn.run("backend.app:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
