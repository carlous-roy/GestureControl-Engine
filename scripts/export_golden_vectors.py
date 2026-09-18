"""Export fixtures/golden_vectors.json: landmark sequences with the outputs the
pipeline must produce on every frame.

Both test suites read this file: tests/test_golden_vectors.py (Python) and
demo/test/golden.test.js (JavaScript port). Regenerate it after changing
the rules, the filter, the confirmation logic or the scenarios, then run
scripts/sync_demo_fixtures.py to refresh the copy the demo tests use.

Run from the repository root:  python scripts/export_golden_vectors.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gesturecontrol import scenarios as sc
from gesturecontrol.config import DEFAULT_RULES
from gesturecontrol.pipeline import GesturePipeline

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fixtures" / "golden_vectors.json"
RULES = ROOT / "gesturecontrol" / "rules.json"
COORD_DECIMALS = 6


def _bits(flags: Any) -> str:
    return "".join("1" if f else "0" for f in flags)


def render_sequences() -> list[dict[str, Any]]:
    sequences = []
    for scenario in sc.build_scenarios():
        frames = [
            None
            if f is None
            else [[round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)] for x, y in f]
            for f in scenario.frames
        ]
        pipeline = GesturePipeline(scenario.width, scenario.height, DEFAULT_RULES)
        expected = []
        for frame, t in zip(frames, scenario.timestamps(), strict=True):
            points = None if frame is None else [(x, y) for x, y in frame]
            r = pipeline.process(points, t)
            expected.append(
                {
                    "hand": r.hand_present,
                    "raw": r.raw_count,
                    "confirmed": r.confirmed_count,
                    "changed": r.changed,
                    "relays": _bits(r.relays),
                    "fingers": None if r.finger_states is None else _bits(r.finger_states),
                    "sum_px": None
                    if r.points_px is None
                    else round(sum(x + y for x, y in r.points_px), 6),
                }
            )
        sequences.append(
            {
                "name": scenario.name,
                "description": scenario.description,
                "width": scenario.width,
                "height": scenario.height,
                "fps": scenario.fps,
                "frames": frames,
                "expected": expected,
            }
        )
    return sequences


def render() -> str:
    doc = {
        "version": 1,
        "generated_by": "scripts/export_golden_vectors.py",
        "description": (
            "Landmark sequences (normalised x, y per frame; null = no hand) and the "
            "per-frame outputs of the gesture pipeline: raw count, confirmed count, "
            "change flag, relay states, latched finger states and the sum of the "
            "filtered pixel coordinates. Timestamps are frame_index / fps."
        ),
        "rules": json.loads(RULES.read_text("utf-8")),
        "sequences": render_sequences(),
    }
    return json.dumps(doc, indent=1) + "\n"


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
