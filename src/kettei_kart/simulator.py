"""Own the single-process simulator; keep evaluation state out of observations."""

from collections.abc import Iterator

import numpy as np
from PIL import Image

from .actions import ACTION_TICKS, PHYSICS_HZ, Control
from .native_camera import CameraGuard

_graphics_used = False

TRACKS = {
    "lighthouse": "Lighthouse",
    "olivermath": "Oliver's Math Class",
    "hacienda": "Hacienda",
    "zengarden": "Zen Garden",
    "snowtuxpeak": "Snow Peak",
}


def track_title(track: str) -> str:
    """Display names belong to the recording, never the model observation."""
    return TRACKS.get(track, track.replace("_", " ").title())


class Simulator:
    def __init__(
        self,
        track: str,
        seed: int,
        *,
        players: int = 1,
        player_names: tuple[str, ...] | None = None,
        player_colors: tuple[float, ...] | None = None,
    ):
        global _graphics_used
        if _graphics_used:
            raise RuntimeError(
                "Run each race or replay in a fresh process: the native graphics runtime "
                "cannot safely initialize again after cleanup."
            )
        _graphics_used = True
        # Import lazily: analysis, rendering and unit tests need no graphics context.
        import pystk2 as stk

        self._stk = stk
        self._race = None
        self._camera_guard = None
        graphics = stk.GraphicsConfig.ld()
        graphics.screen_width, graphics.screen_height = 384, 288
        stk.init(graphics)
        try:
            config = stk.RaceConfig()
            if players not in (1, 2):
                raise ValueError("Only one-player time trials and two-player races are supported")
            config.track, config.seed, config.laps, config.num_kart = track, seed, 1, players
            config.step_size, config.difficulty = 1 / PHYSICS_HZ, 1
            config.mode = (
                stk.RaceConfig.RaceMode.TIME_TRIAL
                if players == 1
                else stk.RaceConfig.RaceMode.NORMAL_RACE
            )
            # The binding filters racing tracks via NORMAL_RACE; TIME_TRIAL
            # uses the same tracks but is not accepted by this discovery API.
            available = stk.list_tracks(stk.RaceConfig.RaceMode.NORMAL_RACE)
            if track not in available:
                raise ValueError(
                    f"Unknown racing track {track!r}. Available: {', '.join(available)}"
                )
            config.players[0].kart = "tux"
            if players == 2:
                config.players.append(stk.PlayerConfig(kart="tux"))
                # Explicit num_cameras follows race rank in this engine version.
                # Player-attached cameras keep identity when the race order changes.
                config.num_cameras = 0
            for player in config.players:
                player.controller = stk.PlayerConfig.Controller.PLAYER_CONTROL
            if player_names is not None:
                if len(player_names) != players:
                    raise ValueError("Supply exactly one display name for each player")
                if players == 1:
                    config.players[0].name = player_names[0]
            if player_colors is not None:
                if len(player_colors) != players or any(not 0 <= hue <= 1 for hue in player_colors):
                    raise ValueError("Supply one hue in [0, 1] for each player")
                for player, hue in zip(config.players, player_colors, strict=True):
                    player.color = hue
            self._race = stk.Race(config)
            self._race.start()
            self._world = stk.WorldState()
            if players == 2:
                self._world.update()
                self._camera_guard = CameraGuard(
                    stk,
                    tuple(int(player.kart.id) for player in self._world.players),
                    graphics.screen_width / graphics.screen_height,
                )
                if player_colors:
                    for slot, hue in enumerate(player_colors):
                        if not self._camera_guard.native.kart_replay_set_hue(slot, hue):
                            raise RuntimeError("The kart material does not support replay colours")
                if player_names:
                    for slot, name in enumerate(player_names):
                        if not self._camera_guard.native.kart_replay_label(slot, name.encode()):
                            raise RuntimeError("Could not add the replay player label")
            track_info = stk.Track()
            track_info.update()
            self.track_length = float(track_info.length)
            # Fixed countdown. No privileged state is used to choose when to start.
            for _ in range(150):
                self._race.step([stk.Action() for _ in range(players)])
        except BaseException:
            self.close()
            raise

    def camera(self, player: int = 0) -> Image.Image:
        pixels = np.array(self._race.render_data[player].image)
        if self._camera_guard:
            self._camera_guard.validate(player, pixels.shape[1] / pixels.shape[0])
        return Image.fromarray(pixels).convert("RGB")

    @property
    def capture_contract(self) -> dict:
        return (
            self._camera_guard.manifest() if self._camera_guard else {"protocol": "single-player"}
        )

    def advance_both(self, controls: tuple[Control, Control], capture=None) -> None:
        """Apply two simultaneous actions in one shared world and clock."""
        actions = []
        for control in controls:
            action = self._stk.Action()
            for key, value in control.as_dict().items():
                setattr(action, key, value)
            actions.append(action)
        for substep in range(ACTION_TICKS):
            if capture is not None:
                capture((self.camera(0), self.camera(1)))
            self._world.update()
            if all(player.kart.has_finished_race for player in self._world.players):
                # The engine's result-screen transition is not part of a race.
                # Hold its final image for any remainder of this video interval.
                continue
            for action, control in zip(actions, controls, strict=True):
                action.rescue = control.rescue and substep == 0
            self._race.step(actions)

    def advance(self, control: Control, *, capture: bool = False) -> Iterator[Image.Image]:
        """Advance exactly six physics ticks, tapping rescue only on the first."""
        action = self._stk.Action()
        for key, value in control.as_dict().items():
            setattr(action, key, value)
        for substep in range(ACTION_TICKS):
            if capture:
                yield self.camera()
            action.rescue = control.rescue and substep == 0
            self._race.step(action)

    def evaluate(self, player: int = 0) -> dict:
        """Evaluation only; callers must never put this into an Observation."""
        self._world.update()
        kart = self._world.players[player].kart
        return {
            "distance": float(kart.overall_distance),
            "on_road": bool(kart.is_on_road),
            "speed": float(kart.speed),
            "laps": int(kart.finished_laps),
            "finished": bool(kart.has_finished_race),
            "finish_time": float(kart.finish_time),
            "position": int(kart.position),
            "kart_id": int(kart.id),
            "location": [float(v) for v in kart.location],
        }

    def close(self) -> None:
        if self._race is not None:
            self._race.stop()
            self._race = None
        self._stk.clean()
