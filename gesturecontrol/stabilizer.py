"""
Temporal confirmation of the finger count.

A count is confirmed only after it has been seen on ``confirm_frames``
consecutive frames with a hand present. Losing the hand resets the run, so
a count seen once before the hand left the frame does not carry over to
its return. The confirmed count is kept while the hand is out of frame
(the relays hold their last state); it only changes on a new confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Confirmation:
    confirmed: int
    """Last confirmed count, or -1 if nothing has been confirmed yet."""
    changed: bool
    """True on the frame the confirmed count changed."""
    run_length: int
    """How many consecutive frames the current raw count has been seen."""


class CountStabilizer:
    def __init__(self, confirm_frames: int) -> None:
        if confirm_frames < 1:
            raise ValueError("confirm_frames must be at least 1")
        self._confirm_frames = confirm_frames
        self._confirmed = -1
        self._candidate = -1
        self._run = 0

    @property
    def confirmed(self) -> int:
        return self._confirmed

    def reset(self) -> None:
        """Forget the pending candidate; the confirmed count is kept."""
        self._candidate = -1
        self._run = 0

    def update(self, raw_count: int) -> Confirmation:
        if raw_count < 0:
            self.reset()
            return Confirmation(self._confirmed, False, 0)

        if raw_count == self._candidate:
            self._run += 1
        else:
            self._candidate = raw_count
            self._run = 1

        changed = False
        if self._run >= self._confirm_frames and self._candidate != self._confirmed:
            self._confirmed = self._candidate
            changed = True
        return Confirmation(self._confirmed, changed, self._run)
