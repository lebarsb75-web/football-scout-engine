# Football Scout Engine

GPU video-analysis engine for the football scouting platform.

## Current development branch

`dev-v2` contains the safer second-generation prototype. It is deliberately not connected to the production RunPod endpoint yet, so code changes here do not spend RunPod GPU credit.

## RunPod input

```json
{
  "input": {
    "video_url": "https://temporary-url-to-match.mp4",
    "target_time_seconds": 12.0,
    "target": {"x": 0.51, "y": 0.63},
    "sample_fps": 5,
    "confidence": 0.22,
    "image_size": 960
  }
}
```

The platform will let the user pause on a frame and click the player. `target.x` and `target.y` are normalized coordinates from 0 to 1 on that selected frame.

## What v2 adds

- player selection at a chosen timestamp instead of assuming frame 1;
- appearance-based re-identification to help recover the selected player after temporary tracking loss;
- hard scene-cut detection;
- movement smoothing and rejection of implausible tracking jumps;
- ball-touch timestamps and possession intervals rather than only totals;
- tracking and ball-visibility quality metrics;
- explicit quality label so low-confidence results can be rejected instead of presented as reliable;
- safe input validation and video-size limits;
- optional pitch homography for real metric distance.

## Real distance calibration

A reliable distance in metres is not inferred from a fixed `meters_per_pixel` value because perspective makes that incorrect for a football broadcast camera.

When the future web interface has pitch calibration, the request can include corresponding image and pitch coordinates:

```json
{
  "pitch_calibration": {
    "image_points": [[120, 680], [1720, 680], [1450, 260], [430, 260]],
    "pitch_points_meters": [[0, 0], [105, 0], [105, 68], [0, 68]]
  }
}
```

At least four valid corresponding points are required. When calibration is absent, metric distance is intentionally omitted instead of inventing a value.

## Important status

This remains a development prototype. Touches, possession and player re-identification must be validated on representative football footage before commercial use. The platform should only expose analyses that pass an agreed quality threshold.
