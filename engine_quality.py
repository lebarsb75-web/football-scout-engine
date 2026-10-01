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


def summarize_tracked_segments(
    samples: Iterable[bool],
    sample_fps: float,
    *,
    minimum_segment_seconds: float = 1.5,
) -> dict:
    """Describe useful continuous sequences instead of reducing a video to one score.

    Broadcast footage naturally contains replays, close-ups and camera cuts.  A report can
    still be useful when several continuous sequences are reliable, provided those sequences
    are reported explicitly and are not silently treated as one uninterrupted track.
    """
    values = [bool(value) for value in samples]
    fps = max(0.001, float(sample_fps))
    minimum_samples = max(1, int(round(float(minimum_segment_seconds) * fps)))
    segments = []
    start = None

    for index, tracked in enumerate(values + [False]):
        if tracked and start is None:
            start = index
        elif not tracked and start is not None:
            length = index - start
            if length >= minimum_samples:
                segments.append(
                    {
                        "start_seconds": round(start / fps, 2),
                        "end_seconds": round(index / fps, 2),
                        "duration_seconds": round(length / fps, 2),
                    }
                )
            start = None

    tracked_samples = sum(values)
    return {
        "tracked_seconds": round(tracked_samples / fps, 2),
        "reliable_segment_count": len(segments),
        "reliable_segments": segments,
        "longest_tracked_sequence_seconds": round(
            max((segment["duration_seconds"] for segment in segments), default=0.0), 2
        ),
    }


def classify_tracking_quality(
    *,
    player_quality: float,
    coverage_percent: float,
    minimum_window_coverage_percent: float,
    longest_untracked_gap_seconds: float,
    scene_cuts: int,
    unrecovered_scene_cuts: int = 0,
    reidentification_rate_percent: float,
    identity_rejection_rate_percent: float,
) -> tuple[str, bool]:
    """Return the label and strict continuity gate used for published metrics."""
    continuity_reliable = (
        coverage_percent >= 80.0
        and minimum_window_coverage_percent >= 65.0
        and longest_untracked_gap_seconds <= 5.0
        and unrecovered_scene_cuts == 0
        and scene_cuts <= 12
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
    ball_search_coverage_percent: float = 0.0,
    validated_ball_samples: int = 0,
    validated_touch_events: int = 0,
    mean_ball_confidence: float = 0.0,
) -> bool:
    """Gate touch metrics on search coverage and temporal evidence.

    Ball visibility cannot reasonably be required on 40% of a match: an
    individual player, especially a centre-back, is not near the ball for that
    share of frames.  V2.6 instead requires that the dedicated detector was run
    across nearly all reliable player frames and that a candidate survived
    proximity and temporal-continuity checks.  The old visibility argument is
    retained for backwards-compatible callers and diagnostics.
    """
    return bool(
        tracking_continuity_reliable
        and player_quality >= 82.0
        and sampled_frames >= 30
        and ball_search_coverage_percent >= 80.0
        and validated_ball_samples >= 3
        and validated_touch_events >= 1
        and mean_ball_confidence >= 0.04
    )
