from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from gesturecontrol import scenarios as sc
from gesturecontrol.config import DEFAULT_RULES, Hysteresis
from gesturecontrol.rules import (
    FingerClassifier,
    hand_frame,
    latch,
    measure,
    relay_states_for_count,
)

FIXTURE = Path(__file__).parent / "fixtures" / "classifier_cases.json"
CASES = json.loads(FIXTURE.read_text("utf-8"))["cases"]


def _pixels(case: dict[str, Any]) -> list[tuple[float, float]]:
    w, h = float(case["width"]), float(case["height"])
    return [(x * w, y * h) for x, y in case["landmarks"]]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fixture_case_from_rest(case: dict[str, Any]) -> None:
    """A fresh classifier (all fingers down) must reach the expected count."""
    clf = FingerClassifier(DEFAULT_RULES)
    assert clf.update(_pixels(case)) == case["expected_count"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_fixture_case_from_all_up(case: dict[str, Any]) -> None:
    """A classifier latched to all-up must also reach it, so both bands hold."""
    clf = FingerClassifier(DEFAULT_RULES)
    clf._states = [True] * 5  # deliberately pre-latched
    assert clf.update(_pixels(case)) == case["expected_count"]


def test_fixture_file_is_current() -> None:
    """The committed fixture must match what the generator produces."""
    expected = [
        {
            "name": c.name,
            "base": c.base,
            "transform": c.transform,
            "expected_count": c.expected_count,
            "width": c.width,
            "height": c.height,
            "landmarks": [[round(x, 6), round(y, 6)] for x, y in c.landmarks],
        }
        for c in sc.build_classifier_cases()
    ]
    assert expected == CASES


def test_fixture_covers_the_audit_failure_cases() -> None:
    names = {c["name"] for c in CASES}
    assert "synthetic_5_rot90" in names
    assert "synthetic_5_rot180" in names
    assert "synthetic_0_rot135" in names
    assert "synthetic_0_rot180" in names
    assert "synthetic_5_palm20" in names
    assert "synthetic_four_thumb_across" in names
    assert "synthetic_four_adducted_yaw60" in names
    assert "photo_fist_mirror" in names


def test_real_hands_all_present() -> None:
    real = {h.name: h for h in sc.load_real_hands()}
    assert set(real) == {
        "webcam_open_palm_a",
        "webcam_open_palm_b",
        "photo_open_palm_back",
        "photo_fist",
    }
    for hand in real.values():
        assert len(hand.landmarks) == 21


def test_measurements_are_rotation_and_scale_invariant() -> None:
    base = sc.synthetic_hand(3)
    ref = measure(base.to_pixels(), DEFAULT_RULES)
    assert ref is not None
    for hand in (sc.rotate(base, 137.0), sc.scale_to_palm(base, 25.0), sc.mirror(base)):
        m = measure(hand.to_pixels(), DEFAULT_RULES)
        assert m is not None
        assert math.isclose(m.thumb, ref.thumb, abs_tol=1e-9)
        for a, b in zip(m.fingers, ref.fingers, strict=True):
            assert math.isclose(a, b, abs_tol=1e-9)


def test_extended_fingers_sit_well_inside_the_bands() -> None:
    """Every real and synthetic case keeps a margin from both hysteresis thresholds."""
    cfg = DEFAULT_RULES
    margin = 0.1
    for case in CASES:
        m = measure(_pixels(case), cfg)
        assert m is not None, case["name"]
        count = int(case["expected_count"])
        up = [False] * 5
        if count == 5:
            up = [True] * 5
        elif count > 0:
            up = [False] + [True] * count + [False] * (4 - count)
        values = [m.thumb, *m.fingers]
        for i, (is_up, value) in enumerate(zip(up, values, strict=True)):
            band = cfg.thumb if i == 0 else cfg.finger
            if is_up:
                assert value > band.raise_threshold + margin, (case["name"], value)
            else:
                assert value < band.lower_threshold - margin, (case["name"], value)


def test_side_axis_points_to_the_thumb_for_both_hands() -> None:
    right = sc.synthetic_hand(5)
    left = sc.mirror(right)
    for hand in (right, left):
        px = hand.to_pixels()
        frame = hand_frame(px, DEFAULT_RULES.min_palm_width_px)
        assert frame is not None
        thumb_dir = (px[4][0] - px[0][0], px[4][1] - px[0][1])
        assert thumb_dir[0] * frame.side[0] + thumb_dir[1] * frame.side[1] > 0


def test_degenerate_geometry_reports_no_hand() -> None:
    tiny = sc.scale_to_palm(sc.synthetic_hand(5), 4.0)
    clf = FingerClassifier(DEFAULT_RULES)
    assert clf.update(tiny.to_pixels()) == -1
    assert clf.states == [False] * 5
    with pytest.raises(ValueError, match="21"):
        clf.update([(0.0, 0.0)] * 20)


def test_hysteresis_latch() -> None:
    band = Hysteresis(raise_threshold=0.35, lower_threshold=0.25)
    assert latch(False, 0.30, band) is False
    assert latch(False, 0.36, band) is True
    assert latch(True, 0.30, band) is True
    assert latch(True, 0.24, band) is False
    with pytest.raises(ValueError, match="lower_threshold"):
        Hysteresis(raise_threshold=0.2, lower_threshold=0.3)


def test_classifier_latches_across_frames() -> None:
    """A finger hovering between the thresholds keeps its previous state."""
    clf = FingerClassifier(DEFAULT_RULES)
    base = sc.synthetic_hand(4)
    px = base.to_pixels()
    assert clf.update(px) == 4
    # Shorten the pinky so its extension lands inside the band (0.25..0.35).
    frame = hand_frame(px, DEFAULT_RULES.min_palm_width_px)
    assert frame is not None
    m = measure(px, DEFAULT_RULES)
    assert m is not None
    reduce = (m.fingers[3] - 0.30) * frame.palm_width
    pts = list(px)
    pts[20] = (pts[20][0] - frame.up[0] * reduce, pts[20][1] - frame.up[1] * reduce)
    m2 = measure(pts, DEFAULT_RULES)
    assert m2 is not None
    assert 0.25 < m2.fingers[3] < 0.35
    assert clf.update(pts) == 4  # stays up, latched
    fresh = FingerClassifier(DEFAULT_RULES)
    assert fresh.update(pts) == 3  # not raised from rest


def test_relay_mapping() -> None:
    assert relay_states_for_count(0) == [False] * 4
    assert relay_states_for_count(3) == [False, False, True, False]
    assert relay_states_for_count(5) == [True] * 4
    assert relay_states_for_count(-1) == [False] * 4
    assert relay_states_for_count(9) == [False] * 4
