"""Render two players' recorded cameras and action distributions."""

import json
from pathlib import Path

import imageio.v2 as iio
import numpy as np
from PIL import Image, ImageDraw

from .actions import ACTION_SECONDS, Control
from .render import ACCENT, BACKGROUND, MUTED, PANEL, SIZE, TEXT, text
from .runner import write_json
from .simulator import Simulator, track_title

NAMES = {"sqwish": "Kettei Fat", "typesafe": "Jev 1.14"}
KART_NAMES = {"sqwish": "Kettei", "typesafe": "Jev"}
LABELS = {
    "hard_left": "Full left",
    "left": "Gentle left",
    "straight": "Straight",
    "right": "Gentle right",
    "hard_right": "Full right",
    "brake": "Brake / reverse",
    "reverse_left": "Reverse left",
    "reverse_right": "Reverse right",
    "rescue": "Rescue",
}


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def smooth_cameras(directory: Path, output: Path) -> dict[str, Path]:
    """Replay saved controls at 30 fps, verifying physics after every decision."""
    manifest = json.loads((directory / "manifest.json").read_text())
    providers = manifest["slot_providers"]
    rows = [read_rows(directory / provider / "decisions.jsonl") for provider in providers]
    if len(rows[0]) != len(rows[1]):
        raise ValueError("Cannot replay unequal decision counts")
    output.mkdir(parents=True, exist_ok=False)
    paths = {provider: output / f"{provider}-camera.mp4" for provider in providers}
    writers, simulator = [], None
    max_error = 0.0
    try:
        simulator = Simulator(
            manifest["track"],
            manifest["seed"],
            players=2,
            player_names=tuple(KART_NAMES[provider] for provider in providers),
        )
        writers = [
            iio.get_writer(
                str(paths[p]),
                fps=30,
                codec="libx264",
                macro_block_size=1,
                ffmpeg_params=["-crf", "17", "-preset", "fast", "-threads", "2"],
            )
            for p in providers
        ]

        def capture(cameras):
            for writer, camera in zip(writers, cameras, strict=True):
                writer.append_data(np.asarray(camera))

        for step, pair in enumerate(zip(*rows, strict=True)):
            simulator.advance_both(
                tuple(Control(**row["control"]) for row in pair), capture=capture
            )
            for slot, row in enumerate(pair):
                actual, expected = simulator.evaluate(slot), row["evaluator"]
                error = max(
                    abs(actual["distance"] - expected["distance"]),
                    *(
                        abs(a - b)
                        for a, b in zip(actual["location"], expected["location"], strict=True)
                    ),
                )
                max_error = max(max_error, error)
                if error > 0.02 or actual["finished"] != expected["finished"]:
                    raise ValueError(f"Replay physics diverged at decision {step}, player {slot}")
        write_json(
            output / "verification.json",
            {
                "passed": True,
                "decisions": len(rows[0]),
                "max_physics_error": max_error,
                "fps": 30,
                "method": "Recorded controls; no model calls",
                "player_names": [KART_NAMES[provider] for provider in providers],
                "names_added_for_replay": True,
            },
        )
        for slot, provider in enumerate(providers):
            simulator.camera(slot).save(output / f"{provider}-final.jpg", quality=92)
    finally:
        for writer in writers:
            writer.close()
        if simulator:
            simulator.close()
    return paths


