import math
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import requests
import runpod
from ultralytics import YOLO

MODEL_NAME = "yolo11m.pt"
MODEL = YOLO(MODEL_NAME)
PERSON_CLASS = 0
BALL_CLASS = 32


def clamp(value, low, high):
    return max(low, min(float(value), high))


def center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def foot_point(box):
    x1, _, x2, y2 = box
    return ((x1 + x2) / 2.0, y2)


def euclidean(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def download_video(url: str, destination: Path, max_mb: int = 4096) -> int:
    max_bytes = max_mb * 1024 * 1024
    written = 0
    headers = {"User-Agent": "football-scout-engine/2.0"}
    with requests.get(url, stream=True, timeout=(30, 300), headers=headers) as response:
        response.raise_for_status()
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError(f"Video exceeds maximum allowed size of {max_mb} MB")
        with destination.open("wb") as file:
            for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(f"Video exceeds maximum allowed size of {max_mb} MB")
                file.write(chunk)
    if written == 0:
        raise ValueError("Downloaded video is empty")
    return written


def safe_crop(frame, box, torso_only=True):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    if torso_only:
        bh = y2 - y1
        y1 = y1 + int(0.12 * bh)
        y2 = y1 + int(0.48 * bh)
    crop = frame[y1:y2, x1:x2]
    return crop if crop.size else None


def appearance_signature(frame, box):
    crop = safe_crop(frame, box, torso_only=True)
    if crop is None or crop.shape[0] < 6 or crop.shape[1] < 4:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L1)
    return hist


def appearance_similarity(reference, candidate):
    if reference is None or candidate is None:
        return 0.0
    distance = cv2.compareHist(reference, candidate, cv2.HISTCMP_BHATTACHARYYA)
    return float(max(0.0, 1.0 - distance))


def blend_signature(reference, candidate, alpha=0.08):
    if candidate is None:
        return reference
    if reference is None:
        return candidate.copy()
    mixed = (1.0 - alpha) * reference + alpha * candidate
    cv2.normalize(mixed, mixed, alpha=1.0, norm_type=cv2.NORM_L1)
    return mixed


def scene_signature(frame):
    small = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    return gray.astype(np.float32)


def is_hard_scene_cut(previous, current, threshold=42.0):
    if previous is None:
        return False
    return float(np.mean(np.abs(previous - current))) >= threshold


def parse_detections(result):
    people, balls = [], []
    if result.boxes is None:
        return people, balls
    boxes = result.boxes.xyxy.cpu().tolist()
    classes = result.boxes.cls.int().cpu().tolist()
    confidences = result.boxes.conf.cpu().tolist()
    if result.boxes.id is not None:
        ids = result.boxes.id.int().cpu().tolist()
    else:
        ids = [None] * len(boxes)
    for box, cls, conf, track_id in zip(boxes, classes, confidences, ids):
        item = {
            "box": box,
            "center": center(box),
            "foot": foot_point(box),
            "id": track_id,
            "confidence": float(conf),
        }
        if cls == PERSON_CLASS:
            people.append(item)
        elif cls == BALL_CLASS:
            balls.append(item)
    return people, balls


def choose_anchor_player(frame, people, target_point):
    if not people:
        return None
    frame_diag = math.hypot(frame.shape[1], frame.shape[0]) or 1.0
    return min(
        people,
        key=lambda p: euclidean(p["center"], target_point) / frame_diag
        - 0.04 * p["confidence"],
    )


def choose_reidentified_player(frame, people, previous_center, reference_signature):
    if not people:
        return None, 0.0
    diag = math.hypot(frame.shape[1], frame.shape[0]) or 1.0
    scored = []
    for person in people:
        signature = appearance_signature(frame, person["box"])
        app = appearance_similarity(reference_signature, signature)
        if previous_center is None:
            motion = 0.5
        else:
            motion_distance = euclidean(person["center"], previous_center) / diag
            motion = max(0.0, 1.0 - motion_distance / 0.16)
        size = max(1.0, person["box"][3] - person["box"][1]) / max(1.0, frame.shape[0])
        score = 0.62 * app + 0.30 * motion + 0.05 * person["confidence"] + 0.03 * min(size * 10.0, 1.0)
        scored.append((score, app, person, signature))
    scored.sort(key=lambda row: row[0], reverse=True)
    best = scored[0]
    if best[0] < 0.38:
        return None, best[0]
    best[2]["signature"] = best[3]
    best[2]["appearance_similarity"] = best[1]
    return best[2], best[0]


def make_homography(calibration):
    if not calibration:
        return None
    image_points = calibration.get("image_points")
    pitch_points = calibration.get("pitch_points_meters")
    if not image_points or not pitch_points or len(image_points) < 4 or len(pitch_points) < 4:
        return None
    src = np.array(image_points, dtype=np.float32)
    dst = np.array(pitch_points, dtype=np.float32)
    if src.shape[1] != 2 or dst.shape[1] != 2 or src.shape[0] != dst.shape[0]:
        return None
    matrix, _ = cv2.findHomography(src, dst, method=0)
    return matrix


