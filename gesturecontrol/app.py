"""
The control loop: camera -> detector -> pipeline -> relays, with fail-safe
shutdown on every exit path.

Exit codes:

* 0: normal exit (Q pressed, frame budget reached, or a shutdown signal);
* 1: a failure while running (camera stopped delivering frames, board lost);
* 2: a failure during start-up (board, camera or model not available);
* 3: the relays could not be de-energised on the way out.

SIGINT, SIGTERM and SIGHUP request a shutdown; the ``finally`` block always
de-energises the relays and closes the board, whichever path led there.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from gesturecontrol.camera import CameraError, FrameSource, open_source
from gesturecontrol.config import (
    DEFAULT_CAMERA_INDEX,
    DEFAULT_DETECTION_CONFIDENCE,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_TRACKING_CONFIDENCE,
    MIN_SWITCH_INTERVAL_S,
    RELAY_ACTIVE_LOW_DEFAULT,
)
from gesturecontrol.controller import HardwareError, HeartbeatThread, RelayController
from gesturecontrol.filters import Point
from gesturecontrol.model import ModelError
from gesturecontrol.pipeline import GesturePipeline

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_SETUP = 2
EXIT_UNSAFE = 3

QUIT_KEYS = frozenset((ord("q"), ord("Q"), 27))
SCREENSHOT_KEY = ord("s")


@dataclass(frozen=True)
class RunOptions:
    port: str | None = None
    camera: int | str = DEFAULT_CAMERA_INDEX
    width: int = DEFAULT_FRAME_WIDTH
    height: int = DEFAULT_FRAME_HEIGHT
    no_ui: bool = False
    detection_confidence: float = DEFAULT_DETECTION_CONFIDENCE
    tracking_confidence: float = DEFAULT_TRACKING_CONFIDENCE
    active_low: bool = RELAY_ACTIVE_LOW_DEFAULT
    min_switch_interval: float = MIN_SWITCH_INTERVAL_S
    max_frames: int | None = None
    """Stop after this many frames (headless runs and tests)."""
    mirror: bool = True
    """Flip frames horizontally so the picture behaves like a mirror."""
    detect_every_frame: bool = False
    """Run MediaPipe's palm detector on every frame instead of tracking (benchmarking)."""
    backend: str = "auto"
    """MediaPipe API: auto, solutions or tasks."""
    model_path: Path | None = None
    """Hand landmarker bundle for the Tasks API (default: per-user cache)."""
    allow_download: bool = True


class Detector(Protocol):
    def process(self, frame: Any, timestamp_ms: int | None = None) -> list[Point] | None: ...

    def draw(self, frame: Any, points_px: Any = None) -> Any: ...

    def close(self) -> None: ...


class Display(Protocol):
    """A window: shows a frame and returns the pressed key code, or -1."""

    def show(self, frame: Any) -> int: ...

    def close(self) -> None: ...


class OpenCVDisplay:
    WINDOW = "Gesture Automation"

    def __init__(self) -> None:
        import cv2

        self._cv2 = cv2

    def show(self, frame: Any) -> int:
        self._cv2.imshow(self.WINDOW, frame)
        key: int = self._cv2.waitKey(1) & 0xFF
        return key

    def close(self) -> None:
        self._cv2.destroyAllWindows()


def _default_detector(opts: RunOptions) -> Detector:
    from gesturecontrol.detector import HandDetector

    backend = opts.backend
    if backend not in ("auto", "solutions", "tasks"):
        raise ValueError(f"unknown backend {backend!r}")
    return HandDetector(
        min_detection_confidence=opts.detection_confidence,
        min_tracking_confidence=opts.tracking_confidence,
        detect_every_frame=opts.detect_every_frame,
        backend=backend,  # type: ignore[arg-type]
        model_path=opts.model_path,
        allow_download=opts.allow_download,
    )


def _default_source(opts: RunOptions) -> FrameSource:
    return open_source(opts.camera, opts.width, opts.height)


def _default_display() -> Display:
    return OpenCVDisplay()


@dataclass
class Dependencies:
    """Factories the loop uses; tests replace them with fakes."""

    controller: RelayController | None = None
    detector_factory: Callable[[RunOptions], Detector] = _default_detector
    source_factory: Callable[[RunOptions], FrameSource] = _default_source
    display_factory: Callable[[], Display] = _default_display
    clock: Callable[[], float] = time.monotonic
    on_frame: Callable[[int], None] | None = None
    """Called with the frame index after each frame (tests use it to inject events)."""
    signals: tuple[int, ...] = field(
        default_factory=lambda: tuple(
            s for s in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGHUP", None)) if s
        )
    )


