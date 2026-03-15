"""Tests for the relay controller. Run with: pytest tests/ -v"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.controller import RelayController


class TestRelayController:

    def setup_method(self):
        self.ctrl = RelayController()

    def test_initial_state(self):
        assert self.ctrl.states == [False, False, False, False]
        assert self.ctrl.is_connected is False

    def test_finger_counts(self):
        expected = {
            0: [False, False, False, False],
            1: [True, False, False, False],
            2: [False, True, False, False],
            3: [False, False, True, False],
            4: [False, False, False, True],
            5: [True, True, True, True],
        }
        for count, states in expected.items():
            self.ctrl.set_from_finger_count(count)
            assert self.ctrl.states == states, f"Failed for {count} fingers"

    def test_invalid_count(self):
        self.ctrl.set_from_finger_count(5)
        self.ctrl.set_from_finger_count(9)
        assert self.ctrl.states == [False, False, False, False]

    def test_set_individual_relay(self):
        self.ctrl.set_relay(2, True)
        assert self.ctrl.states == [False, False, True, False]

    def test_out_of_bounds(self):
        self.ctrl.set_relay(10, True)
        assert self.ctrl.states == [False, False, False, False]

    def test_set_all(self):
        self.ctrl.set_all([True, False, True, False])
        assert self.ctrl.states == [True, False, True, False]

    def test_cleanup(self):
        self.ctrl.set_from_finger_count(5)
        self.ctrl.cleanup()
        assert self.ctrl.states == [False, False, False, False]

    def test_transitions(self):
        for i in range(6):
            self.ctrl.set_from_finger_count(i)
            if i == 0:
                assert sum(self.ctrl.states) == 0
            elif i == 5:
                assert sum(self.ctrl.states) == 4
            else:
                assert sum(self.ctrl.states) == 1
                assert self.ctrl.states[i - 1] is True
