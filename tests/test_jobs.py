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


if __name__ == "__main__":
    unittest.main()
