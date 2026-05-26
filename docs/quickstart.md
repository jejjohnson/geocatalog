# Quickstart — Cloud-free Sentinel-2 NDVI over Lake Tahoe

A 15-minute walkthrough using **real Sentinel-2 L2A data** from
[Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/).
We'll build a catalog from a STAC search, filter by AOI + cloud
cover, and load a single scene as a `GeoTensor`.

This page mirrors the [end-to-end notebook](notebooks/end_to_end_lake_tahoe.ipynb).
The notebook continues into pipelines (`geotoolz`) and patching
(`geopatcher`); this page stops at "load a scene".

## Setup

Install the extras we need:

```bash
pip install 'geocatalog[stac,full]'
# or with uv:
uv add 'geocatalog[stac,full]'
```

The `[stac]` extra pulls `pystac`, `pystac-client`, and
`planetary-computer`. The `[full]` extra adds the DuckDB backend,
xarray, and cloud-storage support.

## The scenario

| | |
| --- | --- |
| **AOI** | Lake Tahoe, EPSG:4326 bbox `(-120.25, 38.85, -119.85, 39.30)` |
| **Time** | 2024-06-01 to 2024-09-30 (summer) |
| **STAC API** | Microsoft Planetary Computer |
| **Collection** | `sentinel-2-l2a` |
| **Cloud cover** | < 20% |

## 1. Build the catalog from a STAC search

```python
import pandas as pd
import geocatalog as gc
from geocatalog.sources import STACSource

# AOI + time window — used everywhere downstream.
TAHOE_BBOX = (-120.25, 38.85, -119.85, 39.30)
SUMMER_2024 = pd.Interval(
    pd.Timestamp("2024-06-01", tz="UTC"),
    pd.Timestamp("2024-09-30", tz="UTC"),
    closed="both",
)

# Planetary Computer signs blob-storage URLs for us.
src = STACSource.planetary_computer()

# Discover matching scenes — every row carries signed asset URLs.
rows = list(src.query(
    bounds=TAHOE_BBOX,
    interval=SUMMER_2024,
    collection="sentinel-2-l2a",
    filters={"eo:cloud_cover": {"lt": 20}},
    limit=50,
))
print(f"discovered {len(rows)} scenes from MPC")
```

`STACSource.planetary_computer()` is a thin wrapper over
`pystac-client` + `planetary-computer.sign`. Every yielded `SourceRow`
carries signed URLs you can hand directly to `rasterio` / GDAL.

### Or use the one-liner

If you don't need provenance, `from_stac_search` builds the catalog in
one call:

```python
catalog = gc.from_stac_search(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    collections=["sentinel-2-l2a"],
    bbox=TAHOE_BBOX,
    datetime="2024-06-01/2024-09-30",
    asset_key="B04",   # red band
    max_items=50,
)
print(f"len(catalog): {len(catalog)}")
print(f"catalog.total_bounds: {catalog.total_bounds}")
```

The catalog now indexes every scene's footprint, time interval, CRS,
and signed asset URL. **No raster pixels have been read yet** — only
STAC metadata.

## 2. Query by AOI and time

The `GeoSlice` we built above is the unit of work. Hand it to the
catalog to filter rows:

```python
aoi = gc.GeoSlice(
    bounds=TAHOE_BBOX,
    interval=SUMMER_2024,
    resolution=(0.0001, 0.0001),   # ~10 m at this latitude
    crs="EPSG:4326",
)

hits = catalog.query(aoi)
print(f"{len(hits)} of {len(catalog)} scenes touch the AOI in summer")
for row in hits.iter_rows():
    print(f"  {row.interval.left.date()}  {row.filepath[:80]}...")
```

`query` returns a new catalog containing only matching rows. The
original is untouched.

## 3. Load a single scene

Pick the lowest-cloud scene and load it:

```python
import geopandas as gpd

# Inspect the gdf to pick the cleanest scene.
gdf = hits.gdf.sort_values("eo:cloud_cover").head(3)
best_row = hits.gdf.iloc[0]
scene_slice = gc.GeoSlice(
    bounds=tuple(best_row.geometry.bounds),
    interval=hits.gdf.index[0],   # the IntervalIndex carries the time
    resolution=aoi.resolution,
    crs=aoi.crs,
)

# Materialise — this is the first time we actually open a raster file.
tensor = gc.load_raster(
    hits,
    scene_slice,
    band_indexes=[1],   # B04 alone, since asset_key="B04" above
)
print(f"tensor.values.shape: {tensor.values.shape}")
print(f"tensor.crs: {tensor.crs}")
```

`load_raster` opens the Sentinel-2 asset via `rasterio` (HTTP-range
reads from Azure blob storage thanks to PC's signed URL), windows it
to the slice, reprojects on the fly if needed, and hands back a
`GeoTensor` — a numpy-subclass array with `crs`, `transform`, and
`bounds` attached.

## 4. Persist the catalog

You'll want to reuse this catalog without re-querying STAC every
time. Write it to GeoParquet:

```python
gc.to_geoparquet(catalog, "tahoe_s2_summer_2024.parquet")

# Later, reopen — prefers DuckDB if installed.
catalog = gc.open_catalog("tahoe_s2_summer_2024.parquet")
```

The artifact is GeoParquet 1.1 — readable by DuckDB, geopandas, GDAL,
QGIS. Upload it to `s3://` and reopen with `open_catalog("s3://...")`
to share with collaborators (or your future self).

## What's next

- **[End-to-end notebook](notebooks/end_to_end_lake_tahoe.ipynb)** —
  continues into NDVI computation (`geotoolz`), tiling
  (`geopatcher`), and stitching.
- **[Concepts](concepts.md)** — the mental model behind catalogs,
  slices, and the two backends.
- **[Recipes](recipes/large-archives.md)** — scaling patterns for
  archive-sized workloads.
- **[API reference](api/reference.md)** — every method, every kwarg.

## Troubleshooting

- **`ModuleNotFoundError: No module named 'pystac_client'`** — install
  `[stac]`: `pip install 'geocatalog[stac]'`.
- **`PermissionError` from blob storage** — the signed URLs expire
  after ~1 hour. Re-run the STAC search to refresh them, or call
  `planetary_computer.sign(item)` again per scene.
- **Empty catalog** — Sentinel-2's `<20%` cloud filter is strict over
  Tahoe in mid-summer when smoke is around. Try `<40%`, or widen the
  time window.
- **Slow loads** — `load_raster` reads via HTTP-range from Azure;
  expect 1–3 seconds per scene on a typical home connection. Use the
  notebook's `stage()` flow to cache to local disk first.
