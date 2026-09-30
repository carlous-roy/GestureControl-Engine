"""
Relay control over Firmata, with the safety policies the hardware needs.

* Polarity is configurable. The default is active-low (relay on when the
  Arduino pin is LOW), which is how the common opto-isolated modules work.
* A relay is never switched twice within ``min_switch_interval`` seconds.
  A change requested inside that window is kept as the desired state and
  applied by the next ``apply`` call once the window has passed.
* Every serial write is guarded. On a failure the controller reconnects
  once and re-sends the relay states; if that fails too it raises
  ``HardwareError`` so the caller can shut down cleanly.
* ``cleanup`` always tries to de-energise every relay and close the board,
  ignores the switching interval, never raises, and reports whether it
  succeeded.
* ``heartbeat`` sends a SysEx message the optional watchdog firmware in
  ``firmware/`` uses to detect host loss; with plain StandardFirmata the
  message is ignored.

Without ``connect`` the controller runs in simulation mode: the same state
machine, no serial writes.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from gesturecontrol.config import (
    HEARTBEAT_INTERVAL_S,
    HEARTBEAT_TIMEOUT_MS,
    MIN_SWITCH_INTERVAL_S,
    RELAY_ACTIVE_LOW_DEFAULT,
    RELAY_PINS,
    SYSEX_HEARTBEAT,
    SYSEX_REPORT_FIRMWARE,
    SYSEX_WATCHDOG_CONFIG,
)
from gesturecontrol.rules import relay_states_for_count

logger = logging.getLogger(__name__)

WATCHDOG_ACK_WAIT_S = 0.5


class HardwareError(RuntimeError):
    """The board could not be reached and the relay state is no longer under control."""


class PinLike(Protocol):
    def write(self, value: int) -> None: ...


class BoardLike(Protocol):
    """The subset of the pyfirmata2 Board interface the controller uses."""

    firmware: str | None
    firmware_version: tuple[int, int] | None

    def get_pin(self, pin_def: str) -> PinLike: ...

    def send_sysex(self, sysex_cmd: int, data: Sequence[int]) -> None: ...

    def add_cmd_handler(self, cmd: int, func: Callable[..., None]) -> None: ...

    def bytes_available(self) -> int: ...

    def iterate(self) -> None: ...

    def exit(self) -> None: ...


BoardFactory = Callable[[str], BoardLike]


def default_board_factory(port: str) -> BoardLike:
    """Open an Arduino UNO layout board with pyfirmata2."""
    try:
        import pyfirmata2
        import serial
    except ImportError as e:
        raise HardwareError(
            "pyfirmata2 is not installed; install the hardware extra with "
            "pip install 'gesturecontrol[hardware]'"
        ) from e
    # Probe the port first so a missing or busy device gives one clear error
    # instead of a half-constructed pyfirmata2 board.
    try:
        serial.Serial(port).close()
    except (serial.SerialException, OSError, ValueError) as e:
        raise HardwareError(f"could not open serial port {port}: {e}") from e
    try:
        board: BoardLike = pyfirmata2.Arduino(port)
    except Exception as e:  # pyfirmata2 raises bare Exception and OSError
        raise HardwareError(f"could not open Firmata board on {port}: {e}") from e
    return board


class RelayController:
    """Four relays behind the policies in the module docstring.

    Relay state is kept in memory whether or not a board is attached, so the
    same controller serves the simulator, the tests and the hardware path.
    All public methods take the controller's lock; the heartbeat thread and
    the loop may call them concurrently.
    """

    def __init__(
        self,
        *,
        active_low: bool = RELAY_ACTIVE_LOW_DEFAULT,
        min_switch_interval: float = MIN_SWITCH_INTERVAL_S,
        pins: Sequence[int] = RELAY_PINS,
        heartbeat_timeout_ms: int = HEARTBEAT_TIMEOUT_MS,
        clock: Callable[[], float] = time.monotonic,
        board_factory: BoardFactory = default_board_factory,
    ) -> None:
        if len(pins) != 4:
            raise ValueError("four relay pins are required")
        if min_switch_interval < 0:
            raise ValueError("min_switch_interval must not be negative")
        self._active_low = active_low
        self._min_switch_interval = min_switch_interval
        self._pin_numbers = tuple(pins)
        self._heartbeat_timeout_ms = heartbeat_timeout_ms
        self._clock = clock
        self._board_factory = board_factory

        self._lock = threading.RLock()
        self._board: BoardLike | None = None
        self._pins: list[PinLike] = []
        self._port: str | None = None
        self._desired = [False, False, False, False]
        self._physical = [False, False, False, False]
        self._last_change = [-math.inf] * 4
        self._last_heartbeat: float | None = None
        self._watchdog_ack = False
        self._lost = False

    # Introspection --------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._board is not None

    @property
    def port(self) -> str | None:
        return self._port

    @property
    def active_low(self) -> bool:
        return self._active_low

    @property
    def states(self) -> list[bool]:
        """Relay states as last written (or held in memory in simulation)."""
        return list(self._physical)

    @property
    def desired(self) -> list[bool]:
        """Requested states, which may still be waiting on the switching interval."""
        return list(self._desired)

    @property
    def pending(self) -> bool:
        return self._desired != self._physical

    @property
    def watchdog_acknowledged(self) -> bool:
        """True when the board answered the watchdog configuration message."""
        return self._watchdog_ack

    def level_for(self, state: bool) -> int:
        """Pin level (0/1) that produces the given relay state under the polarity."""
        on_level = 0 if self._active_low else 1
        return on_level if state else 1 - on_level

    # Connection -----------------------------------------------------------

    def connect(self, port: str) -> None:
        """Open the board and drive every relay to its de-energised level.

        Raises HardwareError when the port cannot be opened or the first
        writes fail; the controller is left disconnected in that case.
        """
        with self._lock:
            board = self._board_factory(port)
            try:
                pins = [board.get_pin(f"d:{n}:o") for n in self._pin_numbers]
            except Exception as e:  # library-specific error types
                self._close_board(board)
                raise HardwareError(f"could not claim relay pins on {port}: {e}") from e
            self._board = board
            self._pins = pins
            self._port = port
            self._physical = [False] * 4
            self._last_change = [-math.inf] * 4
            try:
                for i in range(4):
                    self._pins[i].write(self.level_for(False))
                self._configure_watchdog(board)
            except OSError as e:
                self._close_board(board)
                self._board = None
                self._pins = []
                raise HardwareError(f"serial write failed right after connecting: {e}") from e
            logger.info(
                "Connected to Firmata board on %s (%s trigger)",
                port,
                "active-low" if self._active_low else "active-high",
            )

    def _configure_watchdog(self, board: BoardLike) -> None:
        """Query the firmware and tell the watchdog which level is safe and how long to wait."""
        self._watchdog_ack = False
        board.add_cmd_handler(SYSEX_WATCHDOG_CONFIG, self._on_watchdog_ack)
        board.send_sysex(SYSEX_REPORT_FIRMWARE, [])
        timeout = self._heartbeat_timeout_ms
        board.send_sysex(
            SYSEX_WATCHDOG_CONFIG,
            [1 if self._active_low else 0, timeout & 0x7F, (timeout >> 7) & 0x7F],
        )
        deadline = time.monotonic() + WATCHDOG_ACK_WAIT_S
        while not self._watchdog_ack and time.monotonic() < deadline:
            while board.bytes_available():
                board.iterate()
            if not self._watchdog_ack:
                time.sleep(0.01)
        if board.firmware:
            logger.info("Firmware: %s %s", board.firmware, board.firmware_version)
        else:
            logger.warning(
                "The board did not announce a Firmata firmware; if it is not running "
                "StandardFirmata or the watchdog sketch, no relay will switch."
            )
        if self._watchdog_ack:
            logger.info(
                "Watchdog firmware acknowledged: relays de-energise if no heartbeat "
                "arrives for %d ms",
                timeout,
            )
        else:
            logger.warning(
                "No watchdog acknowledgement from the board. With StandardFirmata the "
                "relays keep their last state if this program dies; flash "
                "firmware/RelayWatchdogFirmata for host-loss protection."
            )
        self._last_heartbeat = self._clock()

    def _on_watchdog_ack(self, *data: int) -> None:
        self._watchdog_ack = True

    def disconnect(self) -> None:
        """Close the board, if any, without touching the relay levels."""
        with self._lock:
            if self._board is not None:
                self._close_board(self._board)
            self._board = None
            self._pins = []

    @staticmethod
    def _close_board(board: BoardLike) -> None:
        try:
            board.exit()
        except Exception as e:  # noqa: BLE001 - closing must not mask the original error
            logger.warning("Error while closing the board: %s", e)

    # Relay commands -------------------------------------------------------

    def set_relay(self, index: int, state: bool) -> None:
        """Request one relay state (index 0-3) and apply what the interval allows."""
        if not 0 <= index < 4:
            logger.warning("Ignoring relay index %d (valid: 0-3)", index)
            return
        with self._lock:
            self._desired[index] = bool(state)
            self.apply()

    def set_all(self, states: Sequence[bool]) -> None:
        """Request the state of every relay and apply what the interval allows."""
        with self._lock:
            for i, state in enumerate(list(states)[:4]):
                self._desired[i] = bool(state)
            self.apply()

    def set_from_finger_count(self, count: int) -> None:
        """Request the relay pattern the gesture mapping assigns to ``count``."""
        self.set_all(relay_states_for_count(count))

    def apply(self) -> list[tuple[int, bool]]:
        """Write every desired change whose switching interval has passed.

        Returns the (index, state) pairs that were switched. Raises
        HardwareError if the board is lost even after one reconnect.
        """
        with self._lock:
            now = self._clock()
            switched: list[tuple[int, bool]] = []
            for i in range(4):
                if self._desired[i] == self._physical[i]:
                    continue
                if now - self._last_change[i] < self._min_switch_interval:
                    continue
                self._write(i, self._desired[i])
                self._physical[i] = self._desired[i]
                self._last_change[i] = now
                switched.append((i, self._desired[i]))
            return switched

    def _write(self, index: int, state: bool) -> None:
        if self._board is None:
            return
        level = self.level_for(state)
        try:
            self._pins[index].write(level)
        except OSError as e:
            logger.warning("Serial write to relay %d failed (%s); reconnecting once", index + 1, e)
            self._reconnect()
            try:
                self._pins[index].write(level)
            except OSError as e2:
                raise HardwareError(f"serial write failed after reconnect: {e2}") from e2

    def _reconnect(self) -> None:
        assert self._port is not None
        old = self._board
        self._board = None
        if old is not None:
            self._close_board(old)
        try:
            board = self._board_factory(self._port)
            pins = [board.get_pin(f"d:{n}:o") for n in self._pin_numbers]
            for i in range(4):
                pins[i].write(self.level_for(self._physical[i]))
        except (HardwareError, OSError) as e:
            self._lost = True
            raise HardwareError(
                f"lost the board on {self._port} and could not reconnect: {e}; "
                "relay states are unknown"
            ) from e
        self._board = board
        self._pins = pins
        self._configure_watchdog(board)
        logger.info("Reconnected to %s and restored relay states", self._port)

    # Heartbeat -------------------------------------------------------------

    def heartbeat(self) -> None:
        """Send one heartbeat; after a gap longer than the timeout, re-send the states.

        The watchdog firmware releases the relays when the heartbeat stops, so
        the host must restate what it wants once it is alive again.
        """
        with self._lock:
            if self._board is None:
                return
            now = self._clock()
            gap_ms = (
                (now - self._last_heartbeat) * 1000 if self._last_heartbeat is not None else 0.0
            )
            try:
                self._board.send_sysex(SYSEX_HEARTBEAT, [])
                if gap_ms > self._heartbeat_timeout_ms:
                    logger.warning(
                        "Heartbeat gap of %.0f ms exceeded the watchdog timeout; "
                        "re-sending relay states",
                        gap_ms,
                    )
                    for i in range(4):
                        self._pins[i].write(self.level_for(self._physical[i]))
            except OSError as e:
                raise HardwareError(f"heartbeat write failed: {e}") from e
            self._last_heartbeat = now

    # Shutdown ---------------------------------------------------------------

    def cleanup(self) -> bool:
        """De-energise every relay and close the board. Never raises.

        Returns True when every relay is known to be off (or no board is
        attached), False when a write failed and a relay may be left on.
        """
        with self._lock:
            ok = True
            self._desired = [False] * 4
            if self._board is not None:
                for i in range(4):
                    try:
                        self._pins[i].write(self.level_for(False))
                        self._physical[i] = False
                    except OSError as e:
                        ok = False
                        logger.error("Could not de-energise relay %d: %s", i + 1, e)
                if not ok:
                    logger.error(
                        "Relays may be left energised: %s. Cut power to the module.",
                        self._physical,
                    )
                self.disconnect()
                logger.info("Board disconnected.")
            elif self._lost:
                ok = False
                logger.error(
                    "The board on %s was lost; relays may be left energised: %s. "
                    "Cut power to the module.",
                    self._port,
                    self._physical,
                )
            else:
                self._physical = [False] * 4
            return ok


class HeartbeatThread(threading.Thread):
    """Calls ``controller.heartbeat()`` at a fixed interval until stopped.

    A HardwareError raised by the heartbeat is stored in ``error`` so the
    main loop can shut down instead of running on without the board.
    """

    def __init__(self, controller: RelayController, interval: float = HEARTBEAT_INTERVAL_S) -> None:
        super().__init__(name="relay-heartbeat", daemon=True)
        self._controller = controller
        self._interval = interval
        self._stop_event = threading.Event()
        self.error: HardwareError | None = None

    def run(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self._controller.heartbeat()
            except HardwareError as e:
                self.error = e
                logger.error("Heartbeat stopped: %s", e)
                return

    def stop(self) -> None:
        self._stop_event.set()
        if self.is_alive():
            self.join(timeout=2.0)


__all__: list[str] = [
    "BoardLike",
    "HardwareError",
    "HeartbeatThread",
    "PinLike",
    "RelayController",
    "default_board_factory",
]
