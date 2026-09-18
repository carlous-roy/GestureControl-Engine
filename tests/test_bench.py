from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from gesturecontrol import scenarios as sc
from gesturecontrol.app import RunOptions
from gesturecontrol.bench import MARKDOWN_HEADER, BenchOptions, bench, markdown_row
from gesturecontrol.filters import Point


class StaticSource:
    def __init__(self, frames: int) -> None:
        self.frames = frames
        self.reads = 0
        self.released = False

    def read(self) -> tuple[bool, Any]:
        if self.reads >= self.frames:
            return False, None
        self.reads += 1
        return True, np.zeros((240, 320, 3), dtype=np.uint8)

    def release(self) -> None:
        self.released = True


class StaticDetector:
    backend = "fake"

    def __init__(self, landmarks: list[Point] | None) -> None:
        self.landmarks = landmarks
        self.closed = False

    def process(self, frame: Any, timestamp_ms: int | None = None) -> list[Point] | None:
        return self.landmarks

    def draw(self, frame: Any, points_px: Any = None) -> Any:
        return frame

    def close(self) -> None:
        self.closed = True


def _ticking_clock(step: float = 0.01) -> Any:
    now = [100.0]

    def clock() -> float:
        now[0] += step
        return now[0]

    return clock


def test_bench_with_fakes_writes_csv_and_summary(tmp_path: Path) -> None:
    hand = sc.synthetic_hand(3, 60.0, 320, 240)
    source = StaticSource(100)
    detector = StaticDetector(list(hand.landmarks))
    out = io.StringIO()
    opts = BenchOptions(
        source="fake.avi", frames=20, warmup=5, csv_path=tmp_path / "b.csv", mirror=False
    )
    result = bench(
        opts,
        detector_factory=lambda _o: detector,
        source_factory=lambda _o: source,
        clock=_ticking_clock(0.01),
        out=out,
    )
    assert result.frames == 20
    assert source.reads == 25 and source.released and detector.closed
    assert result.hand_frames == 20
    # five clock ticks per frame at 10 ms each: 50 ms per frame; 20 frames over ~1 s
    assert result.stages["total"].median_ms == pytest.approx(40.0, abs=0.5)
    assert 15 < result.fps < 25
    with (tmp_path / "b.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 20
    assert rows[0]["frame"] == "0" and rows[-1]["confirmed_count"] == "3"
    sidecar = json.loads((tmp_path / "b.json").read_text())
    assert sidecar["frames"] == 20 and sidecar["context"]["backend"] == "fake"
    assert "README table row" in out.getvalue()
    assert markdown_row(result).count("|") == MARKDOWN_HEADER.splitlines()[0].count("|")


def test_bench_stops_when_the_source_ends(tmp_path: Path) -> None:
    source = StaticSource(8)
    result = bench(
        BenchOptions(source="short.avi", frames=50, warmup=2, mirror=False),
        detector_factory=lambda _o: StaticDetector(None),
        source_factory=lambda _o: source,
        clock=_ticking_clock(),
        out=io.StringIO(),
    )
    assert result.frames == 6


def test_bench_rejects_zero_frames() -> None:
    with pytest.raises(ValueError, match="frames"):
        bench(BenchOptions(frames=0), out=io.StringIO())


def test_bench_on_a_video_file_with_real_mediapipe(tmp_path: Path) -> None:
    cv2 = pytest.importorskip("cv2")
    pytest.importorskip("mediapipe")
    from gesturecontrol.detector import HandDetector, solutions_api_available
    from gesturecontrol.model import ModelError

    video = tmp_path / "blank.avi"
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 30.0, (320, 240))
    assert writer.isOpened()
    for i in range(20):
        frame = np.full((240, 320, 3), 80 + i, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    def detector_factory(o: RunOptions) -> HandDetector:
        try:
            if solutions_api_available():
                return HandDetector(backend="solutions", detect_every_frame=o.detect_every_frame)
            return HandDetector(backend="tasks", detect_every_frame=o.detect_every_frame)
        except ModelError as e:
            pytest.skip(f"model bundle not available: {e}")

    out = io.StringIO()
    result = bench(
        BenchOptions(source=str(video), frames=10, warmup=3, csv_path=tmp_path / "bench.csv"),
        detector_factory=detector_factory,
        out=out,
    )
    assert result.frames == 10
    assert result.context["actual_size"] == "320x240"
    assert result.stages["inference"].median_ms > 0
    assert (tmp_path / "bench.csv").exists()
