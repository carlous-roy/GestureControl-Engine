"""
Relay controller for 4-channel module via Arduino/Firmata.
Runs in simulation mode when no Arduino is connected.

Wiring: Pin 7->IN1, Pin 6->IN2, Pin 5->IN3, Pin 4->IN4
Mapping: 0=all off, 1-4=individual relay, 5=all on
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

RELAY_PINS = [7, 6, 5, 4]


class RelayController:
    def __init__(self) -> None:
        self._board: Any = None
        self._pins: list[Any] = []
        self._states = [False, False, False, False]
        self._hardware_connected = False

    @property
    def is_connected(self) -> bool:
        return self._hardware_connected

    @property
    def states(self) -> list[bool]:
        return self._states.copy()

    def connect(self, port: str) -> bool:
        try:
            import pyfirmata

            self._board = pyfirmata.Arduino(port)
            self._pins = [self._board.get_pin(f"d:{pin}:o") for pin in RELAY_PINS]
            self._hardware_connected = True
            self.set_from_finger_count(0)
            logger.info("Connected to Arduino on %s", port)
            return True
        except ImportError:
            logger.warning("pyfirmata not installed. Install with: pip install pyfirmata")
            return False
        except Exception as e:  # noqa: BLE001 - pyfirmata raises bare Exception
            logger.warning("Could not connect on %s: %s", port, e)
            return False

    def set_relay(self, index: int, state: bool) -> None:
        if 0 <= index < 4:
            self._states[index] = state
            if self._hardware_connected and self._pins:
                self._pins[index].write(1 if state else 0)

    def set_all(self, states: list[bool]) -> None:
        for i, state in enumerate(states[:4]):
            self.set_relay(i, state)

    def set_from_finger_count(self, count: int) -> None:
        mapping = {
            0: [False, False, False, False],
            1: [True, False, False, False],
            2: [False, True, False, False],
            3: [False, False, True, False],
            4: [False, False, False, True],
            5: [True, True, True, True],
        }
        self.set_all(mapping.get(count, [False, False, False, False]))

    def cleanup(self) -> None:
        self.set_from_finger_count(0)
        if self._board:
            self._board.exit()
            logger.info("Arduino disconnected.")
        self._hardware_connected = False
