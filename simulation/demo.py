"""Hardware-free demo: replays scripted landmark sequences through the real
classifier, confirmation and relay logic. Same as `gesturecontrol simulate`."""

from __future__ import annotations

import sys

from gesturecontrol.cli import main

if __name__ == "__main__":
    sys.exit(main(["simulate", *sys.argv[1:]]))
