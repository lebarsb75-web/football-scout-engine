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

## V2.2 changes after Test 01

Before any second paid test, `handler.py` was upgraded to `2.2-dev` with stricter safeguards:

- player re-identification now combines appearance, motion and bounding-box size consistency;
- same-ID candidates are rejected on implausible motion or weak appearance similarity;
- ball candidates are filtered for temporal continuity and proximity instead of trusting any COCO sports-ball detection;
- touch/possession requires two consecutive close-ball samples;
- ball reliability now uses a stricter gate and requires at least 30 sampled frames;
- player tracking quality is reported separately from overall quality;
- scene cuts reset ball continuity and motion state.

No RunPod request is triggered by these changes.

## Test 02 — representative match gameplay

Run only after explicit user approval.

Source: Wikimedia Commons — `2018 FIFA U-17 Women's World Cup - New Zealand vs Canada - 20.webm`

- duration: 37.544 s
- resolution: 1280 × 720
- license: CC BY-SA 4.0
- author: NaBUru38
- source page: https://commons.wikimedia.org/wiki/File:2018_FIFA_U-17_Women%27s_World_Cup_-_New_Zealand_vs_Canada_-_20.webm

This is much more representative of the intended product: a real match with multiple players on a pitch. It is used to inspect player identity recovery, ball visibility and timing performance.

## Sequence

1. Keep `main` untouched.
2. Use `dev-v2` as the test version.
3. Confirm at most one worker and no unintended queued jobs.
4. Obtain explicit user approval before every paid request.
5. Run the shortest relevant benchmark first.
6. Record RunPod execution time, result quality and actual billing signals.
7. Stop if the result is technically broken or unexpectedly slow.
8. Only then progress to longer representative tests.
9. Use measured longer-run data to estimate later 2 min, 10 min and 90 min tests.

## Why these clips

They are publicly accessible, short, football-specific and reusable under Creative Commons terms. The first is intentionally tiny to validate plumbing cheaply; the second is a real match segment for a meaningful first quality check.
