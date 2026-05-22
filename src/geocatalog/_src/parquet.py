"""`to_geoparquet` / `from_geoparquet` — catalog ↔ portable artifact.

Round-trips an `InMemoryGeoCatalog` through GeoParquet 1.1 (geopandas
writes the bbox covering struct when ``write_covering_bbox=True``). The
artifact is then queryable from pandas / DuckDB / GDAL without
ceremony — no pickle-version fragility.

Phase 2 (DuckDB backend) reads the *same* GeoParquet file, so
``to_geoparquet`` writes the canonical interchange format for both
backends.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

import geopandas as gpd
import pandas as pd

from geocatalog._src.base import CatalogSchemaError
from geocatalog._src.memory import InMemoryGeoCatalog


_BACKEND_T = Literal["raster", "xarray", "vector"]


# The reader's current schema version. Bump on every substantive schema
# change and add an entry to `_MIGRATIONS` for ``previous → this``.
SCHEMA_VERSION_CURRENT: int = 0


# Forward migrations keyed by *source* version. `_MIGRATIONS[k]` takes a
# v_k gdf and returns a v_(k+1) gdf. The chain
# ``_MIGRATIONS[v_artifact] ∘ … ∘ _MIGRATIONS[v_current - 1]`` brings an
# old artifact up to the current version. Empty today (current schema
# is v0); populate when shipping v1.
_MIGRATIONS: dict[int, Callable[[gpd.GeoDataFrame], gpd.GeoDataFrame]] = {}


def _apply_migrations(gdf: gpd.GeoDataFrame, *, from_version: int) -> gpd.GeoDataFrame:
    """Chain forward migrations from `from_version` to `SCHEMA_VERSION_CURRENT`.

    Raises:
        CatalogSchemaError: If a migration is missing for any version in
            the chain — that's a library bug (someone bumped
            `SCHEMA_VERSION_CURRENT` without registering the migration).
    """
    for v in range(from_version, SCHEMA_VERSION_CURRENT):
        migration = _MIGRATIONS.get(v)
        if migration is None:
            raise CatalogSchemaError(
                f"missing migration v{v} -> v{v + 1}; this is a library bug — "
                "`SCHEMA_VERSION_CURRENT` was bumped without registering "
                "the corresponding entry in `_MIGRATIONS`."
            )
        gdf = migration(gdf)
    return gdf


def to_geoparquet(
    catalog: InMemoryGeoCatalog,
    path: str | Path,
    *,
    schema_version: int = SCHEMA_VERSION_CURRENT,
    write_covering_bbox: bool = True,
) -> None:
    """Persist ``catalog`` as a GeoParquet file on disk.

    The result is a single Parquet file readable by any GeoParquet-aware
    tool (DuckDB, GDAL, pandas, geopandas) — not a pickle, so it
    survives version bumps and crosses Python / language boundaries.
    The Phase 2 ``DuckDBGeoCatalog`` reads the *same* artifact, so this
    is the canonical interchange format for both backends.

    Two columns are added on write and stripped on load:

    - ``_backend``: round-trips the backend tag so `from_geoparquet`
      restores the right loader dispatch.
    - ``_schema_version``: reserved for forward-compat (§10.4 of the
      design plan); bump on first substantive schema change.

    The row-level ``pd.IntervalIndex`` is unpacked into ``start_time`` /
    ``end_time`` columns (Parquet has no native IntervalIndex type);
    `from_geoparquet` rebuilds the index from those columns.

    Args:
        catalog: An `InMemoryGeoCatalog` to serialise. The catalog's
            ``gdf.crs`` is written into the GeoParquet metadata.
        path: Destination path. The ``.parquet`` extension is
            conventional. Any parent directory must exist.
        schema_version: Value written to the reserved
            ``_schema_version`` column. Default 0.
        write_covering_bbox: Emit the per-row ``bbox`` covering struct
            that GeoParquet 1.1 readers (DuckDB, geopandas ≥0.14) use
            for predicate pushdown. Default True; turn off only if a
            downstream consumer chokes on 1.1.
    """
    gdf = catalog.gdf.copy()
    if isinstance(gdf.index, pd.IntervalIndex):
        gdf["start_time"] = gdf.index.left
        gdf["end_time"] = gdf.index.right
        gdf = gdf.reset_index(drop=True)
    gdf["_backend"] = catalog.backend
    gdf["_schema_version"] = schema_version
    gdf.to_parquet(
        Path(path),
        write_covering_bbox=write_covering_bbox,
    )


def from_geoparquet(path: str | Path) -> InMemoryGeoCatalog:
    """Load a GeoParquet file into an `InMemoryGeoCatalog`.

    Inverse of `to_geoparquet`: rebuilds the `IntervalIndex` from
    ``start_time`` / ``end_time`` columns and recovers the backend tag
    from the reserved ``_backend`` column. Externally produced files
    (no ``_backend`` column) default to backend ``"raster"`` — adjust
    on the returned catalog if that's wrong.

    The reserved ``_schema_version`` column drives forward migration
    (see `SCHEMA_VERSION_CURRENT` and `_MIGRATIONS`):

    - ``v_artifact == v_current``: load directly.
    - ``v_artifact <  v_current``: chain forward migrations transparently.
    - ``v_artifact >  v_current``: raise `CatalogSchemaError` — the
      reader is older than the writer and needs upgrading.

    Args:
        path: Path to a GeoParquet file produced by `to_geoparquet`,
            DuckDB's ``COPY ... TO``, or any GeoParquet 1.x writer.

    Returns:
        An `InMemoryGeoCatalog` with the same rows, CRS, and (where
        recoverable) backend tag as the source.

    Raises:
        CatalogSchemaError: If the artifact's `_schema_version` exceeds
            `SCHEMA_VERSION_CURRENT`.
    """
    gdf = gpd.read_parquet(Path(path))
    backend_col = gdf.pop("_backend") if "_backend" in gdf.columns else None
    if "_schema_version" in gdf.columns:
        version_col = gdf.pop("_schema_version")
        v_artifact = (
            int(version_col.iloc[0]) if len(version_col) > 0 else SCHEMA_VERSION_CURRENT
        )
    else:
        # Pre-versioning artifacts are treated as v0 — that's where the
        # `_schema_version` column was introduced, and the schema today
        # is v0, so no migration is required.
        v_artifact = SCHEMA_VERSION_CURRENT
    if v_artifact > SCHEMA_VERSION_CURRENT:
        raise CatalogSchemaError(
            f"artifact {Path(path)} has _schema_version={v_artifact}, "
            f"exceeds reader v{SCHEMA_VERSION_CURRENT}. "
            "Upgrade `geocatalog` to read this artifact."
        )
    if v_artifact < SCHEMA_VERSION_CURRENT:
        gdf = _apply_migrations(gdf, from_version=v_artifact)
    if "start_time" in gdf.columns and "end_time" in gdf.columns:
        idx = pd.IntervalIndex.from_arrays(
            gdf.pop("start_time"),
            gdf.pop("end_time"),
            closed="both",
            name="datetime",
        )
        gdf = gdf.set_index(idx)
    if backend_col is not None and len(backend_col) > 0:
        backend: _BACKEND_T = backend_col.iloc[0]
    else:
        backend = "raster"
    return InMemoryGeoCatalog(gdf, backend=backend)


def migrate_geoparquet(source: str | Path, *, to_version: int) -> int:
    """Read ``source``, migrate it to ``to_version``, write back in-place.

    A thin file-level wrapper over `from_geoparquet` + `to_geoparquet`
    used by the ``geocatalog migrate`` CLI. The artifact is rewritten
    only if the migration actually changed the version, so calling
    twice is idempotent.

    Args:
        source: GeoParquet file to migrate. Rewritten in-place.
        to_version: Target version. Must equal `SCHEMA_VERSION_CURRENT`
            today (forward-only migrations); kept as an explicit
            parameter so future versions can target a pinned schema.

    Returns:
        The artifact's `_schema_version` *before* the migration. Equal
        to ``to_version`` for already-current files.

    Raises:
        CatalogSchemaError: If ``to_version`` differs from
            `SCHEMA_VERSION_CURRENT`.
    """
    if to_version != SCHEMA_VERSION_CURRENT:
        raise CatalogSchemaError(
            f"migrate target v{to_version} differs from reader "
            f"v{SCHEMA_VERSION_CURRENT}; only forward migrations to the "
            "current version are supported."
        )
    path = Path(source)
    gdf_raw = gpd.read_parquet(path)
    from_version = (
        int(gdf_raw["_schema_version"].iloc[0])
        if "_schema_version" in gdf_raw.columns and len(gdf_raw) > 0
        else SCHEMA_VERSION_CURRENT
    )
    if from_version == to_version:
        return from_version
    cat = from_geoparquet(path)
    to_geoparquet(cat, path, schema_version=to_version)
    return from_version
