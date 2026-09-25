import unittest

from api.costs import authorization_allows_submission, estimate_cost


class CostControlTests(unittest.TestCase):
    def test_requires_benchmark(self):
        result = estimate_cost(120, 0.58, None)
        self.assertFalse(result["ready"])
        self.assertEqual(result["reason"], "benchmark_required")

    def test_estimate_from_measured_speed(self):
        result = estimate_cost(
            duration_seconds=90 * 60,
            gpu_price_per_hour=0.58,
            gpu_seconds_per_video_minute=12,
        )
        self.assertTrue(result["ready"])
        self.assertAlmostEqual(result["estimated_gpu_seconds"], 1080.0)
        self.assertAlmostEqual(result["estimated_cost_usd"], 0.174, places=3)
        self.assertAlmostEqual(
            result["recommended_max_authorization_usd"], 0.2349, places=4
        )

    def test_authorization_blocks_insufficient_cap(self):
        estimate = estimate_cost(600, 0.58, 12)
        self.assertFalse(authorization_allows_submission(estimate, 0.01))

    def test_authorization_accepts_sufficient_cap(self):
        estimate = estimate_cost(600, 0.58, 12)
        approved = estimate["recommended_max_authorization_usd"]
        self.assertTrue(authorization_allows_submission(estimate, approved))

    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            estimate_cost(0, 0.58, 12)


if __name__ == "__main__":
    unittest.main()
