import math
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
import requests
import runpod
from ultralytics import YOLO

from engine_quality import (
    ball_metrics_are_reliable,
    classify_tracking_quality,
    summarize_tracking_samples,
)
from engine_tracking import iter_sample_frame_indices, reset_model_trackers

ENGINE_VERSION = "2.4-dev"
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
    headers = {"User-Agent": f"football-scout-engine/{ENGINE_VERSION}"}
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
        top = y1 + int(0.12 * bh)
        bottom = y1 + int(0.62 * bh)
        y1, y2 = top, max(top + 1, min(h, bottom))
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


def blend_signature(reference, candidate, alpha=0.035):
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
    ids = result.boxes.id.int().cpu().tolist() if result.boxes.id is not None else [None] * len(boxes)
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
    diag = math.hypot(frame.shape[1], frame.shape[0]) or 1.0
    return min(
        people,
        key=lambda p: euclidean(p["center"], target_point) / diag - 0.04 * p["confidence"],
    )


def choose_reidentified_player(frame, people, previous_center, previous_box_height, reference_signature):
    if not people:
        return None, 0.0
    diag = math.hypot(frame.shape[1], frame.shape[0]) or 1.0
    scored = []
    for person in people:
        signature = appearance_signature(frame, person["box"])
        app = appearance_similarity(reference_signature, signature)
        if previous_center is None:
            motion = 0.45
        else:
            d = euclidean(person["center"], previous_center) / diag
            motion = max(0.0, 1.0 - d / 0.12)
        height = max(1.0, person["box"][3] - person["box"][1])
        if previous_box_height is None:
            size = 0.5
        else:
            size = min(height, previous_box_height) / max(height, previous_box_height)
        score = 0.55 * app + 0.30 * motion + 0.10 * size + 0.05 * person["confidence"]
        scored.append((score, app, person, signature))
    scored.sort(key=lambda row: row[0], reverse=True)
    best_score, best_app, best_person, best_signature = scored[0]
    if best_score < 0.40:
        return None, best_score
    if reference_signature is not None and best_app < 0.22 and previous_center is None:
        return None, best_score
    best_person["signature"] = best_signature
    best_person["appearance_similarity"] = best_app
    return best_person, best_score


def choose_plausible_ball(balls, player, previous_ball_center, frame_shape, sample_fps):
    if not balls or player is None:
        return None
    h, w = frame_shape[:2]
    diag = math.hypot(w, h) or 1.0
    candidates = []
    for ball in balls:
        continuity = 0.45
        if previous_ball_center is not None:
            jump = euclidean(ball["center"], previous_ball_center) / diag
            max_jump = max(0.045, 0.20 / max(1.0, sample_fps / 3.0))
            if jump > max_jump:
                continue
            continuity = max(0.0, 1.0 - jump / max_jump)
        player_distance = euclidean(ball["center"], player["foot"]) / diag
        proximity = max(0.0, 1.0 - player_distance / 0.18)
        score = 0.55 * continuity + 0.30 * proximity + 0.15 * ball["confidence"]
        candidates.append((score, ball))
    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0], reverse=True)
    return candidates[0][1]


def ball_close_to_player(ball, player):
    px, py = player["foot"]
    bx, by = ball["center"]
    x1, y1, x2, y2 = player["box"]
    ph = max(1.0, y2 - y1)
    pw = max(1.0, x2 - x1)
    return math.hypot(abs(bx - px) / pw, abs(by - py) / ph) < 0.95


def make_homography(calibration):
    if not calibration or calibration.get("static_camera") is not True:
        return None
    image_points = calibration.get("image_points")
    pitch_points = calibration.get("pitch_points_meters")
    if not image_points or not pitch_points or len(image_points) < 4 or len(pitch_points) < 4:
        return None
    src = np.array(image_points, dtype=np.float32)
    dst = np.array(pitch_points, dtype=np.float32)
    if src.ndim != 2 or dst.ndim != 2 or src.shape[1] != 2 or dst.shape[1] != 2 or src.shape[0] != dst.shape[0]:
        return None
    matrix, _ = cv2.findHomography(src, dst, method=0)
    return matrix


def project_to_pitch(point, homography):
    if homography is None:
        return None
    src = np.array([[[point[0], point[1]]]], dtype=np.float32)
    projected = cv2.perspectiveTransform(src, homography)[0][0]
    return (float(projected[0]), float(projected[1]))


