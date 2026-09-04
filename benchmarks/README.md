# Benchmark plan

This folder prepares controlled RunPod validation without launching anything automatically.

## Safety rule

Nothing in this folder calls RunPod. `ENABLE_PAID_GPU=false` stays unchanged. A paid request must only be sent after explicit user approval.

## Test 01 — technical smoke test

Purpose: verify that the dev-v2 container downloads a real football clip, opens WebM correctly, detects a person, tracks an identity, and returns a structured result.

Source: Wikimedia Commons — `Kylian Mbappe at Real Madrid's UEFA Champions League game versus Juventus Turin on 22 October 2025 (video).webm`

- duration: 6.63 s
- resolution: 2160 × 3840
- license: CC BY-SA 4.0
- author: SdHb
- source page: https://commons.wikimedia.org/wiki/File:Kylian_Mbappe_at_Real_Madrid%27s_UEFA_Champions_League_game_versus_Juventus_Turin_on_22_October_2025_(video).webm
- sampled frames: 20 at 3 fps
- RunPod queue delay observed: 10.25 s
- RunPod execution time observed: 37.13 s
- approximate compute-only cost at $0.58/hour: $0.0060
- result: COMPLETED

The first paid smoke test therefore validated the full request/download/inference/response pipeline. Its ball-derived metrics were below the reliability gate, so they were correctly marked as unverified rather than presented as facts.

Measured execution ratio for this smoke test: about 336 GPU execution seconds per video minute (`37.13 / (6.63 / 60)`). This is only a cold-start/ultra-short benchmark and must not be extrapolated blindly to a 90-minute match; representative longer benchmarks are required.

## V2.4 changes after Test 01

Before any new paid test, `handler.py` was upgraded to `2.4-dev` with stricter safeguards:

- player re-identification now combines appearance, motion and bounding-box size consistency;
- same-ID candidates are rejected on implausible motion or weak appearance similarity;
- ball candidates are filtered for temporal continuity and proximity instead of trusting any COCO sports-ball detection;
- touch/possession requires two consecutive close-ball samples;
- ball reliability now uses a stricter gate and requires at least 30 sampled frames;
- player tracking quality is reported separately from overall quality;
- scene cuts reset ball continuity and motion state.
- BoT-SORT compensates camera motion on broadcast/panoramic footage;
- sampling is timestamp-based and exact, including when source FPS differs from the request;
- trackers are reset explicitly between serverless jobs;
- the public API requires window coverage, maximum gap and identity-churn gates.

No RunPod request is triggered by these changes.

## Test 02 — representative match gameplay

Run only after explicit user approval.

Source: SoccerTrack v2 public demo — `demo-gsr_and_bas.mp4`

- duration: 30 s (26 s analyzed after the selection frame)
- resolution: 4096 × 1080
- source: https://github.com/AtomScott/SoccerTrack-v2/blob/main/docs/assets/demo-gsr_and_bas.mp4
- request: 10 fps, 960 px inference, 260 exact samples

This panoramic footage is more representative of a full-match camera than the lower-resolution overlay demo. It is used to inspect identity continuity, ball visibility and timing performance. Its public video has no frame-level ground truth in this repository, so passing the automatic gate is not an accuracy claim.

## Free local V2.4 baseline

`local-panoramic-v24.json` records the reproducible local CPU result:

- 97.3% tracking coverage;
- 97.3% minimum-window coverage;
- 0.7 s longest untracked gap;
- 96.5% player tracking score;
- 5.0% re-identification rate;
- internal tracking continuity gate passed;
- 9.2% ball visibility, therefore ball metrics failed closed;
- no metric distance without pitch calibration.

The next GPU run must reproduce or improve the tracking diagnostics. Validation against labelled footage remains mandatory before a full-match reliability claim.

## Sequence

1. Keep `main` untouched.
2. Use `dev-v2` as the test version.
3. Confirm at most one worker and no unintended queued jobs.
4. Stay inside the previously approved first-test ceiling (~USD 0.05); notify the user before any higher spend.
5. Run the shortest relevant benchmark first.
6. Record RunPod execution time, result quality and actual billing signals.
7. Stop if the result is technically broken or unexpectedly slow.
8. Only then progress to longer representative tests.
9. Use measured longer-run data to estimate later 2 min, 10 min and 90 min tests.

## Why these clips

They are publicly accessible, short and football-specific. The first is intentionally tiny to validate plumbing cheaply; the second is panoramic match footage for a meaningful continuity check.
