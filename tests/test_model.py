from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gesturecontrol import model
from gesturecontrol.config import MODEL_FILENAME, MODEL_SHA256, MODEL_SIZE_BYTES, MODEL_URL


def _pin_to(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    monkeypatch.setattr(model, "MODEL_SHA256", hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(model, "MODEL_SIZE_BYTES", len(data))


def test_pinned_constants_look_right() -> None:
    assert len(MODEL_SHA256) == 64
    assert MODEL_SIZE_BYTES > 1_000_000
    assert "/float16/1/" in MODEL_URL and "latest" not in MODEL_URL


def test_verify_accepts_matching_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = b"model-bytes" * 100
    _pin_to(monkeypatch, data)
    path = tmp_path / "m.task"
    path.write_bytes(data)
    model.verify(path)
    assert model.ensure_model(path, allow_download=False) == path


def test_verify_rejects_wrong_size(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_to(monkeypatch, b"good")
    path = tmp_path / "m.task"
    path.write_bytes(b"partial-download")
    with pytest.raises(model.ModelError, match="bytes"):
        model.verify(path)


def test_verify_rejects_wrong_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_to(monkeypatch, b"good")
    path = tmp_path / "m.task"
    path.write_bytes(b"bad!")
    with pytest.raises(model.ModelError, match="SHA-256"):
        model.verify(path)


def test_missing_model_without_download_is_loud(tmp_path: Path) -> None:
    with pytest.raises(model.ModelError, match=MODEL_URL):
        model.ensure_model(tmp_path / "missing.task", allow_download=False)


def test_download_from_url_verifies_and_installs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = b"pretend-model" * 1000
    _pin_to(monkeypatch, data)
    source = tmp_path / "source.task"
    source.write_bytes(data)
    target = tmp_path / "cache" / "m.task"
    model.download(target, url=source.as_uri())
    assert target.read_bytes() == data
    assert not [p for p in target.parent.iterdir() if p != target], "no temp files left"


def test_download_of_corrupt_file_fails_and_leaves_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_to(monkeypatch, b"expected-content")
    source = tmp_path / "source.task"
    source.write_bytes(b"something-else!!")
    target = tmp_path / "cache" / "m.task"
    with pytest.raises(model.ModelError, match="SHA-256"):
        model.download(target, url=source.as_uri())
    assert not target.exists()
    assert not list(target.parent.iterdir())


def test_download_failure_names_the_url_and_path(tmp_path: Path) -> None:
    target = tmp_path / "m.task"
    with pytest.raises(model.ModelError, match="could not fetch"):
        model.download(target, url=(tmp_path / "nope.task").as_uri())
    assert not target.exists()


def test_env_override_and_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(model.ENV_MODEL_PATH, str(tmp_path / "x.task"))
    assert model.default_model_path() == tmp_path / "x.task"
    monkeypatch.delenv(model.ENV_MODEL_PATH)
    assert model.default_model_path().name == MODEL_FILENAME
    assert "gesturecontrol" in str(model.cache_dir())
