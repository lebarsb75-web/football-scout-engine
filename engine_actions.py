"""Evidence-first football action aggregation for one selected player.

The detector intentionally emits *candidates* with timestamps and confidence.
The public API decides whether the evidence is strong enough to publish.  This
keeps a missed ball or an uncertain shirt-colour classification from silently
becoming a definitive scouting statistic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


HEATMAP_COLUMNS = 12
HEATMAP_ROWS = 8


def _distance(left, right):
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(float(value), high))


def _angle_between(left, right):
    left_norm = math.hypot(*left)
    right_norm = math.hypot(*right)
    if left_norm <= 1e-6 or right_norm <= 1e-6:
        return 0.0
    cosine = _clamp((left[0] * right[0] + left[1] * right[1]) / (left_norm * right_norm), -1, 1)
    return math.degrees(math.acos(cosine))


def possession_owner(people, ball):
    """Return the most plausible owner near the ball, or ``None``.

    Distances are normalized by each player's box.  That makes the rule usable
    on wide and zoomed broadcast shots without pretending pixels are metres.
    """

    if ball is None:
        return None
    candidates = []
    for person in people:
        x1, y1, x2, y2 = person["box"]
        width = max(1.0, x2 - x1)
        height = max(1.0, y2 - y1)
        dx = abs(ball["center"][0] - person["foot"][0]) / width
        dy = abs(ball["center"][1] - person["foot"][1]) / height
        score = math.hypot(dx, dy)
        if score <= 1.15:
            candidates.append((score, person))
    return min(candidates, key=lambda row: row[0])[1] if candidates else None


@dataclass
class ActionAccumulator:
    sample_fps: float
    frame_width: int
    frame_height: int
    target_track_id: int | None = None
    events: list = field(default_factory=list)
    positions: list = field(default_factory=list)
    pitch_positions: list = field(default_factory=list)
    team_votes: int = 0
    classified_people: int = 0
    previous_owner: dict | None = None
    previous_ball: dict | None = None
    previous_ball_velocity: tuple | None = None
    target_possession_start: float | None = None
    pending_release: dict | None = None
    last_timestamp: float | None = None
    max_speed_kmh: float = 0.0

    def _event(self, event_type, timestamp, confidence, **details):
        event = {
            "type": event_type,
            "timestamp_seconds": round(float(timestamp), 2),
            "confidence": round(_clamp(confidence), 3),
        }
        event.update(details)
        self.events.append(event)

    def _is_target(self, person):
        return person is not None and person.get("role") == "target"

    def _team(self, person):
        return person.get("team") if person else None

    def observe(self, *, timestamp, player, people, ball, pitch_point=None, scene_cut=False):
        timestamp = float(timestamp)
        if scene_cut:
            self.previous_owner = None
            self.previous_ball = None
            self.previous_ball_velocity = None
            self.pending_release = None

        if player is not None:
            self.target_track_id = player.get("id", self.target_track_id)
            nx = _clamp(player["foot"][0] / max(1, self.frame_width))
            ny = _clamp(player["foot"][1] / max(1, self.frame_height))
            self.positions.append((timestamp, nx, ny))
            if pitch_point is not None:
                self.pitch_positions.append((timestamp, float(pitch_point[0]), float(pitch_point[1])))
                if len(self.pitch_positions) >= 2:
                    before = self.pitch_positions[-2]
                    elapsed = timestamp - before[0]
                    if 0 < elapsed <= max(1.0, 2.5 / max(1.0, self.sample_fps)):
                        speed = _distance(before[1:], pitch_point) / elapsed * 3.6
                        if speed <= 40.0:
                            self.max_speed_kmh = max(self.max_speed_kmh, speed)

        for person in people:
            if person.get("team") in {"teammate", "opponent"}:
                self.classified_people += 1
                if person.get("team_confident"):
                    self.team_votes += 1

        owner = possession_owner(people, ball)
        previous_owner = self.previous_owner
        owner_changed = (
            previous_owner is not None
            and owner is not None
            and previous_owner.get("id") != owner.get("id")
        )

        if self._is_target(owner) and not self._is_target(previous_owner):
            nearby_opponent = self._nearest_opponent(player, people)
            aerial = self._is_aerial(ball, player)
            if self._team(previous_owner) == "opponent":
                if nearby_opponent is not None:
                    self._event("tackle", timestamp, 0.78, aerial=aerial)
                    self._event("duel_won", timestamp, 0.74, aerial=aerial)
                else:
                    self._event("interception", timestamp, 0.72, aerial=aerial)
            elif previous_owner is None:
                self._event("recovery", timestamp, 0.62, aerial=aerial)
            self.target_possession_start = timestamp

        if self._is_target(previous_owner) and not self._is_target(owner):
            start_ball = self.previous_ball["center"] if self.previous_ball else None
            start_x = self.positions[-1][1] if self.positions else None
            self.pending_release = {
                "timestamp": timestamp,
                "start_ball": start_ball,
                "start_x": start_x,
                "aerial": self._is_aerial(ball, player),
            }
            if self._team(owner) == "opponent":
                self._event("pass_failed", timestamp, 0.76, start_x=start_x)
                self._event("turnover", timestamp, 0.80, position_x=start_x)
                if self._nearest_opponent(player, people) is not None:
                    self._event("duel_lost", timestamp, 0.72, aerial=self._is_aerial(ball, player))
                self.pending_release = None
            elif self._team(owner) == "teammate":
                details = self._progressive_details(owner)
                self._event("pass_completed", timestamp, 0.82, start_x=start_x, **details)
                self.pending_release = None
            self.target_possession_start = None

        if self.pending_release is not None and owner is not None:
            age = timestamp - self.pending_release["timestamp"]
            if age <= 2.5:
                if self._team(owner) == "teammate":
                    details = self._progressive_details(owner)
                    self._event(
                        "pass_completed",
                        timestamp,
                        0.70,
                        start_x=self.pending_release.get("start_x"),
                        **details,
                    )
                elif self._team(owner) == "opponent":
                    start_x = self.pending_release.get("start_x")
                    self._event("pass_failed", timestamp, 0.68, start_x=start_x)
                    self._event("turnover", timestamp, 0.70, position_x=start_x)
                self.pending_release = None
            else:
                self.pending_release = None

        # A sharp change of a moving ball very close to the selected player is
        # a block candidate. It remains explicitly reviewable evidence.
        if ball is not None and self.previous_ball is not None and self.last_timestamp is not None:
            elapsed = max(1e-6, timestamp - self.last_timestamp)
            velocity = (
                (ball["center"][0] - self.previous_ball["center"][0]) / elapsed,
                (ball["center"][1] - self.previous_ball["center"][1]) / elapsed,
            )
            if (
                self.previous_ball_velocity is not None
                and player is not None
                and not self._is_target(owner)
                and self._ball_near_player(ball, player, 1.35)
                and _angle_between(self.previous_ball_velocity, velocity) >= 65
            ):
                self._event("block", timestamp, 0.58)
            self.previous_ball_velocity = velocity

        # A target release followed by a fast ball with no nearby owner is a
        # clearance candidate. The confidence is lower than a possession swap.
        if self.pending_release is not None and owner is None and ball is not None:
            start_ball = self.pending_release.get("start_ball")
            age = timestamp - self.pending_release["timestamp"]
            if start_ball is not None and 0.25 <= age <= 1.5:
                displacement = _distance(start_ball, ball["center"]) / math.hypot(
                    self.frame_width, self.frame_height
                )
                if displacement >= 0.055:
                    self._event("clearance", timestamp, 0.66, aerial=self.pending_release["aerial"])
                    self.pending_release = None

        self.previous_owner = owner
        self.previous_ball = ball
        self.last_timestamp = timestamp

    def _nearest_opponent(self, player, people):
        if player is None:
            return None
        height = max(1.0, player["box"][3] - player["box"][1])
        opponents = [person for person in people if person.get("team") == "opponent"]
        nearby = [person for person in opponents if _distance(person["center"], player["center"]) <= 2.2 * height]
        return min(nearby, key=lambda person: _distance(person["center"], player["center"])) if nearby else None

    @staticmethod
    def _ball_near_player(ball, player, radius):
        height = max(1.0, player["box"][3] - player["box"][1])
        return _distance(ball["center"], player["center"]) <= radius * height

    @staticmethod
    def _is_aerial(ball, player):
        if ball is None or player is None:
            return False
        _, y1, _, y2 = player["box"]
        return ball["center"][1] <= y1 + 0.58 * max(1.0, y2 - y1)

    def _progressive_details(self, owner):
        if not self.positions or self.pending_release is None:
            return {"progressive": False}
        start_x = self.pending_release.get("start_x")
        end_x = owner["foot"][0] / max(1, self.frame_width)
        if start_x is None:
            return {"progressive": False}
        average_x = sum(position[1] for position in self.positions) / len(self.positions)
        attack_sign = 1 if average_x < 0.5 else -1
        progress = (end_x - start_x) * attack_sign
        return {"progressive": progress >= 0.12, "normalized_progress": round(progress, 3)}

    def summary(self):
        counts = {}
        for event in self.events:
            counts[event["type"]] = counts.get(event["type"], 0) + 1
        passes_completed = counts.get("pass_completed", 0)
        passes_failed = counts.get("pass_failed", 0)
        progressive_passes = sum(
            1 for event in self.events if event["type"] == "pass_completed" and event.get("progressive")
        )
        average_x = (
            sum(position[1] for position in self.positions) / len(self.positions)
            if self.positions else 0.5
        )
        own_goal_left = average_x < 0.5
        def in_defensive_third(x):
            return x is not None and (x <= 0.34 if own_goal_left else x >= 0.66)
        build_up_passes = sum(
            1
            for event in self.events
            if event["type"] == "pass_completed" and in_defensive_third(event.get("start_x"))
        )
        defensive_errors = sum(
            1
            for event in self.events
            if event["type"] == "turnover" and in_defensive_third(event.get("position_x"))
        )
        duels_won = counts.get("duel_won", 0)
        duels_lost = counts.get("duel_lost", 0)
        aerial_won = sum(1 for event in self.events if event["type"] == "duel_won" and event.get("aerial"))
        aerial_lost = sum(1 for event in self.events if event["type"] == "duel_lost" and event.get("aerial"))

        heatmap = [[0 for _ in range(HEATMAP_COLUMNS)] for _ in range(HEATMAP_ROWS)]
        for _, x, y in self.positions:
            column = min(HEATMAP_COLUMNS - 1, int(x * HEATMAP_COLUMNS))
            row = min(HEATMAP_ROWS - 1, int(y * HEATMAP_ROWS))
            heatmap[row][column] += 1
        maximum = max((value for row in heatmap for value in row), default=0)
        normalized_heatmap = [
            [round(value / maximum, 3) if maximum else 0 for value in row] for row in heatmap
        ]
        average_position = None
        if self.positions:
            average_position = {
                "x": round(sum(row[1] for row in self.positions) / len(self.positions), 4),
                "y": round(sum(row[2] for row in self.positions) / len(self.positions), 4),
            }

        pass_attempts = passes_completed + passes_failed
        duel_total = duels_won + duels_lost
        defensive_actions = (
            counts.get("interception", 0)
            + counts.get("recovery", 0)
            + counts.get("tackle", 0)
            + counts.get("clearance", 0)
            + counts.get("block", 0)
        )
        placement = min(10.0, 5.0 + 0.35 * defensive_actions - 0.45 * defensive_errors)
        anticipation = min(10.0, 5.0 + 0.55 * counts.get("interception", 0) + 0.25 * counts.get("recovery", 0))
        aggression = min(10.0, 5.0 + 0.4 * (counts.get("tackle", 0) + duel_total))
        buildup = min(10.0, 5.0 + 4.0 * (passes_completed / max(1, pass_attempts)) + 0.2 * progressive_passes)

        return {
            "passes": {
                "attempted": pass_attempts,
                "completed": passes_completed,
                "failed": passes_failed,
                "completion_percent": round(100 * passes_completed / max(1, pass_attempts), 1),
                "progressive": progressive_passes,
                "build_up": build_up_passes,
            },
            "interceptions": counts.get("interception", 0),
            "recoveries": counts.get("recovery", 0),
            "duels": {
                "won": duels_won,
                "lost": duels_lost,
                "aerial_won": aerial_won,
                "aerial_lost": aerial_lost,
            },
            "tackles": counts.get("tackle", 0),
            "clearances": counts.get("clearance", 0),
            "blocks": counts.get("block", 0),
            "turnovers": counts.get("turnover", 0),
            "defensive_error_candidates": defensive_errors,
            "average_position": average_position,
            "heatmap": {
                "columns": HEATMAP_COLUMNS,
                "rows": HEATMAP_ROWS,
                "values": normalized_heatmap,
                "sample_count": len(self.positions),
            },
            "max_speed_kmh": round(self.max_speed_kmh, 1) if self.pitch_positions else None,
            "qualitative": {
                "placement": round(placement, 1),
                "anticipation": round(anticipation, 1),
                "aggression": round(aggression, 1),
                "communication": None,
                "buildup_quality": round(buildup, 1),
            },
            "event_count": len(self.events),
            "events": self.events,
            "team_classification_confidence_percent": round(
                100 * self.team_votes / max(1, self.classified_people), 1
            ),
        }
