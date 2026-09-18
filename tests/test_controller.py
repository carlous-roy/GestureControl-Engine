"""Relay controller tests: simulation mode, and the hardware path with a fake board."""

from __future__ import annotations

import logging

import pytest

from gesturecontrol.config import SYSEX_HEARTBEAT, SYSEX_REPORT_FIRMWARE, SYSEX_WATCHDOG_CONFIG
from gesturecontrol.controller import (
    BoardLike,
    HardwareError,
    HeartbeatThread,
    RelayController,
)
from tests.fakes import FakeBoard, FakeClock


def make(
    clock: FakeClock | None = None,
    *,
    active_low: bool = True,
    interval: float = 0.5,
    boards: list[FakeBoard] | None = None,
    factory_failures: list[str] | None = None,
) -> tuple[RelayController, list[FakeBoard]]:
    created: list[FakeBoard] = boards if boards is not None else []
    failures = factory_failures if factory_failures is not None else []

    def factory(port: str) -> BoardLike:
        if failures:
            raise HardwareError(failures.pop(0))
        board = FakeBoard(port)
        created.append(board)
        return board

    ctrl = RelayController(
        active_low=active_low,
        min_switch_interval=interval,
        clock=clock or FakeClock(),
        board_factory=factory,
    )
    return ctrl, created


# Simulation mode -----------------------------------------------------------


class TestSimulation:
    def test_initial_state(self) -> None:
        ctrl, _ = make()
        assert ctrl.states == [False, False, False, False]
        assert ctrl.is_connected is False
        assert ctrl.pending is False

    def test_finger_counts(self) -> None:
        clock = FakeClock()
        ctrl, _ = make(clock)
        expected = {
            0: [False, False, False, False],
            1: [True, False, False, False],
            2: [False, True, False, False],
            3: [False, False, True, False],
            4: [False, False, False, True],
            5: [True, True, True, True],
        }
        for count, states in expected.items():
            clock.advance(1.0)
            ctrl.set_from_finger_count(count)
            assert ctrl.states == states, f"Failed for {count} fingers"

    def test_invalid_count_means_all_off(self) -> None:
        clock = FakeClock()
        ctrl, _ = make(clock)
        ctrl.set_from_finger_count(5)
        clock.advance(1.0)
        ctrl.set_from_finger_count(9)
        assert ctrl.states == [False, False, False, False]

    def test_set_individual_relay(self) -> None:
        ctrl, _ = make()
        ctrl.set_relay(2, True)
        assert ctrl.states == [False, False, True, False]

    def test_out_of_bounds_index_is_ignored(self) -> None:
        ctrl, _ = make()
        ctrl.set_relay(10, True)
        ctrl.set_relay(-1, True)
        assert ctrl.states == [False, False, False, False]

    def test_set_all(self) -> None:
        ctrl, _ = make()
        ctrl.set_all([True, False, True, False])
        assert ctrl.states == [True, False, True, False]

    def test_cleanup_turns_everything_off(self) -> None:
        ctrl, _ = make()
        ctrl.set_from_finger_count(5)
        assert ctrl.cleanup() is True
        assert ctrl.states == [False, False, False, False]

    def test_transitions(self) -> None:
        clock = FakeClock()
        ctrl, _ = make(clock)
        for i in range(6):
            clock.advance(1.0)
            ctrl.set_from_finger_count(i)
            if i == 0:
                assert sum(ctrl.states) == 0
            elif i == 5:
                assert sum(ctrl.states) == 4
            else:
                assert sum(ctrl.states) == 1
                assert ctrl.states[i - 1] is True


# Minimum switching interval ---------------------------------------------------


class TestSwitchingInterval:
    def test_change_inside_interval_is_deferred(self) -> None:
        clock = FakeClock()
        ctrl, _ = make(clock, interval=0.5)
        ctrl.set_relay(0, True)
        clock.advance(0.2)
        ctrl.set_relay(0, False)
        assert ctrl.states == [True, False, False, False]
        assert ctrl.desired == [False, False, False, False]
        assert ctrl.pending
        clock.advance(0.3)
        assert ctrl.apply() == [(0, False)]
        assert ctrl.states == [False, False, False, False]
        assert not ctrl.pending

    def test_interval_is_per_relay(self) -> None:
        clock = FakeClock()
        ctrl, _ = make(clock, interval=0.5)
        ctrl.set_from_finger_count(1)
        clock.advance(0.1)
        ctrl.set_from_finger_count(2)
        # relay 1 changed 0.1 s ago and must wait; relay 2 has never switched
        assert ctrl.states == [True, True, False, False]
        clock.advance(0.5)
        ctrl.apply()
        assert ctrl.states == [False, True, False, False]

    def test_chatter_is_collapsed_to_the_final_request(self) -> None:
        clock = FakeClock()
        ctrl, _ = make(clock, interval=0.5)
        ctrl.set_relay(3, True)
        for state in (False, True, False, True, False):
            clock.advance(0.05)
            ctrl.set_relay(3, state)
        assert ctrl.states == [False, False, False, True]
        clock.advance(1.0)
        assert ctrl.apply() == [(3, False)]

    def test_zero_interval_switches_immediately(self) -> None:
        ctrl, _ = make(interval=0.0)
        ctrl.set_relay(1, True)
        ctrl.set_relay(1, False)
        assert ctrl.states == [False, False, False, False]

    def test_negative_interval_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_switch_interval"):
            RelayController(min_switch_interval=-1)


