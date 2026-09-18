"""
Landmark material for tests and the simulator: real hands recorded from
camera frames, a synthetic hand model for poses the recordings do not
cover, geometric transforms, and scripted frame sequences.

Real hands come from ``data/hands.json`` (coordinates only). The synthetic
hand is an anatomically plausible 21-point model in centimetres; it is used
to demonstrate properties of the rules (rotation, scale, mirroring, thumb
placement), not to make claims about detection accuracy.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from importlib import resources

Point = tuple[float, float]
Point3 = tuple[float, float, float]

HANDS_RESOURCE = "data/hands.json"


@dataclass(frozen=True)
class Hand:
    """One hand pose as normalised landmarks inside a frame of a given size."""

    name: str
    expected_count: int
    width: int
    height: int
    landmarks: tuple[Point, ...]
    source: str = ""

    def to_pixels(self) -> list[Point]:
        return [(x * self.width, y * self.height) for x, y in self.landmarks]

    def with_landmarks(self, landmarks: Iterable[Point], name: str) -> Hand:
        return Hand(
            name, self.expected_count, self.width, self.height, tuple(landmarks), self.source
        )


def load_real_hands() -> list[Hand]:
    text = resources.files(__package__).joinpath(HANDS_RESOURCE).read_text("utf-8")
    data = json.loads(text)
    return [
        Hand(
            name=h["name"],
            expected_count=h["expected_count"],
            width=h["width"],
            height=h["height"],
            landmarks=tuple((float(x), float(y)) for x, y, _z in h["landmarks"]),
            source=h["source"],
        )
        for h in data["hands"]
    ]


# Synthetic hand model -----------------------------------------------------
# Hand-local frame in centimetres: x to the pinky side, y towards the
# fingertips, z towards the camera; wrist at the origin.

_MCP: dict[int, Point] = {1: (-2.6, 8.8), 2: (-0.6, 9.3), 3: (1.3, 8.9), 4: (3.1, 7.9)}
_SPLAY_DEG: dict[int, float] = {1: -8.0, 2: -1.0, 3: 7.0, 4: 18.0}
_SEGMENTS: dict[int, tuple[float, float, float]] = {
    1: (4.0, 2.4, 1.9),
    2: (4.4, 2.8, 2.0),
    3: (4.1, 2.6, 2.0),
    4: (3.2, 1.9, 1.8),
}
_THUMBS: dict[str, list[Point3]] = {
    # abducted away from the palm
    "extended": [(-2.4, 2.2, 0.0), (-4.3, 4.6, 0.0), (-5.6, 7.0, 0.0), (-6.5, 9.2, 0.0)],
    # resting against the side of the index finger
    "adducted": [(-2.4, 2.2, 0.5), (-3.3, 5.0, 1.2), (-2.9, 7.2, 1.8), (-2.2, 8.2, 2.0)],
    # folded across the palm, tip under the ring finger
    "across": [(-2.4, 2.2, 0.5), (-2.6, 5.0, 1.5), (-0.9, 7.0, 2.2), (1.3, 8.6, 2.4)],
    # wrapped over the curled fingers of a fist
    "fist": [(-2.4, 2.2, 0.5), (-3.2, 5.0, 1.5), (-2.0, 7.2, 3.0), (-0.9, 8.4, 3.4)],
}
#: Model palm width (index MCP to pinky MCP) in centimetres.
SYNTHETIC_PALM_WIDTH_CM = math.hypot(_MCP[1][0] - _MCP[4][0], _MCP[1][1] - _MCP[4][1])

POSES: dict[int, tuple[tuple[bool, bool, bool, bool], str]] = {
    0: ((False, False, False, False), "fist"),
    1: ((True, False, False, False), "fist"),
    2: ((True, True, False, False), "fist"),
    3: ((True, True, True, False), "fist"),
    4: ((True, True, True, True), "adducted"),
    5: ((True, True, True, True), "extended"),
}


def _finger(index: int, extended: bool) -> list[Point3]:
    mx, my = _MCP[index]
    a = math.radians(_SPLAY_DEG[index])
    dx, dy = math.sin(a), math.cos(a)
    l1, l2, l3 = _SEGMENTS[index]
    if extended:
        pip = (mx + dx * l1, my + dy * l1, 0.0)
        dip = (pip[0] + dx * l2, pip[1] + dy * l2, 0.0)
        tip = (dip[0] + dx * l3, dip[1] + dy * l3, 0.0)
    else:
        # Curled: the proximal phalanx points at the camera, the rest folds down.
        pip = (mx + dx * 1.2, my + dy * 1.2, l1 * 0.9)
        dip = (pip[0], pip[1] - l2 * 0.75, pip[2] - 0.6)
        tip = (dip[0], dip[1] - l3 * 0.6, dip[2] - 1.4)
    return [(mx, my, 0.0), pip, dip, tip]


def synthetic_hand_cm(fingers_up: Sequence[bool], thumb: str = "extended") -> list[Point3]:
    """21 points in the hand-local frame; ``fingers_up`` is index, middle, ring, pinky."""
    if len(fingers_up) != 4:
        raise ValueError("fingers_up needs four booleans")
    points: list[Point3] = [(0.0, 0.0, 0.0)]
    points += _THUMBS[thumb]
    for index, up in zip((1, 2, 3, 4), fingers_up, strict=True):
        points += _finger(index, up)
    return points


def synthetic_pose_cm(count: int) -> list[Point3]:
    fingers, thumb = POSES[count]
    return synthetic_hand_cm(fingers, thumb)


def yaw_cm(points: Iterable[Point3], degrees: float) -> list[Point3]:
    """Rotate about the hand's vertical axis (palm turning sideways); uses z."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [(c * x + s * z, y, -s * x + c * z) for x, y, z in points]


