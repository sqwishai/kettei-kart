"""Render a native camera orbit before the race; no kart teleporting or turning."""

import argparse
import ctypes
import json
import math
import os
from pathlib import Path

import imageio.v2 as iio
import numpy as np
import pystk2 as stk
from daylight import graphics, prepare
from PIL import Image

from kettei_kart.native_camera import load_bridge

ROOT = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--track", default="lighthouse")
    parser.add_argument("--seed", type=int, default=501)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--swap", action="store_true", help="Place Jev in grid slot one")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)
    os.environ["SUPERTUXKART_DATADIR"] = str(prepare())
    native, build = load_bridge(stk)
    vector = ctypes.c_float * 7
    for method in (native.kart_camera_get, native.kart_camera_set):
        method.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_float)]
        method.restype = ctypes.c_int
    native.kart_camera_clear_start_signal.argtypes = []
    native.kart_camera_clear_start_signal.restype = ctypes.c_int
    stk.init(graphics(stk, 640, 360))
    race = None
    proof = {
        "track": args.track,
        "seed": args.seed,
        "frames": 120,
        "fps": 30,
        "purpose": "Presentation-only pre-race camera movement; no model calls.",
        "camera_library_sha256": build["sha256"],
        "grid_swapped": args.swap,
        "max_kart_displacement": 0.0,
        "max_kart_rotation_error": 0.0,
        "poses": [],
    }
    try:
        config = stk.RaceConfig()
        config.track, config.seed, config.laps, config.num_kart = args.track, args.seed, 1, 2
        config.step_size, config.difficulty, config.overlay = 1 / 30, 1, False
        names = ("Jev", "Kettei") if args.swap else ("Kettei", "Jev")
        config.players[0].kart = "tux"
        config.players.append(stk.PlayerConfig(kart="tux"))
        for player in config.players:
            player.controller = stk.PlayerConfig.Controller.PLAYER_CONTROL
        config.num_cameras = 1
        race = stk.Race(config)
        race.start()
        for slot, name in enumerate(names):
            hue = 0.42 if name == "Kettei" else 0.92
            if not native.kart_replay_set_hue(slot, hue):
                raise RuntimeError("Could not set the presentation kart colour")
            if not native.kart_replay_label(slot, name.encode()):
                raise RuntimeError("Could not add the presentation kart label")
        proof["player_colours"] = {"Kettei": "mint green", "Jev": "pink"}
        for index in range(240):
            race.step([stk.Action(), stk.Action()])
            if index >= 180:
                np.array(race.render_data[0].image)
        if not native.kart_camera_clear_start_signal():
            raise RuntimeError("Could not dismiss the pre-race start signal")
        world = stk.WorldState()
        world.update()
        positions = [np.array(p.kart.location, dtype=float) for p in world.players]
        rotations = [np.array(p.kart.rotation, dtype=float) for p in world.players]
        origin = positions[0]
        forward = np.array(world.players[0].kart.front, dtype=float) - origin
        forward[1] = 0
        forward /= np.linalg.norm(forward)
        # Sweep around the outside of player one's grid position, away from player two.
        right = np.array([-forward[2], 0, forward[0]])
        initial_target = np.mean(positions, axis=0) + [0, 0.65, 0]
        endpoint = vector()
        if not native.kart_camera_get(0, endpoint):
            raise RuntimeError("Native camera is unavailable")
        end_position, end_target = np.array(endpoint[:3]), np.array(endpoint[3:6])
        end_radius = np.linalg.norm((end_position - end_target)[[0, 2]])
        end_height = end_position[1] - end_target[1]
        with iio.get_writer(
            str(args.output),
            fps=30,
            codec="libx264",
            macro_block_size=1,
            ffmpeg_params=[
                "-crf",
                "17",
                "-preset",
                "fast",
                "-threads",
                "2",
                "-movflags",
                "+faststart",
            ],
        ) as writer:
            for frame in range(120):
                u = min(1.0, max(0.0, (frame - 24) / 81))
                ease = u * u * (3 - 2 * u)
                angle = math.pi * ease
                target = initial_target * (1 - ease) + end_target * ease
                radius = 4.5 * (1 - ease) + end_radius * ease
                height = 0.8 * (1 - ease) + end_height * ease
                position = (
                    target
                    + radius * (forward * math.cos(angle) + right * math.sin(angle))
                    + [0, height, 0]
                )
                fov = math.radians(58) * (1 - ease) + endpoint[6] * ease
                values = vector(*position, *target, fov)
                race.step([stk.Action(), stk.Action()])
                if not native.kart_camera_set(0, values):
                    raise RuntimeError("Native camera rejected the requested position")
                pixels = np.array(race.render_data[0].image)
                writer.append_data(pixels)
                if frame in (0, 24, 64, 105, 119):
                    Image.fromarray(pixels).save(
                        args.output.with_name(args.output.stem + f"-{frame:03}.png")
                    )
                world.update()
                displacement = max(
                    float(np.linalg.norm(p.kart.location - before))
                    for p, before in zip(world.players, positions, strict=True)
                )
                rotation_error = max(
                    float(np.linalg.norm(p.kart.rotation - before))
                    for p, before in zip(world.players, rotations, strict=True)
                )
                proof["max_kart_displacement"] = max(proof["max_kart_displacement"], displacement)
                proof["max_kart_rotation_error"] = max(
                    proof["max_kart_rotation_error"], rotation_error
                )
                proof["poses"].append(list(values))
        if proof["max_kart_displacement"] >= 0.1 or proof["max_kart_rotation_error"] >= 0.001:
            raise RuntimeError("The karts moved during filming; this intro failed verification")
        proof["passed"] = True
        args.output.with_suffix(".json").write_text(json.dumps(proof, indent=2))
        print(json.dumps({k: v for k, v in proof.items() if k != "poses"}), flush=True)
    finally:
        if race:
            race.stop()
        stk.clean()


if __name__ == "__main__":
    main()
