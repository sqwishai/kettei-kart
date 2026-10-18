import gzip
import json
from unittest.mock import Mock

import pytest
from PIL import Image

from kettei_kart.actions import CONTROLS, OUTCOMES, choose
from kettei_kart.client import DecisionClient, pack_json, validate_probabilities
from kettei_kart.observation import History
from kettei_kart.simulator import Simulator


def distribution(**changes):
    return {**dict.fromkeys(OUTCOMES, 0.0), "straight": 1.0, **changes}


def observation():
    return History().observe(Image.new("RGB", (768, 576), "red"), 0)


def test_history_uses_one_and_two_second_spacing_without_duplicate_start_frames():
    history = History()
    image = Image.new("RGB", (768, 576), "red")
    first = history.observe(image, 0)
    assert [f.tick for f in first.frames] == [0]
    for i in range(1, 15):
        history.record_action("straight", CONTROLS["straight"])
        result = history.observe(image, i * 6)
    assert [f.tick for f in result.frames] == [24, 54, 84]
    assert "14 recorded choices covering 2.80 game seconds" in result.context
    assert result.context.count('"action": "straight"') == 6
    assert "CURRENT camera, game tick 84: <image:3>" in result.context


def test_observation_boundary_has_only_camera_history_and_own_controls():
    obs = observation()
    assert set(vars(obs)) == {"context", "frames"}
    assert set(vars(obs.frames[0])) == {"tick", "jpeg"}
    assert not any(
        key in obs.context for key in ("overall_distance", "location", "track_length", "velocity")
    )
    assert obs.images()[0]["media_type"] == "image/jpeg"
    assert "Each action lasts 0.200 seconds" in obs.context


@pytest.mark.parametrize(
    "bad",
    [
        distribution(straight=True),
        distribution(straight=float("nan")),
        distribution(straight=float("inf")),
        distribution(straight=-1),
        distribution(straight=0.5),
        {"straight": 1.0},
        {**distribution(), "nitro": 0},
    ],
)
def test_invalid_probabilities_fail_closed(bad):
    with pytest.raises(ValueError):
        validate_probabilities(bad, rounded=True)


def test_rounded_provider_values_preserve_ranking_and_ties():
    values = distribution(straight=0.49, left=0.49, right=0.01)
    adjusted = validate_probabilities(values, rounded=True)
    assert sum(adjusted.values()) == pytest.approx(1)
    assert choose(adjusted)[0] == choose(values)[0]
    assert adjusted["straight"] == adjusted["left"]
    with pytest.raises(ValueError):
        validate_probabilities(values)


def test_control_duration_and_rescue_tap():
    simulator = object.__new__(Simulator)

    class Action:
        pass

    simulator._stk = Mock(Action=Action)
    recorded = []
    simulator._race = Mock()
    simulator._race.step.side_effect = lambda action: recorded.append(vars(action).copy())
    list(simulator.advance(CONTROLS["rescue"]))
    assert len(recorded) == 6
    assert [r["rescue"] for r in recorded] == [True, False, False, False, False, False]
    assert all(r["acceleration"] == 0 and r["steer"] == 0 for r in recorded)


def test_gzip_is_lossless_and_small_payloads_are_not_compressed():
    body = {"context": "a" * 20000}
    wire, headers, metadata = pack_json(body, compress=True)
    assert json.loads(gzip.decompress(wire)) == body
    assert headers["Content-Encoding"] == "gzip"
    assert metadata["wire_bytes"] < metadata["plain_bytes"]
    assert "Content-Encoding" not in pack_json({"a": 1}, compress=True)[1]


def client(monkeypatch, provider="sqwish"):
    monkeypatch.setenv(
        {"sqwish": "SQWISH_API_KEY", "typesafe": "TYPESAFE_API_KEY"}[provider],
        "test-only-not-a-key",
    )
    monkeypatch.setattr("kettei_kart.client.time.sleep", lambda _: None)
    return DecisionClient(provider)


def response(status=200, model="kettei-fat"):
    result = Mock(status_code=status, headers={}, content=b"response")
    result.json.return_value = {
        "model": model,
        "decisions": {"action": {"probabilities": distribution()}},
    }
    return result


def test_transient_retry_reuses_identical_payload_and_counts_every_attempt(monkeypatch):
    api = client(monkeypatch)
    api._session.post = Mock(side_effect=[response(503), response()])
    _, receipt = api.decide(observation())
    first, second = api._session.post.call_args_list
    assert first.kwargs["data"] == second.kwargs["data"]
    assert api.attempts == 2
    assert [a["status"] for a in receipt["attempts"]] == [503, 200]


def test_auth_failure_is_not_retried_and_body_is_not_exposed(monkeypatch):
    api = client(monkeypatch)
    api._session.post = Mock(return_value=response(401))
    with pytest.raises(RuntimeError, match="HTTP 401"):
        api.decide(observation())
    assert api.attempts == 1


def test_model_substitution_is_rejected(monkeypatch):
    api = client(monkeypatch)
    api._session.post = Mock(return_value=response(model="unexpected-model"))
    with pytest.raises(ValueError, match="different model"):
        api.decide(observation())


def test_native_sqwish_request_contains_only_declared_evidence(monkeypatch):
    api = client(monkeypatch)
    payload, headers, _ = api._request(observation())
    wire = payload["data"]
    body = json.loads(gzip.decompress(wire) if headers.get("Content-Encoding") else wire)
    assert body["model"] == "kettei-fat"
    assert body["fallback"] == "none"
    assert body["decisions"][0]["outcomes"] == OUTCOMES
    assert set(body) == {"model", "context", "images", "fallback", "decisions"}


def test_jev_uses_native_image_multipart(monkeypatch):
    api = client(monkeypatch, "typesafe")
    payload, headers, _ = api._request(observation())
    assert headers["TypeSafe-Danger-Zone-Images"] == "true"
    assert headers["Content-Type"].startswith("multipart/form-data;")
    assert b'"assets"' in payload["data"]
    assert b"image/jpeg" in payload["data"]
    assert b"data:image" not in payload["data"]


def test_two_player_controls_advance_one_shared_clock():
    simulator = object.__new__(Simulator)
    simulator._world = Mock(players=[Mock(kart=Mock(has_finished_race=False)) for _ in range(2)])

    class Action:
        pass

    simulator._stk = Mock(Action=Action)
    simulator._race = Mock()
    steps = []
    simulator._race.step.side_effect = lambda actions: steps.append(
        [vars(a).copy() for a in actions]
    )
    simulator.advance_both((CONTROLS["left"], CONTROLS["rescue"]))
    assert len(steps) == 6
    assert all(len(pair) == 2 and pair[0]["steer"] == -0.4 for pair in steps)
    assert [pair[1]["rescue"] for pair in steps] == [True, False, False, False, False, False]


def test_native_graphics_reinitialization_is_rejected_before_loading_engine(monkeypatch):
    monkeypatch.setattr("kettei_kart.simulator._graphics_used", True)
    with pytest.raises(RuntimeError, match="fresh process"):
        Simulator("lighthouse", 1)
