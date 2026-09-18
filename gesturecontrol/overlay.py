"""
Status overlay drawn on the camera feed: hand presence, live and confirmed
counts, relay indicators, FPS and connection status.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import cv2

GREEN = (0, 200, 0)
RED = (0, 0, 255)
ORANGE = (0, 165, 255)
WHITE = (255, 255, 255)
GRAY = (80, 80, 80)
DARK_BG = (30, 30, 30)
YELLOW = (0, 255, 255)
FONT = cv2.FONT_HERSHEY_SIMPLEX

GESTURE_LABELS = {
    -1: "No gesture yet",
    0: "ALL OFF",
    1: "Appliance 1 ON",
    2: "Appliance 2 ON",
    3: "Appliance 3 ON",
    4: "Appliance 4 ON",
    5: "ALL ON",
}


def draw_overlay(
    frame: Any,
    *,
    hand_present: bool,
    live_count: int,
    confirmed_count: int,
    relay_states: Sequence[bool],
    fps: float,
    hw_connected: bool,
) -> Any:
    """Draw the status overlay in place and return the frame.

    ``live_count`` is the count for this frame (-1 without a usable hand);
    ``confirmed_count`` is what drives the relays and is shown even when the
    hand has left the frame, because the relays keep that state.
    """
    h, w, _ = frame.shape

    cv2.putText(frame, "Gesture Automation System", (10, 30), FONT, 0.65, WHITE, 2)
    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 130, 30), FONT, 0.55, YELLOW, 2)

    # Status indicators (bottom-left)
    y = h - 55
    cv2.circle(frame, (20, y), 5, GREEN if hand_present else RED, cv2.FILLED)
    hand_text = f"Hand: {'Detected' if hand_present else 'None'}"
    cv2.putText(frame, hand_text, (32, y + 4), FONT, 0.4, WHITE, 1)

    hw_color = GREEN if hw_connected else ORANGE
    cv2.circle(frame, (20, y + 22), 5, hw_color, cv2.FILLED)
    hw_text = "Arduino: Connected" if hw_connected else "Mode: Simulation"
    cv2.putText(frame, hw_text, (32, y + 26), FONT, 0.4, WHITE, 1)

    # Relay LEDs (right side)
    rx = w - 45
    cv2.putText(frame, "Relays", (rx - 18, 65), FONT, 0.35, WHITE, 1)
    for i in range(4):
        cy = 90 + i * 38
        is_on = relay_states[i] if i < len(relay_states) else False
        cv2.circle(frame, (rx, cy), 14, WHITE, 1)
        cv2.circle(frame, (rx, cy), 12, GREEN if is_on else GRAY, cv2.FILLED)
        cv2.putText(frame, f"R{i + 1}", (rx - 8, cy + 4), FONT, 0.32, WHITE, 1)
        state_color = GREEN if is_on else GRAY
        cv2.putText(frame, "ON" if is_on else "OFF", (rx - 12, cy + 26), FONT, 0.28, state_color, 1)

    # Count box (bottom-centre): live count large, confirmed gesture as the label
    label = GESTURE_LABELS.get(confirmed_count, "Unknown")
    count_str = str(live_count) if live_count >= 0 else "-"

    box_w, box_h = 250, 65
    box_x = (w - box_w) // 2
    box_y = h - box_h - 10

    overlay = frame.copy()
    cv2.rectangle(overlay, (box_x, box_y), (box_x + box_w, box_y + box_h), DARK_BG, cv2.FILLED)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    box_color = GREEN if hand_present else RED
    cv2.rectangle(frame, (box_x, box_y), (box_x + box_w, box_y + box_h), box_color, 2)
    cv2.putText(frame, count_str, (box_x + 15, box_y + 45), FONT, 1.5, GREEN, 3)
    cv2.putText(frame, label, (box_x + 60, box_y + 42), FONT, 0.6, WHITE, 2)

    return frame
