"""Public command-line entry points."""

import argparse
import json
from pathlib import Path

from .client import PROVIDERS
from .runner import run


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Use a positive integer")
    return number


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Let Kettei Fat drive SuperTuxKart from camera images."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    race = commands.add_parser(
        "run", help="Drive one full lap and retain the complete decision trace"
    )
    race.add_argument("--track", default="lighthouse", help="Installed racing track ID")
    race.add_argument("--seed", type=int, default=301)
    race.add_argument("--provider", choices=PROVIDERS, default="sqwish")
    race.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New run directory; existing directories are never overwritten",
    )
    race.add_argument("--seconds", type=positive, default=300, help="Maximum game seconds")
    race.add_argument(
        "--rate",
        type=float,
        default=1.5,
        help="Maximum API requests/second, including retries (up to 7.5)",
    )
    race.add_argument("--max-attempts", type=positive, default=5000)
    race.add_argument("--wall-seconds", type=positive, default=1800)
    race.add_argument(
        "--no-video",
        action="store_true",
        help="Save screenshots and probabilities without a camera MP4",
    )
    render = commands.add_parser("render", help="Add a probability panel to a recorded run")
    render.add_argument("run_directory", type=Path)
    render.add_argument("--output", type=Path, required=True)
    duel = commands.add_parser("duel", help="Race Fat and Jev in the same world")
    duel.add_argument("--output", type=Path, required=True)
    duel.add_argument("--track", default="lighthouse", help="Installed racing track ID")
    duel.add_argument("--seed", type=int, default=501)
    duel.add_argument("--swap", action="store_true", help="Swap the models' starting grid slots")
    duel.add_argument("--seconds", type=positive, default=300)
    duel.add_argument(
        "--rate", type=float, default=1.5, help="Combined request rate for both players"
    )
    paired = commands.add_parser("render-duel", help="Render both cameras and probability panels")
    paired.add_argument("run_directory", type=Path)
    paired.add_argument("--output", type=Path, required=True)
    paired.add_argument(
        "--detail", action="store_true", help="Render the verified replay with higher detail"
    )
    paired.add_argument(
        "--daylight", action="store_true", help="Add replay-only daylight lighting and disable fog"
    )
    paired.add_argument(
        "--finish-speed",
        type=int,
        choices=(1, 2, 4, 8, 12, 16, 24, 32),
        default=12,
        help="Playback speed between the first finish and the second approach (default: 12)",
    )
    paired.add_argument(
        "--original-cameras",
        action="store_true",
        help="Use the original 5 fps model views, without replay-added kart names",
    )
    args = parser.parse_args()
    if args.command == "render-duel":
        from .duel_render import render_duel

        if args.original_cameras and (args.detail or args.daylight):
            parser.error("--detail and --daylight require a replay, not --original-cameras")
        render_duel(
            args.run_directory,
            args.output,
            smooth=not args.original_cameras,
            detail=args.detail,
            daylight=args.daylight,
            finish_speed=args.finish_speed,
        )
        return
    if args.command == "duel":
        from .duel import run_duel

        result = run_duel(
            output=args.output,
            track=args.track,
            seed=args.seed,
            swap=args.swap,
            seconds=args.seconds,
            rate=args.rate,
        )
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["end"] == "finished" else 2)
    if args.command == "render":
        from .render import render_run

        render_run(args.run_directory, args.output)
        return
    summary = run(
        track=args.track,
        seed=args.seed,
        provider=args.provider,
        output=args.output,
        seconds=args.seconds,
        rate=args.rate,
        video=not args.no_video,
        max_attempts=args.max_attempts,
        wall_seconds=args.wall_seconds,
    )
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if summary["end"] == "finished" else 2)


if __name__ == "__main__":
    main()
