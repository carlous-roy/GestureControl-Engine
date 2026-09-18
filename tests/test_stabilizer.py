from __future__ import annotations

import pytest

from gesturecontrol.stabilizer import CountStabilizer


def _run(stab: CountStabilizer, counts: list[int]) -> list[int]:
    return [stab.update(c).confirmed for c in counts]


def test_commits_on_the_third_consecutive_frame() -> None:
    stab = CountStabilizer(3)
    assert _run(stab, [2, 2]) == [-1, -1]
    r = stab.update(2)
    assert r.confirmed == 2
    assert r.changed is True
    assert r.run_length == 3
    assert stab.update(2).changed is False


def test_two_frames_then_loss_does_not_commit() -> None:
    stab = CountStabilizer(3)
    assert _run(stab, [2, 2, -1, -1]) == [-1, -1, -1, -1]


def test_hold_on_loss() -> None:
    stab = CountStabilizer(3)
    _run(stab, [3, 3, 3])
    assert _run(stab, [-1] * 60) == [3] * 60


def test_run_resets_on_hand_loss() -> None:
    """A count seen before the hand left must not be banked towards a later commit."""
    stab = CountStabilizer(3)
    _run(stab, [0, 0, 0, 5])
    _run(stab, [-1] * 50)
    assert _run(stab, [5, 5]) == [0, 0]
    assert stab.update(5).confirmed == 5


def test_run_resets_on_count_change() -> None:
    stab = CountStabilizer(3)
    assert _run(stab, [1, 1, 2, 2, 1, 1, 2, 2, 2]) == [-1, -1, -1, -1, -1, -1, -1, -1, 2]


def test_confirm_frames_validated() -> None:
    with pytest.raises(ValueError, match="confirm_frames"):
        CountStabilizer(0)
    stab = CountStabilizer(1)
    assert stab.update(4).confirmed == 4
