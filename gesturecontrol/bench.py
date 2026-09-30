"""
Per-stage latency and end-to-end frame rate measurement.

``gesturecontrol bench`` runs the same capture -> inference -> classify ->
actuate loop as ``run`` without a window, times each stage on every
frame, writes the per-frame numbers to CSV, and prints a summary with the
machine, versions and settings so the numbers can be quoted with their
context. It accepts a camera index or a video file, so it also runs where
no camera exists.

Stages:

* capture: reading the frame from the source, plus the mirror flip;
* inference: MediaPipe hand landmark detection;
* classify: One Euro filtering, finger rules and confirmation;
* actuate: relay controller update (serial writes when a board is attached).

End-to-end FPS is the number of measured frames divided by the wall-clock
time they took, after the warm-up frames. On a video file this is a
processing rate, not a camera rate.
"""

from __future__ import annotations

import csv
import json
import logging
import platform
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TextIO

from gesturecontrol import __version__
from gesturecontrol.app import Detector, RunOptions, _default_detector, _default_source, _mirror
from gesturecontrol.camera import FrameSource
from gesturecontrol.controller import HeartbeatThread, RelayController
from gesturecontrol.pipeline import GesturePipeline

logger = logging.getLogger(__name__)

STAGES = ("capture", "inference", "classify", "actuate", "total")
CSV_COLUMNS = (
    "frame",
    "t_ms",
    "capture_ms",
    "inference_ms",
    "classify_ms",
    "actuate_ms",
    "total_ms",
    "hand",
    "raw_count",
    "confirmed_count",
)


@dataclass(frozen=True)
class BenchOptions:
    """Settings for one measurement; the CLI builds them from its arguments."""

    source: int | str = 0
    frames: int = 300
    warmup: int = 10
    width: int = 640
    height: int = 480
    detect_every_frame: bool = False
    backend: str = "auto"
    model_path: Path | None = None
    csv_path: Path | None = None
    port: str | None = None
    active_low: bool = True
    mirror: bool = True
    label: str = ""
    """Free text for the summary, for example the camera model."""


@dataclass
class StageStats:
    """Summary of one stage's per-frame timings, in milliseconds."""

    median_ms: float
    p95_ms: float
    mean_ms: float
    max_ms: float


