"""`geocatalog` — spatiotemporal index over geospatial files.

Surface:

- `GeoSlice`: the cross-cutting unit of work — a bbox + interval + CRS +
  resolution. Catalogs produce them; loaders consume them.
- `GeoCatalog`: Protocol; one shape across backends.
- `CatalogRow`: backend-neutral row view yielded by `iter_rows`.
- `InMemoryGeoCatalog`: GeoDataFrame-backed Phase 1 implementation.
- `DuckDBGeoCatalog`: SQL-backed Phase 2 implementation (extras-gated
  via `[duckdb]`).
- `open_catalog`: factory that picks a backend for a GeoParquet artifact.
- `build_raster_catalog` / `build_xarray_catalog` / `build_vector_catalog`:
  builders, the latter two extras-gated.
- `load_raster` / `load_raster_timeseries` / `load_xarray` / `load_vector`:
  per-backend loaders that consume a `GeoSlice` and return `GeoTensor`
  (raster, vector) or `xr.Dataset` (xarray).
- `query` / `intersect` / `union`: set algebra over catalogs.
- `to_geoparquet` / `from_geoparquet`: portable artifact round-trip.
- `CatalogDomain`: adapter so a downstream `SpatialPatcher` (e.g. from
  `geotoolz.patch`) can iterate a catalog's rows.

The hybrid layout exposes the same surface at three paths: flat top
level (`geocatalog.GeoSlice`), `geocatalog.types.GeoSlice`, and
`geocatalog.catalog.InMemoryGeoCatalog`. Pick whichever reads best
where you import.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger as _logger

from geocatalog._src._align import (
    Align,
    GridAlignmentWarning,
    divide_evenly,
    is_grid_aligned,
)
from geocatalog._src.base import CatalogRow, CatalogSchemaError, GeoCatalog
from geocatalog._src.domain import CatalogDomain
from geocatalog._src.geoslice import (
    PIXEL_PRECISION,
    GeoSlice,
    slice_to_window,
    window_to_slice,
)
from geocatalog._src.memory import InMemoryGeoCatalog
from geocatalog._src.ops import intersect, query, union
from geocatalog._src.parquet import (
    SCHEMA_VERSION_CURRENT,
    from_geoparquet,
    migrate_geoparquet,
    to_geoparquet,
)
from geocatalog._src.raster import (
    build_raster_catalog,
    load_raster,
    load_raster_timeseries,
)
from geocatalog._src.streaming import append_files


# Library hygiene: loguru's recommended pattern is to disable the
# library's own logger at import time so consumers don't see output by
# default. Opt in from a consumer app with `logger.enable("geocatalog")`.
_logger.disable("geocatalog")


if TYPE_CHECKING:
    from geocatalog._src.duckdb_backend import DuckDBGeoCatalog
    from geocatalog._src.stac import (
        from_stac_items,
        from_stac_search,
        to_stac_collection,
    )
    from geocatalog._src.vector import build_vector_catalog, load_vector
    from geocatalog._src.xarray_backend import (
        build_xarray_catalog,
        load_xarray,
    )


__version__ = "0.0.3"

__all__ = [
    "PIXEL_PRECISION",
    "SCHEMA_VERSION_CURRENT",
    "Align",
    "CatalogDomain",
    "CatalogRow",
    "CatalogSchemaError",
    "DuckDBGeoCatalog",
    "GeoCatalog",
    "GeoSlice",
    "GridAlignmentWarning",
    "InMemoryGeoCatalog",
    "append_files",
    "build_raster_catalog",
    "build_vector_catalog",
    "build_xarray_catalog",
    "divide_evenly",
    "from_geoparquet",
    "from_stac_items",
    "from_stac_search",
    "intersect",
    "is_grid_aligned",
    "load_raster",
    "load_raster_timeseries",
    "load_vector",
    "load_xarray",
    "migrate_geoparquet",
    "open_catalog",
    "query",
    "slice_to_window",
    "to_geoparquet",
    "to_stac_collection",
    "union",
    "window_to_slice",
]


_BACKEND_T = Literal["raster", "xarray", "vector"]


def open_catalog(
    source: str | Path,
    *,
    backend: _BACKEND_T | None = None,
    engine: Literal["auto", "memory", "duckdb"] = "auto",
    crs: Any | None = None,
    storage_options: dict[str, Any] | None = None,
) -> GeoCatalog:
    """Open a GeoParquet artifact as a `GeoCatalog`.

    The factory picks an engine. ``"auto"`` prefers the DuckDB backend
    (lazy, scales) when the ``[duckdb]`` extra is installed; otherwise it
    falls back to the in-memory backend via `from_geoparquet`. Pass
    ``engine="memory"`` to force the eager path even with DuckDB present.

    The artifact's stored backend tag (the ``_backend`` column written
    by `to_geoparquet`) is honoured by default — pass ``backend=...``
    only to override a wrong tag or to tag an externally produced
    artifact that lacks the column. Forcing a default would silently
    miscategorise xarray / vector catalogs and break loader dispatch.

    Args:
        source: Path or URI to a GeoParquet file. A directory of shards
            (``shards/``) or a glob (``shards/*.parquet``) is read as one
            virtual table by the DuckDB engine; the in-memory engine
            requires a single file.
        backend: Loader dispatch tag (``"raster"`` / ``"xarray"`` /
            ``"vector"``). ``None`` reads the ``_backend`` column from
            the artifact (default ``"raster"`` if missing).
        engine: ``"auto"`` (DuckDB if available, else memory),
            ``"memory"`` (force `from_geoparquet`), or ``"duckdb"``
            (force `DuckDBGeoCatalog.open`; raises if the extra is not
            installed).
        crs: Optional CRS override; only consulted by the DuckDB engine
            when the artifact doesn't carry one.
        storage_options: Options forwarded to fsspec when reading cloud
            URIs through the in-memory engine.

    Returns:
        A `GeoCatalog` over ``source``. The concrete class is either
        `DuckDBGeoCatalog` or `InMemoryGeoCatalog` depending on the
        resolved engine.

    Raises:
        ImportError: ``engine="duckdb"`` with the extra missing.
    """
    if engine == "memory":
        return _memory_engine(source, backend, storage_options=storage_options)
    if engine == "duckdb":
        from geocatalog._src.duckdb_backend import DuckDBGeoCatalog

        return DuckDBGeoCatalog.open(
            source,
            backend=backend,
            crs=crs,
            storage_options=storage_options,
        )
    # engine == "auto"
    if storage_options is not None:
        return _memory_engine(source, backend, storage_options=storage_options)
    try:
        from geocatalog._src.duckdb_backend import DuckDBGeoCatalog
    except ImportError:
        return _memory_engine(source, backend, storage_options=storage_options)
    try:
        return DuckDBGeoCatalog.open(
            source,
            backend=backend,
            crs=crs,
            storage_options=storage_options,
        )
    except ImportError:
        return _memory_engine(source, backend, storage_options=storage_options)


def _memory_engine(
    source: str | Path,
    backend: _BACKEND_T | None,
    *,
    storage_options: dict[str, Any] | None = None,
) -> InMemoryGeoCatalog:
    """Open ``source`` as an `InMemoryGeoCatalog`, applying a backend override.

    Constructs a fresh catalog rather than mutating ``cat.backend`` so
    the override flows through `InMemoryGeoCatalog.__init__`'s validation.
    """
    cat = from_geoparquet(source, storage_options=storage_options)
    if backend is None or backend == cat.backend:
        return cat
    return InMemoryGeoCatalog(cat.gdf, backend=backend)


_LAZY_ATTRS = {
    "build_xarray_catalog": ("geocatalog._src.xarray_backend",),
    "load_xarray": ("geocatalog._src.xarray_backend",),
    "build_vector_catalog": ("geocatalog._src.vector",),
    "load_vector": ("geocatalog._src.vector",),
    "DuckDBGeoCatalog": ("geocatalog._src.duckdb_backend",),
    "from_stac_items": ("geocatalog._src.stac",),
    "from_stac_search": ("geocatalog._src.stac",),
    "to_stac_collection": ("geocatalog._src.stac",),
}


def __getattr__(name: str) -> Any:
    """Lazy import for the extras-gated backends.

    Importing `geocatalog` at top level should not fail just because an
    optional dep (`xarray`, `duckdb`) is missing. Resolving e.g.
    `load_xarray` or `DuckDBGeoCatalog` finally triggers the import and
    raises a friendly `ImportError` if the corresponding extra isn't
    installed.
    """
    if name in _LAZY_ATTRS:
        import importlib

        module_name = _LAZY_ATTRS[name][0]
        try:
            mod = importlib.import_module(module_name)
        except ImportError as exc:
            if "xarray" in module_name:
                extra = "xarray-raster"
            elif "duckdb" in module_name:
                extra = "duckdb"
            elif "stac" in module_name:
                extra = "stac"
            else:
                extra = "vector"
            raise ImportError(
                f"`geocatalog.{name}` requires the [{extra}] extra; "
                f"install via `pip install 'geocatalog[{extra}]'`."
            ) from exc
        attr = getattr(mod, name)
        globals()[name] = attr
        return attr
    raise AttributeError(f"module 'geocatalog' has no attribute {name!r}")
