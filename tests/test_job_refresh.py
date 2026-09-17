import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from api.jobs import JobStore


class JobRefreshTests(unittest.TestCase):
    def setUp(self):
        import api.app as app_module

        self.app_module = app_module
        self.client = TestClient(app_module.app)
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = JobStore(str(Path(self.tempdir.name) / "jobs.sqlite3"))
        self.store.put(
            job_id="ana_refresh",
            provider="runpod",
            provider_job_id="provider-private",
            status="submitted",
            cost_estimate={},
            request_summary={},
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_completed_job_is_saved_and_quality_gated(self):
        provider_response = Mock(ok=True)
        provider_response.json.return_value = {
            "status": "COMPLETED",
            "output": {
                "status": "completed",
                "engine_version": "2.4-dev",
                "player": {
                    "tracking_coverage_percent": 95,
                    "ball_touches_estimated": 4,
                },
                "quality": {
                    "score_percent": 90,
                    "player_tracking_score_percent": 90,
                    "tracking_continuity_reliable": True,
                    "ball_metrics_reliable": False,
                    "ball_visibility_percent": 10,
                    "pitch_calibration_used": False,
                },
            },
        }
        with patch.object(self.app_module, "JOBS", self.store), patch.object(
            self.app_module, "RUNPOD_ENDPOINT_ID", "endpoint"
        ), patch.object(self.app_module, "RUNPOD_API_KEY", "secret"), patch.object(
            self.app_module.requests, "get", return_value=provider_response
        ):
            response = self.client.post("/analysis/jobs/ana_refresh/refresh")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertNotIn("provider_job_id", body)
        self.assertFalse(body["result"]["metrics"]["ball_touches"]["available"])

    def test_terminal_job_does_not_contact_runpod_twice(self):
        self.store.update_from_provider(
            "ana_refresh",
            status="failed",
            provider_error="worker failed",
        )
        with patch.object(self.app_module, "JOBS", self.store), patch.object(
            self.app_module.requests, "get"
        ) as get:
            response = self.client.post("/analysis/jobs/ana_refresh/refresh")
        self.assertEqual(response.status_code, 200)
        get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
