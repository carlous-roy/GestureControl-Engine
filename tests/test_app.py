"""The control loop with a fake camera, detector, display and board."""

from __future__ import annotations

import logging
import os
import signal
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pytest

from gesturecontrol import scenarios as sc
from gesturecontrol.app import (
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_SETUP,
    EXIT_UNSAFE,
    Dependencies,
    RunOptions,
    run,
)
from gesturecontrol.camera import CameraError
from gesturecontrol.controller import BoardLike, HardwareError, RelayController
from gesturecontrol.filters import Point
from tests.fakes import FakeBoard, FakeClock

POSES = {n: tuple(sc.synthetic_hand(n).landmarks) for n in range(6)}
N = None  # no hand


class FakeSource:
    def __init__(self, frames: int, fail_at: int | None = None) -> None:
        self.frames = frames
        self.fail_at = fail_at
        self.reads = 0
        self.released = False

    def read(self) -> tuple[bool, Any]:
        i = self.reads
        self.reads += 1
        if i >= self.frames or (self.fail_at is not None and i == self.fail_at):
            return False, None
        return True, np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True


class ScriptedDetector:
    """Returns the scripted landmarks for each frame; no MediaPipe involved."""

    def __init__(self, script: Sequence[tuple[Point, ...] | None]) -> None:
        self.script = list(script)
        self.calls = 0
        self.closed = False

    def process(self, frame: Any) -> list[Point] | None:
        want = self.script[self.calls] if self.calls < len(self.script) else None
        self.calls += 1
        return None if want is None else list(want)

    def draw(self, frame: Any, points_px: Any = None) -> Any:
        return frame

    def close(self) -> None:
        self.closed = True


class FakeDisplay:
    def __init__(self, key_at: dict[int, int] | None = None) -> None:
        self.shows = 0
        self.closed = False
        self.key_at = key_at or {}

    def show(self, frame: Any) -> int:
        self.shows += 1
        return self.key_at.get(self.shows, -1)

    def close(self) -> None:
        self.closed = True


class Harness:
    def __init__(
        self,
        script: Sequence[tuple[Point, ...] | None],
        *,
        port: str | None = "/dev/ttyFAKE",
        fail_read_at: int | None = None,
        camera_fails: bool = False,
        no_ui: bool = True,
        max_frames: int | None = None,
        display: FakeDisplay | None = None,
        factory_failures: list[str] | None = None,
        min_switch_interval: float = 0.0,
    ) -> None:
        self.boards: list[FakeBoard] = []
        failures = list(factory_failures or [])
        self.failures = failures
        self.clock = FakeClock()

        def factory(p: str) -> BoardLike:
            if failures:
                raise HardwareError(failures.pop(0))
            board = FakeBoard(p)
            self.boards.append(board)
            return board

        self.controller = RelayController(
            min_switch_interval=min_switch_interval, board_factory=factory, clock=self.clock
        )
        self.source = FakeSource(len(script), fail_at=fail_read_at)
        self.detector = ScriptedDetector(script)
        self.display = display
        self.display_requests = 0

        def source_factory(_opts: RunOptions) -> FakeSource:
            if camera_fails:
                raise CameraError("could not open camera 0")
            return self.source

        def display_factory() -> FakeDisplay:
            self.display_requests += 1
            assert self.display is not None, "display requested in headless mode"
            return self.display

        self.on_frame: Callable[[int], None] | None = None

        def after_frame(index: int) -> None:
            self.clock.advance(1 / 30)  # the loop runs at a steady 30 frames per second
            if self.on_frame is not None:
                self.on_frame(index)

        self.deps = Dependencies(
            controller=self.controller,
            detector_factory=lambda _opts: self.detector,
            source_factory=source_factory,
            display_factory=display_factory,
            clock=self.clock,
            on_frame=after_frame,
            signals=(),
        )
        self.opts = RunOptions(
            port=port,
            no_ui=no_ui,
            max_frames=len(script) if max_frames is None else max_frames,
            mirror=False,
            min_switch_interval=0.0,
        )

    def run(self) -> int:
        return run(self.opts, self.deps)


def test_headless_run_commits_gestures_and_exits_cleanly() -> None:
    h = Harness([POSES[2]] * 5 + [N] * 3 + [POSES[5]] * 4)
    assert h.run() == EXIT_OK
    assert h.display_requests == 0
    board = h.boards[0]
    levels = [v for spec, v in board.writes if spec == "d:6:o"]
    assert 0 in levels  # relay 2 energised (active-low) at the third frame of pose 2
    assert board.last_levels() == {"d:7:o": 1, "d:6:o": 1, "d:5:o": 1, "d:4:o": 1}
    assert board.exited is True
    assert h.source.released and h.detector.closed


