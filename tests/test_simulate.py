from __future__ import annotations

import dataclasses
import io

from gesturecontrol import scenarios as sc
from gesturecontrol.simulate import list_scenarios, run_scenario, simulate


def test_all_scenarios_pass() -> None:
    out = io.StringIO()
    assert simulate(out=out) == 0
    text = out.getvalue()
    assert "15 of 15 scenarios passed" in text
    assert "FAIL" not in text


def test_selected_scenario_and_switch_count() -> None:
    # Without the switching interval: 1 on; 2 on and 1 off; 3 on and 2 off;
    # 4 on and 3 off; then 1, 2 and 3 on again: 10 switches in half a second.
    out = io.StringIO()
    assert simulate(["transition_one_to_five"], min_switch_interval=0.0, out=out) == 0
    assert "10 relay switch(es)" in out.getvalue()
    # With the 0.5 s interval the deferred releases are overtaken by the final
    # all-on state, so each relay switches once.
    out = io.StringIO()
    assert simulate(["transition_one_to_five"], min_switch_interval=0.5, out=out) == 0
    assert "4 relay switch(es)" in out.getvalue()


def test_switching_interval_defers_changes_in_the_trace() -> None:
    out = io.StringIO()
    scenario = next(s for s in sc.build_scenarios() if s.name == "transition_one_to_five")
    report = run_scenario(scenario, min_switch_interval=0.5, out=out)
    assert report.passed
    assert "pending" in out.getvalue()
    out2 = io.StringIO()
    report2 = run_scenario(scenario, min_switch_interval=0.0, out=out2)
    assert report2.passed
    assert "pending" not in out2.getvalue()


def test_unknown_scenario_is_reported() -> None:
    out = io.StringIO()
    assert simulate(["no_such_scenario"], out=out) == 2
    assert "unknown scenario" in out.getvalue()


def test_wrong_expectation_fails() -> None:
    scenario = next(s for s in sc.build_scenarios() if s.name == "hold_on_loss")
    broken = dataclasses.replace(scenario, expected_final_count=4)
    report = run_scenario(broken, out=io.StringIO())
    assert not report.passed
    assert any("final count" in p for p in report.problems)


def test_list_scenarios() -> None:
    out = io.StringIO()
    list_scenarios(out)
    assert "hold_on_loss" in out.getvalue()
