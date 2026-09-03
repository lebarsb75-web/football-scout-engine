from copy import deepcopy
from typing import Any


MIN_TRACKING_COVERAGE = 75.0
MIN_BALL_VISIBILITY = 18.0
MIN_OVERALL_QUALITY = 65.0


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def public_result(engine_result: dict[str, Any]) -> dict[str, Any]:
    """Convert raw engine output into a user-facing, fail-closed result.

    Raw computer-vision values are not automatically treated as trustworthy.
    Each metric is exposed only when the evidence needed for that metric clears
    explicit thresholds. The raw result can still be retained for internal QA.
    """
    if engine_result.get("status") != "completed":
        return {
            "status": "unavailable",
            "reason": "engine_not_completed",
            "metrics": {},
        }

    player = engine_result.get("player") or {}
    quality = engine_result.get("quality") or {}
    tracking = _number(player.get("tracking_coverage_percent"))
    ball_visibility = _number(quality.get("ball_visibility_percent"))
    quality_score = _number(quality.get("score_percent"))
    calibration_used = bool(quality.get("pitch_calibration_used"))

    overall_ok = quality_score >= MIN_OVERALL_QUALITY
    tracking_ok = tracking >= MIN_TRACKING_COVERAGE and overall_ok
    ball_ok = tracking_ok and ball_visibility >= MIN_BALL_VISIBILITY

    metrics: dict[str, Any] = {
        "tracking_coverage_percent": {
            "available": True,
            "value": round(tracking, 1),
            "confidence": "diagnostic",
        },
        "distance_meters": {
            "available": bool(tracking_ok and calibration_used and "distance_meters_estimated" in player),
        },
        "ball_touches": {
            "available": bool(ball_ok and "ball_touches_estimated" in player),
        },
        "possession_seconds": {
            "available": bool(ball_ok and "possession_seconds_estimated" in player),
        },
    }

    if metrics["distance_meters"]["available"]:
        metrics["distance_meters"].update(
            value=round(_number(player["distance_meters_estimated"]), 1),
            confidence="estimated",
        )
    else:
        metrics["distance_meters"]["reason"] = (
            "pitch_calibration_required" if not calibration_used else "tracking_quality_too_low"
        )

    if metrics["ball_touches"]["available"]:
        metrics["ball_touches"].update(
            value=int(player["ball_touches_estimated"]),
            confidence="estimated",
        )
    else:
        metrics["ball_touches"]["reason"] = "ball_or_tracking_quality_too_low"

    if metrics["possession_seconds"]["available"]:
        metrics["possession_seconds"].update(
            value=round(_number(player["possession_seconds_estimated"]), 1),
            confidence="estimated",
        )
    else:
        metrics["possession_seconds"]["reason"] = "ball_or_tracking_quality_too_low"

    public_clips = []
    if ball_ok:
        for clip in deepcopy(engine_result.get("clips") or []):
            if isinstance(clip, dict) and clip.get("type") in {"touch", "possession"}:
                public_clips.append(clip)

    return {
        "status": "ready" if tracking_ok else "review_required",
        "engine_version": engine_result.get("engine_version"),
        "quality": {
            "score_percent": round(quality_score, 1),
            "tracking_coverage_percent": round(tracking, 1),
            "ball_visibility_percent": round(ball_visibility, 1),
            "tracking_pass": tracking_ok,
            "ball_metrics_pass": ball_ok,
            "pitch_calibration_used": calibration_used,
        },
        "metrics": metrics,
        "clips": public_clips,
        "notice": "Computer-vision statistics are estimates and are exposed only when quality gates pass.",
    }
