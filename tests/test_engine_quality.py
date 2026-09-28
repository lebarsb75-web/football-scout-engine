import unittest

from engine_quality import (
    ball_metrics_are_reliable,
    classify_tracking_quality,
    summarize_tracked_segments,
    summarize_tracking_samples,
)


class TrackingContinuityTests(unittest.TestCase):
    def test_summary_detects_long_gap_hidden_by_average(self):
        samples = [True] * 80 + [False] * 20 + [True] * 100
        summary = summarize_tracking_samples(samples, sample_fps=10, window_seconds=10)
        self.assertEqual(summary["coverage_percent"], 90.0)
        self.assertEqual(summary["minimum_window_coverage_percent"], 80.0)
        self.assertEqual(summary["longest_untracked_gap_seconds"], 2.0)

    def test_empty_summary_is_safe(self):
        summary = summarize_tracking_samples([], sample_fps=5)
        self.assertEqual(summary["coverage_percent"], 0.0)
        self.assertEqual(summary["window_coverage_percent"], [])

    def test_good_tracking_requires_no_scene_cut(self):
        label, reliable = classify_tracking_quality(
            player_quality=90,
            coverage_percent=95,
            minimum_window_coverage_percent=90,
            longest_untracked_gap_seconds=1,
            scene_cuts=1,
            unrecovered_scene_cuts=1,
            reidentification_rate_percent=0,
            identity_rejection_rate_percent=0,
        )
        self.assertEqual(label, "usable_with_review")
        self.assertFalse(reliable)

    def test_recovered_broadcast_cut_can_keep_good_tracking(self):
        label, reliable = classify_tracking_quality(
            player_quality=90,
            coverage_percent=95,
            minimum_window_coverage_percent=90,
            longest_untracked_gap_seconds=1,
            scene_cuts=2,
            unrecovered_scene_cuts=0,
            reidentification_rate_percent=1,
            identity_rejection_rate_percent=1,
        )
        self.assertEqual(label, "good")
        self.assertTrue(reliable)

    def test_segments_keep_useful_continuous_passages(self):
        summary = summarize_tracked_segments(
            [True] * 20 + [False] * 5 + [True] * 5 + [False] * 2 + [True] * 30,
            sample_fps=10,
            minimum_segment_seconds=1.5,
        )
        self.assertEqual(summary["reliable_segment_count"], 2)
        self.assertEqual(summary["tracked_seconds"], 5.5)
        self.assertEqual(summary["longest_tracked_sequence_seconds"], 3.0)

    def test_high_identity_churn_cannot_be_labelled_good(self):
        label, reliable = classify_tracking_quality(
            player_quality=95,
            coverage_percent=95,
            minimum_window_coverage_percent=90,
            longest_untracked_gap_seconds=1,
            scene_cuts=0,
            reidentification_rate_percent=45,
            identity_rejection_rate_percent=40,
        )
        self.assertEqual(label, "insufficient")
        self.assertFalse(reliable)

    def test_ball_gate_requires_strict_tracking_continuity(self):
        self.assertFalse(
            ball_metrics_are_reliable(
                tracking_continuity_reliable=False,
                player_quality=95,
                ball_visibility_percent=90,
                sampled_frames=100,
            )
        )


if __name__ == "__main__":
    unittest.main()
