"""Tests for the schema-migration framework (#25).

Covers the three cases laid out in the issue:

1. ``v_artifact == v_current`` → load directly (regression guard).
2. ``v_artifact <  v_current`` → forward migrations chain transparently.
3. ``v_artifact >  v_current`` → `CatalogSchemaError` with the artifact +
   reader versions in the message.

Plus the `geocatalog migrate` CLI subcommand.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import geopandas as gpd
import pytest

from geocatalog import (
    SCHEMA_VERSION_CURRENT,
    CatalogSchemaError,
    from_geoparquet,
    to_geoparquet,
)
from geocatalog._cli import app
from geocatalog._src import parquet as parquet_module


def _build_artifact(
    tmp_path: Path,
    factory: Callable[..., Path],
    *,
    schema_version: int,
) -> Path:
    """Write a 1-row catalog at the given `schema_version`."""
    src = factory((500000, 4000000, 510000, 4010000), "20240601")
    from geocatalog import build_raster_catalog

    cat = build_raster_catalog(
        [src],
        filename_regex=r"S2_T29SND_(?P<date>\d{8})_.*\.tif",
    )
    out = tmp_path / "catalog.parquet"
    to_geoparquet(cat, out, schema_version=schema_version)
    return out


def test_v_current_loads_directly(
    tmp_path: Path, utm29_tile_factory: Callable[..., Path]
) -> None:
    """Regression guard: a catalog at the current version loads as-is."""
    out = _build_artifact(
        tmp_path, utm29_tile_factory, schema_version=SCHEMA_VERSION_CURRENT
    )
    cat = from_geoparquet(out)
    assert len(cat) == 1


def test_v_future_raises_clearly(
    tmp_path: Path, utm29_tile_factory: Callable[..., Path]
) -> None:
    """A v999 artifact raises `CatalogSchemaError` referencing both versions."""
    out = _build_artifact(tmp_path, utm29_tile_factory, schema_version=999)
    with pytest.raises(CatalogSchemaError) as info:
        from_geoparquet(out)
    msg = str(info.value)
    assert "999" in msg
    assert f"v{SCHEMA_VERSION_CURRENT}" in msg
    assert "Upgrade" in msg


def test_forward_migration_chains(
    tmp_path: Path,
    utm29_tile_factory: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A v0 artifact is migrated to v1 transparently when v1 is current."""
    out = _build_artifact(tmp_path, utm29_tile_factory, schema_version=0)

    # Pretend the library is at v1 with one registered v0 -> v1 migration
    # that stamps a marker column. The monkeypatch reverts after the test.
    marker_calls = []

    def _v0_to_v1(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        marker_calls.append(len(gdf))
        gdf = gdf.copy()
        gdf["_migrated_from_v0"] = True
        return gdf

    monkeypatch.setattr(parquet_module, "SCHEMA_VERSION_CURRENT", 1)
    monkeypatch.setattr(parquet_module, "_MIGRATIONS", {0: _v0_to_v1})
    cat = from_geoparquet(out)

    assert marker_calls == [1]
    assert "_migrated_from_v0" in cat.gdf.columns
    assert bool(cat.gdf["_migrated_from_v0"].iloc[0])


def test_migrate_cli_round_trips_v_future(
    tmp_path: Path,
    utm29_tile_factory: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`geocatalog migrate` rejects an artifact newer than the reader."""
    out = _build_artifact(tmp_path, utm29_tile_factory, schema_version=999)
    try:
        result = app(
            ["migrate", str(out)], exit_on_error=False, result_action="return_value"
        )
    except SystemExit as exc:
        result = exc.code
    assert result == 2
    assert "exceeds reader" in capsys.readouterr().err


def test_migrate_cli_noop_on_current(
    tmp_path: Path,
    utm29_tile_factory: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`geocatalog migrate` is a no-op when the artifact is already current."""
    out = _build_artifact(
        tmp_path, utm29_tile_factory, schema_version=SCHEMA_VERSION_CURRENT
    )
    try:
        result = app(
            ["migrate", str(out)], exit_on_error=False, result_action="return_value"
        )
    except SystemExit as exc:
        result = exc.code
    assert result == 0
    assert "already at v" in capsys.readouterr().out
