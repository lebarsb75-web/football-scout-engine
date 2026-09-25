import unittest

from api.results import public_result


class PublicResultTests(unittest.TestCase):
    def base_result(self):
        return {
            "status": "completed",
            "engine_version": "2.0-dev",
            "player": {
                "tracking_coverage_percent": 92.0,
                "distance_meters_estimated": 8421.3,
                "ball_touches_estimated": 57,
                "possession_seconds_estimated": 89.4,
            },
            "quality": {
                "score_percent": 86.0,
                "player_tracking_score_percent": 88.0,
                "tracking_continuity_reliable": True,
                "ball_metrics_reliable": True,
                "ball_visibility_percent": 44.0,
                "pitch_calibration_used": True,
            },
            "clips": [
                {"type": "touch", "start": 10, "end": 14},
                {"type": "possession", "start": 20, "end": 26},
            ],
        }

    def test_good_result_exposes_quality_gated_metrics(self):
        result = public_result(self.base_result())
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["metrics"]["ball_touches"]["value"], 57)
        self.assertEqual(result["metrics"]["distance_meters"]["value"], 8421.3)
        self.assertEqual(len(result["clips"]), 2)

    def test_worker_touch_windows_are_exposed_only_after_ball_gate(self):
        raw = self.base_result()
        raw.pop("clips")
        raw["player"]["touch_clip_windows_seconds"] = [[10.0, 14.0], [20.0, 26.0]]
        result = public_result(raw)
        self.assertEqual(
            result["clips"],
            [
                {"type": "touch", "start": 10.0, "end": 14.0},
                {"type": "touch", "start": 20.0, "end": 26.0},
            ],
        )

        raw["quality"]["ball_metrics_reliable"] = False
        self.assertEqual(public_result(raw)["clips"], [])

    def test_low_ball_visibility_hides_ball_metrics(self):
        raw = self.base_result()
        raw["quality"]["ball_visibility_percent"] = 5
        result = public_result(raw)
        self.assertFalse(result["metrics"]["ball_touches"]["available"])
        self.assertFalse(result["metrics"]["possession_seconds"]["available"])
        self.assertEqual(result["clips"], [])
        self.assertTrue(result["metrics"]["distance_meters"]["available"])

    def test_missing_pitch_calibration_hides_distance(self):
        raw = self.base_result()
        raw["quality"]["pitch_calibration_used"] = False
        result = public_result(raw)
        self.assertFalse(result["metrics"]["distance_meters"]["available"])
        self.assertEqual(
            result["metrics"]["distance_meters"]["reason"],
            "pitch_calibration_required",
        )

    def test_low_tracking_quality_requires_review_and_hides_metrics(self):
        raw = self.base_result()
        raw["player"]["tracking_coverage_percent"] = 40
        result = public_result(raw)
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["metrics"]["distance_meters"]["available"])
        self.assertFalse(result["metrics"]["ball_touches"]["available"])

    def test_engine_ball_reliability_false_cannot_be_overridden_by_high_scores(self):
        raw = self.base_result()
        raw["quality"]["ball_metrics_reliable"] = False
        result = public_result(raw)
        self.assertFalse(result["metrics"]["ball_touches"]["available"])
        self.assertFalse(result["metrics"]["possession_seconds"]["available"])

    def test_missing_continuity_verdict_fails_closed(self):
        raw = self.base_result()
        raw["quality"].pop("tracking_continuity_reliable")
        result = public_result(raw)
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["metrics"]["distance_meters"]["available"])

    def test_failed_engine_result_is_unavailable(self):
        result = public_result({"status": "error", "error": "bad video"})
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["reason"], "engine_not_completed")


if __name__ == "__main__":
    unittest.main()
