"""Copy the shared rules and golden vectors into the demo folder.

The demo is deployed from its own copy of demo/, so it carries copies of
gesturecontrol/rules.json and fixtures/golden_vectors.json. This script
refreshes them; tests/test_golden_vectors.py fails when they drift.

Run from the repository root:  python scripts/sync_demo_fixtures.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COPIES = {
    ROOT / "gesturecontrol" / "rules.json": ROOT / "demo" / "src" / "gesture" / "rules.json",
    ROOT / "fixtures" / "golden_vectors.json": ROOT / "demo" / "test" / "golden_vectors.json",
}

if __name__ == "__main__":
    for source, target in COPIES.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        print(f"{source.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
