"""
Command-line interface.

    gesturecontrol [run] [--port PORT] [--camera N] [--no-ui] ...

``run`` is the default command, so ``gesturecontrol --port /dev/ttyACM0``
works as before. Further commands are registered in ``COMMANDS``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from gesturecontrol import __version__
from gesturecontrol.app import RunOptions, run
from gesturecontrol.camera import parse_source
from gesturecontrol.config import (
    DEFAULT_CAMERA_INDEX,
    DEFAULT_DETECTION_CONFIDENCE,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_TRACKING_CONFIDENCE,
    MIN_SWITCH_INTERVAL_S,
)

logger = logging.getLogger(__name__)


def add_camera_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--camera",
        type=parse_source,
        default=DEFAULT_CAMERA_INDEX,
        metavar="INDEX|FILE",
        help="camera index or video file (default: %(default)s)",
    )
    parser.add_argument("--width", type=int, default=DEFAULT_FRAME_WIDTH, help="requested width")
    parser.add_argument("--height", type=int, default=DEFAULT_FRAME_HEIGHT, help="requested height")
    parser.add_argument(
        "--detection-confidence",
        type=float,
        default=DEFAULT_DETECTION_CONFIDENCE,
        help="MediaPipe palm detection confidence (default: %(default)s)",
    )
    parser.add_argument(
        "--tracking-confidence",
        type=float,
        default=DEFAULT_TRACKING_CONFIDENCE,
        help="MediaPipe landmark tracking confidence (default: %(default)s)",
    )
    parser.add_argument(
        "--no-mirror", action="store_true", help="do not flip the picture horizontally"
    )
    parser.add_argument(
        "--detect-every-frame",
        action="store_true",
        help="run the palm detector on every frame instead of tracking (for benchmarks)",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "solutions", "tasks"),
        default="auto",
        help="MediaPipe API to use (default: solutions when installed, else tasks)",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
        help="hand landmarker bundle for the Tasks API (default: per-user cache)",
    )
    parser.add_argument(
        "--no-download", action="store_true", help="fail instead of fetching a missing model"
    )


def add_relay_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", default=None, help="serial port of the Arduino (Firmata)")
    parser.add_argument(
        "--active-high",
        action="store_true",
        help="relay module switches on HIGH (default: active-low, on when LOW)",
    )
    parser.add_argument(
        "--min-switch-interval",
        type=float,
        default=MIN_SWITCH_INTERVAL_S,
        metavar="SECONDS",
        help="a relay is not switched twice within this time (default: %(default)s)",
    )


def build_run_parser(parser: argparse.ArgumentParser) -> None:
    add_camera_arguments(parser)
    add_relay_arguments(parser)
    parser.add_argument("--no-ui", action="store_true", help="headless: no window is opened at all")
    parser.add_argument("--max-frames", type=int, default=None, help="stop after this many frames")


def cmd_run(args: argparse.Namespace) -> int:
    opts = RunOptions(
        port=args.port,
        camera=args.camera,
        width=args.width,
        height=args.height,
        no_ui=args.no_ui,
        detection_confidence=args.detection_confidence,
        tracking_confidence=args.tracking_confidence,
        active_low=not args.active_high,
        min_switch_interval=args.min_switch_interval,
        max_frames=args.max_frames,
        mirror=not args.no_mirror,
        detect_every_frame=args.detect_every_frame,
        backend=args.backend,
        model_path=args.model,
        allow_download=not args.no_download,
    )
    return run(opts)


def build_simulate_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("scenarios", nargs="*", help="scenario names (default: all)")
    parser.add_argument("--list", action="store_true", help="list scenarios and exit")
    parser.add_argument("--realtime", action="store_true", help="replay at the scenario frame rate")
    parser.add_argument(
        "--verbose-frames", action="store_true", help="print every frame, not only changes"
    )
    parser.add_argument(
        "--min-switch-interval",
        type=float,
        default=MIN_SWITCH_INTERVAL_S,
        metavar="SECONDS",
        help="relay switching interval to simulate (default: %(default)s)",
    )


def cmd_simulate(args: argparse.Namespace) -> int:
    from gesturecontrol.simulate import list_scenarios, simulate

    if args.list:
        list_scenarios()
        return 0
    return simulate(
        args.scenarios,
        min_switch_interval=args.min_switch_interval,
        realtime=args.realtime,
        verbose=args.verbose_frames,
    )


Command = tuple[str, Callable[[argparse.ArgumentParser], None], Callable[[argparse.Namespace], int]]

COMMANDS: dict[str, Command] = {
    "run": ("run the camera-to-relay loop (default)", build_run_parser, cmd_run),
    "simulate": (
        "replay scripted landmark sequences through the classifier and relay logic",
        build_simulate_parser,
        cmd_simulate,
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gesturecontrol",
        description="Finger counting from a webcam driving a 4-channel relay module.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, (help_text, build, _handler) in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text, description=help_text)
        build(sub)
    return parser


def _with_default_command(argv: Sequence[str]) -> list[str]:
    """Insert ``run`` when the first argument is not a command or a global option."""
    args = list(argv)
    if not args:
        return ["run"]
    if args[0] in COMMANDS or args[0] in ("-h", "--help", "--version"):
        return args
    return ["run", *args]


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(_with_default_command(sys.argv[1:] if argv is None else argv))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    _help, _build, handler = COMMANDS[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