def test_relays_hold_while_the_hand_is_away() -> None:
    h = Harness([POSES[3]] * 3 + [N] * 30)
    assert h.run() == EXIT_OK
    board = h.boards[0]
    # relay 3 (pin 5) went on once and stayed on until the final cleanup
    pin5 = [v for spec, v in board.writes if spec == "d:5:o"]
    assert pin5 == [1, 0, 1]


def test_camera_read_failure_exits_nonzero_and_releases_relays(
    caplog: pytest.LogCaptureFixture,
) -> None:
    h = Harness([POSES[5]] * 10, fail_read_at=5)
    with caplog.at_level(logging.ERROR):
        code = h.run()
    assert code == EXIT_RUNTIME
    assert "Camera failure" in caplog.text
    board = h.boards[0]
    assert set(board.last_levels().values()) == {1}
    assert board.exited is True


def test_camera_open_failure_is_a_setup_error_and_still_cleans_up() -> None:
    h = Harness([POSES[1]] * 3, camera_fails=True)
    assert h.run() == EXIT_SETUP
    assert h.boards[0].exited is True


def test_board_connection_failure_fails_fast() -> None:
    h = Harness([POSES[1]] * 3, factory_failures=["could not open Firmata board on COM7: busy"])
    assert h.run() == EXIT_SETUP
    assert h.source.reads == 0, "the camera must not be opened when the board fails"
    assert h.controller.is_connected is False


def test_lost_board_during_run_exits_unsafe(caplog: pytest.LogCaptureFixture) -> None:
    """All relays on, then the serial link dies: cleanup cannot release them."""
    h = Harness([POSES[5]] * 6)

    def break_board(frame_index: int) -> None:
        if frame_index == 3:  # pose 5 was confirmed and written on this frame
            h.boards[0].fail_writes = True
            h.failures.append("port vanished")

    h.on_frame = break_board
    with caplog.at_level(logging.ERROR):
        code = h.run()
    assert code == EXIT_UNSAFE
    assert "may be left energised" in caplog.text
    assert h.boards[0].exited is True


def test_write_failure_mid_run_with_no_reconnect_exits_runtime() -> None:
    """A relay change fails, the reconnect fails: the loop stops with exit code 1 or 3."""
    h = Harness([POSES[5]] * 4 + [POSES[0]] * 8)

    def break_board(frame_index: int) -> None:
        if frame_index == 4:
            h.boards[0].fail_writes = True
            h.failures.extend(["port vanished"] * 2)

    h.on_frame = break_board
    code = h.run()
    assert code in (EXIT_RUNTIME, EXIT_UNSAFE)
    assert h.source.reads < 12, "the loop stopped early"
    assert h.boards[0].exited is True


def test_quit_key_stops_the_ui_run() -> None:
    display = FakeDisplay(key_at={4: ord("q")})
    h = Harness([POSES[1]] * 50, no_ui=False, display=display)
    assert h.run() == EXIT_OK
    assert display.shows == 4
    assert display.closed is True
    assert h.source.reads == 4


def test_no_ui_never_creates_a_display() -> None:
    h = Harness([POSES[1]] * 5, no_ui=True, display=FakeDisplay())
    assert h.run() == EXIT_OK
    assert h.display_requests == 0


def test_max_frames_stops_the_loop() -> None:
    h = Harness([POSES[1]] * 50, max_frames=7)
    assert h.run() == EXIT_OK
    assert h.source.reads == 7


def test_simulation_mode_without_port() -> None:
    h = Harness([POSES[4]] * 4, port=None)
    assert h.run() == EXIT_OK
    assert h.boards == []
    assert h.controller.states == [False] * 4


@pytest.mark.parametrize(
    "signame", [s for s in ("SIGINT", "SIGTERM", "SIGHUP") if hasattr(signal, s)]
)
def test_signal_shuts_down_and_de_energises(signame: str) -> None:
    signum = getattr(signal, signame)
    h = Harness([POSES[5]] * 1000)
    h.deps.signals = (signum,)
    previous = signal.getsignal(signum)

    def fire(frame_index: int) -> None:
        if frame_index == 6:
            os.kill(os.getpid(), signum)

    h.on_frame = fire
    try:
        code = h.run()
    finally:
        signal.signal(signum, previous)
    assert code == EXIT_OK
    assert h.source.reads <= 8
    board = h.boards[0]
    assert set(board.last_levels().values()) == {1}, "all relays released"
    assert board.exited is True
    assert signal.getsignal(signum) is previous
