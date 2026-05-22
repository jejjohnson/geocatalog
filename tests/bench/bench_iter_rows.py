"""Benchmark for `iter_rows()` — the streaming claim from #4.

The in-memory backend's `iter_rows` materialises one `CatalogRow`
per gdf row; the cost-per-row is what we care about, not the total.
"""

from __future__ import annotations

import pytest

from geocatalog import InMemoryGeoCatalog

from .conftest import make_inmemory_catalog


@pytest.fixture(scope="module")
def medium_catalog() -> InMemoryGeoCatalog:
    """A 10⁴-row catalog reused across iter_rows benches."""
    return make_inmemory_catalog(10_000, seed=0)


def test_iter_rows_all(benchmark, medium_catalog) -> None:
    """Walk every row — drains the iterator into a counter."""

    def _drain() -> int:
        return sum(1 for _ in medium_catalog.iter_rows())

    benchmark(_drain)
