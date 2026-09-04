# RunPod staging benchmark — safe procedure

Purpose: validate `dev-v2` on a real GPU without touching production `main` and without risking more than the explicitly approved small test budget.

## Non-negotiable safeguards

- Do not merge `dev-v2` into `main` for this benchmark.
- Keep the current production endpoint on `main` unchanged.
- Use a cloned staging endpoint tracking `dev-v2`.
- Minimum workers: 0.
- Maximum workers: 1.
- Use the same 16 GB GPU class currently selected unless availability forces a manual review.
- Do not increase workers if RunPod suggests it.
- First request is only `benchmarks/test-01-technical.json`.
- Do not run `test-02-gameplay.json` until test 01 is reviewed.
- Approved initial spend ceiling: approximately USD 0.05. Stop if configuration or pricing differs materially from the expected USD 0.58/hour GPU rate.

## Staging endpoint creation

From the current endpoint, choose **Clone Endpoint**. In Repository Configuration select:

- repository: `lebarsb75-web/football-scout-engine`
- branch: `dev-v2`
- Dockerfile path: `/Dockerfile`
- endpoint type: Queue
- endpoint name: `football-scout-engine-dev-v2`
- workers min: 0
- workers max: 1

Build the endpoint and wait until the build is `Completed` / endpoint `Ready` before sending any request.

## First paid request

Use `benchmarks/test-01-technical.json` exactly as committed. It is intentionally tiny: a 6.6-second Creative Commons football video, low inference size, and only 3 sampled frames per second.

If the RunPod request UI exposes an execution timeout, set it to 120 seconds for this first smoke test. If the UI does not expose this value, do not change unrelated endpoint settings just to add it.

## Stop conditions

Stop after the first request if any of these occurs:

- worker fails to start;
- model/container error;
- video download error;
- no player found around the selection point;
- request approaches the timeout;
- unexpected worker count > 1;
- GPU price differs materially from the expected rate;
- balance reduction appears inconsistent with a tiny smoke test.

Do not retry blindly. Inspect logs first and fix the cause on `dev-v2`.

## What to record after the request

Capture and save:

- RunPod job status;
- total worker/run time if shown;
- returned JSON;
- `processing_seconds`;
- tracking coverage;
- quality score and label;
- ball visibility;
- balance before/after if visible.

Then calculate observed cost with `scripts/cost_from_result.py` and only after that decide whether the 38-second gameplay benchmark is justified.
