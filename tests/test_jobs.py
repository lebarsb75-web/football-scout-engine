import tempfile
import unittest
from pathlib import Path

from api.jobs import JobStore


class JobStoreTests(unittest.TestCase):
    def make_store(self, directory: str):
        return JobStore(str(Path(directory) / "jobs.sqlite3"))

    def test_put_get_and_public_dict(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            job = store.put(
                job_id="ana_test123",
                provider="runpod",
                provider_job_id="provider-secret-id",
                status="submitted",
                cost_estimate={"ready": True, "estimated_cost_usd": 0.12},
                request_summary={"video_duration_seconds": 120},
            )

            loaded = store.get("ana_test123")
            self.assertEqual(loaded.provider_job_id, "provider-secret-id")
            self.assertEqual(loaded.status, "submitted")
            self.assertEqual(loaded.cost_estimate["estimated_cost_usd"], 0.12)

            public = store.public_dict(job)
            self.assertEqual(public["job_id"], "ana_test123")
            self.assertNotIn("provider_job_id", public)
            self.assertFalse(public["has_result"])

    def test_list_recent_is_newest_first(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.put(
                job_id="ana_one",
                provider="runpod",
                provider_job_id="r1",
                status="submitted",
                cost_estimate={},
                request_summary={},
            )
            store.put(
                job_id="ana_two",
                provider="runpod",
                provider_job_id="r2",
                status="submitted",
                cost_estimate={},
                request_summary={},
            )
            jobs = store.list_recent()
            self.assertEqual([job.job_id for job in jobs][:2], ["ana_two", "ana_one"])

    def test_update_status(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.put(
                job_id="ana_status",
                provider="runpod",
                provider_job_id="r3",
                status="submitted",
                cost_estimate={},
                request_summary={},
            )
            updated = store.update_status("ana_status", "completed")
            self.assertEqual(updated.status, "completed")
            self.assertGreaterEqual(updated.updated_at, updated.created_at)

    def test_unknown_job_raises_key_error(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            with self.assertRaises(KeyError):
                store.get("missing")

    def test_provider_result_is_persisted_but_hidden_from_public_job(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            store.put(
                job_id="ana_result",
                provider="runpod",
                provider_job_id="r4",
                status="submitted",
                cost_estimate={},
                request_summary={},
            )
            updated = store.update_from_provider(
                "ana_result",
                status="completed",
                engine_result={"status": "completed", "player": {}},
            )
            self.assertEqual(updated.engine_result["status"], "completed")
            public = store.public_dict(updated)
            self.assertTrue(public["has_result"])
            self.assertNotIn("engine_result", public)

    def test_provider_error_is_persisted_but_sanitized_from_public_job(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self.make_store(directory)
            job = store.put(
                job_id="ana_error",
                provider="runpod",
                provider_job_id="provider-secret",
                status="failed",
                cost_estimate={},
                request_summary={},
                provider_error="private worker diagnostic",
            )
            public = store.public_dict(job)
            self.assertNotIn("provider_error", public)
            self.assertTrue(public["has_error"])


if __name__ == "__main__":
    unittest.main()