@dataclass
class BenchResult:
    """The measurement: frame counts, elapsed time, per-stage stats and context."""

    frames: int
    warmup: int
    elapsed_s: float
    fps: float
    hand_frames: int
    stages: dict[str, StageStats]
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    k = (len(ordered) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _stats(values: Sequence[float]) -> StageStats:
    if not values:
        return StageStats(0.0, 0.0, 0.0, 0.0)
    return StageStats(
        median_ms=statistics.median(values),
        p95_ms=_percentile(values, 0.95),
        mean_ms=statistics.fmean(values),
        max_ms=max(values),
    )


def environment() -> dict[str, str]:
    """Machine and library versions, for the summary and the JSON sidecar."""
    from gesturecontrol.detector import mediapipe_version

    try:
        import cv2

        opencv = str(cv2.__version__)
    except ImportError:
        opencv = "not installed"
    return {
        "gesturecontrol": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "mediapipe": mediapipe_version(),
        "opencv": opencv,
    }


@dataclass
class _Measured:
    rows: list[dict[str, Any]]
    elapsed_s: float
    actual_size: tuple[int, int] | None


class _Stopwatch:
    """Runs frames through every stage and reports their timings."""

    def __init__(
        self,
        opts: BenchOptions,
        source: FrameSource,
        detector: Detector,
        controller: RelayController,
        clock: Callable[[], float],
    ) -> None:
        self.opts = opts
        self.source = source
        self.detector = detector
        self.controller = controller
        self.clock = clock
        self.pipeline: GesturePipeline | None = None
        self.t_start = clock()
        self.size: tuple[int, int] | None = None

    def frame(self) -> tuple[dict[str, Any], float] | None:
        """Time one frame; returns (row, start time) or None when the source ends."""
        clock = self.clock
        t0 = clock()
        ok, frame = self.source.read()
        if not ok:
            return None
        if self.opts.mirror:
            frame = _mirror(frame)
        t1 = clock()
        h, w = frame.shape[:2]
        self.size = (w, h)
        if self.pipeline is None:
            self.pipeline = GesturePipeline(w, h)
        landmarks = self.detector.process(frame, int((t1 - self.t_start) * 1000))
        t2 = clock()
        result = self.pipeline.process(landmarks, t2)
        t3 = clock()
        if result.changed:
            self.controller.set_from_finger_count(result.confirmed_count)
        else:
            self.controller.apply()
        t4 = clock()
        row = {
            "frame": 0,
            "t_ms": (t0 - self.t_start) * 1000,
            "capture_ms": (t1 - t0) * 1000,
            "inference_ms": (t2 - t1) * 1000,
            "classify_ms": (t3 - t2) * 1000,
            "actuate_ms": (t4 - t3) * 1000,
            "total_ms": (t4 - t0) * 1000,
            "hand": int(result.hand_present),
            "raw_count": result.raw_count,
            "confirmed_count": result.confirmed_count,
        }
        return row, t0

    def measure(self) -> _Measured:
        rows: list[dict[str, Any]] = []
        window_start: float | None = None
        for index in range(self.opts.warmup + self.opts.frames):
            timed = self.frame()
            if timed is None:
                logger.warning("Frame source ended after %d frames", index)
                break
            row, t0 = timed
            if index < self.opts.warmup:
                continue
            if window_start is None:
                window_start = t0
            row["frame"] = index - self.opts.warmup
            rows.append(row)
        t_end = self.clock()
        elapsed = (t_end - window_start) if (rows and window_start is not None) else 0.0
        return _Measured(rows, elapsed, self.size)


def bench(
    opts: BenchOptions,
    *,
    detector_factory: Callable[[RunOptions], Detector] = _default_detector,
    source_factory: Callable[[RunOptions], FrameSource] = _default_source,
    clock: Callable[[], float] = time.perf_counter,
    out: TextIO | None = None,
) -> BenchResult:
    """Measure ``opts.frames`` frames after the warm-up, write the files and print the summary.

    Raises CameraError, HardwareError or ModelError when a source, board or
    model cannot be opened; the relays are released before the error leaves.
    """
    out = out or sys.stdout
    if opts.frames < 1:
        raise ValueError("frames must be at least 1")
    run_opts = RunOptions(
        port=opts.port,
        camera=opts.source,
        width=opts.width,
        height=opts.height,
        no_ui=True,
        active_low=opts.active_low,
        mirror=opts.mirror,
        detect_every_frame=opts.detect_every_frame,
        backend=opts.backend,
        model_path=opts.model_path,
    )
    controller = RelayController(active_low=opts.active_low)
    heartbeat: HeartbeatThread | None = None
    source: FrameSource | None = None
    detector: Detector | None = None
    try:
        if opts.port:
            controller.connect(opts.port)
            heartbeat = HeartbeatThread(controller)
            heartbeat.start()
        source = source_factory(run_opts)
        detector = detector_factory(run_opts)
        measured = _Stopwatch(opts, source, detector, controller, clock).measure()
        backend = getattr(detector, "backend", opts.backend)
    finally:
        if heartbeat is not None:
            heartbeat.stop()
        if detector is not None:
            detector.close()
        if source is not None:
            source.release()
        controller.cleanup()

    rows = measured.rows
    size = measured.actual_size
    result = BenchResult(
        frames=len(rows),
        warmup=opts.warmup,
        elapsed_s=measured.elapsed_s,
        fps=(len(rows) / measured.elapsed_s) if measured.elapsed_s > 0 else 0.0,
        hand_frames=sum(int(r["hand"]) for r in rows),
        stages={stage: _stats([float(r[f"{stage}_ms"]) for r in rows]) for stage in STAGES},
        context={
            **environment(),
            "source": str(opts.source),
            "source_type": "file" if isinstance(opts.source, str) else "camera",
            "requested_size": f"{opts.width}x{opts.height}",
            "actual_size": f"{size[0]}x{size[1]}" if size else "unknown",
            "backend": backend,
            "detect_every_frame": opts.detect_every_frame,
            "hardware": opts.port or "",
            "label": opts.label,
        },
    )
    if opts.csv_path is not None:
        write_csv(opts.csv_path, rows)
        opts.csv_path.with_suffix(".json").write_text(
            json.dumps(result.as_dict(), indent=2) + "\n", encoding="utf-8"
        )
    out.write(format_summary(result))
    return result


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    """Write the per-frame rows with the ``CSV_COLUMNS`` header, floats to 3 decimals."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {k: (f"{v:.3f}" if isinstance(v, float) else v) for k, v in row.items()}
            )


def format_summary(r: BenchResult) -> str:
    """The human-readable summary printed after a run, ending with the README row."""
    c = r.context
    lines = [
        "",
        f"gesturecontrol bench: {r.frames} frames measured after {r.warmup} warm-up frames",
        f"  machine:    {c.get('platform')} ({c.get('processor')}), Python {c.get('python')}",
        f"  versions:   mediapipe {c.get('mediapipe')}, OpenCV {c.get('opencv')}, "
        f"gesturecontrol {c.get('gesturecontrol')}",
        f"  source:     {c.get('source_type')} {c.get('source')} at {c.get('actual_size')} "
        f"(requested {c.get('requested_size')})" + (f", {c['label']}" if c.get("label") else ""),
        f"  detection:  {c.get('backend')} API, "
        + ("palm detection on every frame" if c.get("detect_every_frame") else "tracking mode")
        + f", hand seen in {r.hand_frames} of {r.frames} frames",
        "  relays:     "
        + (f"serial writes to {c['hardware']}" if c.get("hardware") else "simulated"),
        "",
        f"  {'stage':10s} {'median ms':>10s} {'p95 ms':>10s} {'mean ms':>10s} {'max ms':>10s}",
    ]
    for stage in STAGES:
        s = r.stages[stage]
        lines.append(
            f"  {stage:10s} {s.median_ms:10.2f} {s.p95_ms:10.2f} {s.mean_ms:10.2f} {s.max_ms:10.2f}"
        )
    lines.append("")
    lines.append(f"  end-to-end: {r.fps:.1f} FPS over {r.elapsed_s:.2f} s")
    lines.append("")
    lines.append("  README table row:")
    lines.append("  " + markdown_row(r))
    lines.append("")
    return "\n".join(lines)


def markdown_row(r: BenchResult) -> str:
    """One row for the README's frame-rate table, matching ``MARKDOWN_HEADER``."""
    c = r.context
    mode = "every frame" if c.get("detect_every_frame") else "tracking"
    cells = [
        c.get("label") or f"{c.get('platform')} ({c.get('processor')})",
        f"{c.get('source_type')} {c.get('source')}",
        str(c.get("actual_size")),
        f"{c.get('mediapipe')} ({c.get('backend')}, {mode})",
        str(r.frames),
        f"{r.stages['capture'].median_ms:.1f}",
        f"{r.stages['inference'].median_ms:.1f}",
        f"{r.stages['classify'].median_ms:.2f}",
        f"{r.stages['actuate'].median_ms:.2f}",
        f"{r.stages['total'].median_ms:.1f}",
        f"{r.fps:.1f}",
    ]
    return "| " + " | ".join(cells) + " |"


MARKDOWN_HEADER = (
    "| Machine | Source | Resolution | MediaPipe (API, mode) | Frames | Capture ms | "
    "Inference ms | Classify ms | Actuate ms | Total ms | End-to-end FPS |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|"
)
