# geocatalog

[![Tests](https://github.com/jejjohnson/geocatalog/actions/workflows/ci.yml/badge.svg)](https://github.com/jejjohnson/geocatalog/actions/workflows/ci.yml)
[![Lint](https://github.com/jejjohnson/geocatalog/actions/workflows/lint.yml/badge.svg)](https://github.com/jejjohnson/geocatalog/actions/workflows/lint.yml)
[![Type Check](https://github.com/jejjohnson/geocatalog/actions/workflows/typecheck.yml/badge.svg)](https://github.com/jejjohnson/geocatalog/actions/workflows/typecheck.yml)
[![Deploy Docs](https://github.com/jejjohnson/geocatalog/actions/workflows/pages.yml/badge.svg)](https://github.com/jejjohnson/geocatalog/actions/workflows/pages.yml)
[![codecov](https://codecov.io/gh/jejjohnson/geocatalog/branch/main/graph/badge.svg)](https://codecov.io/gh/jejjohnson/geocatalog)
[![PyPI version](https://img.shields.io/pypi/v/geocatalog.svg)](https://pypi.org/project/geocatalog/)
[![Python versions](https://img.shields.io/pypi/pyversions/geocatalog.svg)](https://pypi.org/project/geocatalog/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

> Spatiotemporal catalog over geospatial files — the `GeoSlice`-driven
> index extracted from [geotoolz](https://github.com/jejjohnson/geotoolz).

`geocatalog` is a queryable spatiotemporal index over geospatial files.
Each row records a file's footprint (bbox), time interval, CRS, and
path. Given a query like *"files overlapping AOI X between dates Y and
Z,"* the catalog returns the matching rows fast without opening any
file.

Two backends honour the same `GeoCatalog` Protocol:

- `InMemoryGeoCatalog` — a `GeoDataFrame` with an R-tree + `IntervalIndex`,
  good up to ~10⁵ rows.
- `DuckDBGeoCatalog` — a lazy SQL relation over a GeoParquet 1.1
  artifact, good to 10⁶+ rows and queryable from a remote URI
  (`[duckdb]` extra).

`GeoSlice` is the cross-cutting unit of work: a bbox + interval + CRS +
resolution. Catalogs produce slices; loaders consume them.

## Install

```bash
pip install geocatalog                  # base: in-memory + raster + vector
pip install 'geocatalog[duckdb]'        # DuckDB backend
pip install 'geocatalog[xarray-raster]' # xarray (NetCDF / Zarr) backend
pip install 'geocatalog[full]'          # everything
```

## Quickstart

```python
import pandas as pd
import geocatalog as gc

catalog = gc.build_raster_catalog(
    filepaths=["scene1.tif", "scene2.tif", "scene3.tif"],
    filename_regex=r"scene(?P<id>\d+)\.tif",
    target_crs="EPSG:32629",
)

aoi = gc.GeoSlice(
    bounds=(500_000, 4_000_000, 540_000, 4_040_000),
    interval=pd.Interval(
        pd.Timestamp("2024-06-01"),
        pd.Timestamp("2024-06-30"),
        closed="both",
    ),
    resolution=(10.0, 10.0),
    crs="EPSG:32629",
)

tensor = gc.load_raster(catalog, aoi, band_indexes=[1, 2, 3])
```

## Layout

The package is laid out as a hybrid: flat top-level plus
sub-namespaces. All three of these resolve to the same symbol:

```python
from geocatalog import GeoSlice          # flat top-level
from geocatalog.types import GeoSlice    # types sub-namespace
from geocatalog import InMemoryGeoCatalog
from geocatalog.catalog import InMemoryGeoCatalog
```

## Bridging to a patcher

`CatalogDomain` adapts a catalog into a `Domain` shape (bounds + an
iterable of `GeoSlice`s) so a tiling patcher can walk a multi-file
archive. The canonical consumer is
[`geotoolz.patch.SpatialPatcher`](https://github.com/jejjohnson/geotoolz),
but any code that iterates `domain.slices()` works.

## Documentation

- [Catalogs concept](https://jejjohnson.github.io/geocatalog/catalogs/)
- [API reference](https://jejjohnson.github.io/geocatalog/api/reference/)
- Tutorials live under `docs/notebooks/`.

## Development

```bash
make install              # uv sync --all-groups + pre-commit
make test                 # pytest
make format               # ruff format + ruff check --fix
make lint                 # ruff check .
make typecheck            # ty check src/geocatalog
make docs-serve           # MkDocs preview
```

## License

MIT — see `LICENSE`.
