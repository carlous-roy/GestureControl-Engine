"""Guard for tests that build a real MediaPipe detector.

MediaPipe's graph builder aborts the interpreter instead of raising on some
platform and version combinations (the 1.0.1 wheel on macOS, for one).
Constructed in-process, such a detector ends the whole pytest run with a bare
"Abort trap" and no test name. So the first test that needs a backend builds
one in a child process; an abort there becomes an ordinary failure that names
the backend and shows the message MediaPipe printed on the way down.
"""

from __future__ import annotations

import functools
import subprocess
import sys

import pytest

MODEL_MISSING_EXIT = 3
_PROBE = """\
import sys
import numpy as np
from gesturecontrol.detector import HandDetector
from gesturecontrol.model import ModelError
try:
    detector = HandDetector(backend={backend!r})
except ModelError as e:
    print(e, file=sys.stderr)
    sys.exit({model_missing_exit})
detector.process(np.zeros((240, 320, 3), dtype=np.uint8))
detector.close()
"""


@functools.cache
def _probe(backend: str) -> tuple[int, str]:
    code = _PROBE.format(backend=backend, model_missing_exit=MODEL_MISSING_EXIT)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=600,  # includes the one-time model download for the Tasks API
        check=False,
    )
    return proc.returncode, proc.stderr


def require_backend(backend: str) -> None:
    """Fail or skip the calling test unless ``backend`` builds and runs a detector."""
    code, stderr = _probe(backend)
    if code == 0:
        return
    tail = "\n".join(stderr.strip().splitlines()[-12:])
    if code == MODEL_MISSING_EXIT:
        pytest.skip(f"model bundle not available: {tail}")
    from gesturecontrol.detector import mediapipe_version

    pytest.fail(
        f"mediapipe {mediapipe_version()} could not build a {backend!r} detector on this "
        f"machine (child process exit code {code}):\n{tail}",
        pytrace=False,
    )
