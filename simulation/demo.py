"""Text-based simulation demo. Cycles through gestures without webcam/Arduino."""

import time
import sys
import os
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.controller import RelayController

GESTURES = {
    0: "Fist", 1: "Index finger", 2: "V-sign",
    3: "Three fingers", 4: "Four fingers", 5: "Open palm",
}


def run_simulation():
    print("Gesture Automation — Simulation Mode")
    print("=" * 40)

    controller = RelayController()

    for cycle in range(1, 3):
        print(f"\nCycle {cycle}:")
        for fc in range(6):
            controller.set_from_finger_count(fc)
            states = controller.states
            on = " ".join(f"R{i+1}:{'ON' if s else 'OFF'}" for i, s in enumerate(states))
            print(f"  {fc} fingers ({GESTURES[fc]:15s}) | {on}")
            time.sleep(0.3)

    print("\nRapid switching:")
    for _ in range(8):
        fc = random.randint(0, 5)
        controller.set_from_finger_count(fc)
        print(f"  {fc} fingers -> {sum(controller.states)} relay(s) active")
        time.sleep(0.15)

    controller.cleanup()
    print("\nDone. Run 'python main.py' for live webcam mode.")


if __name__ == "__main__":
    run_simulation()
