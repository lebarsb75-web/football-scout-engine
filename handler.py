import math
import os
import tempfile
from pathlib import Path

import cv2
import requests
import runpod
from ultralytics import YOLO

MODEL = YOLO("yolo11m.pt")
PERSON_CLASS = 0
BALL_CLASS = 32


def download_video(url: str, destination: Path) -> None:
    with requests.get(url, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with destination.open("wb") as file:
            for chunk in response.iter_content(chunk_size=8 * 1024 * 1024):
                if chunk:
                    file.write(chunk)


def center(box):
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def handler(job):
    data = job.get("input", {})
    video_url = data.get("video_url")
    if not video_url:
        return {"error": "video_url is required"}

    target = data.get("target", {"x": 0.5, "y": 0.5})
    sample_fps = max(1.0, min(float(data.get("sample_fps", 5)), 10.0))
    confidence = max(0.1, min(float(data.get("confidence", 0.25)), 0.9))
    meters_per_pixel = data.get("meters_per_pixel")

    with tempfile.TemporaryDirectory() as temp_dir:
        video_path = Path(temp_dir) / "match.mp4"
        download_video(video_url, video_path)

        capture = cv2.VideoCapture(str(video_path))
        source_fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / source_fps if source_fps else 0
        stride = max(1, round(source_fps / sample_fps))

        target_point = (float(target.get("x", 0.5)) * width,
                        float(target.get("y", 0.5)) * height)
        selected_track_id = None
        previous_player = None
        path_pixels = 0.0
        ball_touches = 0
        possession_samples = 0
        tracked_samples = 0
        last_touch_time = -10.0
        frame_index = 0

        while capture.isOpened():
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % stride:
                frame_index += 1
                continue

            timestamp = frame_index / source_fps
            result = MODEL.track(frame, persist=True, tracker="bytetrack.yaml",
                                 classes=[PERSON_CLASS, BALL_CLASS], conf=confidence,
                                 verbose=False)[0]
            people = []
            balls = []
            if result.boxes is not None:
                boxes = result.boxes.xyxy.cpu().tolist()
                classes = result.boxes.cls.int().cpu().tolist()
                ids = (result.boxes.id.int().cpu().tolist()
                       if result.boxes.id is not None else [None] * len(boxes))
                for box, cls, track_id in zip(boxes, classes, ids):
                    item = {"box": box, "center": center(box), "id": track_id}
                    (people if cls == PERSON_CLASS else balls).append(item)

            if selected_track_id is None and people:
                chosen = min(people, key=lambda p: distance(p["center"], target_point))
                selected_track_id = chosen["id"]

            player = next((p for p in people if p["id"] == selected_track_id), None)
            if player is None and previous_player and people:
                player = min(people, key=lambda p: distance(p["center"], previous_player))
                if distance(player["center"], previous_player) > width * 0.08:
                    player = None

            if player:
                tracked_samples += 1
                player_center = player["center"]
                if previous_player:
                    step = distance(player_center, previous_player)
                    if step < width * 0.04:
                        path_pixels += step
                previous_player = player_center

                if balls:
                    ball = min(balls, key=lambda b: distance(b["center"], player_center))
                    player_height = player["box"][3] - player["box"][1]
                    close = distance(ball["center"], player_center) < player_height * 0.75
                    if close:
                        possession_samples += 1
                        if timestamp - last_touch_time > 0.8:
                            ball_touches += 1
                            last_touch_time = timestamp

            frame_index += 1

        capture.release()
        sampled = max(1, math.ceil(total_frames / stride))
        result = {
            "status": "completed",
            "video": {"duration_seconds": round(duration, 2), "width": width,
                      "height": height, "sample_fps": sample_fps},
            "player": {
                "track_id": selected_track_id,
                "ball_touches_estimated": ball_touches,
                "possession_seconds_estimated": round(possession_samples / sample_fps, 1),
                "tracking_coverage_percent": round(tracked_samples / sampled * 100, 1),
                "distance_pixels": round(path_pixels, 1),
            },
            "warnings": [
                "Touches and possession are computer-vision estimates.",
                "Exact distance requires pitch calibration."
            ]
        }
        if meters_per_pixel is not None:
            result["player"]["distance_meters_estimated"] = round(
                path_pixels * float(meters_per_pixel), 1)
        return result


runpod.serverless.start({"handler": handler})
