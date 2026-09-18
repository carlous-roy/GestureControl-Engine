from __future__ import annotations

import math
import statistics

import pytest

from gesturecontrol.config import DEFAULT_RULES, FilterConfig
from gesturecontrol.filters import LandmarkFilter, OneEuroFilter, smoothing_factor


def test_first_sample_passes_through() -> None:
    f = OneEuroFilter(DEFAULT_RULES.filter)
    assert f(0.42, 0.0) == 0.42


def test_constant_input_is_unchanged() -> None:
    f = OneEuroFilter(DEFAULT_RULES.filter)
    for i in range(50):
        assert f(0.3, i / 30.0) == pytest.approx(0.3, abs=1e-12)


def test_reduces_jitter_at_rest() -> None:
    cfg = DEFAULT_RULES.filter
    f = OneEuroFilter(cfg)
    # Deterministic +/- 3 px jitter on a 640 px frame around a still point.
    noise = [((i * 7919) % 13 - 6) / 6 * 3 / 640 for i in range(300)]
    raw = [0.5 + n for n in noise]
    out = [f(x, i / 30.0) for i, x in enumerate(raw)]
    raw_sd = statistics.pstdev(raw[100:])
    out_sd = statistics.pstdev(out[100:])
    assert out_sd < raw_sd / 3


def test_follows_fast_motion_with_bounded_lag() -> None:
    cfg = DEFAULT_RULES.filter
    f = OneEuroFilter(cfg)
    # A hand crossing the frame in half a second (2 normalised units per second).
    xs = [min(1.0, 2.0 * i / 30.0) for i in range(40)]
    out = [f(x, i / 30.0) for i, x in enumerate(xs)]
    lag_frames = next(i for i, y in enumerate(out) if y > 0.95) - next(
        i for i, x in enumerate(xs) if x > 0.95
    )
    assert lag_frames <= 3
    assert abs(out[-1] - 1.0) < 1e-3


def test_speed_raises_cutoff() -> None:
    slow = OneEuroFilter(FilterConfig(min_cutoff_hz=1.0, beta=0.0, derivative_cutoff_hz=1.0))
    fast = OneEuroFilter(FilterConfig(min_cutoff_hz=1.0, beta=5.0, derivative_cutoff_hz=1.0))
    xs = [i / 30.0 for i in range(30)]
    a = [slow(x, i / 30.0) for i, x in enumerate(xs)]
    b = [fast(x, i / 30.0) for i, x in enumerate(xs)]
    assert b[-1] > a[-1]


def test_duplicate_timestamp_holds_estimate() -> None:
    f = OneEuroFilter(DEFAULT_RULES.filter)
    f(0.1, 0.0)
    y1 = f(0.2, 1 / 30)
    assert f(0.9, 1 / 30) == y1


def test_reset_forgets_history() -> None:
    f = OneEuroFilter(DEFAULT_RULES.filter)
    f(0.1, 0.0)
    f(0.1, 1 / 30)
    f.reset()
    assert f(0.8, 2 / 30) == 0.8


def test_smoothing_factor_matches_paper() -> None:
    # alpha = 1 / (1 + tau / Te) with tau = 1 / (2 pi fc)
    fc, dt = 1.0, 1 / 30
    expected = 1.0 / (1.0 + (1.0 / (2 * math.pi * fc)) / dt)
    assert math.isclose(smoothing_factor(fc, dt), expected)


def test_landmark_filter_shape_and_reset() -> None:
    lf = LandmarkFilter(DEFAULT_RULES.filter)
    pts = [(i / 21, 0.5) for i in range(21)]
    out = lf(pts, 0.0)
    assert out == pts
    moved = [(x + 0.01, y) for x, y in pts]
    out2 = lf(moved, 1 / 30)
    assert all(pts[i][0] < out2[i][0] < moved[i][0] for i in range(21))
    lf.reset()
    assert lf(moved, 2 / 30) == moved
