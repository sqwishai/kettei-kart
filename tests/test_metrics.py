import pytest

from kettei_kart.metrics import driving_metrics


def test_slow_motion_is_distinct_from_prolonged_near_stops():
    speeds = [0] * 4 + [2] * 3 + [0] * 5 + [10] * 2 + [-3] * 2
    rows = [
        {"action": "rescue" if i == 4 else "straight", "evaluator": {"speed": speed}}
        for i, speed in enumerate(speeds)
    ]
    result = driving_metrics(rows)
    assert result["low_speed_seconds"] == pytest.approx(2.8)
    assert result["slow_moving_seconds"] == pytest.approx(1.0)
    assert result["nearly_stationary_seconds"] == pytest.approx(1.8)
    assert result["prolonged_nearly_stationary_seconds"] == pytest.approx(1.0)
    assert result["low_speed_fraction"] == pytest.approx(14 / 16)
    assert result["rescue_button_presses"] == 1


def test_empty_run_does_not_claim_a_measured_speed_fraction():
    result = driving_metrics([])
    assert result["low_speed_seconds"] == 0
    assert result["low_speed_fraction"] is None
    assert result["nearly_stationary_fraction"] is None
