"""Regenerate tests/fixtures/classifier_cases.json from gesturecontrol.scenarios.

Run from the repository root:  python scripts/build_fixtures.py
The test suite checks that the committed file matches this output.
"""

from __future__ import annotations

import json
from pathlib import Path

from gesturecontrol.scenarios import build_classifier_cases

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "classifier_cases.json"


def render() -> str:
    cases = [
        {
            "name": c.name,
            "base": c.base,
            "transform": c.transform,
            "expected_count": c.expected_count,
            "width": c.width,
            "height": c.height,
            "landmarks": [[round(x, 6), round(y, 6)] for x, y in c.landmarks],
        }
        for c in build_classifier_cases()
    ]
    doc = {
        "description": (
            "Single-frame classifier cases: real hands (see gesturecontrol/data/hands.json) "
            "and synthetic poses under transforms that must not change the finger count."
        ),
        "cases": cases,
    }
    return json.dumps(doc, indent=1) + "\n"


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
