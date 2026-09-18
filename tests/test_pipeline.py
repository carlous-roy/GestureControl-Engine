from __future__ import annotations

import pytest

from gesturecontrol import scenarios as sc
from gesturecontrol.config import DEFAULT_RULES
from gesturecontrol.pipeline import FrameResult, GesturePipeline

SCENARIOS = sc.build_scenarios()


def run_scenario(scenario: sc.Scenario) -> list[FrameResult]:
    pipeline = GesturePipeline(scenario.width, scenario.height, DEFAULT_RULES)
    return [
        pipeline.process(frame, t)
        for frame, t in zip(scenario.frames, scenario.timestamps(), strict=True)
    ]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.name for s in SCENARIOS])
def test_scenario_outcome(scenario: sc.Scenario) -> None:
    results = run_scenario(scenario)
    confirmations = [r.confirmed_count for r in results if r.changed]
    assert confirmations == list(scenario.expected_confirmations), scenario.description
    assert results[-1].confirmed_count == scenario.expected_final_count
    assert results[-1].relays == scenario.expected_final_relays


def test_hold_on_loss_keeps_relays_for_the_whole_gap() -> None:
    scenario = next(s for s in SCENARIOS if s.name == "hold_on_loss")
    results = run_scenario(scenario)
    gap = [r for r in results if not r.hand_present]
    assert len(gap) == 20
    assert all(r.confirmed_count == 3 for r in gap)
    assert all(r.relays == (False, False, True, False) for r in gap)
    assert all(r.raw_count == -1 and r.finger_states is None for r in gap)


def test_jitter_scenario_never_flickers() -> None:
    scenario = next(s for s in SCENARIOS if s.name == "jitter_four_fingers")
    results = run_scenario(scenario)
    assert {r.raw_count for r in results} == {4}


def test_rotation_sweep_reads_five_on_every_frame() -> None:
    scenario = next(s for s in SCENARIOS if s.name == "open_palm_rotation_sweep")
    results = run_scenario(scenario)
    assert {r.raw_count for r in results} == {5}


def test_commit_happens_on_third_frame() -> None:
    scenario = next(s for s in SCENARIOS if s.name == "count_up")
    results = run_scenario(scenario)
    change_frames = [i for i, r in enumerate(results) if r.changed]
    assert change_frames == [2, 8, 14, 20, 26, 32]


def test_no_hand_resets_filter_state() -> None:
    pipeline = GesturePipeline(640, 480)
    hand = sc.synthetic_hand(5)
    far = sc.translate(hand, 0.3, 0.0)
    pipeline.process(hand.landmarks, 0.0)
    pipeline.process(None, 1 / 30)
    r = pipeline.process(far.landmarks, 2 / 30)
    assert r.points_px is not None
    # First sample after a reset passes through unfiltered.
    assert r.points_px[0][0] == pytest.approx(far.landmarks[0][0] * 640)


def test_frame_size_validation() -> None:
    with pytest.raises(ValueError, match="positive"):
        GesturePipeline(0, 480)
