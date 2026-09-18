"""
Command-line entry point for the gesture automation system.
Captures webcam feed, detects fingers via MediaPipe, and controls
relays through Arduino/Firmata.

Usage:
  gesturecontrol                     # simulation mode
  gesturecontrol --port COM6         # with Arduino
  gesturecontrol --port /dev/ttyACM0 # Linux
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import cv2

from gesturecontrol.controller import RelayController
from gesturecontrol.hand_detector import HandDetector
from gesturecontrol.ui_overlay import draw_overlay

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gesture-Based Home Automation")
    parser.add_argument("--port", type=str, default=None, help="Arduino serial port")
    parser.add_argument("--camera", type=int, default=0, help="Camera index")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--no-ui", action="store_true", help="Disable overlay")
    parser.add_argument("--detection-confidence", type=float, default=0.7)
    parser.add_argument("--tracking-confidence", type=float, default=0.6)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args(argv)

    controller = RelayController()
    if args.port:
        logger.info("Connecting to Arduino on %s...", args.port)
        if not controller.connect(args.port):
            logger.warning("Failed to connect. Continuing in simulation mode.")
    else:
        logger.info("No --port specified. Running in SIMULATION mode.")

    logger.info("Opening camera %d...", args.camera)
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    if not cap.isOpened():
        logger.error("Could not open camera. Check --camera index or permissions.")
        sys.exit(1)

    detector = HandDetector(
        min_detection_confidence=args.detection_confidence,
        min_tracking_confidence=args.tracking_confidence,
    )

    logger.info("Ready. Show 0-5 fingers. Press Q to exit.")

    prev_time = time.time()
    frame_count = 0
    fps = 0.0
    confirmed_count = -1
    stable_count = -1
    stable_frames = 0
    stable_threshold = 3

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)

            hand_detected = detector.process(frame)
            finger_count = detector.count_fingers()
            detector.draw(frame)

            # Stabilization: only switch relays after seeing the same
            # count for stable_threshold consecutive frames
            if finger_count >= 0:
                if finger_count == stable_count:
                    stable_frames += 1
                else:
                    stable_count = finger_count
                    stable_frames = 1

                if stable_frames >= stable_threshold and stable_count != confirmed_count:
                    confirmed_count = stable_count
                    controller.set_from_finger_count(confirmed_count)
                    logger.info(
                        "Gesture: %d finger(s) -> Relays: %s", confirmed_count, controller.states
                    )

            # When hand leaves: relays hold. Show fist to turn off.

            frame_count += 1
            now = time.time()
            if now - prev_time >= 1.0:
                fps = frame_count / (now - prev_time)
                frame_count = 0
                prev_time = now

            display_count = confirmed_count if not hand_detected else finger_count
            if not args.no_ui:
                draw_overlay(frame, display_count, controller.states, fps, controller.is_connected)
                h, _w, _ = frame.shape
                cv2.putText(
                    frame,
                    "Press Q to exit",
                    (10, h - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    (150, 150, 150),
                    1,
                )

            cv2.imshow("Gesture Automation", frame)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                break
            if key == ord("s"):
                os.makedirs("screenshots", exist_ok=True)
                fname = f"screenshots/gesture_{int(time.time())}.png"
                cv2.imwrite(fname, frame)
                logger.info("Screenshot saved: %s", fname)

    except KeyboardInterrupt:
        logger.info("Interrupted.")
    finally:
        detector.release()
        cap.release()
        cv2.destroyAllWindows()
        controller.cleanup()
        logger.info("Done.")


if __name__ == "__main__":
    main()
