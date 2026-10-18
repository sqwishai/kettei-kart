"""The nine ordinary controls offered on every decision."""

from dataclasses import asdict, dataclass

PHYSICS_HZ = 30
ACTION_TICKS = 6
ACTION_SECONDS = ACTION_TICKS / PHYSICS_HZ


@dataclass(frozen=True)
class Control:
    steer: float
    acceleration: float
    brake: bool = False
    rescue: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


CONTROLS = {
    "hard_left": Control(-1.0, 1.0),
    "left": Control(-0.4, 1.0),
    "straight": Control(0.0, 1.0),
    "right": Control(0.4, 1.0),
    "hard_right": Control(1.0, 1.0),
    "brake": Control(0.0, 0.0, brake=True),
    "reverse_left": Control(-1.0, 0.0, brake=True),
    "reverse_right": Control(1.0, 0.0, brake=True),
    "rescue": Control(0.0, 0.0, rescue=True),
}

OUTCOMES = {
    "hard_left": "Accelerate and steer fully LEFT.",
    "left": "Accelerate and steer gently LEFT.",
    "straight": "Accelerate without steering.",
    "right": "Accelerate and steer gently RIGHT.",
    "hard_right": "Accelerate and steer fully RIGHT.",
    "brake": "Brake; after stopping, reverse straight.",
    "reverse_left": "Reverse with the wheels turned LEFT.",
    "reverse_right": "Reverse with the wheels turned RIGHT.",
    "rescue": "Press the ordinary rescue key: return to the track, with a time penalty.",
}


def choose(
    probabilities: dict[str, float], controls: dict[str, Control] = CONTROLS
) -> tuple[str, Control]:
    """Use argmax; preserve provider order when probabilities are tied."""
    name = max(probabilities, key=probabilities.get)
    return name, controls[name]
