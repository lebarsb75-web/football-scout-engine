import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.idempotency import IdempotencyPendingError, IdempotencyStore


class IdempotencyStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tempdir.name) / "idempotency.sqlite3")

    def tearDown(self):
        self.tempdir.cleanup()

    def make_store(self):
        return IdempotencyStore(ttl_seconds=60, path=self.db_path)

    def test_replay_returns_cached_response(self):
        store = self.make_store()
        payload = {"video": "a", "target": {"x": 0.5}}
        response = {"job_id": "123"}
        store.put("submission-123", payload, response)
        self.assertEqual(store.get("submission-123", payload), response)

    def test_reusing_key_with_different_payload_fails(self):
        store = self.make_store()
        store.put("submission-123", {"video": "a"}, {"job_id": "123"})
        with self.assertRaises(ValueError):
            store.get("submission-123", {"video": "b"})

    def test_fingerprint_is_order_independent(self):
        first = {"a": 1, "b": {"x": 2, "y": 3}}
        second = {"b": {"y": 3, "x": 2}, "a": 1}
        self.assertEqual(IdempotencyStore.fingerprint(first), IdempotencyStore.fingerprint(second))

    def test_reserve_blocks_second_inflight_request(self):
        first = self.make_store()
        second = self.make_store()
        payload = {"video": "a"}

        self.assertIsNone(first.reserve("submission-123", payload))
        with self.assertRaises(IdempotencyPendingError):
            second.reserve("submission-123", payload)

    def test_reservation_survives_new_store_instance(self):
        payload = {"video": "a"}
        self.make_store().reserve("submission-123", payload)
        reloaded = self.make_store()
        with self.assertRaises(IdempotencyPendingError):
            reloaded.get("submission-123", payload)

    def test_completed_reservation_replays_after_restart(self):
        payload = {"video": "a"}
        response = {"job_id": "123"}
        store = self.make_store()
        store.reserve("submission-123", payload)
        store.put("submission-123", payload, response)

        reloaded = self.make_store()
        self.assertEqual(reloaded.get("submission-123", payload), response)
        self.assertEqual(reloaded.reserve("submission-123", payload), response)


class PaidSubmissionGuardTests(unittest.TestCase):
    def setUp(self):
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
                headers={"X-Idempotency-Key": "analysis-test-locked-0001"},
            )
        self.assertEqual(response.status_code, 423)
        self.assertIn("locked", response.json()["detail"].lower())

    def test_pending_key_fails_before_paid_gate(self):
        key = "analysis-test-pending-0001"
        request = self.app_module.SubmitRequest.model_validate(self.payload)
        canonical_payload = request.model_dump(mode="json")

        with tempfile.TemporaryDirectory() as tempdir:
            isolated = IdempotencyStore(path=str(Path(tempdir) / "idempotency.sqlite3"))
            isolated.reserve(key, canonical_payload)
            with patch.object(self.app_module, "SUBMISSION_CACHE", isolated), patch.object(
                self.app_module, "ENABLE_PAID_GPU", True
            ):
                response = self.client.post(
                    "/analysis/submit",
                    json=self.payload,
                    headers={"X-Idempotency-Key": key},
                )
        self.assertEqual(response.status_code, 409)
        self.assertIn("already in progress", response.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
