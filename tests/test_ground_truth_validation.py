import unittest

from ground_truth_validation import evaluate_tracking_ground_truth


class GroundTruthValidationTests(unittest.TestCase):
    def test_gate_uses_position_not_track_presence(self):
        trace = []
        frames = []
        for index in range(30):
            timestamp = index / 10
            trace.append({"timestamp_seconds": timestamp, "tracked": True, "center": {"x": 0.8, "y": 0.8}})
            frames.append({"timestamp_seconds": timestamp, "target_visible": True, "center": {"x": 0.2, "y": 0.2}})
        report = evaluate_tracking_ground_truth(
            {"validation": {"tracking_trace": trace}}, {"frames": frames}
        )
        self.assertEqual(report["identity_accuracy_percent"], 0.0)
        self.assertFalse(report["ground_truth_tracking_gate_passed"])
        self.assertIn("identity_accuracy_below_threshold", report["gate_failures"])

    def test_perfect_annotations_pass_minimum_gate(self):
        trace = []
        frames = []
        for index in range(30):
            timestamp = index / 10
            visible = index < 25
            sample = {"timestamp_seconds": timestamp, "tracked": visible}
            annotation = {"timestamp_seconds": timestamp, "target_visible": visible}
            if visible:
                sample["center"] = {"x": 0.4, "y": 0.6}
                annotation["center"] = {"x": 0.4, "y": 0.6}
            trace.append(sample)
            frames.append(annotation)
        report = evaluate_tracking_ground_truth(
            {"validation": {"tracking_trace": trace}}, {"frames": frames}
        )
        self.assertTrue(report["ground_truth_tracking_gate_passed"])
        self.assertEqual(report["gate_failures"], [])
        self.assertEqual(report["identity_accuracy_percent"], 100.0)

    def test_empty_annotations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            evaluate_tracking_ground_truth({}, {"frames": []})

    def test_duplicate_timestamps_cannot_inflate_validation_set(self):
        frames = [
            {"timestamp_seconds": 1.0, "target_visible": False},
            {"timestamp_seconds": 1.0, "target_visible": False},
        ]
        with self.assertRaisesRegex(ValueError, "unique and strictly increasing"):
            evaluate_tracking_ground_truth({}, {"frames": frames})

    def test_annotation_centers_must_be_normalized(self):
        engine_result = {
            "validation": {
                "tracking_trace": [
                    {
                        "timestamp_seconds": 1.0,
                        "tracked": True,
                        "center": {"x": 0.5, "y": 0.5},
                    }
                ]
            }
        }
        annotations = {
            "frames": [
                {
                    "timestamp_seconds": 1.0,
                    "target_visible": True,
                    "center": {"x": 2.0, "y": 0.5},
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "normalized coordinates"):
            evaluate_tracking_ground_truth(engine_result, annotations)


if __name__ == "__main__":
    unittest.main()
