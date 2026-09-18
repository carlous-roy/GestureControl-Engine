from __future__ import annotations

from pathlib import Path

import pytest

from gesturecontrol import __version__
from gesturecontrol.cli import _with_default_command, build_parser, main


def test_run_is_the_default_command() -> None:
    assert _with_default_command([]) == ["run"]
    assert _with_default_command(["--port", "COM3"]) == ["run", "--port", "COM3"]
    assert _with_default_command(["simulate", "--list"]) == ["simulate", "--list"]
    assert _with_default_command(["--help"]) == ["--help"]


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_run_parser_defaults_and_camera_source() -> None:
    args = build_parser().parse_args(["run"])
    assert args.camera == 0 and args.width == 640 and args.height == 480
    assert args.active_high is False and args.min_switch_interval == 0.5
    assert args.backend == "auto" and args.detect_every_frame is False
    args = build_parser().parse_args(["run", "--camera", "clip.avi", "--active-high"])
    assert args.camera == "clip.avi" and args.active_high is True


def test_simulate_list_and_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["simulate", "--list"]) == 0
    assert "hold_on_loss" in capsys.readouterr().out
    assert main(["simulate", "hold_on_loss", "--min-switch-interval", "0"]) == 0
    assert "1 of 1 scenarios passed" in capsys.readouterr().out
    assert main(["simulate", "no_such_scenario"]) == 2


def test_run_with_bad_port_fails_fast() -> None:
    assert main(["--port", "/dev/does-not-exist-gesturecontrol", "--no-ui"]) == 2


def test_run_with_missing_video_fails_at_setup(tmp_path: Path) -> None:
    assert main(["--camera", str(tmp_path / "missing.avi"), "--no-ui"]) == 2


def test_bench_with_missing_video_reports_setup_error(tmp_path: Path) -> None:
    code = main(
        ["bench", "--camera", str(tmp_path / "missing.avi"), "--csv", str(tmp_path / "b.csv")]
    )
    assert code == 2
    assert not (tmp_path / "b.csv").exists()