# Hardware path with a fake board ----------------------------------------------


class TestHardware:
    def test_connect_claims_pins_and_releases_relays(self) -> None:
        ctrl, boards = make()
        ctrl.connect("/dev/ttyFAKE")
        assert ctrl.is_connected and ctrl.port == "/dev/ttyFAKE"
        board = boards[0]
        assert board.pins_claimed == ["d:7:o", "d:6:o", "d:5:o", "d:4:o"]
        # active-low: HIGH (1) on every pin means every relay is off
        assert board.writes == [("d:7:o", 1), ("d:6:o", 1), ("d:5:o", 1), ("d:4:o", 1)]

    def test_active_low_polarity(self) -> None:
        clock = FakeClock()
        ctrl, boards = make(clock, active_low=True)
        ctrl.connect("/dev/ttyFAKE")
        ctrl.set_from_finger_count(2)
        assert boards[0].last_levels() == {"d:7:o": 1, "d:6:o": 0, "d:5:o": 1, "d:4:o": 1}
        assert ctrl.level_for(True) == 0 and ctrl.level_for(False) == 1

    def test_active_high_polarity(self) -> None:
        clock = FakeClock()
        ctrl, boards = make(clock, active_low=False)
        ctrl.connect("/dev/ttyFAKE")
        ctrl.set_from_finger_count(2)
        assert boards[0].last_levels() == {"d:7:o": 0, "d:6:o": 1, "d:5:o": 0, "d:4:o": 0}

    def test_five_fingers_energises_all_and_cleanup_releases(self) -> None:
        ctrl, boards = make()
        ctrl.connect("/dev/ttyFAKE")
        ctrl.set_from_finger_count(5)
        assert set(boards[0].last_levels().values()) == {0}
        assert ctrl.cleanup() is True
        assert set(boards[0].last_levels().values()) == {1}
        assert boards[0].exited is True
        assert ctrl.is_connected is False
        assert ctrl.states == [False] * 4

    def test_connect_failure_raises_clear_error(self) -> None:
        ctrl, _ = make(factory_failures=["could not open Firmata board on COM9: no such port"])
        with pytest.raises(HardwareError, match="COM9"):
            ctrl.connect("COM9")
        assert ctrl.is_connected is False

    def test_missing_pyfirmata2_is_a_hardware_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import builtins

        from gesturecontrol.controller import default_board_factory

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "pyfirmata2":
                raise ImportError("no module named pyfirmata2")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", fake_import)
        with pytest.raises(HardwareError, match="gesturecontrol\\[hardware\\]"):
            default_board_factory("/dev/ttyACM0")

    def test_write_failure_reconnects_once_and_restores_state(self) -> None:
        clock = FakeClock()
        ctrl, boards = make(clock)
        ctrl.connect("/dev/ttyFAKE")
        ctrl.set_from_finger_count(3)
        boards[0].fail_writes = True
        clock.advance(1.0)
        ctrl.set_from_finger_count(4)
        assert len(boards) == 2, "a second board should have been opened"
        second = boards[1]
        assert second.pins_claimed == ["d:7:o", "d:6:o", "d:5:o", "d:4:o"]
        # states restored on the new board before the pending write went through
        assert second.writes[:4] == [("d:7:o", 1), ("d:6:o", 1), ("d:5:o", 0), ("d:4:o", 1)]
        assert second.last_levels() == {"d:7:o": 1, "d:6:o": 1, "d:5:o": 1, "d:4:o": 0}
        assert boards[0].exited is True
        assert ctrl.states == [False, False, False, True]

    def test_write_failure_then_reconnect_failure_raises(self) -> None:
        clock = FakeClock()
        failures: list[str] = []
        ctrl, boards = make(clock, factory_failures=failures)
        ctrl.connect("/dev/ttyFAKE")
        boards[0].fail_writes = True
        failures.append("port vanished")
        with pytest.raises(HardwareError, match="could not reconnect"):
            ctrl.set_from_finger_count(1)
        assert boards[0].exited is True

    def test_cleanup_reports_failure_but_never_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        clock = FakeClock()
        failures: list[str] = []
        ctrl, boards = make(clock, factory_failures=failures)
        ctrl.connect("/dev/ttyFAKE")
        ctrl.set_from_finger_count(5)
        boards[0].fail_writes = True
        failures.extend(["gone"] * 4)
        with caplog.at_level(logging.ERROR):
            assert ctrl.cleanup() is False
        assert "may be left energised" in caplog.text
        assert boards[0].exited is True
        assert ctrl.is_connected is False

    def test_cleanup_ignores_switching_interval(self) -> None:
        clock = FakeClock()
        ctrl, boards = make(clock, interval=5.0)
        ctrl.connect("/dev/ttyFAKE")
        ctrl.set_from_finger_count(5)
        clock.advance(0.01)
        assert ctrl.cleanup() is True
        assert set(boards[0].last_levels().values()) == {1}


