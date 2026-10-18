"""The game can expose telemetry to scoring without exposing it to the model."""

from types import SimpleNamespace

from PIL import Image

from kettei_kart.actions import OUTCOMES
from kettei_kart.runner import run


def test_track_seed_and_scoring_telemetry_do_not_change_model_request(monkeypatch, tmp_path):
    observations = []

    class CameraOnlySimulator:
        def __init__(self, track, seed):
            self.seed = seed
            self.steps = 0
            self.track_length = seed * 100

        def camera(self):
            return Image.new("RGB", (768, 576), "green")

        def evaluate(self):
            return {
                "distance": self.seed * 10,
                "speed": self.seed,
                "location": [self.seed, self.seed, self.seed],
                "finished": self.steps > 0,
            }

        def advance(self, control, *, capture=False):
            self.steps += 1
            return iter(())

        def close(self):
            pass

    class RecordingClient:
        config = SimpleNamespace(model="test-model")
        attempts = 1

        def __init__(self, *args, **kwargs):
            pass

        def decide(self, observation):
            observations.append(observation)
            return {**dict.fromkeys(OUTCOMES, 0), "straight": 1}, {
                "latency_s": 0.1,
                "attempts": [{"seconds": 0.1}],
            }

        def close(self):
            pass

    monkeypatch.setattr("kettei_kart.runner.Simulator", CameraOnlySimulator)
    monkeypatch.setattr("kettei_kart.runner.DecisionClient", RecordingClient)
    for seed, track in ((17, "lighthouse"), (83, "unseen-circuit")):
        result = run(track=track, seed=seed, output=tmp_path / track, video=False)
        assert result["valid"] and result["end"] == "finished"
    assert len(observations) == 2
    assert observations[0] == observations[1]
    assert "lighthouse" not in observations[0].context
    assert "unseen-circuit" not in observations[1].context
