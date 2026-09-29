"""Detector tests that run real MediaPipe inference on synthetic frames.

They exercise whichever backend the installed mediapipe provides. The Tasks
backend needs the pinned model bundle; set GESTURECONTROL_MODEL to a local
copy or let the test download it once into the per-user cache.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from gesturecontrol.detector import HandDetector, solutions_api_available
from gesturecontrol.model import ModelError
from tests.native import require_backend

mediapipe = pytest.importorskip("mediapipe")


def _blank_frame() -> npt.NDArray[np.uint8]:
    frame = np.full((480, 640, 3), 90, dtype=np.uint8)
    frame[100:380, 200:440] = (60, 120, 200)  # a coloured block, not a hand
    return frame


@pytest.mark.skipif(not solutions_api_available(), reason="legacy Solutions API not installed")
@pytest.mark.parametrize("every_frame", [False, True])
def test_solutions_backend_runs_and_reports_no_hand(every_frame: bool) -> None:
    require_backend("solutions")
    det = HandDetector(backend="solutions", detect_every_frame=every_frame)
    try:
        assert det.backend == "solutions"
        for _ in range(3):
            assert det.process(_blank_frame()) is None
        out = det.draw(_blank_frame())
        assert out.shape == (480, 640, 3)
    finally:
        det.close()


def _tasks_available() -> bool:
    try:
        from mediapipe.tasks.python import vision  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not _tasks_available(), reason="MediaPipe Tasks API not installed")
@pytest.mark.parametrize("every_frame", [False, True])
def test_tasks_backend_runs_in_video_or_image_mode(every_frame: bool) -> None:
    require_backend("tasks")
    det = HandDetector(backend="tasks", detect_every_frame=every_frame)
    try:
        assert det.backend == "tasks"
        for i in range(3):
            assert det.process(_blank_frame(), timestamp_ms=i * 33) is None
        # timestamps must increase; a repeated one is bumped rather than rejected
        assert det.process(_blank_frame(), timestamp_ms=66) is None
        assert det.process(_blank_frame()) is None
    finally:
        det.close()


def test_missing_model_fails_loudly(tmp_path: Path) -> None:
    if not _tasks_available():
        pytest.skip("MediaPipe Tasks API not installed")
    missing = tmp_path / "no-model.task"
    with pytest.raises(ModelError, match=r"no-model\.task"):
        HandDetector(backend="tasks", model_path=missing, allow_download=False)
