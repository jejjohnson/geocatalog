"""`geocatalog` console command (#23).

Thin CLI over the library API — every subcommand maps to a single
public function and adds nothing more than argument parsing and
human / JSON-friendly output. Business logic stays in the library.

Exit codes:

* 0 — success.
* 1 — user error (bad args, missing extra, no files match glob).
* 2 — catalog error (corrupt artifact, schema mismatch).
* 3 — I/O error (path not readable / writable).
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
from cyclopts import App, Parameter


# Three sub-apps + the root. Cyclopts lets us register sub-apps via
# `app.command(sub_app)`; `name=` controls the verb the user types.
app = App(
    name="geocatalog",
    help="Spatiotemporal catalog over geospatial files.",
)
build_app = App(
    name="build", help="Build a catalog from raster / xarray / vector files."
)
app.command(build_app)


_BackendT = Literal["raster", "xarray", "vector"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _expand_glob(pattern: str) -> list[Path]:
    """Local-disk glob expansion with ``**`` support.

    Remote URIs (``s3://``, ``gs://``, ``https://``) raise — a future
    PR can plug in fsspec; for now the CLI is local-only, matching
    the library's loader surface.
    """
    if "://" in pattern:
        raise ValueError(
            f"Remote URIs not supported by the CLI yet (#23 follow-on): {pattern!r}. "
            "Expand the URI list yourself and pass concrete paths."
        )
    matches = sorted(glob.glob(pattern, recursive=True))
    return [Path(m) for m in matches]


def _parse_bbox(s: str) -> tuple[float, float, float, float]:
    """``"xmin,ymin,xmax,ymax"`` → tuple of four floats."""
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 4:
        raise ValueError(f"--bbox must be 'xmin,ymin,xmax,ymax' (4 floats); got {s!r}")
    try:
        xmin, ymin, xmax, ymax = (float(p) for p in parts)
    except ValueError as exc:
        raise ValueError(f"--bbox values must be numeric; got {s!r}") from exc
    return (xmin, ymin, xmax, ymax)


def _emit(payload: dict[str, object], *, as_json: bool) -> None:
    """Print ``payload`` as JSON or pretty key/value lines."""
    if as_json:
        print(json.dumps(payload, default=str, indent=2))
        return
    width = max((len(str(k)) for k in payload), default=0)
    for key, value in payload.items():
        print(f"{key.ljust(width)}  {value}")


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


@build_app.command
def raster(
    *,
    input_glob: Annotated[
        str, Parameter(help="Glob over raster files. Use ** for recursion.")
    ],
    out: Annotated[Path, Parameter(help="Destination GeoParquet path.")],
    regex: Annotated[
        str | None,
        Parameter(
            help=(
                "Filename regex with `(?P<date>...)` or `(?P<start>...)+(?P<stop>...)`."
            )
        ),
    ] = None,
    date_format: Annotated[
        str, Parameter(help="strptime fmt for regex date groups.")
    ] = "%Y%m%d",
    target_crs: Annotated[
        str | None,
        Parameter(help="Catalog CRS. None latches onto the first file's native CRS."),
    ] = None,
    backend: Annotated[
        Literal["memory", "duckdb"],
        Parameter(help="`memory` builds in RAM; `duckdb` streams to GeoParquet."),
    ] = "memory",
) -> int:
    """Build a raster catalog from a glob of GeoTIFFs."""
    from geocatalog import build_raster_catalog, to_geoparquet

    paths = _expand_glob(input_glob)
    if not paths:
        print(f"no files matched {input_glob!r}", file=sys.stderr)
        return 1
    cat = build_raster_catalog(
        paths,
        filename_regex=regex,
        date_format=date_format,
        target_crs=target_crs,
        backend=backend,
        out_path=out if backend == "duckdb" else None,
    )
    if backend == "memory":
        to_geoparquet(cat, out)
    print(f"wrote {out} ({len(cat)} rows)")
    return 0


@build_app.command
def xarray(
    *,
    input_glob: Annotated[str, Parameter(help="Glob over NetCDF / Zarr / HDF stores.")],
    out: Annotated[Path, Parameter(help="Destination GeoParquet path.")],
    time_var: Annotated[
        str, Parameter(help="Coordinate name for the time axis.")
    ] = "time",
    target_crs: Annotated[
        str | None,
        Parameter(help="CRS to tag the catalog with (not used to reproject)."),
    ] = None,
) -> int:
    """Build an xarray-shaped catalog. Requires the `[xarray-raster]` extra."""
    try:
        from geocatalog import build_xarray_catalog, to_geoparquet
    except ImportError as exc:
        print(f"build xarray needs the [xarray-raster] extra: {exc}", file=sys.stderr)
        return 1
    paths = _expand_glob(input_glob)
    if not paths:
        print(f"no files matched {input_glob!r}", file=sys.stderr)
        return 1
    cat = build_xarray_catalog(paths, time_var=time_var, target_crs=target_crs)
    to_geoparquet(cat, out)
    print(f"wrote {out} ({len(cat)} rows)")
    return 0


@build_app.command
def vector(
    *,
    input_glob: Annotated[str, Parameter(help="Glob over vector files.")],
    out: Annotated[Path, Parameter(help="Destination GeoParquet path.")],
    layer: Annotated[
        str | None, Parameter(help="Layer name/index for multi-layer files.")
    ] = None,
    regex: Annotated[
        str | None, Parameter(help="Filename regex for time parsing.")
    ] = None,
    date_format: Annotated[
        str, Parameter(help="strptime fmt for regex date groups.")
    ] = "%Y%m%d",
    target_crs: Annotated[str | None, Parameter(help="Catalog CRS.")] = None,
) -> int:
    """Build a vector catalog (Shapefile / GeoPackage / GeoJSON)."""
    try:
        from geocatalog import build_vector_catalog, to_geoparquet
    except ImportError as exc:
        print(f"build vector failed: {exc}", file=sys.stderr)
        return 1
    paths = _expand_glob(input_glob)
    if not paths:
        print(f"no files matched {input_glob!r}", file=sys.stderr)
        return 1
    cat = build_vector_catalog(
        paths,
        filename_regex=regex,
        date_format=date_format,
        target_crs=target_crs,
        layer=layer,
    )
    to_geoparquet(cat, out)
    print(f"wrote {out} ({len(cat)} rows)")
    return 0


# ---------------------------------------------------------------------------
# query / stats / info
# ---------------------------------------------------------------------------


def _open_catalog(source: Path):
    """Open a catalog artifact, mapping errors to CLI exit codes.

    Returns the opened catalog directly; the caller is expected to
    propagate any raised SystemExit through.
    """
    from geocatalog import open_catalog

    if not source.exists():
        print(f"catalog not found: {source}", file=sys.stderr)
        raise SystemExit(3)
    try:
        return open_catalog(source, engine="memory")
    except (ValueError, KeyError) as exc:
        print(f"corrupt or unrecognised catalog ({source}): {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


@app.command
def query(
    source: Annotated[Path, Parameter(help="GeoParquet catalog to query.")],
    *,
    bbox: Annotated[
        str | None, Parameter(help='"xmin,ymin,xmax,ymax" in --crs units.')
    ] = None,
    crs: Annotated[str, Parameter(help="CRS of --bbox.")] = "EPSG:4326",
    start: Annotated[str | None, Parameter(help="Start of time window (ISO).")] = None,
    end: Annotated[str | None, Parameter(help="End of time window (ISO).")] = None,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="Emit machine-readable JSON.")
    ] = False,
) -> int:
    """Filter ``source`` by bbox + time and print the matching row count."""
    cat = _open_catalog(source)
    bounds = _parse_bbox(bbox) if bbox else None
    time = None
    if start is not None or end is not None:
        time = (
            pd.Timestamp(start) if start else None,
            pd.Timestamp(end) if end else None,
        )
    result = cat.query(bounds=bounds, crs=crs, time=time)
    _emit(
        {
            "source": str(source),
            "rows": len(result),
            "bbox": bounds,
            "time": [str(start), str(end)] if time else None,
        },
        as_json=json_output,
    )
    return 0


@app.command
def stats(
    source: Annotated[Path, Parameter(help="GeoParquet catalog to summarise.")],
    *,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="Emit machine-readable JSON.")
    ] = False,
) -> int:
    """Print rows / bounds / temporal extent / backend / CRS for ``source``."""
    cat = _open_catalog(source)
    extent = cat.temporal_extent
    _emit(
        {
            "rows": len(cat),
            "bounds": list(cat.total_bounds),
            "temporal_start": extent.left,
            "temporal_end": extent.right,
            "backend": cat.backend,
            "crs": str(cat.gdf.crs),
        },
        as_json=json_output,
    )
    return 0


@app.command
def migrate(
    source: Annotated[Path, Parameter(help="GeoParquet catalog to migrate in-place.")],
    *,
    to_version: Annotated[
        int | None,
        Parameter(help="Target schema version. Defaults to the reader's current."),
    ] = None,
) -> int:
    """Rewrite ``source`` at the requested schema version (#25)."""
    from geocatalog import SCHEMA_VERSION_CURRENT, migrate_geoparquet
    from geocatalog._src.base import CatalogSchemaError

    if not source.exists():
        print(f"catalog not found: {source}", file=sys.stderr)
        return 3
    target = SCHEMA_VERSION_CURRENT if to_version is None else to_version
    try:
        v_before = migrate_geoparquet(source, to_version=target)
    except CatalogSchemaError as exc:
        print(f"migrate failed: {exc}", file=sys.stderr)
        return 2
    if v_before == target:
        print(f"{source} already at v{target}")
    else:
        print(f"wrote {source} (v{v_before} -> v{target})")
    return 0


@app.command
def info(
    source: Annotated[Path, Parameter(help="GeoParquet catalog to inspect.")],
    *,
    row: Annotated[int, Parameter(help="Row index to inspect.")] = 0,
    json_output: Annotated[
        bool, Parameter(name=["--json"], help="Emit machine-readable JSON.")
    ] = False,
) -> int:
    """Show one row of ``source`` in detail."""
    cat = _open_catalog(source)
    if row < 0 or row >= len(cat):
        print(f"row {row} out of range [0, {len(cat)})", file=sys.stderr)
        return 1
    series = cat.gdf.iloc[row]
    payload: dict[str, object] = {col: series[col] for col in series.index}
    interval = cat.gdf.index[row]
    if hasattr(interval, "left"):
        payload["start_time"] = interval.left
        payload["end_time"] = interval.right
    _emit(payload, as_json=json_output)
    return 0
