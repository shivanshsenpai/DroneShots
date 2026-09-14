"""
Flight Runs Database & Mission Analytics Engine.
Manages persistent SQLite storage of flight missions, real-time telemetry sampling,
target lock reliability, and time-series performance data with full ACID compliance,
Write-Ahead Logging (WAL), atomic transactions, online backups, and self-healing recovery.
"""
import os
import time
import json
import shutil
import sqlite3
import threading
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger("FlightDatabase")


class FlightDatabase:
    """
    ACID-compliant SQLite database engine for autonomous flight records.
    
    ACID Guarantees:
    - Atomicity: Every insert, update, or mutation runs inside an explicit atomic transaction
      (BEGIN IMMEDIATE ... COMMIT) with automatic ROLLBACK on failure.
    - Consistency: Enforces strict PRAGMA foreign_keys = ON and table CHECK constraints.
      Self-verifies integrity via PRAGMA integrity_check and automatically recovers from corruption.
    - Isolation: PRAGMA journal_mode = WAL allows concurrent readers without blocking writers.
      Guarded by threading.RLock for complete multi-thread safety across FastAPI and background loops.
    - Durability: Synchronous NORMAL under WAL with automatic online point-in-time snapshot backups.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._lock = threading.RLock()
        
        if db_path is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
            os.makedirs(data_dir, exist_ok=True)
            self.db_path = os.path.join(data_dir, "flight_history.db")
        else:
            self.db_path = db_path
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        self.backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

        self.active_run: Optional[Dict[str, Any]] = None
        self.last_sample_time: float = 0.0

        # Verify integrity and self-heal if corrupted
        self._startup_check_and_heal()
        self._init_db()
        self._seed_demo_runs_if_empty()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Creates an optimized SQLite connection with ACID settings:
        WAL journal mode, 5s busy timeout, foreign keys enabled, synchronous NORMAL.
        """
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    @contextmanager
    def atomic_transaction(self):
        """
        Context manager for an atomic, isolated write transaction.
        Begins an IMMEDIATE transaction, commits on completion, and rolls back on any error.
        """
        with self._lock:
            conn = self._get_connection()
            conn.isolation_level = None  # Autocommit disabled for explicit transaction boundaries
            conn.execute("BEGIN IMMEDIATE;")
            try:
                yield conn
                conn.execute("COMMIT;")
            except Exception as e:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                logger.error(f"[FLIGHT_DB] Transaction rolled back due to error: {e}")
                raise
            finally:
                conn.close()

    def verify_integrity(self) -> Dict[str, Any]:
        """Runs PRAGMA integrity_check and quick_check to verify database health."""
        with self._lock:
            if not os.path.exists(self.db_path):
                return {"healthy": False, "status": "DB file does not exist", "integrity": "missing"}
            try:
                conn = self._get_connection()
                try:
                    cur = conn.execute("PRAGMA integrity_check;")
                    row = cur.fetchone()
                    result = row[0] if row else "unknown"
                    
                    cur_fk = conn.execute("PRAGMA foreign_key_check;")
                    fk_violations = cur_fk.fetchall()
                    
                    cur_jm = conn.execute("PRAGMA journal_mode;")
                    jm = cur_jm.fetchone()[0]

                    is_ok = (result == "ok" and len(fk_violations) == 0)
                    return {
                        "healthy": is_ok,
                        "status": "HEALTHY" if is_ok else "CORRUPTED",
                        "integrity": result,
                        "foreign_key_violations": len(fk_violations),
                        "journal_mode": jm,
                        "db_path": self.db_path,
                        "size_bytes": os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                    }
                finally:
                    conn.close()
            except Exception as e:
                return {
                    "healthy": False,
                    "status": "ERROR",
                    "integrity": str(e),
                    "journal_mode": "unknown",
                    "db_path": self.db_path,
                    "size_bytes": 0
                }

    def _startup_check_and_heal(self):
        """Checks DB integrity on startup. If corrupt or 0 bytes, restores from newest backup."""
        with self._lock:
            if not os.path.exists(self.db_path):
                return

            size = os.path.getsize(self.db_path)
            if size == 0:
                logger.warning("[FLIGHT_DB] Database file is 0 bytes! Attempting recovery from backup...")
                self._recover_from_latest_backup()
                return

            health = self.verify_integrity()
            if not health["healthy"]:
                logger.critical(f"[FLIGHT_DB] Database failed integrity check: {health}. Quarantining and recovering...")
                # Quarantine corrupt DB
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                quarantine_path = f"{self.db_path}.corrupt_{ts}"
                try:
                    shutil.move(self.db_path, quarantine_path)
                    logger.warning(f"[FLIGHT_DB] Quarantined corrupted DB to: {quarantine_path}")
                except Exception as e:
                    logger.error(f"[FLIGHT_DB] Failed to quarantine corrupt DB: {e}")

                self._recover_from_latest_backup()

    def _recover_from_latest_backup(self) -> bool:
        """Finds the newest valid backup in self.backup_dir and restores it."""
        backups = self.list_backups()
        for b in backups:
            if b.get("verified", False):
                bpath = b["path"]
                logger.info(f"[FLIGHT_DB] Auto-recovering database from verified backup: {b['filename']}")
                try:
                    shutil.copy2(bpath, self.db_path)
                    logger.info("[FLIGHT_DB] Successfully restored database from backup.")
                    return True
                except Exception as e:
                    logger.error(f"[FLIGHT_DB] Recovery failed for {bpath}: {e}")
        logger.warning("[FLIGHT_DB] No valid backup found for recovery; a fresh database will be created.")
        return False

    def _init_db(self):
        """Creates table schema with strict ACID constraints and user_version tracking."""
        with self.atomic_transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS flight_runs (
                    id TEXT PRIMARY KEY NOT NULL,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    target_name TEXT,
                    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'COMPLETED', 'LANDED', 'ABORTED', 'SHUTDOWN', 'FAILED')),
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    duration_sec REAL DEFAULT 0.0 CHECK (duration_sec >= 0.0),
                    battery_start INTEGER DEFAULT 100 CHECK (battery_start BETWEEN 0 AND 100),
                    battery_end INTEGER DEFAULT 100 CHECK (battery_end BETWEEN 0 AND 100),
                    battery_used INTEGER DEFAULT 0 CHECK (battery_used >= 0),
                    avg_distance_m REAL DEFAULT 0.0,
                    max_distance_m REAL DEFAULT 0.0,
                    avg_speed_mps REAL DEFAULT 0.0,
                    max_speed_mps REAL DEFAULT 0.0,
                    avg_altitude_m REAL DEFAULT 0.0,
                    max_altitude_m REAL DEFAULT 0.0,
                    lock_rate_pct REAL DEFAULT 0.0 CHECK (lock_rate_pct BETWEEN 0.0 AND 100.0),
                    snapshots_count INTEGER DEFAULT 0 CHECK (snapshots_count >= 0),
                    summary TEXT,
                    telemetry_json TEXT
                )
            """)
            conn.execute("PRAGMA user_version = 2;")

    def start_run(
        self,
        source: str = "WEBCAM",
        mode: str = "LEAD",
        target_name: str = "Commander Prime",
        battery_start: int = 95,
        name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Initiates a new live mission run.
        Accepts battery_start or start_battery alias.
        """
        # Parameter alias support
        if "start_battery" in kwargs:
            battery_start = kwargs["start_battery"]

        battery_start = int(max(0, min(100, battery_start)))

        with self._lock:
            # If a run is already active, cleanly conclude it first
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
            logger.info(f"[FLIGHT_DB] Mission started: {run_name} ({run_id})")
            return self._active_run_public()

    def sample_active_run(self, telemetry: Dict[str, Any], tracking: Optional[Dict[str, Any]] = None):
        """Samples live telemetry once per second during an active run."""
        with self._lock:
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
            battery = max(0, min(100, battery))

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
        with self._lock:
            if self.active_run:
                self.active_run["snapshots_count"] += 1

    def end_run(
        self,
        status: str = "COMPLETED",
        battery_end: Optional[int] = None,
        auto_backup: bool = True,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Concludes active flight run and commits atomically to SQLite database.
        Accepts battery_end or end_battery alias.
        Automatically triggers a point-in-time snapshot backup upon successful commit.
        """
        if "end_battery" in kwargs and battery_end is None:
            battery_end = kwargs["end_battery"]

        # Validate status enum
        valid_statuses = {'ACTIVE', 'COMPLETED', 'LANDED', 'ABORTED', 'SHUTDOWN', 'FAILED'}
        if status.upper() not in valid_statuses:
            status = "COMPLETED"
        else:
            status = status.upper()

        with self._lock:
            if not self.active_run:
                return None

            run = self.active_run
            now = datetime.now()
            run["end_time"] = now.isoformat()
            run["status"] = status
            run["duration_sec"] = max(1.0, round(time.time() - run["_start_ts"], 1))

            if battery_end is not None:
                b_end = int(max(0, min(100, battery_end)))
                run["battery_end"] = b_end
                run["battery_used"] = max(0, run["battery_start"] - b_end)

            # Generate summary string
            run["summary"] = (
                f"Mission concluded ({status}). Flight Duration: {int(run['duration_sec'])}s. "
                f"Target Lock Rate: {run['lock_rate_pct']}%. Peak Altitude: {run['max_altitude_m']}m. "
                f"Max Velocity: {run['max_speed_mps']}m/s. Snapshots: {run['snapshots_count']}."
            )

            # Prepare telemetry JSON
            telemetry_str = json.dumps(run["_samples"])

            # Atomic commit to database
            with self.atomic_transaction() as conn:
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

            logger.info(f"[FLIGHT_DB] Mission committed atomically: {run['name']} (Duration: {run['duration_sec']}s)")
            completed = self._active_run_public()
            self.active_run = None

            # Durability: Trigger automatic snapshot backup on mission conclusion
            if auto_backup:
                try:
                    self.create_backup()
                except Exception as e:
                    logger.error(f"[FLIGHT_DB] Automatic backup after mission failed: {e}")

            return completed

    def get_active_run(self) -> Optional[Dict[str, Any]]:
        """Returns live metrics of current in-flight mission."""
        with self._lock:
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
        """Lists historical runs ordered newest first (Read-only query)."""
        with self._lock:
            conn = self._get_connection()
            try:
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
            finally:
                conn.close()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single run with complete telemetry time series."""
        with self._lock:
            conn = self._get_connection()
            try:
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
            finally:
                conn.close()

    def delete_run(self, run_id: str) -> bool:
        """Deletes a run by ID inside an atomic transaction."""
        with self.atomic_transaction() as conn:
            cursor = conn.execute("DELETE FROM flight_runs WHERE id = ?", (run_id,))
            return cursor.rowcount > 0

    def clear_runs(self) -> bool:
        """Clears all historical runs inside an atomic transaction."""
        with self.atomic_transaction() as conn:
            conn.execute("DELETE FROM flight_runs")
            return True

    def clear_all(self) -> bool:
        """Alias for clear_runs."""
        return self.clear_runs()

    def get_summary_stats(self) -> Dict[str, Any]:
        """Computes aggregate analytics across all recorded missions."""
        with self._lock:
            conn = self._get_connection()
            try:
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
            finally:
                conn.close()

    def _get_next_run_number(self) -> int:
        """Helper to get sequence number for mission naming."""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) as cnt FROM flight_runs")
            row = cursor.fetchone()
            return (row["cnt"] if row else 0) + 1
        finally:
            conn.close()

    # -------------------------------------------------------------
    # Online Backup & Recovery Engine (Durability)
    # -------------------------------------------------------------

    def create_backup(self, backup_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates an atomic point-in-time online snapshot backup using SQLite's native backup API.
        Locks pages incrementally without interrupting readers, verifies the backup integrity,
        and rotates older snapshots.
        """
        with self._lock:
            os.makedirs(self.backup_dir, exist_ok=True)
            now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = backup_name or f"flight_history_backup_{now_str}.db"
            dest_path = os.path.join(self.backup_dir, fname)
            temp_dest = dest_path + ".tmp"

            if os.path.exists(temp_dest):
                try:
                    os.remove(temp_dest)
                except Exception:
                    pass

            src_conn = self._get_connection()
            dest_conn = sqlite3.connect(temp_dest)
            try:
                # Lockstep page-by-page copy
                src_conn.backup(dest_conn, pages=100)
                dest_conn.commit()
            finally:
                dest_conn.close()
                src_conn.close()

            # Verify integrity of generated backup
            chk_conn = sqlite3.connect(temp_dest)
            try:
                cur = chk_conn.execute("PRAGMA quick_check;")
                res = cur.fetchone()[0]
                if res != "ok":
                    raise RuntimeError(f"Backup verification failed: {res}")
            finally:
                chk_conn.close()

            # Atomic swap into final backup location
            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.replace(temp_dest, dest_path)

            # Rotate backups: keep up to 10 latest
            self._rotate_backups(max_backups=10)

            size = os.path.getsize(dest_path)
            logger.info(f"[FLIGHT_DB] Point-in-time backup created: {fname} ({size} bytes)")
            return {
                "filename": fname,
                "path": dest_path,
                "size_bytes": size,
                "created_at": datetime.now().isoformat(),
                "verified": True
            }

    def _rotate_backups(self, max_backups: int = 10):
        """Keeps the newest max_backups files in backup_dir, deleting older ones."""
        try:
            entries = []
            for fname in os.listdir(self.backup_dir):
                if fname.endswith(".db") and not fname.endswith(".tmp"):
                    fpath = os.path.join(self.backup_dir, fname)
                    entries.append((os.path.getmtime(fpath), fpath))
            entries.sort(key=lambda x: x[0], reverse=True)

            if len(entries) > max_backups:
                for _, fpath in entries[max_backups:]:
                    try:
                        os.remove(fpath)
                        logger.info(f"[FLIGHT_DB] Pruned old backup: {os.path.basename(fpath)}")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[FLIGHT_DB] Backup rotation error: {e}")

    def list_backups(self) -> List[Dict[str, Any]]:
        """Lists all existing backup files with metadata and integrity status."""
        backups = []
        if not os.path.exists(self.backup_dir):
            return backups

        for fname in os.listdir(self.backup_dir):
            if fname.endswith(".db") and not fname.endswith(".tmp"):
                fpath = os.path.join(self.backup_dir, fname)
                try:
                    mtime = os.path.getmtime(fpath)
                    size = os.path.getsize(fpath)
                    created_at = datetime.fromtimestamp(mtime).isoformat()
                    
                    # Quick check
                    verified = False
                    try:
                        chk = sqlite3.connect(fpath)
                        cur = chk.execute("PRAGMA quick_check;")
                        verified = (cur.fetchone()[0] == "ok")
                        chk.close()
                    except Exception:
                        verified = False

                    backups.append({
                        "filename": fname,
                        "path": fpath,
                        "size_bytes": size,
                        "created_at": created_at,
                        "verified": verified
                    })
                except Exception:
                    continue

        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

    def restore_backup(self, backup_filename: str) -> bool:
        """
        Restores database from a specified backup snapshot.
        Safely flushes active run, checkpoints WAL, and replaces the database file.
        """
        with self._lock:
            backup_path = os.path.join(self.backup_dir, backup_filename)
            if not os.path.exists(backup_path):
                logger.error(f"[FLIGHT_DB] Restore target backup not found: {backup_path}")
                return False

            # Verify backup integrity first
            chk = sqlite3.connect(backup_path)
            try:
                cur = chk.execute("PRAGMA quick_check;")
                if cur.fetchone()[0] != "ok":
                    logger.error("[FLIGHT_DB] Restore aborted: backup file is not valid.")
                    return False
            finally:
                chk.close()

            # Conclude active run if any
            if self.active_run:
                self.end_run(status="ABORTED", auto_backup=False)

            # Checkpoint and close WAL
            self.checkpoint_wal()

            # Backup current state before replacing
            pre_restore_backup = f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            try:
                self.create_backup(backup_name=pre_restore_backup)
            except Exception:
                pass

            # Copy backup to main db_path
            shutil.copy2(backup_path, self.db_path)
            
            # Clean up residual wal and shm files so restored DB starts clean
            for ext in ["-wal", "-shm"]:
                p = self.db_path + ext
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            logger.info(f"[FLIGHT_DB] Restored database from {backup_filename}")
            return True

    def checkpoint_wal(self) -> Dict[str, Any]:
        """Flushes Write-Ahead Log into the main database file (PRAGMA wal_checkpoint(TRUNCATE))."""
        with self._lock:
            conn = self._get_connection()
            try:
                cur = conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
                row = cur.fetchone()
                return {
                    "busy": row[0] if row else 0,
                    "log": row[1] if row else 0,
                    "checkpointed": row[2] if row else 0
                }
            except Exception as e:
                logger.error(f"[FLIGHT_DB] WAL checkpoint error: {e}")
                return {"error": str(e)}
            finally:
                conn.close()

    def _seed_demo_runs_if_empty(self):
        """Seeds realistic historical mission runs if database is new."""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM flight_runs")
                row = cursor.fetchone()
                if row and row["cnt"] > 0:
                    return
            finally:
                conn.close()

        logger.info("[FLIGHT_DB] Initializing new database with seed mission history...")
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

        with self.atomic_transaction() as conn:
            for r in demo_runs:
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
                    INSERT OR REPLACE INTO flight_runs (
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
