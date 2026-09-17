import unittest

from engine_tracking import iter_sample_frame_indices, reset_model_trackers


class FakeTracker:
    def __init__(self):
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1


class TrackerResetTests(unittest.TestCase):
    def test_resets_each_registered_tracker_once(self):
        first = FakeTracker()
        second = FakeTracker()
        predictor = type("Predictor", (), {"trackers": [first, second]})()
        model = type("Model", (), {"predictor": predictor})()
        self.assertEqual(reset_model_trackers(model), 2)
        self.assertEqual(first.reset_calls, 1)
        self.assertEqual(second.reset_calls, 1)

    def test_model_without_predictor_is_safe(self):
        self.assertEqual(reset_model_trackers(object()), 0)

    def test_sampling_25fps_at_10fps_is_time_even_and_not_12_5fps(self):
        indices = list(iter_sample_frame_indices(100, 750, 25, 10))
        self.assertEqual(len(indices), 260)
        self.assertEqual(indices[:6], [100, 102, 105, 108, 110, 112])
        self.assertEqual(len(set(indices)), len(indices))


if __name__ == "__main__":
    unittest.main()
