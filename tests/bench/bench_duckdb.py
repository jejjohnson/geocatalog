"""Benchmarks for `DuckDBGeoCatalog` (#21).

Tracks predicate-pushdown query latency on a 10⁵-row GeoParquet
artifact. The whole module is gated on the `[duckdb]` extra — when
the extra isn't installed we skip rather than crash, so the
default bench job still runs cleanly.
"""

from __future__ import annotations

import pytest

from geocatalog import to_geoparquet

from .conftest import make_inmemory_catalog


# Lazy import — the module is collected even without the extra, but
# every test below is `skip`-guarded if `duckdb` failed to import.
try:
    from geocatalog._src.duckdb_backend import DuckDBGeoCatalog

    _HAS_DUCKDB = True
except ImportError:
    _HAS_DUCKDB = False
    DuckDBGeoCatalog = None  # type: ignore[assignment, misc]


pytestmark = pytest.mark.skipif(
    not _HAS_DUCKDB,
    reason="DuckDB extra not installed; install with `geocatalog[duckdb]`.",
)


_N_MEDIUM = 100_000


@pytest.fixture(scope="module")
def duckdb_catalog(tmp_path_factory: pytest.TempPathFactory):
    """Persist a 10⁵-row in-memory catalog as GeoParquet and reopen via DuckDB."""
    path = tmp_path_factory.mktemp("bench_duckdb") / "catalog.parquet"
    mem = make_inmemory_catalog(_N_MEDIUM, seed=0)
    to_geoparquet(mem, path)
    return DuckDBGeoCatalog.open(path)


def test_duckdb_query_small_aoi(benchmark, duckdb_catalog) -> None:
    """Small-AOI query — exercises the GeoParquet 1.1 bbox-pushdown path."""
    benchmark(
        duckdb_catalog.query,
        bounds=(0.0, 0.0, 1.0, 1.0),
        crs="EPSG:4326",
    )