def project(
    points_cm: Iterable[Point3],
    palm_px: float,
    width: int = 640,
    height: int = 480,
    centre: Point = (0.5, 0.62),
) -> list[Point]:
    """Orthographic projection to normalised image coordinates (y grows downwards).

    ``palm_px`` is the on-screen palm width of the un-rotated model.
    """
    s = palm_px / SYNTHETIC_PALM_WIDTH_CM
    cx, cy = centre[0] * width, centre[1] * height
    return [((cx + s * x) / width, (cy - s * (y - 5.0)) / height) for x, y, _z in points_cm]


def synthetic_hand(
    count: int, palm_px: float = 60.0, width: int = 640, height: int = 480, name: str = ""
) -> Hand:
    landmarks = project(synthetic_pose_cm(count), palm_px, width, height)
    return Hand(
        name or f"synthetic_{count}",
        count,
        width,
        height,
        tuple(landmarks),
        source="synthetic hand model",
    )


# Transforms on normalised landmarks -----------------------------------------


def _centroid(points: Sequence[Point]) -> Point:
    n = float(len(points))
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def rotate(hand: Hand, degrees: float, name: str | None = None) -> Hand:
    """Rotate in the image plane about the landmark centroid (aspect-correct)."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    px = hand.to_pixels()
    cx, cy = _centroid(px)
    out = []
    for x, y in px:
        dx, dy = x - cx, y - cy
        out.append(((cx + c * dx - s * dy) / hand.width, (cy + s * dx + c * dy) / hand.height))
    return hand.with_landmarks(out, name or f"{hand.name}_rot{int(degrees)}")


def scale(hand: Hand, factor: float, name: str | None = None) -> Hand:
    """Scale about the landmark centroid, as if the hand moved nearer or further."""
    px = hand.to_pixels()
    cx, cy = _centroid(px)
    out = [
        ((cx + (x - cx) * factor) / hand.width, (cy + (y - cy) * factor) / hand.height)
        for x, y in px
    ]
    return hand.with_landmarks(out, name or f"{hand.name}_x{factor:g}")


def mirror(hand: Hand, name: str | None = None) -> Hand:
    """Flip left-right, which is also what turns a right hand into a left hand."""
    return hand.with_landmarks(
        [(1.0 - x, y) for x, y in hand.landmarks], name or f"{hand.name}_mirror"
    )


def translate(hand: Hand, dx: float, dy: float, name: str | None = None) -> Hand:
    """Move by a fraction of the frame."""
    return hand.with_landmarks(
        [(x + dx, y + dy) for x, y in hand.landmarks], name or f"{hand.name}_shift"
    )


def resize_frame(hand: Hand, width: int, height: int, name: str | None = None) -> Hand:
    """Same hand captured at another resolution with the same aspect ratio."""
    if abs(width / height - hand.width / hand.height) > 1e-6:
        raise ValueError("resize_frame keeps the aspect ratio; use reframe for a new aspect")
    return Hand(
        name or f"{hand.name}_{width}x{height}",
        hand.expected_count,
        width,
        height,
        hand.landmarks,
        hand.source,
    )


def reframe(hand: Hand, width: int, height: int, name: str | None = None) -> Hand:
    """Place the same physical hand (same pixel geometry) in a frame of another size."""
    px = hand.to_pixels()
    cx, cy = _centroid(px)
    out = [((x - cx + width / 2) / width, (y - cy + height / 2) / height) for x, y in px]
    return Hand(
        name or f"{hand.name}_in{width}x{height}",
        hand.expected_count,
        width,
        height,
        tuple(out),
        hand.source,
    )


def palm_width_px(hand: Hand) -> float:
    px = hand.to_pixels()
    return math.hypot(px[5][0] - px[17][0], px[5][1] - px[17][1])


def scale_to_palm(hand: Hand, palm_px: float, name: str | None = None) -> Hand:
    return scale(hand, palm_px / palm_width_px(hand), name or f"{hand.name}_palm{int(palm_px)}")


# Scripted sequences ------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """A frame sequence with the outcome the pipeline must produce."""

    name: str
    description: str
    width: int
    height: int
    fps: float
    frames: tuple[tuple[Point, ...] | None, ...]
    expected_final_count: int
    expected_final_relays: tuple[bool, bool, bool, bool]
    expected_confirmations: tuple[int, ...] = field(default=())
    """Sequence of confirmed counts, in order, that must occur (and nothing else)."""

    def timestamps(self) -> list[float]:
        return [i / self.fps for i in range(len(self.frames))]


def _hold(hand: Hand | None, frames: int) -> list[tuple[Point, ...] | None]:
    return [None if hand is None else tuple(hand.landmarks)] * frames


def _relays(count: int) -> tuple[bool, bool, bool, bool]:
    from gesturecontrol.rules import relay_states_for_count

    r = relay_states_for_count(count)
    return (r[0], r[1], r[2], r[3])


def _noise(seed: int) -> Iterator[float]:
    """Deterministic pseudo-random values in [-1, 1) (a small LCG, no numpy)."""
    state = seed & 0xFFFFFFFF
    while True:
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        yield (state / 0x7FFFFFFF) * 2.0 - 1.0


def jittered(hand: Hand, frames: int, amplitude_px: float, seed: int) -> list[tuple[Point, ...]]:
    """Copies of a hand with bounded pseudo-random pixel noise on every landmark."""
    rng = _noise(seed)
    out = []
    for _ in range(frames):
        pts = []
        for x, y in hand.landmarks:
            pts.append(
                (
                    x + next(rng) * amplitude_px / hand.width,
                    y + next(rng) * amplitude_px / hand.height,
                )
            )
        out.append(tuple(pts))
    return out


def build_scenarios() -> list[Scenario]:
    real = {h.name: h for h in load_real_hands()}
    w, h, fps = 640, 480, 30.0
    scenarios: list[Scenario] = []

    def add(
        name: str,
        description: str,
        frames: Sequence[tuple[Point, ...] | None],
        final_count: int,
        confirmations: Sequence[int],
        *,
        width: int = w,
        height: int = h,
    ) -> None:
        scenarios.append(
            Scenario(
                name=name,
                description=description,
                width=width,
                height=height,
                fps=fps,
                frames=tuple(frames),
                expected_final_count=final_count,
                expected_final_relays=_relays(final_count),
                expected_confirmations=tuple(confirmations),
            )
        )

    poses = {n: synthetic_hand(n, 60.0, w, h) for n in range(6)}

    frames: list[tuple[Point, ...] | None] = []
    for n in range(6):
        frames += _hold(poses[n], 6)
    add(
        "count_up",
        "poses 0 to 5 held six frames each; each commits on its third frame",
        frames,
        5,
        [0, 1, 2, 3, 4, 5],
    )

    add(
        "hold_on_loss",
        "three fingers, then the hand leaves; relay 3 stays on",
        _hold(poses[3], 5) + _hold(None, 20),
        3,
        [3],
    )

    add(
        "reset_on_loss",
        "two frames of five, a gap, two frames of five: the run restarts after the gap",
        _hold(poses[5], 2) + _hold(None, 10) + _hold(poses[5], 2) + _hold(None, 3),
        -1,
        [],
    )

    add(
        "confirm_after_return",
        "after a gap, a count needs three fresh frames",
        _hold(poses[2], 2) + _hold(None, 5) + _hold(poses[2], 3),
        2,
        [2],
    )

    add(
        "single_frame_flicker",
        "one-frame excursions to another count never reach the relays",
        _hold(poses[2], 4)
        + _hold(poses[3], 1)
        + _hold(poses[2], 2)
        + _hold(poses[4], 1)
        + _hold(poses[2], 2)
        + _hold(poses[5], 2)
        + _hold(poses[2], 3),
        2,
        [2],
    )

    add(
        "fist_turns_everything_off",
        "open palm then fist",
        _hold(poses[5], 4) + _hold(poses[0], 4),
        0,
        [5, 0],
    )

    sweep = [tuple(rotate(poses[5], 6.0 * i).landmarks) for i in range(31)]
    add(
        "open_palm_rotation_sweep",
        "open palm rotating 0 to 180 degrees in the image plane",
        sweep,
        5,
        [5],
    )

    inverted = [tuple(rotate(poses[0], 180.0 - 4.0 * i).landmarks) for i in range(12)]
    add("inverted_fist", "fist pointing down and rotating back up stays zero", inverted, 0, [0])

    approach = [tuple(scale_to_palm(poses[5], 20.0 + 4.0 * i).landmarks) for i in range(26)]
    add("open_palm_approach", "open palm growing from 20 px to 120 px palm width", approach, 5, [5])

    add(
        "jitter_four_fingers",
        "four fingers with 3 px landmark noise on every frame; the count never flickers",
        jittered(poses[4], 40, 3.0, seed=7),
        4,
        [4],
    )

    add(
        "real_webcam_open_palm",
        "recorded open palm, mirrored copy afterwards",
        _hold(real["webcam_open_palm_a"], 4)
        + _hold(None, 2)
        + _hold(mirror(real["webcam_open_palm_a"]), 4),
        5,
        [5],
    )

    add(
        "real_tilted_palm_and_fist",
        "recorded tilted palm, then the recorded fist",
        _hold(real["webcam_open_palm_b"], 4) + _hold(None, 2) + _hold(real["photo_fist"], 4),
        0,
        [5, 0],
    )

    add(
        "real_palm_from_behind_small",
        "recorded palm photographed from behind, shrunk to a 24 px palm",
        _hold(scale_to_palm(real["photo_open_palm_back"], 24.0), 4),
        5,
        [5],
    )

    add(
        "transition_one_to_five",
        "1 to 5 passing through 2, 3 and 4 held three frames each: every step commits",
        _hold(poses[1], 5)
        + _hold(poses[2], 3)
        + _hold(poses[3], 3)
        + _hold(poses[4], 3)
        + _hold(poses[5], 5),
        5,
        [1, 2, 3, 4, 5],
    )

    hd = reframe(poses[3], 1280, 720)
    add(
        "hd_frame_three_fingers",
        "three fingers in a 1280x720 frame",
        _hold(hd, 4),
        3,
        [3],
        width=1280,
        height=720,
    )

    return scenarios


# Single-frame classifier cases -------------------------------------------------


@dataclass(frozen=True)
class ClassifierCase:
    name: str
    base: str
    transform: str
    expected_count: int
    width: int
    height: int
    landmarks: tuple[Point, ...]

    @classmethod
    def from_hand(cls, hand: Hand, base: str, transform: str) -> ClassifierCase:
        return cls(
            hand.name, base, transform, hand.expected_count, hand.width, hand.height, hand.landmarks
        )


def build_classifier_cases() -> list[ClassifierCase]:
    """Real and synthetic hands under transforms that must not change the count."""
    bases: list[Hand] = list(load_real_hands()) + [synthetic_hand(n) for n in range(6)]
    cases: list[ClassifierCase] = []

    def add(hand: Hand, base: str, transform: str) -> None:
        cases.append(ClassifierCase.from_hand(hand, base, transform))

    for hand in bases:
        add(hand, hand.name, "identity")
        add(mirror(hand), hand.name, "mirror")
        for deg in (30, 45, 75, 90, 135, 180, -45):
            add(rotate(hand, deg), hand.name, f"rotate {deg}")
        for palm in (12.0, 20.0, 30.0, 120.0):
            add(scale_to_palm(hand, palm), hand.name, f"palm {palm:g} px")
        if hand.width == 640 and hand.height == 480:
            add(resize_frame(hand, 320, 240), hand.name, "frame 320x240")
            add(resize_frame(hand, 1280, 960), hand.name, "frame 1280x960")
        add(reframe(hand, 1280, 720), hand.name, "frame 1280x720")
        add(reframe(hand, 1920, 1080), hand.name, "frame 1920x1080")
        add(translate(hand, -0.3, 0.2), hand.name, "translate")
        combined = mirror(scale_to_palm(rotate(hand, 120), 16.0), f"{hand.name}_combined")
        add(combined, hand.name, "rotate 120, palm 16 px, mirror")

    four = (True, True, True, True)
    for thumb in ("adducted", "across", "fist"):
        hand = Hand(
            f"synthetic_four_thumb_{thumb}",
            4,
            640,
            480,
            tuple(project(synthetic_hand_cm(four, thumb), 60.0)),
            "synthetic hand model",
        )
        add(hand, hand.name, "identity")
        add(rotate(hand, 90), hand.name, "rotate 90")
    for deg in (30, 45, 60):
        pts = yaw_cm(synthetic_hand_cm(four, "adducted"), deg)
        add(
            Hand(
                f"synthetic_four_adducted_yaw{deg}",
                4,
                640,
                480,
                tuple(project(pts, 60.0)),
                "synthetic hand model",
            ),
            "synthetic_4",
            f"yaw {deg}",
        )
        pts = yaw_cm(synthetic_hand_cm(four, "extended"), deg)
        add(
            Hand(
                f"synthetic_five_yaw{deg}",
                5,
                640,
                480,
                tuple(project(pts, 60.0)),
                "synthetic hand model",
            ),
            "synthetic_5",
            f"yaw {deg}",
        )
    return cases