class StopRequest:
    """Set by a signal handler or by the loop itself to end the run."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.reason = ""

    def request(self, reason: str) -> None:
        if not self._event.is_set():
            self.reason = reason
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()


def install_signal_handlers(stop: StopRequest, signals: tuple[int, ...]) -> Callable[[], None]:
    """Route the given signals to ``stop``; returns a function restoring the old handlers."""
    previous: dict[int, Any] = {}

    def handler(signum: int, _frame: Any) -> None:
        name = signal.Signals(signum).name
        logger.info("Received %s, shutting down", name)
        stop.request(name)

    for signum in signals:
        try:
            previous[signum] = signal.signal(signum, handler)
        except (ValueError, OSError) as e:
            logger.debug("Cannot install handler for signal %s: %s", signum, e)

    def restore() -> None:
        for signum, old in previous.items():
            signal.signal(signum, old)

    return restore


def _mirror(frame: Any) -> Any:
    import cv2

    return cv2.flip(frame, 1)


def _screenshot(frame: Any) -> None:
    import cv2

    os.makedirs("screenshots", exist_ok=True)
    fname = f"screenshots/gesture_{int(time.time())}.png"
    cv2.imwrite(fname, frame)
    logger.info("Screenshot saved: %s", fname)


def run(opts: RunOptions, deps: Dependencies | None = None) -> int:  # noqa: PLR0912, PLR0915
    deps = deps or Dependencies()
    stop = StopRequest()
    restore_signals = install_signal_handlers(stop, deps.signals)

    controller = deps.controller or RelayController(
        active_low=opts.active_low, min_switch_interval=opts.min_switch_interval
    )
    heartbeat: HeartbeatThread | None = None
    source: FrameSource | None = None
    detector: Detector | None = None
    display: Display | None = None
    started = False
    exit_code = EXIT_OK

    try:
        if opts.port:
            logger.info("Connecting to the board on %s", opts.port)
            controller.connect(opts.port)
            heartbeat = HeartbeatThread(controller)
            heartbeat.start()
        else:
            logger.info("No --port given: relays are simulated")

        logger.info("Opening frame source %s", opts.camera)
        source = deps.source_factory(opts)
        detector = deps.detector_factory(opts)
        if not opts.no_ui:
            display = deps.display_factory()
        pipeline: GesturePipeline | None = None
        started = True
        logger.info("Ready. Show 0-5 fingers. %s", "Press Q to exit." if display else "")

        frames = 0
        fps = 0.0
        fps_frames = 0
        t_start = deps.clock()
        fps_since = t_start

        while not stop.is_set():
            if heartbeat is not None and heartbeat.error is not None:
                raise heartbeat.error

            ok, frame = source.read()
            if not ok:
                raise CameraError("the frame source stopped delivering frames")
            if opts.mirror:
                frame = _mirror(frame)
            h, w = frame.shape[:2]
            if pipeline is None:
                pipeline = GesturePipeline(w, h)

            t = deps.clock()
            landmarks = detector.process(frame, int((t - t_start) * 1000))
            result = pipeline.process(landmarks, t)
            if result.changed:
                controller.set_from_finger_count(result.confirmed_count)
                logger.info(
                    "Gesture: %d finger(s) -> relays %s",
                    result.confirmed_count,
                    "".join("1" if s else "0" for s in controller.states),
                )
            elif controller.pending:
                controller.apply()

            frames += 1
            fps_frames += 1
            now = deps.clock()
            if now - fps_since >= 1.0:
                fps = fps_frames / (now - fps_since)
                fps_frames = 0
                fps_since = now

            if display is not None:
                from gesturecontrol.overlay import draw_overlay

                detector.draw(frame, result.points_px)
                draw_overlay(
                    frame,
                    hand_present=result.hand_present,
                    live_count=result.raw_count,
                    confirmed_count=result.confirmed_count,
                    relay_states=controller.states,
                    fps=fps,
                    hw_connected=controller.is_connected,
                )
                key = display.show(frame)
                if key in QUIT_KEYS:
                    stop.request("quit key")
                elif key == SCREENSHOT_KEY:
                    _screenshot(frame)

            if deps.on_frame is not None:
                deps.on_frame(frames)
            if opts.max_frames is not None and frames >= opts.max_frames:
                stop.request("frame budget reached")

    except HardwareError as e:
        logger.error("Board failure: %s", e)
        exit_code = EXIT_RUNTIME if started else EXIT_SETUP
    except CameraError as e:
        logger.error("Camera failure: %s", e)
        exit_code = EXIT_RUNTIME if started else EXIT_SETUP
    except ModelError as e:
        logger.error("Model failure: %s", e)
        exit_code = EXIT_SETUP
    except KeyboardInterrupt:
        stop.request("keyboard interrupt")
    finally:
        restore_signals()
        if heartbeat is not None:
            heartbeat.stop()
        if detector is not None:
            detector.close()
        if source is not None:
            source.release()
        if display is not None:
            display.close()
        if not controller.cleanup():
            exit_code = EXIT_UNSAFE
        if stop.reason:
            logger.info("Stopped: %s", stop.reason)
        logger.info("Done (exit code %d).", exit_code)
    return exit_code
