"""
All tunable constants in one place.

The classifier constants are read from ``rules.json``, which is also the
file the browser demo loads, so the two implementations cannot drift apart.
Hardware and pipeline defaults that only apply to the Python engine live
below as plain module constants.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

RULES_RESOURCE = "rules.json"


@dataclass(frozen=True)
class FilterConfig:
    """One Euro filter parameters (Casiez, Roussel and Vogel, CHI 2012).

    The filter runs on normalised landmark coordinates (0..1), so ``beta``
    is expressed per normalised unit per second and does not depend on the
    camera resolution.
    """

    min_cutoff_hz: float
    beta: float
    derivative_cutoff_hz: float


@dataclass(frozen=True)
class Hysteresis:
    """A latched threshold: a finger raises above one value and lowers below another."""

    raise_threshold: float
    lower_threshold: float

    def __post_init__(self) -> None:
        if self.lower_threshold >= self.raise_threshold:
            raise ValueError("lower_threshold must be below raise_threshold")


@dataclass(frozen=True)
class RulesConfig:
    """Classifier constants shared with the browser demo."""

    filter: FilterConfig
    finger: Hysteresis
    thumb: Hysteresis
    min_palm_width_px: float
    confirm_frames: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RulesConfig:
        return cls(
            filter=FilterConfig(**data["filter"]),
            finger=Hysteresis(**data["finger"]),
            thumb=Hysteresis(**data["thumb"]),
            min_palm_width_px=float(data["min_palm_width_px"]),
            confirm_frames=int(data["confirm_frames"]),
        )

    @classmethod
    def load(cls, path: Path | None = None) -> RulesConfig:
        """Load the packaged rules.json, or a specific file."""
        if path is None:
            text = resources.files(__package__).joinpath(RULES_RESOURCE).read_text("utf-8")
        else:
            text = Path(path).read_text("utf-8")
        data = json.loads(text)
        if data.get("version") != 1:
            raise ValueError(f"unsupported rules file version: {data.get('version')!r}")
        return cls.from_dict(data)


DEFAULT_RULES = RulesConfig.load()

# Relay hardware -----------------------------------------------------------

#: Arduino digital pins wired to IN1..IN4 of the relay module, in relay order.
RELAY_PINS: tuple[int, int, int, int] = (7, 6, 5, 4)

#: The common 5 V four-channel opto-isolated relay modules are low-level
#: trigger: the IN pin sits at VCC through the optocoupler LED and the relay
#: energises when the pin is driven LOW. That is the default here; pass
#: active_low=False (``--active-high``) for boards that switch on HIGH.
#: See docs/HARDWARE.md for how to check which kind you have.
RELAY_ACTIVE_LOW_DEFAULT = True

#: A relay is not switched again within this many seconds of its last change.
MIN_SWITCH_INTERVAL_S = 0.5

#: Host-side heartbeat period and the firmware watchdog timeout it must beat.
HEARTBEAT_INTERVAL_S = 0.25
HEARTBEAT_TIMEOUT_MS = 1000

#: Firmata SysEx command ids (0x00-0x0F are reserved for user commands).
SYSEX_HEARTBEAT = 0x01
SYSEX_WATCHDOG_CONFIG = 0x02

# Vision -------------------------------------------------------------------

DEFAULT_CAMERA_INDEX = 0
DEFAULT_FRAME_WIDTH = 640
DEFAULT_FRAME_HEIGHT = 480
DEFAULT_DETECTION_CONFIDENCE = 0.7
DEFAULT_TRACKING_CONFIDENCE = 0.6

#: Hand landmarker bundle for the MediaPipe Tasks API, pinned to a fixed
#: release path (not "latest") and verified by checksum after download.
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
MODEL_SIZE_BYTES = 7_819_105
MODEL_FILENAME = "hand_landmarker.float16.v1.task"
