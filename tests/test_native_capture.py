"""Opt-in native checks: KART_NATIVE_TESTS=1 pytest tests/test_native_capture.py."""

import json
import os
import subprocess
import sys

import pytest

SCRIPT = """
import json
import sys
from pathlib import Path
from kettei_kart.actions import Control
from kettei_kart.simulator import Simulator

track, mode, output = sys.argv[1:]
styled = mode == "styled"
sim = Simulator(track, 501, players=2,
    player_names=("Kettei", "Jev") if styled else None,
    player_colors=(.42, .92) if styled else None,
    replay_detail=styled, replay_daylight=styled)
rows = []
try:
    for step in range(35):
        sim.advance_both((Control(0, 0, rescue=step == 20),
                          Control(0, 1 if step < 15 else 0, rescue=step == 20)))
        rows.append([sim.evaluate(slot) for slot in range(2)])
        for slot in range(2):
            image = sim.camera(slot)
            assert image.width / image.height == 4 / 3
    assert any(pair[1]["position"] < pair[0]["position"] for pair in rows)
    sim._camera_guard.native.kart_camera_set_aspect(0, 8 / 3)
    try:
        sim.camera(0)
    except RuntimeError as error:
        assert "projection" in str(error)
    else:
        raise AssertionError("Accepted an incorrect camera projection")
    Path(output).write_text(json.dumps(rows))
finally:
    sim.close()
"""


@pytest.mark.skipif(
    os.getenv("KART_NATIVE_TESTS") != "1", reason="Requires native graphics and cached game assets"
)
@pytest.mark.parametrize("track", ["lighthouse", "olivermath", "hacienda"])
def test_native_overtake_rescue_and_cosmetic_replay(tmp_path, track):
    for mode in ("original", "styled"):
        subprocess.run(
            [sys.executable, "-c", SCRIPT, track, mode, str(tmp_path / f"{mode}.json")],
            check=True,
            timeout=180,
        )
    assert json.loads((tmp_path / "original.json").read_text()) == json.loads(
        (tmp_path / "styled.json").read_text()
    )
