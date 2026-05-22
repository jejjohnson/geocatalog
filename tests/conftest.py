"""Shared fixtures for catalog tests — synthetic raster/vector files on disk."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import rasterio
from hypothesis import settings
from rasterio.transform import from_bounds


# Hypothesis profiles. The `default` profile is what runs locally; `ci`
# is selected via ``HYPOTHESIS_PROFILE=ci`` (set in the CI workflow) and
# derandomises example generation so a green run today proves the same
# inputs will pass tomorrow.
settings.register_profile("ci", settings(derandomize=True, deadline=None))
settings.register_profile(
    "dev",
    settings(deadline=None, print_blob=True),
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))


@pytest.fixture
def utm29_tile_factory(tmp_path: Path):
    """Build a small GeoTIFF with given bounds (UTM zone 29N) at 10 m res.

    Returns a `(bounds, date_str) -> path` callable so each test can
    populate ``tmp_path`` with the catalog files it needs.
    """

    def _make(
        bounds: tuple[float, float, float, float],
        date_str: str,
        *,
        n_bands: int = 3,
        value: int = 1,
        shape: tuple[int, int] = (32, 32),
    ) -> Path:
        xmin, ymin, xmax, ymax = bounds
        height, width = shape
        transform = from_bounds(xmin, ymin, xmax, ymax, width, height)
        path = tmp_path / f"S2_T29SND_{date_str}_{int(xmin)}_{int(ymin)}.tif"
        data = np.full((n_bands, height, width), value, dtype=np.uint16)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=n_bands,
            dtype="uint16",
            crs="EPSG:32629",
            transform=transform,
        ) as dst:
            dst.write(data)
        return path

    return _make
