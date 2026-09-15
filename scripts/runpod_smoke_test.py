"""Fail-closed RunPod smoke test for the committed 26-second benchmark.

The command is read-only unless ``--execute`` is supplied.  Even in execute
mode it submits exactly one job, never retries a submission, and cancels the
known job if the wall-clock ceiling is reached.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from api.results import public_result


EXPECTED_ENDPOINT_ID = "47kdwxukrvp695"
EXPECTED_ENGINE_VERSION = "2.4-dev"
EXPECTED_PAYLOAD = {
    "input": {
        "video_url": "https://raw.githubusercontent.com/AtomScott/SoccerTrack-v2/main/docs/assets/demo-gsr_and_bas.mp4",
        "target_time_seconds": 4.0,
        "target": {"x": 0.5949, "y": 0.3501},
        "sample_fps": 10,
        "confidence": 0.15,
        "image_size": 960,
        "max_video_mb": 100,
    }
}
GRAPHQL_URL = "https://api.runpod.io/graphql"
CONTROL_BASE_URL = "https://api.runpod.io/v2"
INVOKE_BASE_URL = "https://api.runpod.ai/v2"
EXECUTION_TIMEOUT_MS = 120_000
REQUEST_TTL_MS = 300_000
MAX_FIRST_TEST_COST_USD = 0.05
MAX_WALL_SECONDS = 295


class SmokeTestError(RuntimeError):
    pass


def _number(value: Any, *, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SmokeTestError(f"Missing or invalid numeric field: {field}") from exc


def request_json(session: requests.Session, method: str, url: str, **kwargs) -> dict:
    try:
        response = session.request(method, url, timeout=45, **kwargs)
    except requests.RequestException as exc:
        raise SmokeTestError(f"RunPod request failed without a safe retry: {method} {url}") from exc
    if not response.ok:
        raise SmokeTestError(
            f"RunPod returned HTTP {response.status_code} for {method} {url}: "
            f"{response.text[:500]}"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise SmokeTestError(f"RunPod returned invalid JSON for {method} {url}") from exc
    if not isinstance(body, dict):
        raise SmokeTestError(f"RunPod returned a non-object response for {method} {url}")
    return body


def get_balance(session: requests.Session) -> dict:
    body = request_json(
        session,
        "POST",
        GRAPHQL_URL,
        json={
            "query": "query { myself { clientBalance currentSpendPerHr } }",
            "variables": {},
        },
    )
    if body.get("errors"):
        raise SmokeTestError(f"RunPod balance query failed: {body['errors']}")
    account = (body.get("data") or {}).get("myself")
    if not isinstance(account, dict):
        raise SmokeTestError("RunPod balance response did not contain data.myself")
    return {
        "client_balance_usd": _number(account.get("clientBalance"), field="clientBalance"),
        "current_spend_per_hour_usd": _number(
            account.get("currentSpendPerHr"), field="currentSpendPerHr"
        ),
    }


def load_exact_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload != EXPECTED_PAYLOAD:
        raise SmokeTestError(
            "Refusing to run: the payload is not the committed 26-second Test 02 contract"
        )
    return payload


def verify_local_engine_version(handler_path: Path) -> None:
    source = handler_path.read_text(encoding="utf-8")
    match = re.search(r'^ENGINE_VERSION\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
    if not match or match.group(1) != EXPECTED_ENGINE_VERSION:
        actual = match.group(1) if match else "missing"
        raise SmokeTestError(
            f"Local worker is {actual}; expected {EXPECTED_ENGINE_VERSION} before any paid request"
        )


def configured_serverless_price(endpoint: dict, catalog: dict) -> tuple[float, list[str]]:
    gpu = endpoint.get("gpu") or {}
    pools = gpu.get("pools") or []
    if not isinstance(pools, list) or not pools:
        raise SmokeTestError("Endpoint has no configured GPU pool")

    catalog_gpus = catalog.get("gpus")
    if not isinstance(catalog_gpus, list):
        raise SmokeTestError("RunPod GPU catalog did not contain a gpus list")
    matching = [item for item in catalog_gpus if item.get("pool") in pools]
    prices = {
        _number((item.get("price") or {}).get("serverless"), field="price.serverless")
        for item in matching
    }
    if not prices:
        raise SmokeTestError(f"No current Serverless price found for GPU pool(s): {pools}")
    if len(prices) != 1:
        raise SmokeTestError(f"GPU pools map to inconsistent Serverless prices: {sorted(prices)}")
    return prices.pop(), pools


def validate_preflight(
    endpoint: dict,
    workers: dict,
    health: dict,
    catalog: dict,
    balance: dict,
    *,
    endpoint_id: str,
    max_hourly_price: float,
    cost_ceiling_usd: float,
    max_wall_seconds: int,
) -> dict:
    if endpoint.get("id") != endpoint_id:
        raise SmokeTestError("RunPod returned a different endpoint")
    if endpoint.get("type") != "QUEUE":
        raise SmokeTestError("Endpoint must remain queue-based")

    scaling = endpoint.get("workers") or {}
    if scaling.get("min") != 0 or scaling.get("max") != 1:
        raise SmokeTestError(
            f"Unsafe worker limits: min={scaling.get('min')} max={scaling.get('max')} (required 0/1)"
        )
    idle_timeout = int(_number(scaling.get("idleTimeout"), field="workers.idleTimeout"))
    if idle_timeout > 5:
        raise SmokeTestError(f"Idle timeout is {idle_timeout}s; expected at most 5s")

    gpu = endpoint.get("gpu") or {}
    if gpu.get("count") != 1:
        raise SmokeTestError(f"Endpoint must use exactly one GPU, got {gpu.get('count')}")
    endpoint_timeout = int(_number(endpoint.get("timeout"), field="timeout"))
    if endpoint_timeout > EXECUTION_TIMEOUT_MS:
        raise SmokeTestError(
            f"Endpoint timeout is {endpoint_timeout}ms; expected at most {EXECUTION_TIMEOUT_MS}ms"
        )

    worker_summary = workers.get("summary") or {}
    active_worker_total = int(_number(worker_summary.get("total", 0), field="workers.summary.total"))
    if active_worker_total > 1:
        raise SmokeTestError(f"Endpoint has {active_worker_total} active workers; maximum is 1")
    for state in ("running", "initializing", "throttled", "unhealthy"):
        if int(_number(worker_summary.get(state, 0), field=f"workers.summary.{state}")):
            raise SmokeTestError(f"Endpoint has an unexpected {state} worker before the test")

    jobs = health.get("jobs") or {}
    for state in ("inQueue", "inProgress"):
        if int(_number(jobs.get(state, 0), field=f"health.jobs.{state}")):
            raise SmokeTestError(f"Endpoint already has a job {state}; refusing to add another")
    health_workers = health.get("workers") or {}
    health_worker_total = sum(
        int(value) for value in health_workers.values() if isinstance(value, (int, float))
    )
    if health_worker_total > 1:
        raise SmokeTestError(f"Job API health reports {health_worker_total} workers; maximum is 1")

    hourly_price, gpu_pools = configured_serverless_price(endpoint, catalog)
    if hourly_price > max_hourly_price:
        raise SmokeTestError(
            f"Current Serverless price ${hourly_price:.4f}/h exceeds approved ${max_hourly_price:.4f}/h"
        )
    conservative_cost = (max_wall_seconds + idle_timeout) / 3600.0 * hourly_price
    if conservative_cost > cost_ceiling_usd:
        raise SmokeTestError(
            f"Conservative first-test bound ${conservative_cost:.4f} exceeds ${cost_ceiling_usd:.4f}"
        )
    if balance["client_balance_usd"] < cost_ceiling_usd:
        raise SmokeTestError("RunPod balance is below the first-test cost ceiling")

    return {
        "endpoint_id": endpoint_id,
        "endpoint_name": endpoint.get("name"),
        "endpoint_type": endpoint.get("type"),
        "image": endpoint.get("image"),
        "gpu_pools": gpu_pools,
        "gpu_count": gpu.get("count"),
        "serverless_price_per_hour_usd": hourly_price,
        "workers_min": scaling.get("min"),
        "workers_max": scaling.get("max"),
        "active_workers": active_worker_total,
        "idle_timeout_seconds": idle_timeout,
        "execution_timeout_ms": endpoint_timeout,
        "queued_jobs": int(jobs.get("inQueue", 0)),
        "running_jobs": int(jobs.get("inProgress", 0)),
        "conservative_cost_bound_usd": round(conservative_cost, 4),
        "balance_before_usd": round(balance["client_balance_usd"], 4),
    }


def validate_engine_result(output: dict) -> dict:
    if output.get("status") != "completed":
        raise SmokeTestError(f"Worker did not complete successfully: {output.get('error', output)}")
    if output.get("engine_version") != EXPECTED_ENGINE_VERSION:
        raise SmokeTestError(
            f"Wrong engine version: {output.get('engine_version')} (expected {EXPECTED_ENGINE_VERSION})"
        )

    video = output.get("video") or {}
    player = output.get("player") or {}
    quality = output.get("quality") or {}
    coverage = _number(player.get("tracking_coverage_percent"), field="tracking coverage")
    player_quality = _number(
        quality.get("player_tracking_score_percent"), field="player tracking quality"
    )
    minimum_window = _number(
        quality.get("minimum_window_coverage_percent"), field="minimum window coverage"
    )
    longest_gap = _number(
        quality.get("longest_untracked_gap_seconds"), field="longest untracked gap"
    )
    reidentification_rate = _number(
        quality.get("reidentification_rate_percent"), field="re-identification rate"
    )
    identity_rejection_rate = _number(
        quality.get("identity_rejection_rate_percent"), field="identity rejection rate"
    )
    scene_cuts = int(_number(quality.get("scene_cuts_detected"), field="scene cuts"))

    gate_checks = {
        "player_found": player.get("last_track_id") is not None,
        "coverage_at_least_80": coverage >= 80.0,
        "player_quality_at_least_82": player_quality >= 82.0,
        "minimum_window_at_least_65": minimum_window >= 65.0,
        "longest_gap_at_most_5s": longest_gap <= 5.0,
        "no_scene_cut": scene_cuts == 0,
        "reidentification_at_most_5_percent": reidentification_rate <= 5.0,
        "identity_rejection_at_most_5_percent": identity_rejection_rate <= 5.0,
        "engine_continuity_gate": quality.get("tracking_continuity_reliable") is True,
        "quality_label_good": quality.get("label") == "good",
    }
    failed = [name for name, passed in gate_checks.items() if not passed]
    if failed:
        raise SmokeTestError(f"Tracking quality gates failed: {', '.join(failed)}")

    public = public_result(output)
    if public.get("status") != "ready" or public["quality"].get("tracking_pass") is not True:
        raise SmokeTestError("Public result transformation did not pass the tracking gate")

    calibration_used = quality.get("pitch_calibration_used") is True
    distance_available = public["metrics"]["distance_meters"]["available"]
    if not calibration_used and ("distance_meters_estimated" in player or distance_available):
        raise SmokeTestError("Distance was exposed without pitch calibration")

    ball_visibility = _number(quality.get("ball_visibility_percent"), field="ball visibility")
    ball_reliable = quality.get("ball_metrics_reliable") is True
    public_ball_available = any(
        public["metrics"][name]["available"]
        for name in ("ball_touches", "possession_seconds")
    )
    if not ball_reliable and (public_ball_available or public.get("clips")):
        raise SmokeTestError("Ball touches/possession escaped the reliability gate")

    duration = _number(video.get("analysis_duration_seconds"), field="analysis duration")
    if not 25.0 <= duration <= 27.0:
        raise SmokeTestError(f"Expected a 26-second analysis, got {duration:.2f}s")

    return {
        "passed": True,
        "engine_version": output.get("engine_version"),
        "processing_seconds": _number(output.get("processing_seconds"), field="processing time"),
        "analysis_duration_seconds": duration,
        "sampled_frames": int(_number(video.get("sampled_frames"), field="sampled frames")),
        "tracking_coverage_percent": coverage,
        "player_tracking_score_percent": player_quality,
        "quality_label": quality.get("label"),
        "minimum_window_coverage_percent": minimum_window,
        "longest_untracked_gap_seconds": longest_gap,
        "reidentification_rate_percent": reidentification_rate,
        "identity_rejection_rate_percent": identity_rejection_rate,
        "tracking_continuity_reliable": True,
        "ball_visibility_percent": ball_visibility,
        "ball_metrics_reliable": ball_reliable,
        "ball_metrics_exposed": public_ball_available,
        "pitch_calibration_used": calibration_used,
        "distance_meters_exposed": distance_available,
        "gate_checks": gate_checks,
    }


def cancel_job(session: requests.Session, endpoint_id: str, job_id: str) -> dict:
    return request_json(
        session,
        "POST",
        f"{INVOKE_BASE_URL}/{endpoint_id}/cancel/{job_id}",
    )


def poll_job(
    session: requests.Session,
    endpoint_id: str,
    job_id: str,
    *,
    poll_interval_seconds: float,
    max_wall_seconds: int,
) -> tuple[dict, float]:
    started = time.monotonic()
    while True:
        elapsed = time.monotonic() - started
        if elapsed >= max_wall_seconds:
            cancel_job(session, endpoint_id, job_id)
            raise SmokeTestError(
                f"Job reached the {max_wall_seconds}s wall-clock ceiling and was cancelled; do not retry"
            )
        status = request_json(
            session,
            "GET",
            f"{INVOKE_BASE_URL}/{endpoint_id}/status/{job_id}",
        )
        provider_status = str(status.get("status") or "").upper()
        if provider_status in {"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED"}:
            return status, elapsed
        time.sleep(poll_interval_seconds)


def write_record(output_dir: Path, record: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"runpod-v24-26s-{stamp}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Submit one paid 26-second job")
    parser.add_argument("--endpoint-id", default=EXPECTED_ENDPOINT_ID)
    parser.add_argument("--payload", type=Path, default=Path("benchmarks/test-02-gameplay.json"))
    parser.add_argument("--handler", type=Path, default=Path("handler.py"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/runpod"))
    parser.add_argument("--max-hourly-price", type=float, default=0.58)
    parser.add_argument("--cost-ceiling-usd", type=float, default=MAX_FIRST_TEST_COST_USD)
    parser.add_argument("--max-wall-seconds", type=int, default=MAX_WALL_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=3.0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.endpoint_id != EXPECTED_ENDPOINT_ID:
        raise SystemExit(f"Refusing endpoint {args.endpoint_id}; expected {EXPECTED_ENDPOINT_ID}")
    if args.cost_ceiling_usd > MAX_FIRST_TEST_COST_USD:
        raise SystemExit(f"First-test ceiling cannot exceed ${MAX_FIRST_TEST_COST_USD:.2f}")
    if args.max_wall_seconds > MAX_WALL_SECONDS:
        raise SystemExit(f"Wall-clock ceiling cannot exceed {MAX_WALL_SECONDS}s")

    api_key = os.getenv("RUNPOD_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("RUNPOD_API_KEY is required; never commit or print it")

    payload = load_exact_payload(args.payload)
    verify_local_engine_version(args.handler)
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {api_key}"})

    endpoint = request_json(
        session, "GET", f"{CONTROL_BASE_URL}/serverless/{args.endpoint_id}"
    )
    workers = request_json(
        session, "GET", f"{CONTROL_BASE_URL}/serverless/{args.endpoint_id}/workers"
    )
    health = request_json(
        session, "GET", f"{INVOKE_BASE_URL}/{args.endpoint_id}/health"
    )
    catalog = request_json(
        session,
        "GET",
        f"{CONTROL_BASE_URL}/catalog/gpus",
        params={"include": "AVAILABILITY", "product": "SERVERLESS"},
    )
    balance_before = get_balance(session)
    preflight = validate_preflight(
        endpoint,
        workers,
        health,
        catalog,
        balance_before,
        endpoint_id=args.endpoint_id,
        max_hourly_price=args.max_hourly_price,
        cost_ceiling_usd=args.cost_ceiling_usd,
        max_wall_seconds=args.max_wall_seconds,
    )
    print(json.dumps({"mode": "preflight", "passed": True, **preflight}, indent=2))
    if not args.execute:
        return

    request_payload = copy.deepcopy(payload)
    request_payload["policy"] = {
        "executionTimeout": EXECUTION_TIMEOUT_MS,
        "ttl": REQUEST_TTL_MS,
    }
    submitted_at = datetime.now(timezone.utc).isoformat()
    submission = request_json(
        session,
        "POST",
        f"{INVOKE_BASE_URL}/{args.endpoint_id}/run",
        json=request_payload,
    )
    job_id = str(submission.get("id") or "")
    if not job_id:
        raise SmokeTestError("RunPod submission returned no job ID; do not resubmit")
    print(json.dumps({"mode": "submitted", "job_id": job_id, "status": submission.get("status")}))

    provider_result, poll_elapsed_seconds = poll_job(
        session,
        args.endpoint_id,
        job_id,
        poll_interval_seconds=args.poll_interval_seconds,
        max_wall_seconds=args.max_wall_seconds,
    )
    balance_after = get_balance(session)
    output = provider_result.get("output")
    if not isinstance(output, dict):
        validation = {"passed": False, "reason": "provider_result_has_no_object_output"}
    else:
        try:
            validation = validate_engine_result(output)
        except SmokeTestError as exc:
            validation = {"passed": False, "reason": str(exc)}

    execution_ms = _number(provider_result.get("executionTime", 0), field="executionTime")
    unit_price = preflight["serverless_price_per_hour_usd"]
    estimated_execution_cost = execution_ms / 3_600_000.0 * unit_price
    balance_delta = max(
        0.0,
        balance_before["client_balance_usd"] - balance_after["client_balance_usd"],
    )
    record = {
        "test": "v2.4 26-second panoramic RunPod smoke",
        "submitted_at": submitted_at,
        "endpoint_preflight": preflight,
        "request": request_payload,
        "job_id": job_id,
        "provider_status": provider_result.get("status"),
        "provider_execution_time_ms": execution_ms,
        "provider_delay_time_ms": provider_result.get("delayTime"),
        "poll_elapsed_seconds": round(poll_elapsed_seconds, 2),
        "estimated_execution_cost_usd": round(estimated_execution_cost, 6),
        "balance_before": balance_before,
        "balance_after": balance_after,
        "observed_balance_delta_usd": round(balance_delta, 6),
        "validation": validation,
        "provider_result": provider_result,
    }
    record_path = write_record(args.output_dir, record)
    safe_summary = {
        "job_id": job_id,
        "provider_status": provider_result.get("status"),
        "estimated_execution_cost_usd": round(estimated_execution_cost, 6),
        "observed_balance_delta_usd": round(balance_delta, 6),
        "validation": validation,
        "record_path": str(record_path),
    }
    print(json.dumps(safe_summary, indent=2))
    if provider_result.get("status") != "COMPLETED":
        raise SystemExit("RunPod job did not complete; inspect the saved record and do not retry")
    if not validation.get("passed"):
        raise SystemExit("RunPod output failed validation; inspect the saved record and do not retry")


if __name__ == "__main__":
    main()