def project_to_pitch(point, homography):
    if homography is None:
        return None
    src = np.array([[[point[0], point[1]]]], dtype=np.float32)
    projected = cv2.perspectiveTransform(src, homography)[0][0]
    return (float(projected[0]), float(projected[1]))


def ball_close_to_player(ball, player):
    px, py = player["foot"]
    bx, by = ball["center"]
    x1, y1, x2, y2 = player["box"]
    player_height = max(1.0, y2 - y1)
    player_width = max(1.0, x2 - x1)
    horizontal = abs(bx - px) / player_width
    vertical = abs(by - py) / player_height
    normalized_distance = math.hypot(horizontal, vertical)
    return normalized_distance < 1.05


def analyze_video(data):
    video_url = data.get("video_url")
    if not video_url:
        raise ValueError("video_url is required")

    target = data.get("target", {"x": 0.5, "y": 0.5})
    target_time = max(0.0, float(data.get("target_time_seconds", 0.0)))
    sample_fps = clamp(data.get("sample_fps", 5), 1.0, 10.0)
    confidence = clamp(data.get("confidence", 0.22), 0.1, 0.9)
    image_size = int(clamp(data.get("image_size", 960), 640, 1280))
    max_video_mb = int(clamp(data.get("max_video_mb", 4096), 100, 8192))
    calibration = data.get("pitch_calibration")

    started = time.time()
    with tempfile.TemporaryDirectory() as temp_dir:
        video_path = Path(temp_dir) / "match.mp4"
        downloaded_bytes = download_video(video_url, video_path, max_video_mb)

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise ValueError("OpenCV could not open the downloaded video")

        source_fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / source_fps if source_fps else 0.0
        if width <= 0 or height <= 0 or total_frames <= 0:
            capture.release()
            raise ValueError("Invalid video metadata")

        target_time = min(target_time, max(0.0, duration - 0.1))
        target_point = (
            clamp(target.get("x", 0.5), 0.0, 1.0) * width,
            clamp(target.get("y", 0.5), 0.0, 1.0) * height,
        )

        capture.set(cv2.CAP_PROP_POS_MSEC, target_time * 1000.0)
        ok, anchor_frame = capture.read()
        if not ok:
            capture.release()
            raise ValueError("Could not read the player-selection frame")

        anchor_result = MODEL.predict(
            anchor_frame,
            classes=[PERSON_CLASS],
            conf=confidence,
            imgsz=image_size,
            verbose=False,
        )[0]
        anchor_people, _ = parse_detections(anchor_result)
        anchor_player = choose_anchor_player(anchor_frame, anchor_people, target_point)
        if anchor_player is None:
            capture.release()
            raise ValueError("No player detected near the selected target point")

        reference_signature = appearance_signature(anchor_frame, anchor_player["box"])
        anchor_distance_px = euclidean(anchor_player["center"], target_point)

        capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
        stride = max(1, round(source_fps / sample_fps))
        homography = make_homography(calibration)

        selected_track_id = None
        previous_center = None
        smoothed_center = None
        previous_pitch_point = None
        previous_scene = None
        pixel_path = 0.0
        distance_meters = 0.0
        tracked_samples = 0
        sampled_frames = 0
        reidentifications = 0
        scene_cuts = 0
        rejected_jumps = 0
        possession_samples = 0
        ball_visible_samples = 0
        touch_events = []
        possession_intervals = []
        possession_started = None
        previous_ball_close = False
        last_touch_time = -10.0
        track_scores = []
        frame_index = 0

        while capture.isOpened():
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % stride:
                frame_index += 1
                continue

            sampled_frames += 1
            timestamp = frame_index / source_fps
            current_scene = scene_signature(frame)
            hard_cut = is_hard_scene_cut(previous_scene, current_scene)
            previous_scene = current_scene
            if hard_cut:
                scene_cuts += 1
                selected_track_id = None
                previous_center = None
                smoothed_center = None
                previous_pitch_point = None

            result = MODEL.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                classes=[PERSON_CLASS, BALL_CLASS],
                conf=confidence,
                imgsz=image_size,
                verbose=False,
            )[0]
            people, balls = parse_detections(result)
            if balls:
                ball_visible_samples += 1

            player = None
            match_score = 1.0
            if selected_track_id is not None:
                player = next((p for p in people if p["id"] == selected_track_id), None)

            if player is None:
                player, match_score = choose_reidentified_player(
                    frame, people, previous_center, reference_signature
                )
                if player is not None:
                    if selected_track_id != player["id"]:
                        reidentifications += 1
                    selected_track_id = player["id"]

            if player is not None:
                tracked_samples += 1
                track_scores.append(float(match_score))
                raw_center = player["center"]
                if smoothed_center is None:
                    smoothed_center = raw_center
                else:
                    smoothing = 0.55
                    smoothed_center = (
                        smoothing * raw_center[0] + (1.0 - smoothing) * smoothed_center[0],
                        smoothing * raw_center[1] + (1.0 - smoothing) * smoothed_center[1],
                    )

                if previous_center is not None:
                    step_px = euclidean(smoothed_center, previous_center)
                    max_step_px = max(width * 0.045, (player["box"][3] - player["box"][1]) * 1.7)
                    if step_px <= max_step_px:
                        pixel_path += step_px
                    else:
                        rejected_jumps += 1
                previous_center = smoothed_center

                current_signature = appearance_signature(frame, player["box"])
                if getattr(player, "appearance_similarity", None) is not None:
                    pass
                if current_signature is not None:
                    reference_signature = blend_signature(reference_signature, current_signature)

                pitch_point = project_to_pitch(player["foot"], homography)
                if pitch_point is not None:
                    if previous_pitch_point is not None:
                        step_m = euclidean(pitch_point, previous_pitch_point)
                        max_step_m = 13.0 / sample_fps
                        if step_m <= max_step_m:
                            distance_meters += step_m
                        else:
                            rejected_jumps += 1
                    previous_pitch_point = pitch_point

                close = False
                if balls:
                    ball = min(balls, key=lambda b: euclidean(b["center"], player["foot"]))
                    close = ball_close_to_player(ball, player)

                if close:
                    possession_samples += 1
                    if possession_started is None:
                        possession_started = timestamp
                    if not previous_ball_close and timestamp - last_touch_time >= 0.55:
                        touch_events.append(round(timestamp, 2))
                        last_touch_time = timestamp
                elif possession_started is not None:
                    possession_intervals.append(
                        [round(possession_started, 2), round(timestamp, 2)]
                    )
                    possession_started = None
                previous_ball_close = close
            else:
                if possession_started is not None:
                    possession_intervals.append(
                        [round(possession_started, 2), round(timestamp, 2)]
                    )
                    possession_started = None
                previous_ball_close = False

            frame_index += 1

        capture.release()
        if possession_started is not None:
            possession_intervals.append([round(possession_started, 2), round(duration, 2)])

        coverage = tracked_samples / max(1, sampled_frames) * 100.0
        ball_visibility = ball_visible_samples / max(1, sampled_frames) * 100.0
        mean_track_score = sum(track_scores) / max(1, len(track_scores))
        quality_score = 0.72 * min(coverage / 90.0, 1.0) + 0.18 * min(ball_visibility / 45.0, 1.0) + 0.10 * min(mean_track_score, 1.0)
        quality_score = round(quality_score * 100.0, 1)

        if quality_score >= 82:
            quality_label = "good"
        elif quality_score >= 65:
            quality_label = "usable_with_review"
        else:
            quality_label = "insufficient"

        result = {
            "status": "completed",
            "engine_version": "2.0-dev",
            "model": MODEL_NAME,
            "processing_seconds": round(time.time() - started, 2),
            "video": {
                "duration_seconds": round(duration, 2),
                "width": width,
                "height": height,
                "source_fps": round(source_fps, 3),
                "sample_fps": sample_fps,
                "sampled_frames": sampled_frames,
                "downloaded_mb": round(downloaded_bytes / 1024 / 1024, 2),
            },
            "selection": {
                "target_time_seconds": round(target_time, 2),
                "target": {
                    "x": round(target_point[0] / width, 4),
                    "y": round(target_point[1] / height, 4),
                },
                "anchor_detection_distance_pixels": round(anchor_distance_px, 1),
            },
            "player": {
                "last_track_id": selected_track_id,
                "tracking_coverage_percent": round(coverage, 1),
                "reidentifications": reidentifications,
                "distance_pixels_estimated": round(pixel_path, 1),
                "ball_touches_estimated": len(touch_events),
                "touch_timestamps_seconds": touch_events,
                "possession_seconds_estimated": round(possession_samples / sample_fps, 1),
                "possession_intervals_seconds": possession_intervals,
            },
            "quality": {
                "score_percent": quality_score,
                "label": quality_label,
                "ball_visibility_percent": round(ball_visibility, 1),
                "scene_cuts_detected": scene_cuts,
                "rejected_tracking_jumps": rejected_jumps,
            },
            "warnings": [
                "Touches and possession remain computer-vision estimates and must be validated before commercial use.",
                "A single broadcast camera cannot guarantee perfect player identity after occlusions or cuts without stronger re-identification.",
            ],
        }

        if homography is not None:
            result["player"]["distance_meters_estimated"] = round(distance_meters, 1)
            result["quality"]["pitch_calibration_used"] = True
        else:
            result["quality"]["pitch_calibration_used"] = False
            result["warnings"].append(
                "Metric distance is intentionally omitted until pitch calibration points are supplied."
            )

        return result


def handler(job):
    try:
        data = job.get("input", {})
        return analyze_video(data)
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "engine_version": "2.0-dev",
        }


runpod.serverless.start({"handler": handler})
