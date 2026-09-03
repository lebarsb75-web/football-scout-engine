import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.idempotency import IdempotencyStore


class IdempotencyStoreTests(unittest.TestCase):
    def test_replay_returns_cached_response(self):
        store = IdempotencyStore(ttl_seconds=60)
        payload = {"video": "a", "target": {"x": 0.5}}
        response = {"job_id": "123"}
        store.put("submission-123", payload, response)
        self.assertEqual(store.get("submission-123", payload), response)

    def test_reusing_key_with_different_payload_fails(self):
        store = IdempotencyStore(ttl_seconds=60)
        store.put("submission-123", {"video": "a"}, {"job_id": "123"})
        with self.assertRaises(ValueError):
            store.get("submission-123", {"video": "b"})

    def test_fingerprint_is_order_independent(self):
        first = {"a": 1, "b": {"x": 2, "y": 3}}
        second = {"b": {"y": 3, "x": 2}, "a": 1}
        self.assertEqual(IdempotencyStore.fingerprint(first), IdempotencyStore.fingerprint(second))


class PaidSubmissionGuardTests(unittest.TestCase):
    def setUp(self):
        # Importing after environment patching lets this test verify the default
        # locked behavior without ever making a network request.
        import api.app as app_module

        self.app_module = app_module
        self.client = TestClient(app_module.app)
        self.payload = {
            "video_url": "https://example.com/match.mp4",
            "video_duration_seconds": 60,
            "target": {"x": 0.5, "y": 0.5},
            "target_time_seconds": 1,
            "sample_fps": 5,
            "confidence": 0.22,
            "image_size": 960,
            "approved_max_cost_usd": 1,
        }

    def test_submit_requires_idempotency_key_even_when_gpu_locked(self):
        with patch.object(self.app_module, "ENABLE_PAID_GPU", False):
            response = self.client.post("/analysis/submit", json=self.payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("X-Idempotency-Key", response.json()["detail"])

    def test_valid_key_still_hits_paid_gpu_lock(self):
        with patch.object(self.app_module, "ENABLE_PAID_GPU", False):
            response = self.client.post(
                "/analysis/submit",
                json=self.payload,
                headers={"X-Idempotency-Key": "analysis-test-0001"},
            )
        self.assertEqual(response.status_code, 423)
        self.assertIn("locked", response.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
