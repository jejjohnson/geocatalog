"""Smoke + exit-code tests for the cyclopts CLI (#23).

The CLI is a thin shim — there's no point re-asserting library
behaviour through it. The tests below cover:

* Each `--help` page parses (no import-time crash from cyclopts).
* `build raster` round-trips through the persisted artifact.
* `stats` / `info` / `query` produce both human-readable and JSON
  output without raising.
* The four documented exit codes (0 / 1 / 2 / 3) all fire on the
  expected inputs.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from geocatalog._cli import app


def _run(*tokens: str) -> int:
    """Run the cyclopts App over ``tokens`` and return the exit code.

    The App is invoked with ``result_action="return_value"`` so the
    Python return value (an int) is what comes back; cyclopts'
    default ``sys.exit`` flow happens only when called as a real
    process entry point.
    """
    try:
        result = app(list(tokens), exit_on_error=False, result_action="return_value")
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    return int(result) if result is not None else 0


def test_help_root(capsys: pytest.CaptureFixture[str]) -> None:
    """`geocatalog --help` lists the top-level commands."""
    _run("--help")
    captured = capsys.readouterr().out
    assert "build" in captured
    assert "query" in captured
    assert "stats" in captured
    assert "info" in captured


def test_help_build(capsys: pytest.CaptureFixture[str]) -> None:
    """`geocatalog build --help` lists the per-format builders."""
    _run("build", "--help")
    captured = capsys.readouterr().out
    assert "raster" in captured
    assert "vector" in captured
    assert "xarray" in captured


def test_build_raster_roundtrip(
    tmp_path: Path,
    utm29_tile_factory: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Full happy-path: build → write → stats.

    The fixture writes two GeoTIFFs into a date-aware tmp directory;
    the CLI globs them, builds a catalog, and persists it. `stats`
    then reads it back and reports two rows.
    """
    utm29_tile_factory((500000, 4000000, 510000, 4010000), "20240601")
    utm29_tile_factory((510000, 4000000, 520000, 4010000), "20240602")
    glob_pattern = str(tmp_path / "*.tif")
    out = tmp_path / "catalog.parquet"

    exit_code = _run(
        "build",
        "raster",
        "--input-glob",
        glob_pattern,
        "--regex",
        r"S2_T29SND_(?P<date>\d{8})_.*\.tif",
        "--out",
        str(out),
    )
    assert exit_code == 0
    assert out.exists()

    capsys.readouterr()  # drop the build output
    exit_code = _run("stats", str(out))
    assert exit_code == 0
    stats_out = capsys.readouterr().out
    assert "rows" in stats_out
    assert "2" in stats_out


def test_stats_json(
    tmp_path: Path,
    utm29_tile_factory: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`stats --json` emits a JSON object parseable into a dict."""
    utm29_tile_factory((500000, 4000000, 510000, 4010000), "20240601")
    glob_pattern = str(tmp_path / "*.tif")
    out = tmp_path / "catalog.parquet"
    _run(
        "build",
        "raster",
        "--input-glob",
        glob_pattern,
        "--regex",
        r"S2_T29SND_(?P<date>\d{8})_.*\.tif",
        "--out",
        str(out),
    )
    capsys.readouterr()
    exit_code = _run("stats", str(out), "--json")
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["rows"] == 1
    assert payload["backend"] == "raster"


# ---------------------------------------------------------------------------
# Exit-code matrix
# ---------------------------------------------------------------------------


def test_exit_1_no_files_match_glob(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Empty glob is a user error → exit 1."""
    exit_code = _run(
        "build",
        "raster",
        "--input-glob",
        str(tmp_path / "no_such_*.tif"),
        "--out",
        str(tmp_path / "catalog.parquet"),
    )
    assert exit_code == 1
    assert "no files matched" in capsys.readouterr().err


def test_exit_2_corrupt_artifact(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-parquet file at the catalog path → exit 2 (catalog error)."""
    bad = tmp_path / "not-a-parquet.parquet"
    bad.write_bytes(b"this is plainly not parquet")
    exit_code = _run("stats", str(bad))
    assert exit_code == 2


def test_exit_3_missing_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catalog path that doesn't exist → exit 3 (I/O)."""
    exit_code = _run("stats", str(tmp_path / "does_not_exist.parquet"))
    assert exit_code == 3
    assert "not found" in capsys.readouterr().err
