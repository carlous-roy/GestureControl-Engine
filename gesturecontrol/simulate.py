"""
Run scripted landmark sequences through the real pipeline and relay
controller without a camera, a display or a board.

Each scenario in ``scenarios.build_scenarios`` declares the confirmations
it must produce and the final relay state. The command replays the frames
at the scenario's frame rate (on a simulated clock unless ``--realtime``),
prints what happened, and exits non-zero if any expectation fails. CI runs
it as the end-to-end smoke test.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TextIO

from gesturecontrol import scenarios as sc
from gesturecontrol.config import DEFAULT_RULES, MIN_SWITCH_INTERVAL_S, RulesConfig
from gesturecontrol.controller import RelayController
from gesturecontrol.pipeline import GesturePipeline


@dataclass
class ScenarioReport:
    name: str
    frames: int
    confirmations: list[int]
    final_count: int
    final_relays: list[bool]
    relay_switches: int
    passed: bool
    problems: list[str]


def _bits(states: Sequence[bool]) -> str:
    return "".join("1" if s else "0" for s in states)


def run_scenario(
    scenario: sc.Scenario,
    *,
    config: RulesConfig = DEFAULT_RULES,
    min_switch_interval: float = MIN_SWITCH_INTERVAL_S,
    realtime: bool = False,
    verbose: bool = False,
    out: TextIO | None = None,
) -> ScenarioReport:
    out = out or sys.stdout
    now = [0.0]
    controller = RelayController(min_switch_interval=min_switch_interval, clock=lambda: now[0])
    pipeline = GesturePipeline(scenario.width, scenario.height, config)
    confirmations: list[int] = []
    switches = 0
    last_line = ""
    for i, (frame, t) in enumerate(zip(scenario.frames, scenario.timestamps(), strict=True)):
        now[0] = t
        if realtime and i:
            time.sleep(1.0 / scenario.fps)
        result = pipeline.process(frame, t)
        before = controller.states
        if result.changed:
            confirmations.append(result.confirmed_count)
            controller.set_from_finger_count(result.confirmed_count)
        else:
            controller.apply()
        switches += sum(a != b for a, b in zip(before, controller.states, strict=True))
        line = (
            f"  frame {i:3d} t={t:5.2f}s hand={'yes' if result.hand_present else 'no ':3s} "
            f"raw={result.raw_count:2d} confirmed={result.confirmed_count:2d} "
            f"relays={_bits(controller.states)}" + ("  pending" if controller.pending else "")
        )
        if verbose or result.changed or line[-20:] != last_line[-20:]:
            out.write(line + "\n")
        last_line = line
    # Let deferred relay changes through before judging the final state.
    now[0] += min_switch_interval
    before = controller.states
    controller.apply()
    switches += sum(a != b for a, b in zip(before, controller.states, strict=True))

    problems: list[str] = []
    if confirmations != list(scenario.expected_confirmations):
        problems.append(
            f"confirmations {confirmations} != expected {list(scenario.expected_confirmations)}"
        )
    if pipeline.confirmed_count != scenario.expected_final_count:
        problems.append(
            f"final count {pipeline.confirmed_count} != expected {scenario.expected_final_count}"
        )
    if tuple(controller.states) != scenario.expected_final_relays:
        problems.append(
            f"final relays {_bits(controller.states)} != expected "
            f"{_bits(scenario.expected_final_relays)}"
        )
    return ScenarioReport(
        name=scenario.name,
        frames=len(scenario.frames),
        confirmations=confirmations,
        final_count=pipeline.confirmed_count,
        final_relays=controller.states,
        relay_switches=switches,
        passed=not problems,
        problems=problems,
    )


def simulate(
    names: Sequence[str] | None = None,
    *,
    min_switch_interval: float = MIN_SWITCH_INTERVAL_S,
    realtime: bool = False,
    verbose: bool = False,
    out: TextIO | None = None,
) -> int:
    """Run the named scenarios (all by default); returns 0 when every one passes."""
    out = out or sys.stdout
    available = {s.name: s for s in sc.build_scenarios()}
    if names:
        unknown = [n for n in names if n not in available]
        if unknown:
            out.write(f"unknown scenario(s): {', '.join(unknown)}\n")
            out.write(f"available: {', '.join(available)}\n")
            return 2
        selected = [available[n] for n in names]
    else:
        selected = list(available.values())

    reports: list[ScenarioReport] = []
    for scenario in selected:
        out.write(f"\n{scenario.name}: {scenario.description}\n")
        report = run_scenario(
            scenario,
            min_switch_interval=min_switch_interval,
            realtime=realtime,
            verbose=verbose,
            out=out,
        )
        status = "ok" if report.passed else "FAIL"
        out.write(
            f"  -> {status}: confirmations {report.confirmations}, final count "
            f"{report.final_count}, relays {_bits(report.final_relays)}, "
            f"{report.relay_switches} relay switch(es) over {report.frames} frames\n"
        )
        for problem in report.problems:
            out.write(f"     {problem}\n")
        reports.append(report)

    failed = [r for r in reports if not r.passed]
    out.write(f"\n{len(reports) - len(failed)} of {len(reports)} scenarios passed\n")
    return 1 if failed else 0


def list_scenarios(out: TextIO | None = None) -> None:
    out = out or sys.stdout
    for scenario in sc.build_scenarios():
        out.write(f"{scenario.name:32s} {len(scenario.frames):4d} frames  {scenario.description}\n")
