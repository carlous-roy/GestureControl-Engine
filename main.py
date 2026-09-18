"""Compatibility shim: `python main.py` behaves like the `gesturecontrol` command."""

import sys

from gesturecontrol.cli import main

if __name__ == "__main__":
    sys.exit(main())
