"""Describe driving after a run; these measurements never enter model inputs."""

from itertools import groupby

from .actions import ACTION_SECONDS


def driving_metrics(rows: list[dict]) -> dict:
    """Estimate durations from equally spaced, post-action speed samples.

    Slow movement may be useful cornering. Keep it distinct from near-stops;
    neither category is an automatic label of bad driving. A prolonged near-stop
    is a contiguous sequence below 1 m/s lasting at least one game second.
    """
    speeds = [abs(row["evaluator"]["speed"]) for row in rows]
    stopped = [speed < 1 for speed in speeds]
    low = sum(speed < 5 for speed in speeds)
    moving_slowly = sum(1 <= speed < 5 for speed in speeds)
    near_stop_lengths = [
        sum(1 for _ in group) for is_stopped, group in groupby(stopped) if is_stopped
    ]
    prolonged = sum(count for count in near_stop_lengths if count * ACTION_SECONDS >= 1)
    return {
        "rescue_button_presses": sum(row["action"] == "rescue" for row in rows),
        "low_speed_seconds": low * ACTION_SECONDS,
        "low_speed_fraction": low / len(rows) if rows else None,
        "slow_moving_seconds": moving_slowly * ACTION_SECONDS,
        "nearly_stationary_seconds": sum(stopped) * ACTION_SECONDS,
        "nearly_stationary_fraction": sum(stopped) / len(rows) if rows else None,
        "prolonged_nearly_stationary_seconds": prolonged * ACTION_SECONDS,
    }
