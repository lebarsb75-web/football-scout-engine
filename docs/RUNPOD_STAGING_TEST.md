# RunPod staging benchmark — safe procedure

Purpose: validate `dev-v2` on a real GPU without touching production `main` and without risking more than the explicitly approved small test budget.

## Non-negotiable safeguards

- Do not merge `dev-v2` into `main` for this benchmark.
- Keep `main` unchanged.
- Use the existing endpoint only after confirming it tracks `dev-v2`, or a cloned staging endpoint tracking `dev-v2`.
- Minimum workers: 0.
- Maximum workers: 1.
- Use the same 16 GB GPU class currently selected unless availability forces a manual review.
- Do not increase workers if RunPod suggests it.
- Do not rerun the already successful V2.1 smoke test unless endpoint plumbing has changed.
- First V2.4 request is `benchmarks/test-02-gameplay.json` and must remain below the previously approved ~USD 0.05 ceiling.
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

Build the endpoint and wait until the build is `Completed` / endpoint `Ready` before sending any request. Confirm from the returned result that `engine_version` is exactly `2.4-dev`; stop on any older version.

## First V2.4 paid request

Use `benchmarks/test-02-gameplay.json` exactly as committed. It analyzes 26 seconds of panoramic match footage at an exact 10 fps. Compare it with `benchmarks/local-panoramic-v24.json`.

Keep the 120-second execution timeout for this test. Do not increase it until the short result passes and longer-run timing justifies a bounded value.

## Stop conditions

Stop after the first request if any of these occurs:

- worker fails to start;
- model/container error;
- video download error;
- engine version is not `2.4-dev`;
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

Then calculate observed cost with `scripts/cost_from_result.py`. Progress to a 2-minute excerpt only if identity continuity is visually reviewed, the automatic tracking gate passes, and projected spend remains inside the next explicitly communicated ceiling.
