import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Calculate GPU compute cost from a Football Scout result JSON."
    )
    parser.add_argument("result", type=Path)
    parser.add_argument("--hourly-price", type=float, default=0.58)
    args = parser.parse_args()

    data = json.loads(args.result.read_text(encoding="utf-8"))
    processing_seconds = data.get("processing_seconds")
    duration_seconds = data.get("video", {}).get("duration_seconds")
    if processing_seconds is None:
        raise SystemExit("processing_seconds missing from result")

    cost = float(processing_seconds) / 3600.0 * args.hourly_price
    print(f"GPU processing time: {float(processing_seconds):.2f} s")
    print(f"Hourly GPU price: ${args.hourly_price:.4f}")
    print(f"Estimated compute cost: ${cost:.4f}")

    if duration_seconds:
        video_minutes = float(duration_seconds) / 60.0
        gpu_seconds_per_video_minute = float(processing_seconds) / max(0.001, video_minutes)
        projected_90_gpu_seconds = gpu_seconds_per_video_minute * 90.0
        projected_90_cost = projected_90_gpu_seconds / 3600.0 * args.hourly_price
        print(f"Measured GPU seconds / video minute: {gpu_seconds_per_video_minute:.2f}")
        print(f"Projected 90-min compute cost at same speed: ${projected_90_cost:.4f}")
        print("Projection excludes cold-start and storage/network costs.")


if __name__ == "__main__":
    main()
