"""
The classification pipeline between the landmark detector and the relays:
One Euro filtering, finger rules with hysteresis, and N-frame confirmation.

Input per frame: the 21 normalised landmarks of one hand (or None when no
hand was detected) and a timestamp in seconds. Output: the raw count for
the frame, the confirmed count, and the relay states the confirmed count
maps to. This module has no dependency on OpenCV, MediaPipe or hardware,
which is what makes the golden-vector tests and the browser port possible.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gesturecontrol.config import DEFAULT_RULES, RulesConfig
from gesturecontrol.filters import LandmarkFilter, Point
from gesturecontrol.rules import FingerClassifier, relay_states_for_count
from gesturecontrol.stabilizer import CountStabilizer


@dataclass(frozen=True)
class FrameResult:
    hand_present: bool
    raw_count: int
    """Count for this frame after filtering and hysteresis, or -1 without a hand."""
    finger_states: tuple[bool, bool, bool, bool, bool] | None
    """Latched per-finger states (thumb, index, middle, ring, pinky), if a hand was usable."""
    confirmed_count: int
    """Last confirmed count, or -1 before the first confirmation."""
    changed: bool
    """True on the frame the confirmed count changed."""
    relays: tuple[bool, bool, bool, bool]
    """Relay states the confirmed count maps to."""
    points_px: tuple[Point, ...] | None
    """Filtered landmarks in pixel coordinates, for drawing."""


class GesturePipeline:
    def __init__(self, width: int, height: int, config: RulesConfig = DEFAULT_RULES) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("frame size must be positive")
        self._width = width
        self._height = height
        self._config = config
        self._filter = LandmarkFilter(config.filter)
        self._classifier = FingerClassifier(config)
        self._stabilizer = CountStabilizer(config.confirm_frames)

    @property
    def config(self) -> RulesConfig:
        return self._config

    @property
    def confirmed_count(self) -> int:
        return self._stabilizer.confirmed

    def reset(self) -> None:
        """Forget filter state, latches and the pending candidate (not the confirmed count)."""
        self._filter.reset()
        self._classifier.reset()
        self._stabilizer.reset()

    def process(self, landmarks: Sequence[Point] | None, t: float) -> FrameResult:
        """Advance one frame. ``landmarks`` are normalised (0..1) or None for no hand."""
        if landmarks is None:
            self.reset()
            confirmation = self._stabilizer.update(-1)
            return FrameResult(
                hand_present=False,
                raw_count=-1,
                finger_states=None,
                confirmed_count=confirmation.confirmed,
                changed=False,
                relays=_relays(confirmation.confirmed),
                points_px=None,
            )

        filtered = self._filter(landmarks, t)
        points_px = tuple((x * self._width, y * self._height) for x, y in filtered)
        raw = self._classifier.update(points_px)
        confirmation = self._stabilizer.update(raw)
        s = self._classifier.states
        states = (s[0], s[1], s[2], s[3], s[4]) if raw >= 0 else None
        return FrameResult(
            hand_present=True,
            raw_count=raw,
            finger_states=states,
            confirmed_count=confirmation.confirmed,
            changed=confirmation.changed,
            relays=_relays(confirmation.confirmed),
            points_px=points_px,
        )


def _relays(count: int) -> tuple[bool, bool, bool, bool]:
    r = relay_states_for_count(count)
    return (r[0], r[1], r[2], r[3])