def merge_windows(timestamps, duration, before=4.0, after=4.0, merge_gap=1.5):
    windows = []
    for timestamp in timestamps:
        start = max(0.0, float(timestamp) - before)
        end = min(float(duration), float(timestamp) + after)
        if not windows or start > windows[-1][1] + merge_gap:
            windows.append([start, end])
        else:
            windows[-1][1] = max(windows[-1][1], end)
    return [[round(a, 2), round(b, 2)] for a, b in windows]


def analyze_video(data):
    video_url = data.get("video_url")
    if not video_url:
        raise ValueError("video_url is required")

    target = data.get("target", {"x": 0.5, "y": 0.5})
    target_time = max(0.0, float(data.get("target_time_seconds", 0.0)))
    requested_sample_fps = clamp(data.get("sample_fps", 5), 1.0, 10.0)
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
        target_frame_index = min(total_frames - 1, max(0, int(round(target_time * source_fps))))
        target_point = (
            clamp(target.get("x", 0.5), 0.0, 1.0) * width,
            clamp(target.get("y", 0.5), 0.0, 1.0) * height,
        )

        capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame_index)
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
        anchor_distance_ratio = anchor_distance_px / (math.hypot(width, height) or 1.0)
        if anchor_distance_ratio > 0.10:
            capture.release()
            raise ValueError(
                "Selected point is too far from the nearest detected player; choose a clearer frame"
            )
        anchor_center = anchor_player["center"]
        anchor_box_height = max(1.0, anchor_player["box"][3] - anchor_player["box"][1])

        # V2.3 deliberately starts at the user's selected frame. This guarantees that
        # identity is seeded from the actual selected player instead of trying to
        # re-identify that player backwards from frame zero with only a jersey-colour histogram.
        capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame_index)
        effective_sample_fps = min(requested_sample_fps, source_fps)
        sample_indices = iter_sample_frame_indices(
            target_frame_index,
            total_frames,
            source_fps,
            effective_sample_fps,
        )
        next_sample_frame = next(sample_indices, None)
        homography = make_homography(calibration)
        reset_model_trackers(MODEL)

        selected_track_id = None
        previous_center = anchor_center
        smoothed_center = anchor_center
        previous_box_height = anchor_box_height
        previous_pitch_point = None
        previous_scene = scene_signature(anchor_frame)
        previous_ball_center = None
        pixel_path = 0.0
        distance_meters = 0.0
        tracked_samples = 0
        sampled_frames = 0
        reidentifications = 0
        identity_rejections = 0
        scene_cuts = 0
        rejected_jumps = 0
        possession_samples = 0
        ball_visible_samples = 0
        ball_rejections = 0
        touch_events = []
        possession_intervals = []
        possession_started = None
        close_streak = 0
        far_streak = 0
        last_touch_time = -10.0
        track_scores = []
        appearance_scores = []
        tracking_samples = []
        frame_index = target_frame_index
        first_sample = True

        while capture.isOpened():
            ok, frame = capture.read()
            if not ok:
                break
            if next_sample_frame is None:
                break
            if frame_index < next_sample_frame:
                frame_index += 1
                continue
            next_sample_frame = next(sample_indices, None)

            sampled_frames += 1
            timestamp = frame_index / source_fps
            current_scene = scene_signature(frame)
            hard_cut = (not first_sample) and is_hard_scene_cut(previous_scene, current_scene)
            previous_scene = current_scene
            if hard_cut:
                scene_cuts += 1
                selected_track_id = None
                previous_center = None
                smoothed_center = None
                previous_box_height = None
                previous_pitch_point = None
                previous_ball_center = None
                close_streak = 0
                far_streak = 0
                reset_model_trackers(MODEL)

            tracked = MODEL.track(
                frame,
                persist=True,
                # BoT-SORT's camera-motion compensation is materially more stable
                # than ByteTrack on broadcast/panoramic football footage sampled
                # below the source frame rate.
                tracker="botsort.yaml",
                classes=[PERSON_CLASS, BALL_CLASS],
                conf=confidence,
                imgsz=image_size,
                verbose=False,
            )[0]
            people, balls = parse_detections(tracked)
            player = None
            match_score = 1.0

            # Hard-lock the first sampled frame to the player's actual selection.
            if first_sample:
                player = choose_anchor_player(frame, people, target_point)
                if player is not None:
                    candidate_signature = appearance_signature(frame, player["box"])
                    player["signature"] = candidate_signature
                    player["appearance_similarity"] = appearance_similarity(reference_signature, candidate_signature)
                    selected_track_id = player["id"]
                    reidentifications += 1
                    match_score = 1.0
                first_sample = False

            if player is None and selected_track_id is not None:
                candidate = next((p for p in people if p["id"] == selected_track_id), None)
                if candidate is not None:
                    candidate_signature = appearance_signature(frame, candidate["box"])
                    candidate_app = appearance_similarity(reference_signature, candidate_signature)
                    diag = math.hypot(width, height) or 1.0
                    motion_ok = previous_center is None or euclidean(candidate["center"], previous_center) / diag <= 0.14
                    # ByteTrack's persistent ID is the strongest signal inside a
                    # continuous shot. Small/distant jersey crops are noisy, so a
                    # weak histogram alone must not reject an otherwise plausible
                    # persistent track.
                    if (reference_signature is None or candidate_app >= 0.08) and motion_ok:
                        candidate["signature"] = candidate_signature
                        candidate["appearance_similarity"] = candidate_app
                        player = candidate
                        match_score = 0.70 + 0.30 * candidate_app
                    else:
                        identity_rejections += 1
                        selected_track_id = None

            if player is None:
                player, match_score = choose_reidentified_player(
                    frame, people, previous_center, previous_box_height, reference_signature
                )
                if player is not None:
                    if selected_track_id != player["id"]:
                        reidentifications += 1
                    selected_track_id = player["id"]

            if player is not None:
                tracked_samples += 1
                track_scores.append(float(match_score))
                app_score = float(player.get("appearance_similarity", 0.0))
                if reference_signature is not None:
                    appearance_scores.append(app_score)

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
                previous_box_height = max(1.0, player["box"][3] - player["box"][1])

                current_signature = player.get("signature")
                if current_signature is None:
                    current_signature = appearance_signature(frame, player["box"])
                if current_signature is not None and (reference_signature is None or app_score >= 0.40):
                    reference_signature = blend_signature(reference_signature, current_signature)

                pitch_point = project_to_pitch(player["foot"], homography)
                if pitch_point is not None:
                    if previous_pitch_point is not None:
                        step_m = euclidean(pitch_point, previous_pitch_point)
                        max_step_m = 13.0 / effective_sample_fps
                        if step_m <= max_step_m:
                            distance_meters += step_m
                        else:
                            rejected_jumps += 1
                    previous_pitch_point = pitch_point

                ball = choose_plausible_ball(
                    balls,
                    player,
                    previous_ball_center,
                    frame.shape,
                    effective_sample_fps,
                )
                if balls and ball is None:
                    ball_rejections += 1
                close = False
                if ball is not None:
                    ball_visible_samples += 1
                    previous_ball_center = ball["center"]
                    close = ball_close_to_player(ball, player)

                if close:
                    close_streak += 1
                    far_streak = 0
                else:
                    far_streak += 1
                    close_streak = 0

                if close_streak >= 2:
                    possession_samples += 1
                    if possession_started is None:
                        possession_started = max(
                            target_time, timestamp - 1.0 / effective_sample_fps
                        )
                    if close_streak == 2 and timestamp - last_touch_time >= 0.65:
                        touch_events.append(round(timestamp, 2))
                        last_touch_time = timestamp

                if far_streak >= 2 and possession_started is not None:
                    possession_intervals.append([round(possession_started, 2), round(timestamp, 2)])
                    possession_started = None
            else:
                close_streak = 0
                far_streak += 1
                previous_ball_center = None
                if possession_started is not None:
                    possession_intervals.append([round(possession_started, 2), round(timestamp, 2)])
                    possession_started = None

            tracking_samples.append(player is not None)
            frame_index += 1

        capture.release()
        if possession_started is not None:
            possession_intervals.append([round(possession_started, 2), round(duration, 2)])

        tracking_summary = summarize_tracking_samples(
            tracking_samples, effective_sample_fps
        )
        coverage = tracking_summary["coverage_percent"]
        ball_visibility = ball_visible_samples / max(1, sampled_frames) * 100.0
        mean_track_score = sum(track_scores) / max(1, len(track_scores))
        mean_appearance = sum(appearance_scores) / max(1, len(appearance_scores))
        player_quality = round(
            (
                0.72 * min(coverage / 90.0, 1.0)
                + 0.18 * min(mean_track_score, 1.0)
                + 0.10 * min(mean_appearance / 0.70, 1.0)
            )
            * 100.0,
            1,
        )
        quality_score = round(
            (0.78 * (player_quality / 100.0) + 0.22 * min(ball_visibility / 45.0, 1.0)) * 100.0,
            1,
        )
        reidentification_rate = (
            max(0, reidentifications - 1) / max(1, sampled_frames) * 100.0
        )
        identity_rejection_rate = identity_rejections / max(1, sampled_frames) * 100.0

        quality_label, tracking_continuity_reliable = classify_tracking_quality(
            player_quality=player_quality,
            coverage_percent=coverage,
            minimum_window_coverage_percent=tracking_summary[
                "minimum_window_coverage_percent"
            ],
            longest_untracked_gap_seconds=tracking_summary[
                "longest_untracked_gap_seconds"
            ],
            scene_cuts=scene_cuts,
            reidentification_rate_percent=reidentification_rate,
            identity_rejection_rate_percent=identity_rejection_rate,
        )
        ball_metrics_reliable = ball_metrics_are_reliable(
            tracking_continuity_reliable=tracking_continuity_reliable,
            player_quality=player_quality,
            ball_visibility_percent=ball_visibility,
            sampled_frames=sampled_frames,
        )
        tracked_seconds = tracked_samples / effective_sample_fps
        possession_seconds = possession_samples / effective_sample_fps
        analyzed_duration = max(0.0, duration - target_time)

        result = {
            "status": "completed",
            "engine_version": ENGINE_VERSION,
            "model": MODEL_NAME,
            "processing_seconds": round(time.time() - started, 2),
            "video": {
                "duration_seconds": round(duration, 2),
                "analysis_start_seconds": round(target_time, 2),
                "analysis_duration_seconds": round(analyzed_duration, 2),
                "width": width,
                "height": height,
                "source_fps": round(source_fps, 3),
                "requested_sample_fps": requested_sample_fps,
                "sample_fps": round(effective_sample_fps, 3),
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
                "anchor_detection_distance_ratio": round(anchor_distance_ratio, 4),
                "anchor_seeded_forward_tracking": True,
            },
            "player": {
                "last_track_id": selected_track_id,
                "tracking_coverage_percent": round(coverage, 1),
                "tracked_seconds_estimated": round(tracked_seconds, 1),
                "reidentifications": reidentifications,
                "identity_rejections": identity_rejections,
                "distance_pixels_estimated": round(pixel_path, 1),
                "ball_touches_estimated": len(touch_events),
                "touch_timestamps_seconds": touch_events,
                "touch_clip_windows_seconds": merge_windows(touch_events, duration),
                "possession_seconds_estimated": round(possession_seconds, 1),
                "possession_intervals_seconds": possession_intervals,
                "possession_percent_of_tracked_time": round(
                    possession_seconds / max(0.001, tracked_seconds) * 100.0, 1
                ),
            },
            "quality": {
                "score_percent": quality_score,
                "player_tracking_score_percent": player_quality,
                "label": quality_label,
                "review_required": quality_label != "good",
                "tracking_continuity_reliable": tracking_continuity_reliable,
                "minimum_window_coverage_percent": tracking_summary[
                    "minimum_window_coverage_percent"
                ],
                "longest_untracked_gap_seconds": tracking_summary[
                    "longest_untracked_gap_seconds"
                ],
                "window_coverage_percent": tracking_summary["window_coverage_percent"],
                "ball_metrics_reliable": ball_metrics_reliable,
                "ball_visibility_percent": round(ball_visibility, 1),
                "ball_candidate_rejections": ball_rejections,
                "mean_identity_appearance_similarity": round(mean_appearance, 3),
                "reidentification_rate_percent": round(reidentification_rate, 1),
                "identity_rejection_rate_percent": round(identity_rejection_rate, 1),
                "scene_cuts_detected": scene_cuts,
                "rejected_tracking_jumps": rejected_jumps,
            },
            "warnings": [
                "V2.4 analyzes forward from the player-selection frame; pre-selection footage is not included yet.",
                "Touches and possession remain computer-vision estimates until validated against labelled match footage.",
                "Broadcast-camera identity can still fail after occlusions or cuts without a dedicated re-identification model.",
            ],
        }

        if homography is not None:
            result["player"]["distance_meters_estimated"] = round(distance_meters, 1)
            result["quality"]["pitch_calibration_used"] = True
        else:
            result["quality"]["pitch_calibration_used"] = False
            result["warnings"].append(
                "Metric distance is omitted unless a static-camera pitch calibration with at least four point correspondences is supplied."
            )

        if not ball_metrics_reliable:
            result["warnings"].append(
                "Ball-derived metrics are below the reliability gate and should not be displayed as verified statistics."
            )

        return result


def handler(job):
    try:
        return analyze_video(job.get("input", {}))
    except Exception as exc:
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "engine_version": ENGINE_VERSION,
        }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
