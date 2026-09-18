"""Compatibility shim: `python main.py` behaves like the `gesturecontrol` command."""

from gesturecontrol.cli import main

if __name__ == "__main__":
    main()
