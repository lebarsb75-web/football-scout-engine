import argparse
import json
import subprocess
from pathlib import Path


def load_windows(result_path: Path):
    data = json.loads(result_path.read_text(encoding="utf-8"))
    return data.get("player", {}).get("touch_clip_windows_seconds", [])


def build_clip(input_video: Path, output_file: Path, start: float, end: float):
    duration = max(0.1, end - start)
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        "-i",
        str(input_video),
        "-t",
        str(duration),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_file),
    ]
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Create action clips from a Football Scout analysis JSON."
    )
    parser.add_argument("video", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path, default=Path("clips"))
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"Video not found: {args.video}")
    if not args.result.exists():
        raise SystemExit(f"Analysis result not found: {args.result}")

    windows = load_windows(args.result)
    if not windows:
        raise SystemExit("No touch_clip_windows_seconds found in analysis result")

    args.output.mkdir(parents=True, exist_ok=True)
    for index, window in enumerate(windows, start=1):
        if not isinstance(window, list) or len(window) != 2:
            continue
        start, end = float(window[0]), float(window[1])
        output_file = args.output / f"action_{index:03d}_{start:.1f}-{end:.1f}.mp4"
        print(f"Creating {output_file.name}")
        build_clip(args.video, output_file, start, end)

    print(f"Done. Clips saved to {args.output}")


if __name__ == "__main__":
    main()
