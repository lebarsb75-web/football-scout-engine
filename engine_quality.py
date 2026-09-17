from __future__ import annotations

from typing import Iterable


def summarize_tracking_samples(
    samples: Iterable[bool],
    sample_fps: float,
    *,
    window_seconds: float = 30.0,
) -> dict:
    """Summarise tracking continuity without hiding long failures in an average."""
    values = [bool(value) for value in samples]
    fps = max(0.001, float(sample_fps))
    window_size = max(1, int(round(float(window_seconds) * fps)))

    if not values:
        return {
            "coverage_percent": 0.0,
            "minimum_window_coverage_percent": 0.0,
            "longest_untracked_gap_seconds": 0.0,
            "window_coverage_percent": [],
        }

    windows = []
    for start in range(0, len(values), window_size):
        window = values[start : start + window_size]
        windows.append(round(sum(window) / len(window) * 100.0, 1))

    longest_gap = 0
    current_gap = 0
    for tracked in values:
        if tracked:
            longest_gap = max(longest_gap, current_gap)
            current_gap = 0
        else:
            current_gap += 1
    longest_gap = max(longest_gap, current_gap)

    return {
        "coverage_percent": round(sum(values) / len(values) * 100.0, 1),
        "minimum_window_coverage_percent": min(windows),
        "longest_untracked_gap_seconds": round(longest_gap / fps, 2),
        "window_coverage_percent": windows,
    }


def classify_tracking_quality(
    *,
    player_quality: float,
    coverage_percent: float,
    minimum_window_coverage_percent: float,
    longest_untracked_gap_seconds: float,
    scene_cuts: int,
    reidentification_rate_percent: float,
    identity_rejection_rate_percent: float,
) -> tuple[str, bool]:
    """Return the label and strict continuity gate used for published metrics."""
    continuity_reliable = (
        coverage_percent >= 80.0
        and minimum_window_coverage_percent >= 65.0
        and longest_untracked_gap_seconds <= 5.0
        and scene_cuts == 0
        and reidentification_rate_percent <= 5.0
        and identity_rejection_rate_percent <= 5.0
    )
    if player_quality >= 82.0 and continuity_reliable:
        return "good", True
    if (
        player_quality >= 65.0
        and coverage_percent >= 60.0
        and minimum_window_coverage_percent >= 40.0
        and longest_untracked_gap_seconds <= 12.0
        and reidentification_rate_percent <= 35.0
        and identity_rejection_rate_percent <= 35.0
    ):
        return "usable_with_review", False
    return "insufficient", False


def ball_metrics_are_reliable(
    *,
    tracking_continuity_reliable: bool,
    player_quality: float,
    ball_visibility_percent: float,
    sampled_frames: int,
) -> bool:
    return bool(
        tracking_continuity_reliable
        and player_quality >= 82.0
        and ball_visibility_percent >= 40.0
        and sampled_frames >= 30
    )
