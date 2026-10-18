import json
from unittest.mock import Mock

import pytest
from PIL import Image

from kettei_kart import duel
from kettei_kart.actions import OUTCOMES


@pytest.mark.parametrize("second_finishes", [True, False])
def test_race_continues_after_first_finish_without_calling_finished_model(
    tmp_path, monkeypatch, second_finishes
):
    clients = []

    def client(*args, **kwargs):
        instance = Mock(attempts=0)
        instance.decide.return_value = ({**dict.fromkeys(OUTCOMES, 0), "straight": 1}, {})
        clients.append(instance)
        return instance

    class Simulator:
        capture_contract = {"protocol": "fixed-player-cameras-v1"}

        def __init__(self, *args, **kwargs):
            self.step = 0

        def camera(self, slot):
            return Image.new("RGB", (32, 24))

        def evaluate(self, slot):
            finished = self.step >= (1 if slot == 0 else 3) and (slot == 0 or second_finishes)
            return {"finished": finished, "finish_time": (0.15, 0.55)[slot], "speed": 10}

        def advance_both(self, controls):
            if self.step:
                assert controls[0].acceleration == 0
                assert controls[0].steer == 0
            self.step += 1

        def close(self):
            pass

    monkeypatch.setattr(duel, "DecisionClient", client)
    monkeypatch.setattr(duel, "Simulator", Simulator)
    monkeypatch.setattr(duel.iio, "get_writer", lambda *a, **kw: Mock())
    result = duel.run_duel(output=tmp_path / "race", seconds=1)
    assert result["valid"]
    assert result["winner"] == "sqwish"
    assert result["decisions_per_model"] == [1, 3 if second_finishes else 5]
    assert clients[0].decide.call_count == 1
    assert clients[1].decide.call_count == (3 if second_finishes else 5)
    assert result["both_finished"] == second_finishes
    assert result["finish_gap_seconds"] == (pytest.approx(0.4) if second_finishes else None)
    assert result["end"] == ("finished" if second_finishes else "game_time_limit")
    assert result["player_metrics"]["sqwish"]["low_speed_seconds"] == 0
    rows = [
        json.loads(line)
        for line in (tmp_path / "race/sqwish/decisions.jsonl").read_text().splitlines()
    ]
    assert rows[1]["decision_made"] is False
    assert rows[1]["probabilities"] is None
    assert rows[1]["image_files"] == []
