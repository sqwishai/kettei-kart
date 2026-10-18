"""A deliberately narrow boundary: camera pixels and the player's own controls."""

import base64
import hashlib
import io
import json
from collections import deque
from dataclasses import dataclass

from PIL import Image

from .actions import ACTION_SECONDS, ACTION_TICKS, PHYSICS_HZ, Control

RESOLUTION = (640, 480)
FRAME_COUNT = 3
FRAME_STRIDE = 5
RECENT_CONTROLS = 6
REPETITION_WINDOW = 30
QUESTION = "Following the stated driving policy, which control should you apply NOW?"
INTRODUCTION = (
    "SuperTuxKart, a Mario Kart-style racing game. Drive the kart at the bottom CENTER of the "
    "camera image forward around the track and complete one lap. The camera follows your kart "
    "from behind. These are ordinary player camera screenshots including the HUD. "
    "Choose the next button press. Steering LEFT turns your kart left; RIGHT turns it right. "
    "The game pauses while you answer. "
)
DRIVING_POLICY = (
    "Follow this driving policy in priority order. "
    "1. If the rescue bird is already lifting or returning your kart, choose straight and "
    "let the animation finish; do not press rescue again during it. "
    "2. If recent pictures show you stationary against a fence, wall or terrain while your "
    "own controls keep accelerating, press rescue now. Repeating a steering input against "
    "an obstacle will not free you. Also use rescue when stranded off the road with no "
    "clear route back visible. Rescue is an ordinary player button and has a time penalty. "
    "3. Otherwise steer toward the road's middle ahead of your kart. Use gentle steering "
    "for small alignment errors, full steering for sharp bends, and straight once aligned. "
    "Do not keep turning just because the last choice was a turn. Compare the oldest and "
    "newest pictures to judge motion; do not infer being stuck from a single picture."
)


@dataclass(frozen=True)
class Frame:
    tick: int
    jpeg: bytes

    @property
    def filename(self) -> str:
        return f"observations/tick-{self.tick:06d}.jpg"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.jpeg).hexdigest()


@dataclass(frozen=True)
class Observation:
    context: str
    frames: tuple[Frame, ...]

    def images(self) -> list[dict]:
        return [
            {"id": i, "media_type": "image/jpeg", "data": base64.b64encode(f.jpeg).decode()}
            for i, f in enumerate(self.frames, 1)
        ]


class History:
    """Keep current, one-second-old and two-second-old camera frames."""

    def __init__(self) -> None:
        self._frames: deque[Frame] = deque(maxlen=(FRAME_COUNT - 1) * FRAME_STRIDE + 1)
        self._actions: deque[dict] = deque(maxlen=REPETITION_WINDOW)

    def record_action(self, name: str, control: Control, ticks: int = ACTION_TICKS) -> None:
        self._actions.append({"action": name, "steer": round(control.steer, 3), "ticks": ticks})

    def observe(self, image: Image.Image, tick: int) -> Observation:
        buffer = io.BytesIO()
        image.convert("RGB").resize(RESOLUTION).save(buffer, "JPEG", quality=90, subsampling=0)
        self._frames.append(Frame(tick, buffer.getvalue()))
        frames = list(self._frames)
        indices = sorted({max(0, len(frames) - 1 - i * FRAME_STRIDE) for i in range(FRAME_COUNT)})
        selected = tuple(frames[i] for i in indices)
        parts = [
            INTRODUCTION,
            f"Each action lasts {ACTION_SECONDS:.3f} seconds of game time.",
            DRIVING_POLICY,
        ]
        if self._actions:
            recent = list(self._actions)
            repeated = []
            for item in reversed(recent):
                if item["action"] != recent[-1]["action"]:
                    break
                repeated.append(item)
            parts.append(
                f"Your latest control was {recent[-1]['action']}, repeated for "
                f"{len(repeated)} recorded choices covering "
                f"{sum(item['ticks'] for item in repeated) / PHYSICS_HZ:.2f} game seconds. "
                "This describes only your inputs; use the pictures to decide whether they worked."
            )
            parts.append(
                "Your recent controls, oldest first: " + json.dumps(recent[-RECENT_CONTROLS:])
            )
        for i, frame in enumerate(selected, 1):
            parts.append(
                f"{'CURRENT' if i == len(selected) else 'PAST'} camera, "
                f"game tick {frame.tick}: <image:{i}>"
            )
        return Observation("\n".join(parts), selected)
