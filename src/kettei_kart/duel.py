"""A genuine shared-world race: two cameras, two models, one simulation clock."""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imageio.v2 as iio
import numpy as np

from .actions import ACTION_SECONDS, ACTION_TICKS, CONTROLS, OUTCOMES, Control, choose
from .client import DecisionClient, RateLimiter
from .metrics import driving_metrics
from .observation import History, Observation
from .runner import write_json
from .simulator import Simulator

RACE_GUIDANCE = (
    "This is a one-lap race against one other kart in the same game. Your kart is the one "
    "at the bottom center of YOUR camera. Both karts use the same vehicle and controls. "
    "Finish the lap ahead of the opponent; keep making forward progress. Contact with the "
    "other kart is part of the game. Use only the offered controls.\n"
    "Use the CURRENT camera to choose steering; older cameras are only evidence of motion, "
    "not the road you should aim at now. Look along the visible road into the next bend and "
    "start turning before your kart reaches the outside edge. If the road is clearly to one "
    "side of your kart, use a short full-steering correction rather than holding a gentle "
    "turn too long; then reassess and release steering once aligned. If you are moving "
    "toward a fence, cliff or outside edge and cannot turn back in time, a brief brake is "
    "preferable to accelerating farther off the road. After the rescue bird puts you down, "
    "align with the road that is visible NOW instead of repeating the turn that preceded "
    "the rescue. The other Tux is your opponent, not a waypoint: keep a safe road line "
    "around it and do not follow it off the track.\n"
)


def race_observation(history: History, camera, tick: int) -> Observation:
    observation = history.observe(camera, tick)
    return Observation(observation.context + "\n" + RACE_GUIDANCE, observation.frames)


