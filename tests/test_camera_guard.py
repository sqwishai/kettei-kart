import json
from unittest.mock import Mock

import pytest

from kettei_kart import native_camera
from kettei_kart.actions import Control
from kettei_kart.duel_render import render_duel, smooth_cameras
from kettei_kart.simulator import Simulator


def test_guard_rejects_camera_identity_and_projection_changes(monkeypatch):
    class Native:
        identity = [7, 8]
        aspect = [2.6667, 2.6667]

        def kart_camera_count(self):
            return 2

        def kart_camera_set_aspect(self, slot, aspect):
            self.aspect[slot] = aspect
            return 1

        def kart_camera_info(self, slot, values):
            values[0], values[1] = self.aspect[slot], self.identity[slot]
            return 1

    native = Native()
    monkeypatch.setattr(native_camera, "load_bridge", lambda stk: (native, {}))
    guard = native_camera.CameraGuard(None, (7, 8), 4 / 3)
    guard.validate(0, 4 / 3)
    native.identity.reverse()
    with pytest.raises(RuntimeError, match="ownership"):
        guard.validate(0, 4 / 3)
    native.identity.reverse()
    native.aspect[0] = 8 / 3
    with pytest.raises(RuntimeError, match="projection"):
        guard.validate(0, 4 / 3)


@pytest.mark.parametrize("renderer", [render_duel, smooth_cameras])
def test_legacy_capture_cannot_be_rendered_as_a_valid_comparison(tmp_path, renderer):
    (tmp_path / "manifest.json").write_text(json.dumps({"slot_providers": ["sqwish", "typesafe"]}))
    (tmp_path / "result.json").write_text("{}")
    with pytest.raises(ValueError, match="predates fixed player cameras"):
        renderer(tmp_path, tmp_path / "new.mp4")


def test_finished_race_holds_frame_without_advancing_into_result_screen():
    simulator = object.__new__(Simulator)
    simulator._stk = Mock(Action=Mock)
    simulator._race = Mock()
    simulator._world = Mock(players=[Mock(kart=Mock(has_finished_race=True)) for _ in range(2)])
    simulator.camera = Mock(return_value=None)
    capture = Mock()
    simulator.advance_both((Control(0, 0), Control(0, 0)), capture=capture)
    simulator._race.step.assert_not_called()
    assert capture.call_count == 6
