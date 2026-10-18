"""A 1080p game-and-probability replay built entirely from recorded evidence."""

import json
from functools import lru_cache
from pathlib import Path

import imageio.v2 as iio
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .actions import ACTION_SECONDS, OUTCOMES
from .simulator import track_title

SIZE = (1920, 1080)
BACKGROUND, PANEL, TEXT, MUTED, ACCENT = "#090E17", "#121D2B", "#F1F5FA", "#93A5BC", "#B6F777"
LABELS = {
    "hard_left": "Accelerate + full left",
    "left": "Accelerate + gentle left",
    "straight": "Accelerate straight",
    "right": "Accelerate + gentle right",
    "hard_right": "Accelerate + full right",
    "brake": "Brake / reverse straight",
    "reverse_left": "Reverse + left",
    "reverse_right": "Reverse + right",
    "rescue": "Tap rescue",
}
MODEL_NAMES = {"kettei-fat": "Kettei Fat", "d1-ultra": "D1 Ultra", "jev-1.14.0": "Jev 1.14"}


@lru_cache(maxsize=32)
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    suffix = "-Bold" if bold else ""
    paths = [
        Path(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf"
        ),
    ]
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def text(
    draw: ImageDraw.ImageDraw,
    xy: tuple,
    value: str,
    size: int = 24,
    color: str = TEXT,
    bold: bool = False,
    **kwargs,
) -> None:
    draw.text(xy, value, font=font(size, bold), fill=color, **kwargs)


def compose(
    camera: Image.Image,
    row: dict,
    summary: dict,
    game_time: float,
    *,
    chapter: str = "",
    completed: bool = False,
) -> Image.Image:
    canvas = Image.new("RGB", SIZE, BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    model = MODEL_NAMES.get(summary["model"], summary["model"])
    track = track_title(summary["track"])
    text(draw, (34, 23), "sqwish", 25, ACCENT, True)
    text(draw, (173, 17), f"{model} at the wheel", 42, bold=True)
    text(draw, (36, 79), "SUPERTUXKART  /  CAMERA-ONLY CONTROL", 18, MUTED, True)
    text(draw, (1886, 26), track, 29, bold=True, anchor="ra")
    text(draw, (1886, 76), chapter or "ONE LAP  /  NINE POSSIBLE ACTIONS", 17, MUTED, anchor="ra")
    canvas.paste(camera.convert("RGB").resize((1200, 900), Image.Resampling.LANCZOS), (32, 130))
    draw.rounded_rectangle((1264, 130, 1888, 1030), 20, fill=PANEL)
    text(draw, (1292, 153), "MODEL ACTION PROBABILITIES", 19, MUTED, True)
    if completed:
        text(draw, (1292, 188), "LAP COMPLETE", 34, ACCENT, True)
        text(draw, (1292, 235), f"{summary['game_seconds']:.1f}s game time", 21, MUTED)
    else:
        text(draw, (1292, 188), LABELS[row["action"]], 30, ACCENT, True)
        text(
            draw,
            (1292, 235),
            f"Next control: {ACTION_SECONDS:.1f}s   |   Game: {game_time:05.1f}s",
            21,
            MUTED,
        )
    for i, name in enumerate(OUTCOMES):
        y = 288 + i * 67
        selected = name == row["action"]
        color = ACCENT if selected else "#83A8CE"
        probability = row["probabilities"][name]
        text(draw, (1292, y), LABELS[name], 22, TEXT if selected else MUTED, selected)
        text(draw, (1860, y), f"{probability * 100:5.1f}%", 23, color, selected, anchor="ra")
        draw.rounded_rectangle((1292, y + 35, 1860, y + 44), 4, fill="#253446")
        width = 568 * probability
        if width >= 1:
            draw.rounded_rectangle((1292, y + 35, 1292 + max(2, width), y + 44), 4, fill=color)
    draw.line((1292, 905, 1860, 905), fill="#2A394B", width=1)
    text(draw, (1292, 925), "CAMERA + CONTROL HISTORY", 19, MUTED, True)
    text(draw, (1292, 960), "Current frame + up to two past frames", 22)
    text(draw, (1292, 995), "6 recent controls", 20, MUTED)
    text(draw, (32, 1045), "GAME-SPEED REPLAY  ·  Simulation pauses during API calls", 19, MUTED)
    text(
        draw,
        (1886, 1045),
        "Recorded probabilities · Highest probability wins",
        18,
        MUTED,
        anchor="ra",
    )
    return canvas


def render_run(directory: Path, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    summary = json.loads((directory / "summary.json").read_text())
    rows = [json.loads(line) for line in (directory / "decisions.jsonl").read_text().splitlines()]
    if not rows:
        raise ValueError("No recorded decisions to render")
    camera_path = directory / "camera.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    reader = iio.get_reader(str(camera_path)) if camera_path.exists() else None
    fps = 30 if reader else 5
    try:
        with iio.get_writer(
            str(output),
            fps=fps,
            codec="libx264",
            macro_block_size=1,
            ffmpeg_params=["-crf", "19", "-preset", "fast", "-movflags", "+faststart"],
        ) as writer:
            for index in range(round(summary["game_seconds"] * fps)):
                row = rows[min(int(index / fps / ACTION_SECONDS + 1e-7), len(rows) - 1)]
                camera = (
                    Image.fromarray(reader.get_next_data())
                    if reader
                    else Image.open(directory / row["image_files"][-1])
                )
                writer.append_data(np.asarray(compose(camera, row, summary, index / fps)))
            final = Image.open(directory / "final.jpg")
            for _ in range(fps * 2):
                writer.append_data(
                    np.asarray(
                        compose(
                            final,
                            rows[-1],
                            summary,
                            summary["game_seconds"],
                            completed=bool(summary["final"]["finished"]),
                        )
                    )
                )
    finally:
        if reader:
            reader.close()
