import os
from typing import Optional

import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator

from api.costs import authorization_allows_submission, estimate_cost
from api.security import (
    approval_secret_configured,
    approval_secret_matches,
    validate_video_url_for_submission,
)

app = FastAPI(title="Football Scout API", version="0.3.0")

RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
ENABLE_PAID_GPU = os.getenv("ENABLE_PAID_GPU", "false").lower() == "true"
GPU_PRICE_PER_HOUR = float(os.getenv("GPU_PRICE_PER_HOUR", "0.58"))
BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE = os.getenv(
    "BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE"
)


class Target(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class AnalysisRequest(BaseModel):
    video_url: HttpUrl
    video_duration_seconds: float = Field(gt=0, le=6 * 60 * 60)
    target: Target
    target_time_seconds: float = Field(ge=0)
    sample_fps: float = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=0.22, ge=0.1, le=0.9)
    image_size: int = Field(default=960, ge=640, le=1280)

    @model_validator(mode="after")
    def selected_frame_must_be_inside_video(self):
        if self.target_time_seconds >= self.video_duration_seconds:
            raise ValueError("target_time_seconds must be inside the video duration")
        return self


class SubmitRequest(AnalysisRequest):
    approved_max_cost_usd: float = Field(gt=0, le=25)


def benchmark_seconds_per_video_minute() -> Optional[float]:
    if not BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE:
        return None
    value = float(BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE)
    return value if value > 0 else None


def build_estimate(duration_seconds: float):
    return estimate_cost(
        duration_seconds=duration_seconds,
        gpu_price_per_hour=GPU_PRICE_PER_HOUR,
        gpu_seconds_per_video_minute=benchmark_seconds_per_video_minute(),
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "paid_gpu_enabled": ENABLE_PAID_GPU,
        "runpod_configured": bool(RUNPOD_ENDPOINT_ID and RUNPOD_API_KEY),
        "benchmark_available": benchmark_seconds_per_video_minute() is not None,
        "cost_approval_guard_configured": approval_secret_configured(),
        "video_host_allowlist_configured": bool(os.getenv("VIDEO_HOST_ALLOWLIST", "").strip()),
    }


@app.post("/analysis/estimate")
def analysis_estimate(request: AnalysisRequest):
    return build_estimate(request.video_duration_seconds)


@app.post("/analysis/submit")
def analysis_submit(
    request: SubmitRequest,
    x_cost_approval_secret: str | None = Header(default=None),
):
    # This endpoint intentionally fails closed behind several independent gates.
    # Changing only ENABLE_PAID_GPU is not sufficient to spend GPU credit.
    if not ENABLE_PAID_GPU:
        raise HTTPException(
            status_code=423,
            detail="Paid GPU execution is locked. Set ENABLE_PAID_GPU=true only after explicit approval.",
        )
    if not approval_secret_configured():
        raise HTTPException(
            status_code=423,
            detail="Paid GPU execution is locked until COST_APPROVAL_SECRET is configured.",
        )
    if not approval_secret_matches(x_cost_approval_secret):
        raise HTTPException(status_code=403, detail="Invalid cost approval secret")
    if not RUNPOD_ENDPOINT_ID or not RUNPOD_API_KEY:
        raise HTTPException(status_code=503, detail="RunPod is not configured")

    try:
        validate_video_url_for_submission(str(request.video_url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    estimate = build_estimate(request.video_duration_seconds)
    if not estimate.get("ready"):
        raise HTTPException(
            status_code=412,
            detail="A measured short-video benchmark is required before paid execution.",
        )

    if not authorization_allows_submission(estimate, request.approved_max_cost_usd):
        raise HTTPException(
            status_code=412,
            detail={
                "message": "Estimated cost exceeds the user-approved maximum.",
                "estimate": estimate,
                "approved_max_cost_usd": request.approved_max_cost_usd,
            },
        )

    url = f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/run"
    payload = {
        "input": {
            "video_url": str(request.video_url),
            "target": request.target.model_dump(),
            "target_time_seconds": request.target_time_seconds,
            "sample_fps": request.sample_fps,
            "confidence": request.confidence,
            "image_size": request.image_size,
        }
    }
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
        json=payload,
        timeout=30,
    )
    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail={"message": "RunPod rejected the job", "body": response.text[:1000]},
        )
    return {"submitted": True, "cost_estimate": estimate, "runpod": response.json()}
