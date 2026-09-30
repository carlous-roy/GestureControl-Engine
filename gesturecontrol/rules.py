"""
Finger-state rules on the 21 MediaPipe hand landmarks.

Every measurement is taken in the hand's own frame of reference:

* the *up* axis runs from the wrist (landmark 0) to the middle-finger MCP
  joint (landmark 9);
* the *side* axis is perpendicular to it and points towards the thumb
  side of the hand (determined from the index and pinky MCP joints, so it
  is correct for either hand and for mirrored frames);
* palm width, the distance between the index MCP (5) and the pinky MCP
  (17), is the unit of length.

A finger counts as extended when its tip lies beyond its PIP joint along
the up axis by more than a fraction of the palm width. The thumb counts as
extended when its tip lies beyond the index MCP along the side axis by more
than a fraction of the palm width. Because both measures are ratios inside a
frame that rotates with the hand, they do not change with camera distance,
image resolution, mirroring or in-plane rotation.

Each finger latches with hysteresis: it must cross the raise threshold to
count as up and fall below the lower threshold to count as down again.

Landmark indices follow MediaPipe Hands:
0 wrist; 1-4 thumb (CMC, MCP, IP, tip); 5-8 index (MCP, PIP, DIP, tip);
9-12 middle; 13-16 ring; 17-20 pinky.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from gesturecontrol.config import Hysteresis, RulesConfig

Point = tuple[float, float]

WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
MIDDLE_MCP = 9
PINKY_MCP = 17
#: (tip, pip) landmark pairs for index, middle, ring and pinky.
FINGER_TIP_PIP: tuple[tuple[int, int], ...] = ((8, 6), (12, 10), (16, 14), (20, 18))
NUM_LANDMARKS = 21

FINGER_NAMES = ("thumb", "index", "middle", "ring", "pinky")


@dataclass(frozen=True)
class HandFrame:
    """Axes and scale of one hand pose, in the units of the input points."""

    up: Point
    side: Point
    palm_width: float


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1])


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _length(a: Point) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1])


def hand_frame(points: Sequence[Point], min_palm_width: float) -> HandFrame | None:
    """Compute the hand frame, or None when the geometry is too small to trust."""
    if len(points) != NUM_LANDMARKS:
        raise ValueError(f"expected {NUM_LANDMARKS} landmarks, got {len(points)}")
    up_vec = _sub(points[MIDDLE_MCP], points[WRIST])
    up_len = _length(up_vec)
    across = _sub(points[INDEX_MCP], points[PINKY_MCP])
    palm_width = _length(across)
    if palm_width < min_palm_width or up_len < min_palm_width:
        return None
    up = (up_vec[0] / up_len, up_vec[1] / up_len)
    side: Point = (-up[1], up[0])
    if _dot(across, side) < 0.0:
        side = (-side[0], -side[1])
    return HandFrame(up=up, side=side, palm_width=palm_width)


def finger_extensions(points: Sequence[Point], frame: HandFrame) -> list[float]:
    """Tip-beyond-PIP distance along the up axis, in palm widths, for index..pinky."""
    return [
        _dot(_sub(points[tip], points[pip]), frame.up) / frame.palm_width
        for tip, pip in FINGER_TIP_PIP
    ]


def thumb_extension(points: Sequence[Point], frame: HandFrame) -> float:
    """Thumb tip offset from the index MCP along the side axis, in palm widths."""
    return _dot(_sub(points[THUMB_TIP], points[INDEX_MCP]), frame.side) / frame.palm_width


def latch(was_up: bool, value: float, band: Hysteresis) -> bool:
    """Apply a hysteresis band to one measurement."""
    if was_up:
        return value > band.lower_threshold
    return value > band.raise_threshold


@dataclass(frozen=True)
class Measurements:
    """Raw extension values for one frame, useful for tuning and tests."""

    thumb: float
    fingers: tuple[float, float, float, float]
    palm_width: float


def measure(points: Sequence[Point], config: RulesConfig) -> Measurements | None:
    """Raw thumb and finger extensions for one frame, or None for unusable geometry."""
    frame = hand_frame(points, config.min_palm_width_px)
    if frame is None:
        return None
    ext = finger_extensions(points, frame)
    return Measurements(
        thumb=thumb_extension(points, frame),
        fingers=(ext[0], ext[1], ext[2], ext[3]),
        palm_width=frame.palm_width,
    )


class FingerClassifier:
    """Stateful per-finger classification with hysteresis.

    ``update`` returns the number of extended fingers (0-5) or -1 when the
    landmarks are unusable. ``states`` holds the latched per-finger booleans
    in the order thumb, index, middle, ring, pinky.
    """

    def __init__(self, config: RulesConfig) -> None:
        self._config = config
        self._states = [False] * 5

    @property
    def states(self) -> list[bool]:
        return list(self._states)

    def reset(self) -> None:
        self._states = [False] * 5

    def update(self, points: Sequence[Point]) -> int:
        m = measure(points, self._config)
        if m is None:
            self.reset()
            return -1
        cfg = self._config
        self._states[0] = latch(self._states[0], m.thumb, cfg.thumb)
        for i, value in enumerate(m.fingers, start=1):
            self._states[i] = latch(self._states[i], value, cfg.finger)
        return sum(self._states)


RELAY_MAPPING: dict[int, tuple[bool, bool, bool, bool]] = {
    0: (False, False, False, False),
    1: (True, False, False, False),
    2: (False, True, False, False),
    3: (False, False, True, False),
    4: (False, False, False, True),
    5: (True, True, True, True),
}


def relay_states_for_count(count: int) -> list[bool]:
    """Map a finger count to relay states; anything outside 0-5 means all off."""
    return list(RELAY_MAPPING.get(count, (False, False, False, False)))
