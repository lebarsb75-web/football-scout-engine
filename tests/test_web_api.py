import unittest

from fastapi.testclient import TestClient

from api.app import app


class WebApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_local_web_origin_can_preflight_submission(self):
        response = self.client.options(
            "/analysis/submit",
            headers={
                "Origin": "http://localhost:4173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-idempotency-key,x-cost-approval-secret",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:4173",
        )

    def test_unknown_origin_is_not_allowed(self):
        response = self.client.options(
            "/analysis/submit",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_estimate_only_requires_video_duration(self):
        response = self.client.post(
            "/analysis/estimate",
            json={"video_duration_seconds": 26},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["ready"])

    def test_report_identity_metadata_is_validated_without_gpu_call(self):
        payload = {
            "video_url": "https://example.com/match.mp4",
            "video_duration_seconds": 90,
            "target": {"x": 0.5, "y": 0.5},
            "target_time_seconds": 4,
            "approved_max_cost_usd": 1,
            "player_profile": {
                "name": "Brieg Le Bars",
                "position": "Milieu central",
                "team": "Lamballe FC",
                "shirt_number": 100,
            },
            "match_context": {
                "opponent": "Stade Rennais B",
                "match_date": "2026-09-17",
                "source_filename": "match.mp4",
            },
        }

        response = self.client.post(
            "/analysis/submit",
            json=payload,
            headers={"X-Idempotency-Key": "analysis-metadata-test-0001"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("shirt_number", str(response.json()))


if __name__ == "__main__":
    unittest.main()
