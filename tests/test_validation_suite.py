import json
import tempfile
import unittest
from pathlib import Path

from scripts.evaluate_validation_suite import evaluate_suite


class ValidationSuiteTests(unittest.TestCase):
    def _make_sequence(self, directory: Path, name: str, wrong: bool = False):
        trace = []
        frames = []
        for n in range(30):
            visible = n < 25
            t = n / 10
            tracked = visible
            sample = {"timestamp_seconds": t, "tracked": tracked}
            annotation = {"timestamp_seconds": t, "target_visible": visible}
            if visible:
                sample["center"] = {"x": 0.8 if wrong else 0.3, "y": 0.4}
                annotation["center"] = {"x": 0.3, "y": 0.4}
            trace.append(sample)
            frames.append(annotation)
        (directory / f"{name}-result.json").write_text(
            json.dumps({"validation": {"tracking_trace": trace}}), encoding="utf-8"
        )
        (directory / f"{name}-labels.json").write_text(
            json.dumps({"frames": frames}), encoding="utf-8"
        )
        return {"name": name, "result": f"{name}-result.json", "annotations": f"{name}-labels.json"}

    def test_ten_good_independent_sequences_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            entries = [self._make_sequence(root, f"clip-{n}") for n in range(10)]
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sequences": entries}), encoding="utf-8")
            result = evaluate_suite(manifest)
            self.assertTrue(result["tracking_validation_passed"])
            self.assertEqual(result["passed_sequence_count"], 10)
            self.assertEqual(result["commercial_readiness"], "NOT_ASSESSED")

    def test_one_bad_sequence_rejects_whole_suite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            entries = [self._make_sequence(root, f"clip-{n}", wrong=n == 3) for n in range(10)]
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sequences": entries}), encoding="utf-8")
            result = evaluate_suite(manifest)
            self.assertFalse(result["tracking_validation_passed"])
            self.assertEqual(result["failed_sequence_count"], 1)

    def test_fewer_than_ten_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sequences": [self._make_sequence(root, "clip-1")]}), encoding="utf-8")
            self.assertFalse(evaluate_suite(manifest)["tracking_validation_passed"])

    def test_missing_result_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sequences": [
                {"name": "missing", "result": "missing.json", "annotations": "missing-labels.json"}
            ]}), encoding="utf-8")
            result = evaluate_suite(manifest, minimum_sequences=1)
            self.assertFalse(result["tracking_validation_passed"])
            self.assertIn("error", result["sequences"][0])

    def test_duplicate_names_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            entry = self._make_sequence(root, "duplicate")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"sequences": [entry, entry]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate sequence"):
                evaluate_suite(manifest)


if __name__ == "__main__":
    unittest.main()
