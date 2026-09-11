"""
Flight Runs Database & Mission Analytics Engine.
Manages persistent SQLite storage of flight missions, real-time telemetry sampling,
target lock reliability, and time-series performance data.
"""
import os
import time
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional


class FlightDatabase:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "flight_history.db")
        else:
            self.db_path = db_path
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.active_run: Optional[Dict[str, Any]] = None
        self.last_sample_time: float = 0.0

        self._init_db()
        self._seed_demo_runs_if_empty()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates table schema if not existing."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS flight_runs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    target_name TEXT,
                    status TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_sec REAL DEFAULT 0.0,
                    battery_start INTEGER DEFAULT 100,
                    battery_end INTEGER DEFAULT 100,
                    battery_used INTEGER DEFAULT 0,
                    avg_distance_m REAL DEFAULT 0.0,
                    max_distance_m REAL DEFAULT 0.0,
                    avg_speed_mps REAL DEFAULT 0.0,
                    max_speed_mps REAL DEFAULT 0.0,
                    avg_altitude_m REAL DEFAULT 0.0,
                    max_altitude_m REAL DEFAULT 0.0,
                    lock_rate_pct REAL DEFAULT 0.0,
                    snapshots_count INTEGER DEFAULT 0,
                    summary TEXT,
                    telemetry_json TEXT
                )
            """)
            conn.commit()

    def start_run(
        self,
        source: str = "WEBCAM",
        mode: str = "LEAD",
        target_name: str = "Commander Prime",
        battery_start: int = 95,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Initiates a new live mission run."""
        # If a run is already active, finalize it first
        if self.active_run:
            self.end_run(status="COMPLETED", battery_end=battery_start)

        now = datetime.now()
        run_id = f"run_{now.strftime('%Y%m%d_%H%M%S')}_{mode.lower()}"
        run_name = name or f"Mission #{self._get_next_run_number():02d} - {mode} Follow"

        self.active_run = {
            "id": run_id,
            "name": run_name,
            "source": source,
            "mode": mode,
            "target_name": target_name,
            "status": "ACTIVE",
            "start_time": now.isoformat(),
            "end_time": None,
            "duration_sec": 0.0,
            "battery_start": battery_start,
            "battery_end": battery_start,
            "battery_used": 0,
            "avg_distance_m": 0.0,
            "max_distance_m": 0.0,
            "avg_speed_mps": 0.0,
            "max_speed_mps": 0.0,
            "avg_altitude_m": 0.0,
            "max_altitude_m": 0.0,
            "lock_rate_pct": 100.0,
            "snapshots_count": 0,
            "summary": f"Autonomous 3D {mode} Follow engagement tracking {target_name}.",
            "_start_ts": time.time(),
            "_samples": [],
            "_distances": [],
            "_speeds": [],
            "_altitudes": [],
            "_locked_samples": 0,
            "_total_samples": 0
        }
        self.last_sample_time = time.time()
        print(f"[FLIGHT_DB] Mission started: {run_name} ({run_id})")
        return self._active_run_public()

    def sample_active_run(self, telemetry: Dict[str, Any], tracking: Optional[Dict[str, Any]] = None):
        """Samples live telemetry once per second during an active run."""
        if not self.active_run:
            return

        now = time.time()
        # Sample at maximum 1.0Hz
        if now - self.last_sample_time < 0.95:
            return
        self.last_sample_time = now

        duration = round(now - self.active_run["_start_ts"], 1)
        self.active_run["duration_sec"] = duration

        # Extract values
        alt_m = round((telemetry.get("altitude_cm", 0.0) or 0.0) / 100.0, 2)
        battery = int(telemetry.get("battery", 100) or 100)

        dist_m = 0.0
        speed_mps = 0.0
        lock_conf = 0
        is_matched = False

        if tracking and tracking.get("target_detected"):
            dist_m = round(float(tracking.get("estimated_distance_m", 0.0) or 0.0), 2)
            is_matched = bool(tracking.get("target_matched", False))
            lock_conf = int((tracking.get("confidence", 0.0) or 0.0) * 100)
            vel = tracking.get("velocity")
            if vel and isinstance(vel, dict):
                speed_mps = round(float(vel.get("speed_mps", 0.0) or 0.0), 2)

        # Accumulate metrics
        self.active_run["_total_samples"] += 1
        if is_matched or lock_conf > 60:
            self.active_run["_locked_samples"] += 1

        if dist_m > 0:
            self.active_run["_distances"].append(dist_m)
        if speed_mps >= 0:
            self.active_run["_speeds"].append(speed_mps)
        if alt_m >= 0:
            self.active_run["_altitudes"].append(alt_m)

        # Rolling calculations
        if self.active_run["_distances"]:
            self.active_run["avg_distance_m"] = round(sum(self.active_run["_distances"]) / len(self.active_run["_distances"]), 2)
            self.active_run["max_distance_m"] = round(max(self.active_run["_distances"]), 2)

        if self.active_run["_speeds"]:
            self.active_run["avg_speed_mps"] = round(sum(self.active_run["_speeds"]) / len(self.active_run["_speeds"]), 2)
            self.active_run["max_speed_mps"] = round(max(self.active_run["_speeds"]), 2)

        if self.active_run["_altitudes"]:
            self.active_run["avg_altitude_m"] = round(sum(self.active_run["_altitudes"]) / len(self.active_run["_altitudes"]), 2)
            self.active_run["max_altitude_m"] = round(max(self.active_run["_altitudes"]), 2)

        total_s = max(1, self.active_run["_total_samples"])
        self.active_run["lock_rate_pct"] = round((self.active_run["_locked_samples"] / total_s) * 100.0, 1)

        self.active_run["battery_end"] = battery
        self.active_run["battery_used"] = max(0, self.active_run["battery_start"] - battery)

        # Append time-series sample
        sample_point = {
            "t": duration,
            "alt": alt_m,
            "dist": dist_m,
            "spd": speed_mps,
            "lock": lock_conf,
            "bat": battery
        }
        self.active_run["_samples"].append(sample_point)

    def increment_snapshot_count(self):
        """Increments snapshot counter for active run."""
        if self.active_run:
            self.active_run["snapshots_count"] += 1

    def end_run(self, status: str = "COMPLETED", battery_end: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Concludes active flight run and commits to SQLite database."""
        if not self.active_run:
            return None

        run = self.active_run
        now = datetime.now()
        run["end_time"] = now.isoformat()
        run["status"] = status
        run["duration_sec"] = max(1.0, round(time.time() - run["_start_ts"], 1))

        if battery_end is not None:
            run["battery_end"] = int(battery_end)
            run["battery_used"] = max(0, run["battery_start"] - int(battery_end))

        # Generate summary string
        run["summary"] = (
            f"Mission concluded ({status}). Flight Duration: {int(run['duration_sec'])}s. "
            f"Target Lock Rate: {run['lock_rate_pct']}%. Peak Altitude: {run['max_altitude_m']}m. "
            f"Max Velocity: {run['max_speed_mps']}m/s. Snapshots: {run['snapshots_count']}."
        )

        # Prepare for DB storage
        telemetry_str = json.dumps(run["_samples"])

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO flight_runs (
                    id, name, source, mode, target_name, status,
                    start_time, end_time, duration_sec, battery_start, battery_end, battery_used,
                    avg_distance_m, max_distance_m, avg_speed_mps, max_speed_mps,
                    avg_altitude_m, max_altitude_m, lock_rate_pct, snapshots_count,
                    summary, telemetry_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                run["id"], run["name"], run["source"], run["mode"], run["target_name"], run["status"],
                run["start_time"], run["end_time"], run["duration_sec"], run["battery_start"], run["battery_end"], run["battery_used"],
                run["avg_distance_m"], run["max_distance_m"], run["avg_speed_mps"], run["max_speed_mps"],
                run["avg_altitude_m"], run["max_altitude_m"], run["lock_rate_pct"], run["snapshots_count"],
                run["summary"], telemetry_str
            ))
            conn.commit()

        print(f"[FLIGHT_DB] Mission saved: {run['name']} (Duration: {run['duration_sec']}s, Lock: {run['lock_rate_pct']}%)")
        completed = self._active_run_public()
        self.active_run = None
        return completed

    def get_active_run(self) -> Optional[Dict[str, Any]]:
        """Returns live metrics of current in-flight mission."""
        if not self.active_run:
            return None
        self.active_run["duration_sec"] = round(time.time() - self.active_run["_start_ts"], 1)
        return self._active_run_public()

    def _active_run_public(self) -> Dict[str, Any]:
        """Returns sanitized copy of active run for REST JSON response."""
        if not self.active_run:
            return {}
        pub = {k: v for k, v in self.active_run.items() if not k.startswith("_")}
        pub["samples_count"] = len(self.active_run.get("_samples", []))
        return pub

    def list_runs(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Lists historical runs ordered newest first."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, name, source, mode, target_name, status,
                       start_time, end_time, duration_sec, battery_start, battery_end, battery_used,
                       avg_distance_m, max_distance_m, avg_speed_mps, max_speed_mps,
                       avg_altitude_m, max_altitude_m, lock_rate_pct, snapshots_count, summary
                FROM flight_runs
                ORDER BY start_time DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single run with complete telemetry time series."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM flight_runs WHERE id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = dict(row)
            try:
                data["telemetry"] = json.loads(data.get("telemetry_json") or "[]")
            except Exception:
                data["telemetry"] = []
            return data

    def delete_run(self, run_id: str) -> bool:
        """Deletes a run by ID."""
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM flight_runs WHERE id = ?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0

    def clear_runs(self) -> bool:
        """Clears all historical runs."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM flight_runs")
            conn.commit()
            return True

    def get_summary_stats(self) -> Dict[str, Any]:
        """Computes aggregate analytics across all recorded missions."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT 
                    COUNT(*) as total_missions,
                    COALESCE(SUM(duration_sec), 0.0) as total_flight_sec,
                    COALESCE(AVG(lock_rate_pct), 0.0) as avg_lock_rate,
                    COALESCE(MAX(max_speed_mps), 0.0) as peak_speed_mps,
                    COALESCE(MAX(max_altitude_m), 0.0) as peak_altitude_m,
                    COALESCE(SUM(snapshots_count), 0) as total_snapshots
                FROM flight_runs
            """)
            row = cursor.fetchone()
            stats = dict(row) if row else {
                "total_missions": 0,
                "total_flight_sec": 0.0,
                "avg_lock_rate": 0.0,
                "peak_speed_mps": 0.0,
                "peak_altitude_m": 0.0,
                "total_snapshots": 0
            }
            stats["total_flight_sec"] = round(stats["total_flight_sec"], 1)
            stats["avg_lock_rate"] = round(stats["avg_lock_rate"], 1)
            stats["peak_speed_mps"] = round(stats["peak_speed_mps"], 2)
            stats["peak_altitude_m"] = round(stats["peak_altitude_m"], 2)
            return stats

    def _get_next_run_number(self) -> int:
        """Helper to get sequence number for mission naming."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM flight_runs")
            row = cursor.fetchone()
            return (row["cnt"] if row else 0) + 1

    def _seed_demo_runs_if_empty(self):
        """Seeds realistic historical mission runs if database is new."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM flight_runs")
            row = cursor.fetchone()
            if row and row["cnt"] > 0:
                return

        print("[FLIGHT_DB] Initializing new database with seed mission history...")
        demo_runs = [
            {
                "id": "run_20260910_183015_lead",
                "name": "Mission #01 - Lead Follow Verification",
                "source": "WEBCAM",
                "mode": "LEAD",
                "target_name": "Commander Prime",
                "status": "COMPLETED",
                "start_time": "2026-09-10T18:30:15",
                "end_time": "2026-09-10T18:32:45",
                "duration_sec": 150.0,
                "battery_start": 98,
                "battery_end": 94,
                "battery_used": 4,
                "avg_distance_m": 2.05,
                "max_distance_m": 2.40,
                "avg_speed_mps": 0.45,
                "max_speed_mps": 1.10,
                "avg_altitude_m": 1.25,
                "max_altitude_m": 1.35,
                "lock_rate_pct": 97.4,
                "snapshots_count": 2,
                "summary": "Flawless 3D Lead Tracking test. Face + Torso ReID maintained continuous lock without jitter."
            },
            {
                "id": "run_20260910_191500_chase",
                "name": "Mission #02 - Chase Behind Trail",
                "source": "WEBCAM",
                "mode": "CHASE",
                "target_name": "Subject Alpha",
                "status": "LANDED",
                "start_time": "2026-09-10T19:15:00",
                "end_time": "2026-09-10T19:17:10",
                "duration_sec": 130.0,
                "battery_start": 94,
                "battery_end": 89,
                "battery_used": 5,
                "avg_distance_m": 2.10,
                "max_distance_m": 2.85,
                "avg_speed_mps": 0.62,
                "max_speed_mps": 1.45,
                "avg_altitude_m": 1.30,
                "max_altitude_m": 1.50,
                "lock_rate_pct": 94.2,
                "snapshots_count": 1,
                "summary": "Chase mode executed smoothly. Hair and upper torso color signatures handled 180° body turns cleanly."
            },
            {
                "id": "run_20260911_140020_orbit",
                "name": "Mission #03 - 360° Dynamic Orbit",
                "source": "DRONE_WIFI",
                "mode": "ORBIT",
                "target_name": "Commander Prime",
                "status": "COMPLETED",
                "start_time": "2026-09-11T14:00:20",
                "end_time": "2026-09-11T14:03:00",
                "duration_sec": 160.0,
                "battery_start": 89,
                "battery_end": 80,
                "battery_used": 9,
                "avg_distance_m": 2.20,
                "max_distance_m": 2.60,
                "avg_speed_mps": 0.85,
                "max_speed_mps": 1.82,
                "avg_altitude_m": 1.40,
                "max_altitude_m": 1.65,
                "lock_rate_pct": 92.8,
                "snapshots_count": 3,
                "summary": "Full 360° circular orbit around target. Kalman filter maintained smooth yaw and roll trajectory."
            }
        ]

        with self._get_connection() as conn:
            for r in demo_runs:
                # Generate sample curve
                samples = []
                dur = int(r["duration_sec"])
                for sec in range(0, dur, 2):
                    samples.append({
                        "t": sec,
                        "alt": round(r["avg_altitude_m"] + 0.15 * (sec % 10 - 5) / 5.0, 2),
                        "dist": round(r["avg_distance_m"] + 0.2 * (sec % 8 - 4) / 4.0, 2),
                        "spd": round(r["avg_speed_mps"] + 0.3 * (sec % 6 - 3) / 3.0, 2),
                        "lock": int(min(100, max(80, r["lock_rate_pct"] + (sec % 5 - 2)))),
                        "bat": int(r["battery_start"] - (sec / dur) * r["battery_used"])
                    })

                conn.execute("""
                    INSERT INTO flight_runs (
                        id, name, source, mode, target_name, status,
                        start_time, end_time, duration_sec, battery_start, battery_end, battery_used,
                        avg_distance_m, max_distance_m, avg_speed_mps, max_speed_mps,
                        avg_altitude_m, max_altitude_m, lock_rate_pct, snapshots_count,
                        summary, telemetry_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    r["id"], r["name"], r["source"], r["mode"], r["target_name"], r["status"],
                    r["start_time"], r["end_time"], r["duration_sec"], r["battery_start"], r["battery_end"], r["battery_used"],
                    r["avg_distance_m"], r["max_distance_m"], r["avg_speed_mps"], r["max_speed_mps"],
                    r["avg_altitude_m"], r["max_altitude_m"], r["lock_rate_pct"], r["snapshots_count"],
                    r["summary"], json.dumps(samples)
                ))
            conn.commit()
