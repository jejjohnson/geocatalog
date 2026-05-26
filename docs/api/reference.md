# `geocatalog` — API Reference

Curated mkdocstrings reference. For the conceptual walkthrough see
[Concepts](../concepts.md); for a worked example see the
[Quickstart](../quickstart.md).

## Cross-cutting type

::: geocatalog._src.geoslice.GeoSlice
::: geocatalog._src.geoslice.slice_to_window
::: geocatalog._src.geoslice.window_to_slice

## Protocol

::: geocatalog._src.base.GeoCatalog
::: geocatalog._src.base.CatalogRow

## Backends

::: geocatalog._src.memory.InMemoryGeoCatalog

### DuckDB *(extras: `[duckdb]`)*

::: geocatalog._src.duckdb_backend.DuckDBGeoCatalog

## Factory

::: geocatalog.open_catalog

## Raster

::: geocatalog._src.raster.build_raster_catalog
::: geocatalog._src.raster.load_raster
::: geocatalog._src.raster.load_raster_timeseries

## Xarray *(extras: `[xarray-raster]`)*

::: geocatalog._src.xarray_backend.build_xarray_catalog
::: geocatalog._src.xarray_backend.load_xarray

## Vector

::: geocatalog._src.vector.build_vector_catalog
::: geocatalog._src.vector.load_vector

## Set algebra

::: geocatalog._src.ops.query
::: geocatalog._src.ops.intersect
::: geocatalog._src.ops.union

## GeoParquet roundtrip

::: geocatalog._src.parquet.to_geoparquet
::: geocatalog._src.parquet.from_geoparquet

## Bridge to a patcher

::: geocatalog._src.domain.CatalogDomain
