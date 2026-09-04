# Football Scout Engine — Agent Operating Brief

## Mission
Build the football scouting platform end-to-end with minimal user intervention. The user should not be asked to make technical/product choices unless unavoidable. Take the lead on code, tests, GitHub, deployment, RunPod, cost control, backend, frontend, reports, storage, auth, and later payments.

## Repository / branch policy
- Repository: `lebarsb75-web/football-scout-engine`
- Work on `dev-v2`.
- Do not merge to `main` until controlled launch.
- Existing draft PR: #1 (`V2 — safer tracking, cost gate, web prototype`).

## RunPod budget / safety
- Current remaining RunPod credit: about $9.98.
- Treat this as the total development GPU budget ceiling.
- Keep max workers at 1.
- Prefer short representative tests; never debug on a 90-minute match.
- Progression: short smoke -> ~2 min -> ~10 min -> 90 min only after quality gates pass.
- Never raise max workers to 2 just because RunPod suggests it.
- Track actual spend and preserve budget.

## Current RunPod endpoint
- Name: `football-scout-engine`
- Endpoint ID: `47kdwxukrvp695`
- Queue based
- GPU: 16 GB, about $0.58/hour
- Max workers: 1
- Min/active workers: 0 when idle
- Idle timeout: 5 sec
- Execution timeout: 120 sec for short tests
- Branch target: `dev-v2`

## Current engine state
- Current intended engine: `2.4-dev`
- Model: `yolo11m.pt`
- V2.3 fixed forward seeding from `target_time_seconds` after V2.2 produced 0% coverage.
- V2.4 adds BoT-SORT camera-motion compensation, exact timestamp-based sampling, direct tracker reset between jobs, anchor-distance rejection, temporal continuity diagnostics, identity-churn gates, and fail-closed API result exposure.
- Local tests: 45 passing before RunPod deployment.
- Local 26 s panoramic benchmark: 97.3% coverage, 97.3% minimum-window coverage, 0.7 s longest gap, 5.0% re-identification rate, internal tracking gate passed.
- The same benchmark has only 9.2% ball visibility, so touches/possession remain hidden; distance remains hidden without calibration.
- This is not ground-truth validation. Annotated full-match validation is still required.

## Current RunPod deployment gate
- Before any new runtime test, verify that the active build contains `ENGINE_VERSION = "2.4-dev"`, the endpoint is Ready, minimum workers is 0 and maximum workers is 1.
- Verify current balance and GPU price before submission.
- RunPod credentials are not stored in the repository.

## Stable gameplay test source
Use this GitHub-hosted clip rather than Wikimedia (Wikimedia returned HTTP 429):
`https://raw.githubusercontent.com/AtomScott/SoccerTrack-v2/main/docs/assets/demo-gsr_and_bas.mp4`

Representative payload:
```json
{
  "input": {
    "video_url": "https://raw.githubusercontent.com/AtomScott/SoccerTrack-v2/main/docs/assets/demo-tracking.mp4",
    "target_time_seconds": 4.0,
    "target": {"x": 0.5949, "y": 0.3501},
    "sample_fps": 10,
    "confidence": 0.15,
    "image_size": 960,
    "max_video_mb": 100
  },
  "policy": {"ttl": 300000}
}
```

## Known benchmark results
### Test 01
- 6.63 s video
- 20 sampled frames at 3 fps
- RunPod execution: 37.13 s
- Pipeline worked end-to-end
- Approx compute cost at $0.58/h: ~$0.006

### Gameplay test on V2.2
- Video duration: 30 s
- 150 sampled frames at 5 fps
- Delay: 14.02 s
- RunPod execution: 7.36 s
- Engine processing: 7.23 s
- `tracking_coverage_percent`: 0
- `last_track_id`: null
- touches/possession: 0
- `ball_metrics_reliable`: false
- Anchor detection distance: ~85.6 px
- This test proved the selection step found a person, but tracking was not seeded correctly.

### Local panoramic test on V2.4
- Analysis duration: 26 s
- Resolution: 4096 x 1080
- 260 sampled frames at an exact 10 fps
- Local CPU processing: 53.58 s
- Tracking coverage: 97.3%
- Player tracking quality: 96.5%
- Minimum-window coverage: 97.3%
- Longest untracked gap: 0.7 s
- Re-identification rate: 5.0%
- Ball visibility: 9.2%, ball metrics hidden
- Internal continuity gate passed; ground-truth identity accuracy not yet measured

## Quality policy
Do not present unreliable stats as facts.
- Good: player quality >= 82 and coverage >= 80
- Usable with review: player quality >= 65 and coverage >= 60
- Otherwise insufficient
- Ball metrics should remain hidden unless their reliability gate passes.
- Metric distance must be omitted unless a valid static-camera pitch calibration is present.

## Platform state
Backend/API, local web prototype, contracts, scripts, tests, CI, and security guards already exist on `dev-v2`.
- `api/app.py`, `api/costs.py`
- `web/index.html`, `web/styles.css`, `web/app.js`
- `contracts/`
- `scripts/build_clips.py`, `scripts/render_report.py`, `scripts/cost_from_result.py`
- `.github/workflows/quality.yml`

## Execution style
- Do the work rather than asking the user what technical step to take.
- Prefer tool calls / direct GitHub and RunPod control.
- Only involve the user for account authentication, credentials, payment, or UI actions that the available tools truly cannot perform.
- Report concise progress and concrete outcomes.
