"""Fakes shared by the controller and loop tests."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from gesturecontrol.config import SYSEX_WATCHDOG_CONFIG


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakePin:
    def __init__(self, board: FakeBoard, spec: str) -> None:
        self.board = board
        self.spec = spec

    def write(self, value: int) -> None:
        if self.board.fail_writes:
            raise OSError(5, "Input/output error")
        self.board.writes.append((self.spec, value))


class FakeBoard:
    """Records everything the controller sends; can fail on demand."""

    def __init__(
        self, port: str, *, acks_watchdog: bool = False, firmware: str | None = None
    ) -> None:
        self.port = port
        self.firmware = firmware
        self.firmware_version: tuple[int, int] | None = (2, 5) if firmware else None
        self.writes: list[tuple[str, int]] = []
        self.sysex: list[tuple[int, list[int]]] = []
        self.pins_claimed: list[str] = []
        self.exited = False
        self.fail_writes = False
        self.acks_watchdog = acks_watchdog
        self._handlers: dict[int, Callable[..., None]] = {}
        self._pending_ack = False

    def get_pin(self, pin_def: str) -> FakePin:
        self.pins_claimed.append(pin_def)
        return FakePin(self, pin_def)

    def send_sysex(self, sysex_cmd: int, data: Sequence[int]) -> None:
        if self.fail_writes:
            raise OSError(5, "Input/output error")
        self.sysex.append((sysex_cmd, list(data)))
        if sysex_cmd == SYSEX_WATCHDOG_CONFIG and self.acks_watchdog:
            self._pending_ack = True

    def add_cmd_handler(self, cmd: int, func: Callable[..., None]) -> None:
        self._handlers[cmd] = func

    def bytes_available(self) -> int:
        return 1 if self._pending_ack else 0

    def iterate(self) -> None:
        if self._pending_ack:
            self._pending_ack = False
            self._handlers[SYSEX_WATCHDOG_CONFIG](1)

    def exit(self) -> None:
        self.exited = True

    def last_levels(self) -> dict[str, int]:
        levels: dict[str, int] = {}
        for spec, value in self.writes:
            levels[spec] = value
        return levels
