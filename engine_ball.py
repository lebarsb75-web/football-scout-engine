from __future__ import annotations


def local_ball_search_crop(
    player_box,
    frame_width: int,
    frame_height: int,
    *,
    horizontal_player_widths: float = 8.0,
    above_player_heights: float = 2.2,
    below_player_heights: float = 1.4,
) -> tuple[int, int, int, int]:
    """Return a clipped crop that magnifies the ball around the selected player.

    A football is often only a few pixels wide in panoramic footage. Running a
    second detector on a bounded local crop gives it substantially more pixels
    without multiplying inference cost across a full-frame tile grid.
    """
    x1, y1, x2, y2 = [float(value) for value in player_box]
    player_width = max(4.0, x2 - x1)
    player_height = max(8.0, y2 - y1)
    foot_x = (x1 + x2) / 2.0
    foot_y = y2
    half_width = horizontal_player_widths * player_width / 2.0
    crop = (
        int(max(0, round(foot_x - half_width))),
        int(max(0, round(foot_y - above_player_heights * player_height))),
        int(min(frame_width, round(foot_x + half_width))),
        int(min(frame_height, round(foot_y + below_player_heights * player_height))),
    )
    return crop


def translate_box(box, offset_x: int, offset_y: int) -> list[float]:
    """Translate crop-relative detection coordinates back to the source frame."""
    x1, y1, x2, y2 = [float(value) for value in box]
    return [x1 + offset_x, y1 + offset_y, x2 + offset_x, y2 + offset_y]


def calibration_points_are_valid(image_points, pitch_points) -> bool:
    """Reject incomplete, degenerate or implausible four-corner calibrations."""
    if not isinstance(image_points, (list, tuple)) or not isinstance(
        pitch_points, (list, tuple)
    ):
        return False
    if len(image_points) != 4 or len(pitch_points) != 4:
        return False
    try:
        image = [(float(point[0]), float(point[1])) for point in image_points]
        pitch = [(float(point[0]), float(point[1])) for point in pitch_points]
    except (TypeError, ValueError, IndexError):
        return False

    def polygon_area(points):
        return abs(
            sum(
                points[index][0] * points[(index + 1) % len(points)][1]
                - points[(index + 1) % len(points)][0] * points[index][1]
                for index in range(len(points))
            )
            / 2.0
        )

    return polygon_area(image) >= 100.0 and polygon_area(pitch) >= 100.0
