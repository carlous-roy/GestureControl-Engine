"""
Command-line entry point for the gesture automation system.
Captures webcam feed, detects hand landmarks via MediaPipe, classifies the
finger count and controls relays through Arduino/Firmata.

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

from gesturecontrol.config import (
    DEFAULT_CAMERA_INDEX,
    DEFAULT_DETECTION_CONFIDENCE,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_WIDTH,
    DEFAULT_TRACKING_CONFIDENCE,
)
from gesturecontrol.controller import RelayController
from gesturecontrol.detector import HandDetector
from gesturecontrol.overlay import draw_overlay
from gesturecontrol.pipeline import GesturePipeline

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gesture-Based Home Automation")
    parser.add_argument("--port", type=str, default=None, help="Arduino serial port")
    parser.add_argument("--camera", type=int, default=DEFAULT_CAMERA_INDEX, help="Camera index")
    parser.add_argument("--width", type=int, default=DEFAULT_FRAME_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_FRAME_HEIGHT)
    parser.add_argument("--no-ui", action="store_true", help="Disable overlay")
    parser.add_argument("--detection-confidence", type=float, default=DEFAULT_DETECTION_CONFIDENCE)
    parser.add_argument("--tracking-confidence", type=float, default=DEFAULT_TRACKING_CONFIDENCE)
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
    pipeline: GesturePipeline | None = None

    logger.info("Ready. Show 0-5 fingers. Press Q to exit.")

    prev_time = time.monotonic()
    frame_count = 0
    fps = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            if pipeline is None:
                pipeline = GesturePipeline(w, h)

            landmarks = detector.process(frame)
            result = pipeline.process(landmarks, time.monotonic())
            if result.changed:
                controller.set_from_finger_count(result.confirmed_count)
                logger.info(
                    "Gesture: %d finger(s) -> Relays: %s", result.confirmed_count, controller.states
                )
            # When the hand leaves the frame the relays hold; a fist turns them off.

            frame_count += 1
            now = time.monotonic()
            if now - prev_time >= 1.0:
                fps = frame_count / (now - prev_time)
                frame_count = 0
                prev_time = now

            if not args.no_ui:
                detector.draw(frame, result.points_px)
                draw_overlay(
                    frame,
                    hand_present=result.hand_present,
                    live_count=result.raw_count,
                    confirmed_count=result.confirmed_count,
                    relay_states=controller.states,
                    fps=fps,
                    hw_connected=controller.is_connected,
                )
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
        detector.close()
        cap.release()
        cv2.destroyAllWindows()
        controller.cleanup()
        logger.info("Done.")


if __name__ == "__main__":
    main()
