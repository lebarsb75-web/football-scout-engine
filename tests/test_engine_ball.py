import unittest

from engine_ball import (
    calibration_points_are_valid,
    local_ball_search_crop,
    translate_box,
)


class LocalBallSearchTests(unittest.TestCase):
    def test_crop_is_expanded_around_player_feet_and_clipped(self):
        crop = local_ball_search_crop([2, 10, 12, 50], 100, 80)
        self.assertEqual(crop[0], 0)
        self.assertEqual(crop[1], 0)
        self.assertGreater(crop[2], 12)
        self.assertEqual(crop[3], 80)

    def test_translates_crop_detection_to_source_frame(self):
        self.assertEqual(translate_box([1, 2, 5, 8], 100, 40), [101.0, 42.0, 105.0, 48.0])

    def test_calibration_requires_four_non_degenerate_points(self):
        pitch = [[0, 0], [105, 0], [105, 68], [0, 68]]
        self.assertTrue(
            calibration_points_are_valid(
                [[100, 100], [1800, 100], [1700, 900], [200, 900]], pitch
            )
        )
        self.assertFalse(calibration_points_are_valid([[1, 1]] * 4, pitch))


if __name__ == "__main__":
    unittest.main()
