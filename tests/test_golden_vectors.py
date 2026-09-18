"""The pipeline must reproduce fixtures/golden_vectors.json, and the demo's
copies of the shared files must be identical to the originals."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from gesturecontrol.config import DEFAULT_RULES, RulesConfig
from gesturecontrol.pipeline import GesturePipeline

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "fixtures" / "golden_vectors.json"
RULES = ROOT / "gesturecontrol" / "rules.json"
DEMO_COPIES = {
    RULES: ROOT / "demo" / "src" / "gesture" / "rules.json",
    GOLDEN: ROOT / "demo" / "test" / "golden_vectors.json",
}

DOC = json.loads(GOLDEN.read_text("utf-8"))
SEQUENCES = DOC["sequences"]


def _bits(flags: Any) -> str:
    return "".join("1" if f else "0" for f in flags)


@pytest.mark.parametrize("seq", SEQUENCES, ids=[s["name"] for s in SEQUENCES])
def test_pipeline_reproduces_golden_sequence(seq: dict[str, Any]) -> None:
    config = RulesConfig.from_dict(DOC["rules"])
    pipeline = GesturePipeline(int(seq["width"]), int(seq["height"]), config)
    frames = seq["frames"]
    expected = seq["expected"]
    fps = float(seq["fps"])
    for i, (frame, want) in enumerate(zip(frames, expected, strict=True)):
        points = None if frame is None else [(x, y) for x, y in frame]
        r = pipeline.process(points, i / fps)
        got = {
            "hand": r.hand_present,
            "raw": r.raw_count,
            "confirmed": r.confirmed_count,
            "changed": r.changed,
            "relays": _bits(r.relays),
            "fingers": None if r.finger_states is None else _bits(r.finger_states),
        }
        assert got == {k: want[k] for k in got}, f"{seq['name']} frame {i}"
        if r.points_px is None:
            assert want["sum_px"] is None
        else:
            assert sum(x + y for x, y in r.points_px) == pytest.approx(want["sum_px"], abs=1e-5)


def _load_exporter() -> Any:
    path = ROOT / "scripts" / "export_golden_vectors.py"
    spec = importlib.util.spec_from_file_location("export_golden_vectors", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_golden_file_matches_current_rules_and_scenarios() -> None:
    exporter = _load_exporter()
    assert DOC["rules"] == json.loads(RULES.read_text("utf-8"))
    assert exporter.render() == GOLDEN.read_text("utf-8"), (
        "fixtures/golden_vectors.json is stale; run scripts/export_golden_vectors.py "
        "and scripts/sync_demo_fixtures.py"
    )


def test_golden_rules_are_the_default_rules() -> None:
    assert RulesConfig.from_dict(DOC["rules"]) == DEFAULT_RULES


@pytest.mark.parametrize("source", list(DEMO_COPIES), ids=lambda p: p.name)
def test_demo_copies_are_in_sync(source: Path) -> None:
    copy = DEMO_COPIES[source]
    assert copy.exists(), f"{copy} missing; run scripts/sync_demo_fixtures.py"
    assert copy.read_bytes() == source.read_bytes(), (
        f"{copy} differs from {source}; run scripts/sync_demo_fixtures.py"
    )
