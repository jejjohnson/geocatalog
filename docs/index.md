# geocatalog

> Spatiotemporal catalog over geospatial files — the `GeoSlice`-driven
> index extracted from [geotoolz](https://github.com/jejjohnson/geotoolz).

`geocatalog` is a **queryable spatiotemporal index over geospatial
files**. Each row records a file's footprint (bbox), time interval, CRS,
and path. Given a query like *"files overlapping AOI X between dates Y
and Z,"* the catalog returns the matching rows fast without opening any
file.

Two backends honour the same `GeoCatalog` Protocol:

- `InMemoryGeoCatalog` — a `GeoDataFrame` with an R-tree + `IntervalIndex`,
  good up to ~10⁵ rows.
- `DuckDBGeoCatalog` — a lazy SQL relation over a GeoParquet file,
  good to 10⁶+ rows and queryable from a remote URI (requires the
  `[duckdb]` extra).

## Installation

```bash
pip install geocatalog                  # base: in-memory + raster + vector
pip install 'geocatalog[duckdb]'        # DuckDB backend
pip install 'geocatalog[xarray-raster]' # xarray (NetCDF / Zarr) backend
pip install 'geocatalog[full]'          # all of the above
```

Or with `uv`:

```bash
uv add geocatalog
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

## Links

- [Catalogs concept](catalogs.md)
- [API Reference](api/reference.md)
- [Tutorials](notebooks/catalog_intro.ipynb)
- [Changelog](CHANGELOG.md)
- [GitHub](https://github.com/jejjohnson/geocatalog)
