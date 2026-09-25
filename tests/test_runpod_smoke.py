import unittest

from scripts.runpod_smoke_test import SmokeTestError, validate_engine_result, validate_preflight


class RunPodSmokePreflightTests(unittest.TestCase):
    def endpoint(self):
        return {
            "id": "47kdwxukrvp695",
            "name": "football-scout-engine",
            "type": "QUEUE",
            "image": "registry.example/football-scout:dev-v2",
            "gpu": {"pools": ["AMPERE_16"], "count": 1},
            "workers": {"min": 0, "max": 1, "idleTimeout": 5},
            "timeout": 120000,
        }

    def catalog(self):
        return {
            "gpus": [
                {
                    "id": "NVIDIA RTX A4000",
                    "pool": "AMPERE_16",
                    "price": {"serverless": 0.58},
                }
            ]
        }

    def call_validate(self, endpoint=None, catalog=None):
        return validate_preflight(
            endpoint or self.endpoint(),
            {"summary": {"total": 0}},
            {"jobs": {"inQueue": 0, "inProgress": 0}, "workers": {"idle": 0, "running": 0}},
            catalog or self.catalog(),
            {"client_balance_usd": 9.98, "current_spend_per_hour_usd": 0},
            endpoint_id="47kdwxukrvp695",
            max_hourly_price=0.58,
            cost_ceiling_usd=0.05,
            max_wall_seconds=295,
        )

    def test_expected_endpoint_is_inside_first_test_ceiling(self):
        result = self.call_validate()

        self.assertEqual(result["workers_max"], 1)
        self.assertLess(result["conservative_cost_bound_usd"], 0.05)

    def test_more_than_one_worker_fails_closed(self):
        endpoint = self.endpoint()
        endpoint["workers"]["max"] = 2

        with self.assertRaisesRegex(SmokeTestError, "Unsafe worker limits"):
            self.call_validate(endpoint=endpoint)

    def test_higher_current_serverless_price_fails_closed(self):
        catalog = self.catalog()
        catalog["gpus"][0]["price"]["serverless"] = 0.61

        with self.assertRaisesRegex(SmokeTestError, "exceeds approved"):
            self.call_validate(catalog=catalog)


class RunPodSmokeQualityTests(unittest.TestCase):
    def result(self):
        return {
            "status": "completed",
            "engine_version": "2.4-dev",
            "processing_seconds": 8.2,
            "video": {
                "analysis_duration_seconds": 26.0,
                "sampled_frames": 260,
            },
            "player": {
                "last_track_id": 12,
                "tracking_coverage_percent": 97.3,
                "distance_pixels_estimated": 8432,
                "ball_touches_estimated": 2,
                "possession_seconds_estimated": 1.4,
            },
            "quality": {
                "score_percent": 80.0,
                "player_tracking_score_percent": 96.5,
                "label": "good",
                "tracking_continuity_reliable": True,
                "minimum_window_coverage_percent": 97.3,
                "longest_untracked_gap_seconds": 0.7,
                "reidentification_rate_percent": 5.0,
                "identity_rejection_rate_percent": 0.0,
                "scene_cuts_detected": 0,
                "ball_metrics_reliable": False,
                "ball_visibility_percent": 9.2,
                "pitch_calibration_used": False,
            },
        }

    def test_good_tracking_passes_while_unreliable_metrics_stay_hidden(self):
        summary = validate_engine_result(self.result())

        self.assertTrue(summary["passed"])
        self.assertFalse(summary["ball_metrics_exposed"])
        self.assertFalse(summary["distance_meters_exposed"])

    def test_wrong_engine_version_stops_test(self):
        result = self.result()
        result["engine_version"] = "2.3-dev"

        with self.assertRaisesRegex(SmokeTestError, "Wrong engine version"):
            validate_engine_result(result)

    def test_continuity_regression_stops_test(self):
        result = self.result()
        result["quality"]["longest_untracked_gap_seconds"] = 5.1

        with self.assertRaisesRegex(SmokeTestError, "longest_gap_at_most_5s"):
            validate_engine_result(result)


if __name__ == "__main__":
    unittest.main()