# Watchdog heartbeat ---------------------------------------------------------------


class TestHeartbeat:
    def test_config_sent_and_acknowledged(self, caplog: pytest.LogCaptureFixture) -> None:
        clock = FakeClock()
        created: list[FakeBoard] = []

        def factory(port: str) -> BoardLike:
            board = FakeBoard(port, acks_watchdog=True, firmware="RelayWatchdogFirmata.ino")
            created.append(board)
            return board

        ctrl = RelayController(clock=clock, board_factory=factory, heartbeat_timeout_ms=1000)
        with caplog.at_level(logging.INFO):
            ctrl.connect("/dev/ttyFAKE")
        assert created[0].sysex == [
            (SYSEX_REPORT_FIRMWARE, []),
            (SYSEX_WATCHDOG_CONFIG, [1, 1000 & 0x7F, 1000 >> 7]),
        ]
        assert ctrl.watchdog_acknowledged is True
        assert "RelayWatchdogFirmata.ino (2, 5)" in caplog.text

    def test_missing_firmware_announcement_is_reported(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        ctrl, _ = make()
        with caplog.at_level(logging.WARNING):
            ctrl.connect("/dev/ttyFAKE")
        assert "did not announce a Firmata firmware" in caplog.text

    def test_no_ack_is_reported(self, caplog: pytest.LogCaptureFixture) -> None:
        clock = FakeClock()
        ctrl, _ = make(clock)
        with caplog.at_level(logging.WARNING):
            ctrl.connect("/dev/ttyFAKE")
        assert ctrl.watchdog_acknowledged is False
        assert "StandardFirmata" in caplog.text

    def test_heartbeat_sends_sysex(self) -> None:
        clock = FakeClock()
        ctrl, boards = make(clock)
        ctrl.connect("/dev/ttyFAKE")
        clock.advance(0.25)
        ctrl.heartbeat()
        assert boards[0].sysex[-1] == (SYSEX_HEARTBEAT, [])

    def test_heartbeat_gap_resends_states(self) -> None:
        clock = FakeClock()
        ctrl, boards = make(clock)
        ctrl.connect("/dev/ttyFAKE")
        ctrl.set_from_finger_count(2)
        before = len(boards[0].writes)
        clock.advance(0.25)
        ctrl.heartbeat()
        assert len(boards[0].writes) == before
        clock.advance(3.0)
        ctrl.heartbeat()
        assert boards[0].writes[before:] == [("d:7:o", 1), ("d:6:o", 0), ("d:5:o", 1), ("d:4:o", 1)]

    def test_heartbeat_in_simulation_is_a_no_op(self) -> None:
        ctrl, _ = make()
        ctrl.heartbeat()

    def test_heartbeat_thread_stops_on_hardware_error(self) -> None:
        clock = FakeClock()
        failures: list[str] = []
        ctrl, boards = make(clock, factory_failures=failures)
        ctrl.connect("/dev/ttyFAKE")
        boards[0].fail_writes = True
        thread = HeartbeatThread(ctrl, interval=0.01)
        thread.start()
        thread.join(timeout=2.0)
        assert thread.is_alive() is False
        assert isinstance(thread.error, HardwareError)
        thread.stop()

    def test_heartbeat_thread_runs_and_stops(self) -> None:
        import time

        ctrl, boards = make(FakeClock())
        ctrl.connect("/dev/ttyFAKE")
        thread = HeartbeatThread(ctrl, interval=0.01)
        thread.start()
        time.sleep(0.1)
        thread.stop()
        assert thread.is_alive() is False
        assert thread.error is None
        beats = [s for s in boards[0].sysex if s[0] == SYSEX_HEARTBEAT]
        assert len(beats) >= 2
