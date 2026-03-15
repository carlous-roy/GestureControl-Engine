"""
Hand detection and finger counting using MediaPipe Hands.
Supports both the legacy solutions API and newer Tasks API.
"""

import cv2
import math
import numpy as np
from typing import List, Optional
import logging

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
]


def _distance(p1, p2):
    return math.sqrt((p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2)


class HandDetector:
    TIP_IDS = [4, 8, 12, 16, 20]

    def __init__(self, max_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.6):
        self._landmarks = []
        self._results = None
        self._use_tasks = _USE_TASKS_API

        if self._use_tasks:
            self._init_tasks_api(max_hands, min_detection_confidence, min_tracking_confidence)
        else:
            self._init_solutions_api(max_hands, min_detection_confidence, min_tracking_confidence)

    def _init_solutions_api(self, max_hands, det_conf, track_conf):
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

    def _init_tasks_api(self, max_hands, det_conf, track_conf):
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision
        import os, tempfile

        self._model_path = os.path.join(tempfile.gettempdir(), "hand_landmarker.task")
        self._task_landmarker = None

        if not os.path.exists(self._model_path):
            logger.info("Downloading hand landmark model...")
            try:
                import urllib.request
                urllib.request.urlretrieve(
                    "https://storage.googleapis.com/mediapipe-models/"
                    "hand_landmarker/hand_landmarker/float16/latest/"
                    "hand_landmarker.task",
                    self._model_path,
                )
            except Exception as e:
                logger.warning(f"Could not download model: {e}")
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

    def process(self, frame):
        """Process a BGR frame. Returns True if a hand was found."""
        self._landmarks = []
        if self._use_tasks:
            return self._process_tasks(frame)
        return self._process_solutions(frame)

    def _process_solutions(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        self._results = self.hands.process(rgb)
        if self._results.multi_hand_landmarks:
            hand = self._results.multi_hand_landmarks[0]
            h, w, _ = frame.shape
            for idx, lm in enumerate(hand.landmark):
                self._landmarks.append([idx, int(lm.x * w), int(lm.y * h)])
            return True
        return False

    def _process_tasks(self, frame):
        if not self._task_landmarker:
            return False
        import mediapipe as mp
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        self._results = self._task_landmarker.detect(mp_image)
        if self._results.hand_landmarks:
            hand = self._results.hand_landmarks[0]
            h, w, _ = frame.shape
            for idx, lm in enumerate(hand):
                self._landmarks.append([idx, int(lm.x * w), int(lm.y * h)])
            return True
        return False

    def _is_thumb_up(self):
        """
        Thumb detection using palm-width ratio.
        Measures thumb tip to index base distance vs palm width.
        When tucked (4 fingers), ratio is ~30-40%. When out (5 fingers), ~60-80%.
        """
        if len(self._landmarks) < 21:
            return False

        thumb_tip = self._landmarks[4]
        index_mcp = self._landmarks[5]
        pinky_mcp = self._landmarks[17]

        palm_width = _distance(index_mcp, pinky_mcp)
        if palm_width < 1:
            return False

        thumb_to_index = _distance(thumb_tip, index_mcp)
        return thumb_to_index > palm_width * 0.6

    def count_fingers(self):
        """Count raised fingers (0-5), or -1 if no hand detected."""
        if not self._landmarks or len(self._landmarks) < 21:
            return -1

        fingers = [1 if self._is_thumb_up() else 0]

        # Index, middle, ring, pinky: tip must be above PIP by 15px minimum
        for i in range(1, 5):
            tip_y = self._landmarks[self.TIP_IDS[i]][2]
            pip_y = self._landmarks[self.TIP_IDS[i] - 2][2]
            fingers.append(1 if (pip_y - tip_y) > 15 else 0)

        return sum(fingers)

    def get_landmarks(self):
        return self._landmarks.copy()

    def draw(self, frame):
        """Draw hand landmarks on the frame."""
        if self._use_tasks:
            return self._draw_manual(frame)
        return self._draw_solutions(frame)

    def _draw_solutions(self, frame):
        if self._results and self._results.multi_hand_landmarks:
            for hand_lm in self._results.multi_hand_landmarks:
                self.mp_draw.draw_landmarks(
                    frame, hand_lm, self.mp_hands.HAND_CONNECTIONS,
                    self.mp_styles.get_default_hand_landmarks_style(),
                    self.mp_styles.get_default_hand_connections_style(),
                )
        return frame

    def _draw_manual(self, frame):
        if not self._landmarks:
            return frame
        for start, end in HAND_CONNECTIONS:
            if start < len(self._landmarks) and end < len(self._landmarks):
                pt1 = (self._landmarks[start][1], self._landmarks[start][2])
                pt2 = (self._landmarks[end][1], self._landmarks[end][2])
                cv2.line(frame, pt1, pt2, (0, 255, 0), 2)
        for lm in self._landmarks:
            cv2.circle(frame, (lm[1], lm[2]), 4, (0, 0, 255), cv2.FILLED)
        return frame

    def release(self):
        if self._use_tasks:
            if hasattr(self, '_task_landmarker') and self._task_landmarker:
                self._task_landmarker.close()
        else:
            self.hands.close()
