"""
The hand landmarker model bundle for the MediaPipe Tasks API.

The bundle is pinned to a fixed release path and a SHA-256 checksum
(``config.MODEL_URL`` and ``config.MODEL_SHA256``), cached once per user,
and verified every time it is loaded. A missing, corrupt or unreachable
model raises ``ModelError`` with the URL and the expected path, so a
broken install fails at start-up instead of running with no detections.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from gesturecontrol.config import MODEL_FILENAME, MODEL_SHA256, MODEL_SIZE_BYTES, MODEL_URL

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT_S = 60
ENV_MODEL_PATH = "GESTURECONTROL_MODEL"


class ModelError(RuntimeError):
    """The model bundle is missing, corrupt or could not be fetched."""


def cache_dir() -> Path:
    """Per-user cache directory following the platform convention."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "gesturecontrol" / "Cache"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "gesturecontrol"
    else:
        base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
        return Path(base) / "gesturecontrol"


def default_model_path() -> Path:
    override = os.environ.get(ENV_MODEL_PATH)
    if override:
        return Path(override)
    return cache_dir() / MODEL_FILENAME


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path) -> None:
    """Raise ModelError unless ``path`` holds exactly the pinned bundle."""
    if not path.is_file():
        raise ModelError(f"model file not found: {path}")
    size = path.stat().st_size
    if size != MODEL_SIZE_BYTES:
        raise ModelError(
            f"model file {path} has {size} bytes, expected {MODEL_SIZE_BYTES}; "
            "delete it and run again to download a fresh copy"
        )
    actual = sha256_of(path)
    if actual != MODEL_SHA256:
        raise ModelError(
            f"model file {path} has SHA-256 {actual}, expected {MODEL_SHA256}; "
            "delete it and run again to download a fresh copy"
        )


def download(path: Path, url: str = MODEL_URL) -> None:
    """Fetch the bundle to a temporary file, verify it, then move it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading the hand landmarker model from %s", url)
    fd, tmp_name = tempfile.mkstemp(prefix=MODEL_FILENAME + ".", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with (
            os.fdopen(fd, "wb") as out,
            urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_S) as r,
        ):
            for chunk in iter(lambda: r.read(1 << 16), b""):
                out.write(chunk)
        verify(tmp)
        os.replace(tmp, path)
    except (urllib.error.URLError, OSError, ModelError) as e:
        tmp.unlink(missing_ok=True)
        raise ModelError(
            f"could not fetch the hand landmarker model: {e}. Download {url} yourself, "
            f"check that its SHA-256 is {MODEL_SHA256}, and place it at {path} "
            f"(or point {ENV_MODEL_PATH} / --model at it)."
        ) from e
    logger.info("Model stored at %s", path)


def ensure_model(path: Path | None = None, *, allow_download: bool = True) -> Path:
    """Return the path of a verified model bundle, downloading it if allowed."""
    target = path or default_model_path()
    if target.exists():
        verify(target)
        return target
    if not allow_download:
        raise ModelError(
            f"model file not found: {target}. Download {MODEL_URL} (SHA-256 {MODEL_SHA256}) "
            f"and place it there, or point {ENV_MODEL_PATH} / --model at it."
        )
    download(target)
    return target
