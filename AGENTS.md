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
- Current intended engine: `2.3-dev`
- Model: `yolo11m.pt`
- The 2.2 gameplay test completed technically but produced 0% tracking coverage.
- Root cause identified: anchor selection worked, but the tracking loop tried to recover identity from frame 0 instead of seeding from the selected frame.
- V2.3 changes start tracking at `target_time_seconds`, hard-lock the first sampled frame to the selected player, and continue identity recovery forward.
- Commit implementing V2.3: `6bad22cca4eb701f1162cbefd773274fd7cd2a4a`.

## Current RunPod build issue
- RunPod rolled back V2.3 to a previous build after the build did not become active.
- A fresh commit was pushed to force a rebuild after rollback.
- Before any new runtime test, verify that the active build actually contains `ENGINE_VERSION = "2.3-dev"` and that the endpoint is Ready.

## Stable gameplay test source
Use this GitHub-hosted clip rather than Wikimedia (Wikimedia returned HTTP 429):
`https://raw.githubusercontent.com/AtomScott/SoccerTrack-v2/main/docs/assets/demo-tracking.mp4`

Representative payload:
```json
{
  "input": {
    "video_url": "https://raw.githubusercontent.com/AtomScott/SoccerTrack-v2/main/docs/assets/demo-tracking.mp4",
    "target_time_seconds": 3.0,
    "target": {"x": 0.5, "y": 0.55},
    "sample_fps": 5,
    "confidence": 0.22,
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
