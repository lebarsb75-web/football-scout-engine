import os
import re
import uuid
from typing import Any, Optional

import requests
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl, model_validator

from api.costs import authorization_allows_submission, estimate_cost
from api.idempotency import IdempotencyPendingError, IdempotencyStore
from api.jobs import JobStore
from api.results import public_result
from api.security import (
    approval_secret_configured,
    approval_secret_matches,
    validate_video_url_for_submission,
)

app = FastAPI(title="Football Scout API", version="0.8.0")

RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
ENABLE_PAID_GPU = os.getenv("ENABLE_PAID_GPU", "false").lower() == "true"
GPU_PRICE_PER_HOUR = float(os.getenv("GPU_PRICE_PER_HOUR", "0.58"))
BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE = os.getenv(
    "BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE"
)
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{12,128}$")
SUBMISSION_CACHE = IdempotencyStore()
JOBS = JobStore()


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


class EngineResultPreviewRequest(BaseModel):
    engine_result: dict[str, Any]


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


def validate_idempotency_key(value: str | None) -> str:
    if not value or not IDEMPOTENCY_KEY_PATTERN.fullmatch(value):
        raise HTTPException(
            status_code=400,
            detail=(
                "X-Idempotency-Key is required and must contain 12-128 safe characters. "
                "Reuse the same key only when retrying the exact same submission."
            ),
        )
    return value


def get_cached_submission_or_none(key: str, payload: dict[str, Any]):
    try:
        return SUBMISSION_CACHE.get(key, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IdempotencyPendingError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "This analysis submission is already in progress. Do not retry with a "
                "new key because that could create a duplicate paid job."
            ),
        ) from exc


def reserve_submission_or_replay(key: str, payload: dict[str, Any]):
    try:
        return SUBMISSION_CACHE.reserve(key, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IdempotencyPendingError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "This analysis submission is already in progress. Keep the same "
                "idempotency key and wait for its recorded job instead of resubmitting."
            ),
        ) from exc


@app.get("/health")
def health():
    return {
        "status": "ok",
        "paid_gpu_enabled": ENABLE_PAID_GPU,
        "runpod_configured": bool(RUNPOD_ENDPOINT_ID and RUNPOD_API_KEY),
        "benchmark_available": benchmark_seconds_per_video_minute() is not None,
        "cost_approval_guard_configured": approval_secret_configured(),
        "video_host_allowlist_configured": bool(os.getenv("VIDEO_HOST_ALLOWLIST", "").strip()),
        "idempotency_guard": "sqlite_durable_single_host",
        "job_registry": "sqlite_local",
    }


@app.post("/analysis/estimate")
def analysis_estimate(request: AnalysisRequest):
    return build_estimate(request.video_duration_seconds)


@app.post("/analysis/result/preview")
def analysis_result_preview(request: EngineResultPreviewRequest):
    """Free/local transformation of raw engine output into user-safe metrics."""
    return public_result(request.engine_result)


@app.get("/analysis/jobs")
def analysis_jobs(limit: int = Query(default=20, ge=1, le=100)):
    """Return locally remembered jobs without contacting RunPod."""
    return {"jobs": [JOBS.public_dict(job) for job in JOBS.list_recent(limit)]}


def public_job_payload(job):
    payload = JOBS.public_dict(job)
    if job.engine_result is not None:
        payload["result"] = public_result(job.engine_result)
    return payload


@app.get("/analysis/jobs/{job_id}")
def analysis_job(job_id: str):
    """Return the last locally known state. This endpoint never spends GPU credit."""
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown analysis job") from exc
    return public_job_payload(job)


RUNPOD_STATUS_MAP = {
    "IN_QUEUE": "queued",
    "IN_PROGRESS": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "TIMED_OUT": "timed_out",
    "CANCELLED": "cancelled",
}


@app.post("/analysis/jobs/{job_id}/refresh")
def refresh_analysis_job(job_id: str):
    """Refresh a submitted job without starting another billable execution."""
    try:
        job = JOBS.get(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown analysis job") from exc

    if job.status in {"completed", "failed", "timed_out", "cancelled"}:
        return public_job_payload(job)
    if not RUNPOD_ENDPOINT_ID or not RUNPOD_API_KEY:
        raise HTTPException(status_code=503, detail="RunPod is not configured")

    url = (
        f"https://api.runpod.ai/v2/{RUNPOD_ENDPOINT_ID}/status/"
        f"{job.provider_job_id}"
    )
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {RUNPOD_API_KEY}"},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="RunPod status request failed") from exc
    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "RunPod status request was not successful.",
                "body": response.text[:1000],
            },
        )
    try:
        provider_response = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="RunPod returned invalid JSON") from exc

    provider_status = str(provider_response.get("status") or "").upper()
    status = RUNPOD_STATUS_MAP.get(provider_status, "unknown")
    output = provider_response.get("output")
    engine_result = output if status == "completed" and isinstance(output, dict) else None
    provider_error = None
    if status in {"failed", "timed_out", "cancelled"}:
        provider_error = str(provider_response.get("error") or status)[:1000]
    elif status == "completed" and engine_result is None:
        status = "failed"
        provider_error = "RunPod completed without a valid object result"

    updated = JOBS.update_from_provider(
        job_id,
        status=status,
        engine_result=engine_result,
        provider_error=provider_error,
    )
    return public_job_payload(updated)


@app.post("/analysis/submit")
def analysis_submit(
    request: SubmitRequest,
    x_cost_approval_secret: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
):
    # This endpoint intentionally fails closed behind several independent gates.
    # Changing only ENABLE_PAID_GPU is not sufficient to spend GPU credit.
    idempotency_key = validate_idempotency_key(x_idempotency_key)
    request_payload = request.model_dump(mode="json")

    cached = get_cached_submission_or_none(idempotency_key, request_payload)
    if cached is not None:
        return {**cached, "idempotent_replay": True}

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

    # Critical safety boundary: claim the key atomically before the first network
    # request that can create a billable job. A simultaneous retry will now fail
    # closed as pending rather than launching a second GPU job.
    replay = reserve_submission_or_replay(idempotency_key, request_payload)
    if replay is not None:
        return {**replay, "idempotent_replay": True}

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
        # Keep the reservation pending on ambiguity. A human/operator can inspect
        # the provider before deciding whether the key is safe to release; automatic
        # release here could duplicate a job after a network/proxy failure.
        raise HTTPException(
            status_code=502,
            detail={
                "message": (
                    "RunPod did not return a successful submission response. The "
                    "idempotency key remains reserved to prevent accidental double spend."
                ),
                "body": response.text[:1000],
            },
        )

    provider_response = response.json()
    provider_job_id = str(provider_response.get("id") or provider_response.get("jobId") or "")
    if not provider_job_id:
        raise HTTPException(
            status_code=502,
            detail=(
                "RunPod accepted the request but returned no job identifier. The "
                "idempotency key remains reserved for safety."
            ),
        )

    public_job_id = f"ana_{uuid.uuid4().hex}"
    job = JOBS.put(
        job_id=public_job_id,
        provider="runpod",
        provider_job_id=provider_job_id,
        status="submitted",
        cost_estimate=estimate,
        request_summary={
            "video_duration_seconds": request.video_duration_seconds,
            "target_time_seconds": request.target_time_seconds,
            "sample_fps": request.sample_fps,
            "image_size": request.image_size,
        },
    )

    result = {
        "submitted": True,
        "idempotent_replay": False,
        "job": JOBS.public_dict(job),
        "cost_estimate": estimate,
    }
    SUBMISSION_CACHE.put(idempotency_key, request_payload, result)
    return result
