from __future__ import annotations


def iter_sample_frame_indices(
    start_frame: int,
    total_frames: int,
    source_fps: float,
    requested_sample_fps: float,
):
    """Yield a timestamp-even sampling schedule without exceeding target FPS."""
    target_fps = min(max(0.001, float(requested_sample_fps)), float(source_fps))
    interval = float(source_fps) / target_fps
    position = float(start_frame)
    previous = None
    while True:
        frame_index = int(round(position))
        if frame_index >= int(total_frames):
            break
        if frame_index != previous:
            yield frame_index
            previous = frame_index
        position += interval


def reset_model_trackers(model) -> int:
    """Reset tracker state between jobs while keeping per-frame persistence enabled.

    Passing ``persist=False`` to the first Ultralytics ``track`` call registers
    non-persistent callbacks that can reset IDs on every later frame. Resetting
    the tracker objects directly avoids cross-job leakage without that side effect.
    """
    predictor = getattr(model, "predictor", None)
    trackers = getattr(predictor, "trackers", None) or []
    reset_count = 0
    for tracker in trackers:
        reset = getattr(tracker, "reset", None)
        if callable(reset):
            reset()
            reset_count += 1
    return reset_count
