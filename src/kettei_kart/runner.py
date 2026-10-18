"""A synchronous camera -> decision -> control loop with immutable evidence."""

import hashlib
import json
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import imageio.v2 as iio
import numpy as np

from . import __version__
from .actions import ACTION_SECONDS, ACTION_TICKS, OUTCOMES, PHYSICS_HZ, choose
from .client import DecisionClient
from .metrics import driving_metrics
from .observation import History
from .simulator import Simulator


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def run(
    *,
    track: str,
    seed: int,
    output: Path,
    provider: str = "sqwish",
    seconds: int = 300,
    rate: float = 1.5,
    video: bool = True,
    max_attempts: int = 5000,
    wall_seconds: int = 1800,
) -> dict:
    client = DecisionClient(provider, rate=rate, max_attempts=max_attempts)
    output.mkdir(parents=True, exist_ok=False)
    (output / "observations").mkdir()
    manifest = {
        "created_utc": datetime.now(UTC).isoformat(),
        "version": __version__,
        "model": client.config.model,
        "provider": provider,
        "track": track,
        "seed": seed,
        "simulator": "PySuperTuxKart2 0.7.4 / STK 1.5",
        "lap_count": 1,
        "resolution": [640, 480],
        "physics_hz": PHYSICS_HZ,
        "action_ticks": ACTION_TICKS,
        "game_seconds_cap": seconds,
        "request_rate_cap": rate,
        "max_attempts": max_attempts,
        "wall_seconds_cap": wall_seconds,
        "input_contract": "Camera and visible HUD, own actions, public driving rules.",
        "timing": "Simulation pauses during inference; replay runs at game speed.",
        "source_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))
        },
    }
    write_json(output / "manifest.json", manifest)
    simulator, writer, rows = None, None, []
    started = time.monotonic()
    error, end = None, "game_time_limit"
    initial = final = None
    try:
        simulator = Simulator(track, seed)
        initial = final = simulator.evaluate()
        manifest["rendered_resolution"] = list(simulator.camera().size)
        manifest["track_length_evaluator_only"] = simulator.track_length
        write_json(output / "manifest.json", manifest)
        if video:
            writer = iio.get_writer(
                str(output / "camera.mp4"),
                fps=PHYSICS_HZ,
                codec="libx264",
                macro_block_size=1,
                ffmpeg_params=["-crf", "18", "-preset", "fast", "-movflags", "+faststart"],
            )
        history = History()
        with (output / "decisions.jsonl").open("w", encoding="utf-8") as log:
            for step in range(int(seconds / ACTION_SECONDS)):
                if (output / "STOP").exists():
                    end = "stopped"
                    break
                if time.monotonic() - started > wall_seconds:
                    raise RuntimeError("Wall time limit reached")
                observation = history.observe(simulator.camera(), step * ACTION_TICKS)
                for frame in observation.frames:
                    path = output / frame.filename
                    if not path.exists():
                        path.write_bytes(frame.jpeg)
                probabilities, receipt = client.decide(observation)
                name, control = choose(probabilities)
                for camera in simulator.advance(control, capture=video):
                    writer.append_data(np.asarray(camera))
                final = simulator.evaluate()
                history.record_action(name, control)
                row = {
                    "step": step,
                    "tick": (step + 1) * ACTION_TICKS,
                    "action": name,
                    "control": control.as_dict(),
                    "probabilities": probabilities,
                    "receipt": receipt,
                    "evaluator": final,
                    "image_files": [f.filename for f in observation.frames],
                    "frame_sha256": [f.sha256 for f in observation.frames],
                    "model_context": observation.context,
                    "offered_outcomes": OUTCOMES,
                }
                log.write(json.dumps(row, allow_nan=False) + "\n")
                log.flush()
                rows.append(row)
                if step % 30 == 0:
                    print(f"{track}: {(step + 1) * ACTION_SECONDS:.1f}s | {name}", flush=True)
                if final["finished"]:
                    end = "finished"
                    break
    except (Exception, KeyboardInterrupt) as exc:
        # Exception messages come only from validated local paths and this client.
        error = client.redact(exc) if str(exc) else type(exc).__name__
        end = "interrupted" if isinstance(exc, KeyboardInterrupt) else "error"
    finally:
        if simulator is not None:
            simulator.camera().save(output / "final.jpg", quality=92)
        if writer is not None:
            writer.close()
        if simulator is not None:
            simulator.close()
        client.close()
    samples = [r["evaluator"] for r in rows]
    best = max((r["distance"] for r in samples), default=0)
    length = manifest.get("track_length_evaluator_only", 1)
    progress = 1.0 if final and final["finished"] else max(0, min(1, best / length))
    summary = {
        "model": client.config.model,
        "provider": provider,
        "track": track,
        "seed": seed,
        "valid": error is None and end != "stopped",
        "end": end,
        "error": error,
        "decisions": len(rows),
        "game_seconds": len(rows) * ACTION_SECONDS,
        "wall_seconds": time.monotonic() - started,
        "attempts": client.attempts,
        "progress_fraction": progress,
        "initial_evaluator": initial,
        "final": final,
        "action_counts": dict(Counter(r["action"] for r in rows)),
        **driving_metrics(rows),
        "latency_median_s": statistics.median(r["receipt"]["latency_s"] for r in rows)
        if rows
        else None,
        "api_roundtrip_median_s": statistics.median(
            r["receipt"]["attempts"][-1]["seconds"] for r in rows
        )
        if rows
        else None,
    }
    write_json(output / "summary.json", summary)
    return summary