def run_duel(
    *,
    output: Path,
    track: str = "lighthouse",
    seed: int = 501,
    swap: bool = False,
    seconds: int = 300,
    rate: float = 1.5,
) -> dict:
    providers = ["typesafe", "sqwish"] if swap else ["sqwish", "typesafe"]
    clients = [DecisionClient(provider, rate=7.5, max_attempts=5000) for provider in providers]
    gate = RateLimiter(rate)
    for client in clients:
        client.send_gate = gate
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "manifest.json",
        {
            "track": track,
            "seed": seed,
            "slot_providers": providers,
            "laps": 1,
            "mode": "NORMAL_RACE",
            "karts": ["tux", "tux"],
            "game_seconds_cap": seconds,
            "shared_request_rate": rate,
            "actions": OUTCOMES,
            "guidance": RACE_GUIDANCE,
            "guidance_sha256": hashlib.sha256(RACE_GUIDANCE.encode()).hexdigest(),
            "timing": "Both models decide from their own pre-step camera before six shared physics ticks.",
            "scoring": "Continue until both finish or the time limit. Compare engine finish times; never infer a time gap from distance.",
            "completion_protocol": "both-finish-v1",
            "source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(Path(__file__).parent.glob("*.py"))
            },
        },
    )
    histories = [History(), History()]
    logs, writers, rows = [], [], [[], []]
    simulator, states, error, end = None, [], None, "game_time_limit"
    started = time.monotonic()
    try:
        simulator = Simulator(track, seed, players=2)
        manifest = json.loads((output / "manifest.json").read_text())
        manifest["camera_capture"] = simulator.capture_contract
        write_json(output / "manifest.json", manifest)
        states = [simulator.evaluate(i) for i in range(2)]
        write_json(output / "initial.json", states)
        for provider in providers:
            directory = output / provider
            (directory / "observations").mkdir(parents=True)
            logs.append((directory / "decisions.jsonl").open("w", encoding="utf-8"))
            writers.append(
                iio.get_writer(
                    str(directory / "camera.mp4"),
                    fps=5,
                    codec="libx264",
                    macro_block_size=1,
                    ffmpeg_params=["-crf", "18", "-preset", "fast", "-threads", "2"],
                )
            )
        with ThreadPoolExecutor(max_workers=2) as pool:
            for step in range(int(seconds / ACTION_SECONDS)):
                if (output / "STOP").exists():
                    end = "stopped"
                    break
                if time.monotonic() - started > 3600:
                    raise RuntimeError("Head-to-head wall time limit reached")
                observations = {}
                for slot, provider in enumerate(providers):
                    camera = simulator.camera(slot)
                    writers[slot].append_data(np.asarray(camera))
                    if states[slot]["finished"]:
                        continue
                    obs = race_observation(histories[slot], camera, step * ACTION_TICKS)
                    observations[slot] = obs
                    for frame in obs.frames:
                        path = output / provider / frame.filename
                        if not path.exists():
                            path.write_bytes(frame.jpeg)
                pending = {
                    slot: pool.submit(clients[slot].decide, obs, OUTCOMES)
                    for slot, obs in observations.items()
                }
                # Resolve every response before stepping either kart. A transport
                # failure stops the race instead of granting the other kart time.
                decisions = {slot: future.result() for slot, future in pending.items()}
                # Finished players receive no more API calls. Neutral controls keep
                # the replay clock aligned without inventing a model decision.
                selected = [
                    choose(decisions[slot][0], CONTROLS)
                    if slot in decisions
                    else ("finished", Control(0.0, 0.0))
                    for slot in range(2)
                ]
                simulator.advance_both(tuple(control for _, control in selected))
                states = [simulator.evaluate(i) for i in range(2)]
                for slot in range(2):
                    name, control = selected[slot]
                    obs = observations.get(slot)
                    probabilities, receipt = decisions.get(slot, (None, None))
                    if obs is not None:
                        histories[slot].record_action(name, control)
                    row = {
                        "step": step,
                        "tick": (step + 1) * ACTION_TICKS,
                        "action": name,
                        "decision_made": obs is not None,
                        "control": control.as_dict(),
                        "probabilities": probabilities,
                        "receipt": receipt,
                        "evaluator": states[slot],
                        "model_context": obs.context if obs else None,
                        "image_files": [f.filename for f in obs.frames] if obs else [],
                        "frame_sha256": [f.sha256 for f in obs.frames] if obs else [],
                        "offered_outcomes": OUTCOMES if obs else None,
                    }
                    rows[slot].append(row)
                    logs[slot].write(json.dumps(row, allow_nan=False) + "\n")
                    logs[slot].flush()
                if step % 30 == 0:
                    print(
                        f"{(step + 1) * ACTION_SECONDS:.1f}s | "
                        + " | ".join(
                            f"{provider}: {name}"
                            for provider, (name, _) in zip(providers, selected, strict=True)
                        ),
                        flush=True,
                    )
                if all(state["finished"] for state in states):
                    end = "finished"
                    break
    except (Exception, KeyboardInterrupt) as exc:
        error = str(exc) or type(exc).__name__
        for client in clients:
            error = client.redact(error)
        end = "error"
    finally:
        if simulator:
            for slot, provider in enumerate(providers):
                (output / provider).mkdir(exist_ok=True)
                try:
                    simulator.camera(slot).save(output / provider / "final.jpg", quality=92)
                except Exception as exc:
                    error = error or str(exc)
                    end = "error"
            simulator.close()
        for log in logs:
            log.close()
        for writer in writers:
            writer.close()
        for client in clients:
            client.close()
    finishers = [
        (state["finish_time"], providers[i]) for i, state in enumerate(states) if state["finished"]
    ]
    finishers.sort()
    tied = len(finishers) == 2 and abs(finishers[0][0] - finishers[1][0]) < 1e-6
    winner = finishers[0][1] if finishers and not tied and error is None else None
    valid = error is None and end != "stopped"
    result = {
        "valid": valid,
        "end": end,
        "error": error,
        "track": track,
        "seed": seed,
        "slot_providers": providers,
        "states": states,
        "winner": winner,
        "tie": tied,
        "both_finished": len(finishers) == 2,
        "finish_times": {provider: finish_time for finish_time, provider in finishers},
        "finish_gap_seconds": (
            finishers[1][0] - finishers[0][0] if valid and len(finishers) == 2 else None
        ),
        "decisions_per_model": [sum(row["decision_made"] for row in part) for part in rows],
        "recorded_intervals": len(rows[0]),
        "game_seconds": len(rows[0]) * ACTION_SECONDS,
        "wall_seconds": time.monotonic() - started,
        "request_attempts": [client.attempts for client in clients],
        "player_metrics": {
            provider: driving_metrics([row for row in part if row["decision_made"]])
            for provider, part in zip(providers, rows, strict=True)
        },
    }
    write_json(output / "result.json", result)
    return result
