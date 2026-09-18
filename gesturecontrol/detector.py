"""
Hand landmark detection with MediaPipe Hands.

Two MediaPipe APIs are supported and chosen at import time:

* the legacy Solutions API (``mediapipe.solutions.hands``, mediapipe
  < 0.10.30), whose model files ship inside the wheel;
* the Tasks API (``mediapipe.tasks.python.vision.HandLandmarker``), which
  needs a model bundle downloaded on first use.

Either way ``process`` returns the 21 normalised (x, y) landmarks of the
first detected hand, or None. Classification happens elsewhere.
"""

from __future__ import annotations

import logging
import os
import tempfile
import urllib.request
from typing import Any

import cv2

from gesturecontrol.config import (
    DEFAULT_DETECTION_CONFIDENCE,
    DEFAULT_TRACKING_CONFIDENCE,
)
from gesturecontrol.filters import Point

logger = logging.getLogger(__name__)

_USE_TASKS_API = False
try:
    import mediapipe as mp

    _ = mp.solutions.hands
except AttributeError:
    _USE_TASKS_API = True

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16),
    (0, 17), (17, 18), (18, 19), (19, 20),
    (5, 9), (9, 13), (13, 17),
]  # fmt: skip


class HandDetector:
    def __init__(
        self,
        max_hands: int = 1,
        min_detection_confidence: float = DEFAULT_DETECTION_CONFIDENCE,
        min_tracking_confidence: float = DEFAULT_TRACKING_CONFIDENCE,
    ) -> None:
        self._landmarks: list[Point] | None = None
        self._results: Any = None
        self._use_tasks = _USE_TASKS_API
        self._task_landmarker: Any = None

        if self._use_tasks:
            self._init_tasks_api(max_hands, min_detection_confidence, min_tracking_confidence)
        else:
            self._init_solutions_api(max_hands, min_detection_confidence, min_tracking_confidence)

    @property
    def backend(self) -> str:
        return "tasks" if self._use_tasks else "solutions"

    def _init_solutions_api(self, max_hands: int, det_conf: float, track_conf: float) -> None:
        import mediapipe as mp

        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.mp_styles = mp.solutions.drawing_styles
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=det_conf,
            min_tracking_confidence=track_conf,
        )

    def _init_tasks_api(self, max_hands: int, det_conf: float, track_conf: float) -> None:
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        self._model_path = os.path.join(tempfile.gettempdir(), "hand_landmarker.task")

        if not os.path.exists(self._model_path):
            logger.info("Downloading hand landmark model...")
            try:
                urllib.request.urlretrieve(
                    "https://storage.googleapis.com/mediapipe-models/"
                    "hand_landmarker/hand_landmarker/float16/latest/"
                    "hand_landmarker.task",
                    self._model_path,
                )
            except OSError as e:
                logger.warning("Could not download model: %s", e)
                return

        base_options = mp_python.BaseOptions(model_asset_path=self._model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=max_hands,
            min_hand_detection_confidence=det_conf,
            min_hand_presence_confidence=track_conf,
            min_tracking_confidence=track_conf,
            running_mode=vision.RunningMode.IMAGE,
        )
        self._task_landmarker = vision.HandLandmarker.create_from_options(options)

    def process(self, frame: Any) -> list[Point] | None:
        """Detect on a BGR frame; returns normalised landmarks of the first hand, or None."""
        self._landmarks = None
        if self._use_tasks:
            self._landmarks = self._process_tasks(frame)
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

    def _process_tasks(self, frame: Any) -> list[Point] | None:
        if not self._task_landmarker:
            return None
        import mediapipe as mp

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._results = self._task_landmarker.detect(mp_image)
        if self._results.hand_landmarks:
            hand = self._results.hand_landmarks[0]
            return [(float(lm.x), float(lm.y)) for lm in hand]
        return None

    def draw(self, frame: Any, points_px: Any = None) -> Any:
        """Draw the hand skeleton; ``points_px`` (filtered pixel points) wins if given."""
        if points_px is not None:
            return self._draw_points(frame, points_px)
        if not self._use_tasks:
            return self._draw_solutions(frame)
        if self._landmarks is not None:
            h, w, _ = frame.shape
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
        if self._use_tasks:
            if self._task_landmarker:
                self._task_landmarker.close()
        else:
            self.hands.close()