def compose_pair(
    cameras: dict, rows: dict, result: dict, game_time: float, *, finished: bool = False
) -> Image.Image:
    canvas = Image.new("RGB", SIZE, BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    text(draw, (28, 18), "Kettei Fat", 39, ACCENT, True)
    text(draw, (1892, 18), "Jev 1.14", 39, "#78C8F4", True, anchor="ra")
    center = track_title(result["track"])
    if finished and result.get("winner"):
        center = f"{NAMES[result['winner']]} wins  /  {track_title(result['track'])}"
    text(draw, (960, 23), center, 26, TEXT, True, anchor="ma")
    text(draw, (960, 65), f"{game_time:.1f}s", 23, MUTED, anchor="ma")
    for slot, provider in enumerate(("sqwish", "typesafe")):
        x = 24 + slot * 960
        canvas.paste(
            cameras[provider].convert("RGB").resize((912, 684), Image.Resampling.LANCZOS), (x, 108)
        )
        row = rows[provider]
        color = ACCENT if provider == "sqwish" else "#78C8F4"
        draw.rounded_rectangle((x, 810, x + 912, 1015), 14, fill=PANEL)
        text(draw, (x + 18, 823), "ACTION PROBABILITIES", 17, MUTED, True)
        names = list(row["probabilities"])
        columns = (len(names) + 1) // 2
        width = 876 / columns
        for index, name in enumerate(names):
            xx, yy = x + 18 + (index % columns) * width, 860 + (index // columns) * 75
            probability = row["probabilities"][name]
            selected = row["action"] == name
            text(draw, (xx, yy), LABELS[name], 17, color if selected else TEXT, selected)
            text(draw, (xx, yy + 25), f"{probability * 100:.1f}%", 17, color if selected else MUTED)
            draw.rounded_rectangle((xx + 59, yy + 32, xx + width - 13, yy + 40), 4, fill="#29394C")
            if probability:
                draw.rounded_rectangle(
                    (xx + 59, yy + 32, xx + 59 + max(2, probability * (width - 72)), yy + 40),
                    4,
                    fill=color,
                )
    text(
        draw,
        (26, 1036),
        "GAME-SPEED REPLAY · SAME WORLD · SAME HARNESS · BOTH CHOOSE BEFORE THE CLOCK ADVANCES"
        + (" · PLAYER LABELS ADDED IN REPLAY" if result.get("names_added_for_replay") else ""),
        17,
        MUTED,
    )
    return canvas


def render_duel(directory: Path, output: Path, *, smooth: bool = True) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    result = json.loads((directory / "result.json").read_text())
    manifest = json.loads((directory / "manifest.json").read_text())
    result.setdefault("track", manifest["track"])
    rows = {p: read_rows(directory / p / "decisions.jsonl") for p in NAMES}
    if not rows["sqwish"] or len(rows["sqwish"]) != len(rows["typesafe"]):
        raise ValueError("A paired replay requires equal, nonempty decision streams")
    paths = (
        smooth_cameras(directory, output.with_suffix(".replay"))
        if smooth
        else {p: directory / p / "camera.mp4" for p in NAMES}
    )
    result["names_added_for_replay"] = smooth
    readers = {p: iio.get_reader(str(path)) for p, path in paths.items()}
    fps = readers["sqwish"].get_meta_data()["fps"]
    if readers["typesafe"].get_meta_data()["fps"] != fps:
        raise ValueError("Camera frame rates differ")
    output.parent.mkdir(parents=True, exist_ok=True)
    count = len(rows["sqwish"])
    try:
        with iio.get_writer(
            str(output),
            fps=fps,
            codec="libx264",
            macro_block_size=1,
            ffmpeg_params=[
                "-crf",
                "19",
                "-preset",
                "fast",
                "-threads",
                "2",
                "-movflags",
                "+faststart",
            ],
        ) as writer:
            for frame in range(round(count * ACTION_SECONDS * fps)):
                index = min(int(frame / fps / ACTION_SECONDS + 1e-7), count - 1)
                cameras = {
                    p: Image.fromarray(reader.get_next_data()) for p, reader in readers.items()
                }
                decisions = {p: part[index] for p, part in rows.items()}
                writer.append_data(
                    np.asarray(compose_pair(cameras, decisions, result, frame / fps))
                )
            cameras = {
                p: Image.open(
                    output.with_suffix(".replay") / f"{p}-final.jpg"
                    if smooth
                    else directory / p / "final.jpg"
                )
                for p in NAMES
            }
            final = compose_pair(
                cameras,
                {p: part[-1] for p, part in rows.items()},
                result,
                count * ACTION_SECONDS,
                finished=True,
            )
            for _ in range(round(fps * 3)):
                writer.append_data(np.asarray(final))
    finally:
        for reader in readers.values():
            reader.close()
