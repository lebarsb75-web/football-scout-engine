def estimate_cost(
    duration_seconds: float,
    gpu_price_per_hour: float,
    gpu_seconds_per_video_minute: float | None,
    safety_margin: float = 1.35,
):
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")
    if gpu_price_per_hour <= 0:
        raise ValueError("gpu_price_per_hour must be > 0")
    if safety_margin < 1:
        raise ValueError("safety_margin must be >= 1")

    if gpu_seconds_per_video_minute is None or gpu_seconds_per_video_minute <= 0:
        return {
            "ready": False,
            "reason": "benchmark_required",
            "message": "A measured short-video benchmark is required before paid execution.",
        }

    video_minutes = duration_seconds / 60.0
    estimated_gpu_seconds = video_minutes * gpu_seconds_per_video_minute
    estimated_cost = estimated_gpu_seconds / 3600.0 * gpu_price_per_hour
    recommended_limit = estimated_cost * safety_margin

    return {
        "ready": True,
        "gpu_price_per_hour_usd": round(gpu_price_per_hour, 4),
        "benchmark_gpu_seconds_per_video_minute": round(
            gpu_seconds_per_video_minute, 3
        ),
        "estimated_gpu_seconds": round(estimated_gpu_seconds, 1),
        "estimated_cost_usd": round(estimated_cost, 4),
        "recommended_max_authorization_usd": round(recommended_limit, 4),
        "safety_margin": round(safety_margin, 3),
    }


def authorization_allows_submission(estimate: dict, approved_max_cost_usd: float) -> bool:
    if not estimate.get("ready"):
        return False
    if approved_max_cost_usd <= 0:
        return False
    return estimate["recommended_max_authorization_usd"] <= approved_max_cost_usd
