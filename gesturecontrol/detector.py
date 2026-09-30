"""
Hand landmark detection with MediaPipe Hands.

MediaPipe Hands is a two-stage pipeline: a palm detector finds the hand
region, and a landmark model regresses 21 points inside that region. In
video (tracking) mode the palm detector runs only when there is no hand
being tracked from the previous frame; every frame runs the landmark model,
and the palm detector is invoked again when tracking is lost. Forcing the
detector on every frame (``detect_every_frame=True``) is available for
benchmarking the difference.

Two MediaPipe APIs are supported:

* the legacy Solutions API (``mediapipe.solutions.hands``, mediapipe
  < 0.10.30), whose models ship inside the wheel; ``static_image_mode``
  selects between tracking and detect-every-frame;
* the Tasks API (``mediapipe.tasks.python.vision.HandLandmarker``,
  any mediapipe >= 0.10.14), which needs the model bundle from
  ``gesturecontrol.model``; ``RunningMode.VIDEO`` is the tracking mode and
  ``RunningMode.IMAGE`` treats every frame as an unrelated still.

``process`` returns the 21 normalised (x, y) landmarks of the first
detected hand, or None. Classification happens elsewhere.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

import cv2

from gesturecontrol.config import DEFAULT_DETECTION_CONFIDENCE, DEFAULT_TRACKING_CONFIDENCE
from gesturecontrol.filters import Point
from gesturecontrol.model import ensure_model

logger = logging.getLogger(__name__)

Backend = Literal["auto", "solutions", "tasks"]

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]  # fmt: skip


def solutions_api_available() -> bool:
    """True when the installed mediapipe still ships the Solutions hands module."""
    try:
        import mediapipe as mp

        return hasattr(mp, "solutions") and hasattr(mp.solutions, "hands")
    except ImportError:
        return False


def mediapipe_version() -> str:
    """The installed mediapipe version, or a note that it is not installed."""
    try:
        import mediapipe as mp

        return str(getattr(mp, "__version__", "unknown"))
    except ImportError:
        return "not installed"


class HandDetector:
    """MediaPipe Hands on either API, returning normalised landmarks per frame.

    ``backend="auto"`` takes the Solutions API when the installed mediapipe
    has it and the Tasks API otherwise. The Tasks API needs the pinned model
    bundle, which ``gesturecontrol.model`` fetches and verifies at start-up.
    """

    def __init__(
        self,
        *,
        max_hands: int = 1,
        min_detection_confidence: float = DEFAULT_DETECTION_CONFIDENCE,
        min_tracking_confidence: float = DEFAULT_TRACKING_CONFIDENCE,
        detect_every_frame: bool = False,
        backend: Backend = "auto",
        model_path: Path | None = None,
        allow_download: bool = True,
    ) -> None:
        self._landmarks: list[Point] | None = None
        self._results: Any = None
        self._detect_every_frame = detect_every_frame
        self._last_timestamp_ms = -1
        self._task_landmarker: Any = None
        self.hands: Any = None

        if backend == "auto":
            backend = "solutions" if solutions_api_available() else "tasks"
        self._backend: Literal["solutions", "tasks"] = backend
        if backend == "solutions":
            self._init_solutions(max_hands, min_detection_confidence, min_tracking_confidence)
        else:
            self.model_path = ensure_model(model_path, allow_download=allow_download)
            self._init_tasks(max_hands, min_detection_confidence, min_tracking_confidence)
        logger.info(
            "MediaPipe %s, %s API, %s",
            mediapipe_version(),
            self._backend,
            "palm detection on every frame" if detect_every_frame else "tracking mode",
        )

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def detect_every_frame(self) -> bool:
        return self._detect_every_frame

    def _init_solutions(self, max_hands: int, det_conf: float, track_conf: float) -> None:
        import mediapipe as mp

        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.mp_styles = mp.solutions.drawing_styles
        self.hands = self.mp_hands.Hands(
            static_image_mode=self._detect_every_frame,
            max_num_hands=max_hands,
            min_detection_confidence=det_conf,
            min_tracking_confidence=track_conf,
        )

    def _init_tasks(self, max_hands: int, det_conf: float, track_conf: float) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        mode = vision.RunningMode.IMAGE if self._detect_every_frame else vision.RunningMode.VIDEO
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self.model_path)),
            num_hands=max_hands,
            min_hand_detection_confidence=det_conf,
            min_hand_presence_confidence=track_conf,
            min_tracking_confidence=track_conf,
            running_mode=mode,
        )
        self._task_landmarker = vision.HandLandmarker.create_from_options(options)

    def process(self, frame: Any, timestamp_ms: int | None = None) -> list[Point] | None:
        """Detect on a BGR frame; returns normalised landmarks of the first hand, or None.

        ``timestamp_ms`` must increase from frame to frame for the Tasks API
        video mode; when omitted, a counter is used.
        """
        if self._backend == "tasks":
            self._landmarks = self._process_tasks(frame, timestamp_ms)
        else:
            self._landmarks = self._process_solutions(frame)
        return self._landmarks

    @property
    def landmarks(self) -> list[Point] | None:
        return self._landmarks

    def _process_solutions(self, frame: Any) -> list[Point] | None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        self._results = self.hands.process(rgb)
        if self._results.multi_hand_landmarks:
            hand = self._results.multi_hand_landmarks[0]
            return [(float(lm.x), float(lm.y)) for lm in hand.landmark]
        return None

    def _process_tasks(self, frame: Any, timestamp_ms: int | None) -> list[Point] | None:
        import mediapipe as mp

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        if self._detect_every_frame:
            self._results = self._task_landmarker.detect(mp_image)
        else:
            ts = self._last_timestamp_ms + 1 if timestamp_ms is None else timestamp_ms
            if ts <= self._last_timestamp_ms:
                ts = self._last_timestamp_ms + 1
            self._last_timestamp_ms = ts
            self._results = self._task_landmarker.detect_for_video(mp_image, ts)
        if self._results.hand_landmarks:
            hand = self._results.hand_landmarks[0]
            return [(float(lm.x), float(lm.y)) for lm in hand]
        return None

    def draw(self, frame: Any, points_px: Any = None) -> Any:
        """Draw the hand skeleton; ``points_px`` (filtered pixel points) wins if given."""
        if points_px is not None:
            return self._draw_points(frame, points_px)
        if self._backend == "solutions":
            return self._draw_solutions(frame)
        if self._landmarks is not None:
            h, w = frame.shape[:2]
            return self._draw_points(frame, [(x * w, y * h) for x, y in self._landmarks])
        return frame

    def _draw_solutions(self, frame: Any) -> Any:
        if self._results and self._results.multi_hand_landmarks:
            for hand_lm in self._results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    frame,
                    hand_lm,
                    self.mp_hands.HAND_CONNECTIONS,
                    self.mp_styles.get_default_hand_landmarks_style(),
                    self.mp_styles.get_default_hand_connections_style(),
                )
        return frame

    @staticmethod
    def _draw_points(frame: Any, points_px: Any) -> Any:
        pts = [(round(x), round(y)) for x, y in points_px]
        for start, end in HAND_CONNECTIONS:
            cv2.line(frame, pts[start], pts[end], (0, 255, 0), 2)
        for p in pts:
            cv2.circle(frame, p, 4, (0, 0, 255), cv2.FILLED)
        return frame

    def close(self) -> None:
        """Release the MediaPipe graph; the detector cannot be used afterwards."""
        if self._task_landmarker is not None:
            self._task_landmarker.close()
            self._task_landmarker = None
        if self.hands is not None:
            self.hands.close()
            self.hands = None
