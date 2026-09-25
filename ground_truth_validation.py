from __future__ import annotations

import math
from typing import Any


def _nearest_sample(trace: list[dict[str, Any]], timestamp: float) -> dict[str, Any] | None:
    if not trace:
        return None
    return min(trace, key=lambda item: abs(float(item["timestamp_seconds"]) - timestamp))


def evaluate_tracking_ground_truth(
    engine_result: dict[str, Any],
    annotations: dict[str, Any],
    *,
    maximum_time_delta_seconds: float = 0.075,
    maximum_center_error_ratio: float = 0.035,
) -> dict[str, Any]:
    """Compare a private engine trace with independently labelled target positions.

    A visible target is correct only when the engine returned a player close to the
    annotated centre. Merely returning any track is deliberately not enough.
    """
    trace = engine_result.get("validation", {}).get("tracking_trace") or []
    frames = annotations.get("frames") or []
    if not frames:
        raise ValueError("annotations.frames must contain at least one labelled frame")
    annotation_times = [float(frame["timestamp_seconds"]) for frame in frames]
    if annotation_times != sorted(annotation_times) or len(set(annotation_times)) != len(
        annotation_times
    ):
        raise ValueError("annotation timestamps must be unique and strictly increasing")

    visible = correct_visible = missed_visible = 0
    absent = correct_absent = false_positive = 0
    unmatched = 0
    center_errors = []

    for annotation in frames:
        timestamp = float(annotation["timestamp_seconds"])
        sample = _nearest_sample(trace, timestamp)
        if sample is None or abs(float(sample["timestamp_seconds"]) - timestamp) > maximum_time_delta_seconds:
            unmatched += 1
            continue

        target_visible = bool(annotation["target_visible"])
        predicted_visible = bool(sample.get("tracked"))
        if not target_visible:
            absent += 1
            if predicted_visible:
                false_positive += 1
            else:
                correct_absent += 1
            continue

        visible += 1
        if not predicted_visible or not isinstance(sample.get("center"), dict):
            missed_visible += 1
            continue
        expected = annotation.get("center")
        if not isinstance(expected, dict):
            raise ValueError("visible annotations require a normalized center")
        expected_x = float(expected["x"])
        expected_y = float(expected["y"])
        if not 0.0 <= expected_x <= 1.0 or not 0.0 <= expected_y <= 1.0:
            raise ValueError("annotation centers must use normalized coordinates from 0 to 1")
        error = math.hypot(
            float(sample["center"]["x"]) - expected_x,
            float(sample["center"]["y"]) - expected_y,
        )
        center_errors.append(error)
        if error <= maximum_center_error_ratio:
            correct_visible += 1
        else:
            missed_visible += 1

    evaluated = visible + absent
    identity_accuracy = correct_visible / visible * 100.0 if visible else 0.0
    absence_accuracy = correct_absent / absent * 100.0 if absent else None
    false_positive_rate = false_positive / absent * 100.0 if absent else None
    mean_center_error = sum(center_errors) / len(center_errors) if center_errors else None
    gate_passed = bool(
        evaluated >= 30
        and visible >= 20
        and unmatched == 0
        and identity_accuracy >= 95.0
        and (false_positive_rate is None or false_positive_rate <= 5.0)
    )
    gate_failures = []
    if evaluated < 30:
        gate_failures.append("insufficient_evaluated_frames")
    if visible < 20:
        gate_failures.append("insufficient_visible_target_frames")
    if unmatched:
        gate_failures.append("unmatched_annotations")
    if identity_accuracy < 95.0:
        gate_failures.append("identity_accuracy_below_threshold")
    if false_positive_rate is not None and false_positive_rate > 5.0:
        gate_failures.append("false_positive_rate_above_threshold")
    return {
        "annotated_frames": len(frames),
        "evaluated_frames": evaluated,
        "unmatched_annotations": unmatched,
        "visible_target_frames": visible,
        "correct_identity_frames": correct_visible,
        "missed_or_wrong_identity_frames": missed_visible,
        "identity_accuracy_percent": round(identity_accuracy, 2),
        "absence_accuracy_percent": round(absence_accuracy, 2) if absence_accuracy is not None else None,
        "false_positive_rate_percent": round(false_positive_rate, 2) if false_positive_rate is not None else None,
        "mean_center_error_ratio": round(mean_center_error, 6) if mean_center_error is not None else None,
        "ground_truth_tracking_gate_passed": gate_passed,
        "gate_failures": gate_failures,
        "gate_requirements": {
            "minimum_evaluated_frames": 30,
            "minimum_visible_target_frames": 20,
            "minimum_identity_accuracy_percent": 95.0,
            "maximum_false_positive_rate_percent": 5.0,
        },
    }
