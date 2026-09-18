"""
One Euro filter for landmark coordinates.

Reference: Casiez, G., Roussel, N. and Vogel, D. (2012). "1 Euro Filter: A
Simple Speed-based Low-pass Filter for Noisy Input in Interactive Systems."
Proceedings of CHI 2012, pages 2527-2530. https://doi.org/10.1145/2207676.2208639

The filter is an exponential low-pass whose cutoff frequency rises with the
speed of the signal: at rest it smooths jitter, in fast motion it follows the
input with little lag. ``min_cutoff`` sets the smoothing at rest, ``beta``
sets how quickly the cutoff opens with speed, and ``derivative_cutoff``
smooths the speed estimate itself. The implementation follows the algorithm
listing in the paper, with the speed taken between the raw sample and the
previous filtered value.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from gesturecontrol.config import FilterConfig

Point = tuple[float, float]


def smoothing_factor(cutoff_hz: float, dt: float) -> float:
    """Alpha for an exponential low-pass with the given cutoff and sample period."""
    tau = 1.0 / (2.0 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    """Filter one scalar signal sampled at irregular times."""

    def __init__(self, config: FilterConfig) -> None:
        self._config = config
        self._t_prev: float | None = None
        self._x_prev = 0.0
        self._dx_prev = 0.0

    def reset(self) -> None:
        self._t_prev = None
        self._x_prev = 0.0
        self._dx_prev = 0.0

    def __call__(self, x: float, t: float) -> float:
        if self._t_prev is None:
            self._t_prev = t
            self._x_prev = x
            self._dx_prev = 0.0
            return x

        dt = t - self._t_prev
        if dt <= 0.0:
            # Duplicate or out-of-order timestamp: hold the last estimate.
            return self._x_prev

        dx = (x - self._x_prev) / dt
        a_d = smoothing_factor(self._config.derivative_cutoff_hz, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev

        cutoff = self._config.min_cutoff_hz + self._config.beta * abs(dx_hat)
        a = smoothing_factor(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev

        self._t_prev = t
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        return x_hat


class LandmarkFilter:
    """One Euro filter per coordinate for a fixed number of 2D landmarks."""

    def __init__(self, config: FilterConfig, num_points: int = 21) -> None:
        self._filters = [(OneEuroFilter(config), OneEuroFilter(config)) for _ in range(num_points)]

    @property
    def num_points(self) -> int:
        return len(self._filters)

    def reset(self) -> None:
        for fx, fy in self._filters:
            fx.reset()
            fy.reset()

    def __call__(self, points: Sequence[Point], t: float) -> list[Point]:
        if len(points) != len(self._filters):
            raise ValueError(f"expected {len(self._filters)} points, got {len(points)}")
        return [
            (fx(x, t), fy(y, t)) for (x, y), (fx, fy) in zip(points, self._filters, strict=True)
        ]
