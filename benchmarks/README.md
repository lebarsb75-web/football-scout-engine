# Benchmark plan

This folder prepares the first paid RunPod validation without launching anything.

## Safety rule

Nothing in this folder calls RunPod. `ENABLE_PAID_GPU=false` stays unchanged. A paid request must only be sent after explicit user approval.

## Test 01 — technical smoke test

Purpose: verify that the dev-v2 container downloads a real football clip, opens WebM correctly, detects a person, tracks an identity, and returns a structured result.

Source: Wikimedia Commons — `Kylian Mbappe at Real Madrid's UEFA Champions League game versus Juventus Turin on 22 October 2025 (video).webm`

- duration: 6.6 s
- resolution: 2160 × 3840
- license: CC BY-SA 4.0
- author: SdHb
- source page: https://commons.wikimedia.org/wiki/File:Kylian_Mbappe_at_Real_Madrid%27s_UEFA_Champions_League_game_versus_Juventus_Turin_on_22_October_2025_(video).webm

The request uses a conservative 3 sampled frames/s and 640px inference size to keep the first GPU use very small. The selected player is the person nearest the centre of the frame at 1.5 seconds.

## Test 02 — representative match gameplay

Run only if Test 01 completes technically.

Source: Wikimedia Commons — `2018 FIFA U-17 Women's World Cup - New Zealand vs Canada - 20.webm`

- duration: 37.544 s
- resolution: 1280 × 720
- license: CC BY-SA 4.0
- author: NaBUru38
- source page: https://commons.wikimedia.org/wiki/File:2018_FIFA_U-17_Women%27s_World_Cup_-_New_Zealand_vs_Canada_-_20.webm

This is much more representative of the intended product: a real match with multiple players on a pitch. It is used to inspect player identity recovery, ball visibility and timing performance.

## Sequence

1. Keep the current `main` endpoint untouched.
2. Build/deploy `dev-v2` as the test version without sending a request.
3. Confirm `0 running workers` before the test.
4. Obtain explicit user approval for the paid smoke test.
5. Send only `test-01-technical.json`.
6. Record RunPod execution time and result quality.
7. Stop if the result is technically broken or unexpectedly slow.
8. Only after a successful smoke test, ask for approval before `test-02-gameplay.json`.
9. Use measured GPU seconds/video minute to estimate later 2 min, 10 min and 90 min tests.

## Why these clips

They are publicly accessible, short, football-specific and reusable under Creative Commons terms. The first is intentionally tiny to validate plumbing cheaply; the second is a real match segment for a meaningful first quality check.
