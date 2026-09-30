"""Frame sources: a camera index or a video file, behind one small interface."""

from __future__ import annotations

from typing import Any, Protocol

import cv2


class CameraError(RuntimeError):
    """The frame source could not be opened or stopped delivering frames."""


class FrameSource(Protocol):
    def read(self) -> tuple[bool, Any]: ...

    def release(self) -> None: ...


class OpenCVSource:
    """cv2.VideoCapture with the requested size applied for live cameras."""

    def __init__(self, capture: Any, width: int, height: int, is_file: bool) -> None:
        self._capture = capture
        self.width = width
        self.height = height
        self.is_file = is_file

    def read(self) -> tuple[bool, Any]:
        ok, frame = self._capture.read()
        return bool(ok), frame

    def release(self) -> None:
        self._capture.release()


def parse_source(text: str) -> int | str:
    """A bare integer is a camera index; anything else is a file path or URL."""
    try:
        return int(text)
    except ValueError:
        return text


def open_source(source: int | str, width: int, height: int) -> OpenCVSource:
    """Open a camera or a video file, or raise CameraError naming the source."""
    is_file = isinstance(source, str)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        capture.release()
        if is_file:
            raise CameraError(f"could not open video file {source!r}")
        raise CameraError(
            f"could not open camera {source}; check the --camera index and camera permissions"
        )
    if not is_file:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    actual_w = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or width
    actual_h = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or height
    return OpenCVSource(capture, actual_w, actual_h, is_file)
