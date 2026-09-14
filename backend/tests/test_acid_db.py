"""
Unit tests for ACID compliance, database integrity checks, online backups,
and self-healing recovery in AERO-FOLLOW 3D.
"""
import os
import time
import shutil
import sqlite3
import tempfile
import unittest
import threading
from backend.database.flight_db import FlightDatabase
from backend.profiles.profile_store import ProfileStore


class TestFlightDatabaseACID(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="drone_test_acid_")
        self.db_path = os.path.join(self.test_dir, "test_flight.db")
        self.db = FlightDatabase(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_1_atomicity_transaction_rollback(self):
        """Atomicity: Test that transaction rolls back completely on error."""
        initial_count = len(self.db.list_runs())

        with self.assertRaises(ValueError):
            with self.db.atomic_transaction() as conn:
                conn.execute("""
                    INSERT INTO flight_runs (
                        id, name, source, mode, target_name, status, start_time
                    ) VALUES ('run_rollback_test', 'Rollback Test', 'WEBCAM', 'LEAD', 'Target', 'ACTIVE', '2026-09-14T00:00:00')
                """)
                # Simulate mid-transaction unhandled failure
                raise ValueError("Simulated failure inside transaction")

        # Verify the record was NOT committed
        runs = self.db.list_runs()
        self.assertEqual(len(runs), initial_count)
        self.assertIsNone(self.db.get_run("run_rollback_test"))

    def test_2_consistency_schema_constraints(self):
        """Consistency: Test table CHECK constraints on status, duration, and battery."""
        health = self.db.verify_integrity()
        self.assertTrue(health["healthy"])
        self.assertEqual(health["integrity"], "ok")

        # Invalid status CHECK constraint violation
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.atomic_transaction() as conn:
                conn.execute("""
                    INSERT INTO flight_runs (
                        id, name, source, mode, target_name, status, start_time
                    ) VALUES ('bad_status_run', 'Bad Status', 'WEBCAM', 'LEAD', 'Target', 'INVALID_STATUS', '2026-09-14T00:00:00')
                """)

        # Negative duration CHECK constraint violation
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.atomic_transaction() as conn:
                conn.execute("""
                    INSERT INTO flight_runs (
                        id, name, source, mode, target_name, status, start_time, duration_sec
                    ) VALUES ('bad_duration_run', 'Bad Duration', 'WEBCAM', 'LEAD', 'Target', 'COMPLETED', '2026-09-14T00:00:00', -15.0)
                """)

        # Battery > 100 CHECK constraint violation
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.atomic_transaction() as conn:
                conn.execute("""
                    INSERT INTO flight_runs (
                        id, name, source, mode, target_name, status, start_time, battery_start
                    ) VALUES ('bad_battery_run', 'Bad Battery', 'WEBCAM', 'LEAD', 'Target', 'COMPLETED', '2026-09-14T00:00:00', 150)
                """)

    def test_3_isolation_wal_mode_and_concurrency(self):
        """Isolation: Test WAL journal mode and non-blocking concurrent thread access."""
        health = self.db.verify_integrity()
        self.assertEqual(health["journal_mode"].lower(), "wal")

        errors = []

        def worker_writer(worker_id):
            try:
                for i in range(5):
                    run_id = f"run_thread_{worker_id}_{i}"
                    self.db.start_run(source="WEBCAM", mode="LEAD", name=f"Thread Run {worker_id}-{i}")
                    time.sleep(0.01)
                    self.db.end_run(status="COMPLETED", battery_end=90, auto_backup=False)
            except Exception as e:
                errors.append(e)

        def worker_reader():
            try:
                for _ in range(15):
                    self.db.list_runs(limit=10)
                    self.db.get_summary_stats()
                    time.sleep(0.005)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker_writer, args=(1,)),
            threading.Thread(target=worker_writer, args=(2,)),
            threading.Thread(target=worker_reader),
            threading.Thread(target=worker_reader),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrency errors occurred: {errors}")

    def test_4_durability_online_backup_and_restore(self):
        """Durability: Test online point-in-time backup and atomic restore."""
        # 1. Start and end a specific run
        self.db.start_run(source="WEBCAM", mode="ORBIT", name="Durability Test Mission")
        self.db.end_run(status="COMPLETED", battery_end=85, auto_backup=False)

        # 2. Create online backup snapshot
        backup_meta = self.db.create_backup("test_durability_snapshot.db")
        self.assertTrue(backup_meta["verified"])
        self.assertTrue(os.path.exists(backup_meta["path"]))
        self.assertGreater(backup_meta["size_bytes"], 0)

        # 3. Clear runs from active database
        self.db.clear_runs()
        self.assertEqual(len(self.db.list_runs()), 0)

        # 4. Restore from backup
        restored = self.db.restore_backup("test_durability_snapshot.db")
        self.assertTrue(restored)

        # 5. Verify data is recovered
        runs = self.db.list_runs()
        self.assertGreater(len(runs), 0)
        self.assertTrue(any("Durability Test Mission" in r["name"] for r in runs))

    def test_5_self_healing_startup_recovery(self):
        """Self-Healing: Test automatic recovery when database file is corrupted on startup."""
        # 1. Create a verified backup
        self.db.create_backup("golden_state.db")

        # 2. Simulate severe database file corruption (overwrite with random garbage)
        with open(self.db_path, "wb") as f:
            f.write(b"CORRUPTED_GARBAGE_HEADER_DATA_1234567890")

        # 3. Instantiate FlightDatabase on the corrupted file
        healed_db = FlightDatabase(db_path=self.db_path)
        health = healed_db.verify_integrity()

        # Database should have self-healed using the verified backup!
        self.assertTrue(health["healthy"], f"Self-healing failed: {health}")
        self.assertEqual(health["integrity"], "ok")


class TestProfileStoreAtomicity(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="drone_test_profiles_")
        self.store = ProfileStore(storage_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_atomic_profile_save_and_backup(self):
        """Test atomic file writing (os.replace) and snapshot backup of profiles."""
        profile = {
            "name": "Special Agent 007",
            "orientation_at_scan": "FRONT",
            "face_detected": True
        }
        pid = self.store.save_profile(profile)
        self.assertTrue(pid)

        # Verify file exists on disk
        saved = self.store.get_profile(pid)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["name"], "Special Agent 007")

        # Test snapshot backup
        backup_info = self.store.backup_profiles()
        self.assertGreaterEqual(backup_info["profiles_backed_up"], 1)
        self.assertTrue(os.path.exists(backup_info["backup_dir"]))


if __name__ == "__main__":
    unittest.main()
