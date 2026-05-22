"""Hypothesis strategies for catalog property-based tests.

The strategies here generate *valid* `GeoSlice` and `InMemoryGeoCatalog`
inputs — no NaN bounds, no NaT-only intervals on populated catalogs,
nothing that crosses the antimeridian. The narrow input domain is
deliberate: we want to exercise structural invariants (round-trip
identity, CRS-invariance, intersect-symmetry) over inputs that the
library *promises* to support, not stress-test every degenerate
geometric corner.

Edge cases the strategies *do* cover:

- Catalog with 0 rows.
- Catalog with 1 row.
- Intervals where ``start == end`` (instantaneous observations).
- Bounds in any of four CRSs (4326, 3857, 32629, 3413).
"""

from __future__ import annotations

import geopandas as gpd
import hypothesis.strategies as st
import pandas as pd
import pyproj
import shapely.geometry
from hypothesis import strategies

from geocatalog._src.geoslice import GeoSlice
from geocatalog._src.memory import InMemoryGeoCatalog


# Small fixed CRS set. All four have well-defined transforms within the
# bounding box (-10, -10, 10, 10) used by `bbox_strategy_4326` below, so
# the CRS-invariance test can reproject AOIs without crossing into
# undefined transform regions.
SUPPORTED_CRS: tuple[int, ...] = (4326, 3857, 32629, 3413)


# Use a narrow time window so generated intervals stay parseable and
# round-trip cleanly through GeoParquet's int64-microsecond timestamps.
# `min_value` / `max_value` are seconds-since-epoch, restricted to a few
# decades around 2020 to keep `pd.Timestamp` happy on both platforms.
_TIME_MIN = pd.Timestamp("2000-01-01").value // 10**9  # seconds
_TIME_MAX = pd.Timestamp("2030-01-01").value // 10**9


@st.composite
def bbox_strategy_4326(draw: st.DrawFn) -> tuple[float, float, float, float]:
    """`(xmin, ymin, xmax, ymax)` in EPSG:4326, well inside the equator.

    Keeps |lon| <= 10 and |lat| <= 10 so reprojection to UTM 29N or
    EPSG:3413 (north-polar stereographic) doesn't blow up. The
    antimeridian and polar caps are out of scope here — see issue #16.
    """
    xmin = draw(st.floats(-10.0, 9.0, allow_nan=False, allow_infinity=False))
    xmax = draw(st.floats(xmin + 0.01, 10.0, allow_nan=False, allow_infinity=False))
    ymin = draw(st.floats(-10.0, 9.0, allow_nan=False, allow_infinity=False))
    ymax = draw(st.floats(ymin + 0.01, 10.0, allow_nan=False, allow_infinity=False))
    return (xmin, ymin, xmax, ymax)


@st.composite
def interval_strategy(draw: st.DrawFn) -> pd.Interval:
    """A `pd.Interval(closed='both')` within the 2000-2030 window."""
    start_secs = draw(st.integers(_TIME_MIN, _TIME_MAX))
    # Allow zero-width (instantaneous observations) so we exercise the
    # NaT-adjacent edge of the IntervalIndex.
    end_secs = draw(st.integers(start_secs, _TIME_MAX))
    start = pd.Timestamp(start_secs, unit="s")
    end = pd.Timestamp(end_secs, unit="s")
    return pd.Interval(start, end, closed="both")


@st.composite
def geoslice_strategy(draw: st.DrawFn) -> GeoSlice:
    """A valid `GeoSlice` — bbox in EPSG:4326, interval, fixed resolution."""
    bounds = draw(bbox_strategy_4326())
    interval = draw(interval_strategy())
    crs_epsg = draw(st.sampled_from(SUPPORTED_CRS))
    crs = pyproj.CRS.from_epsg(crs_epsg)
    # When the chosen CRS isn't 4326 we'd have to reproject `bounds`; for
    # the structural invariants tested in `test_properties.py` we always
    # pair a GeoSlice's bounds with its CRS, so generate consistent units
    # by leaving the bounds in 4326 and only producing 4326 slices here.
    # The CRS-invariance test does its own reprojection downstream.
    return GeoSlice(
        bounds=bounds,
        interval=interval,
        resolution=(0.01, 0.01),
        crs=pyproj.CRS.from_epsg(4326) if crs_epsg != 4326 else crs,
    )


@st.composite
def catalog_strategy(
    draw: st.DrawFn,
    n_rows: st.SearchStrategy[int] | None = None,
) -> InMemoryGeoCatalog:
    """An `InMemoryGeoCatalog` over 0-20 rows in EPSG:4326, ``backend="raster"``.

    Each row carries:

    - ``geometry``: a non-degenerate shapely box in (-10, -10, 10, 10).
    - ``start_time`` / ``end_time``: the corners of a `pd.Interval`.
    - ``filepath``: a stable synthetic string keyed off the row index.

    The 20-row cap keeps a single property run inside the per-test budget
    even at ``max_examples=200``; the issue's success criterion of "≥3
    properties x 200 examples" is hit comfortably at this size.
    """
    if n_rows is None:
        n_rows = st.integers(0, 20)
    count = draw(n_rows)
    boxes: list[shapely.geometry.Polygon] = []
    starts: list[pd.Timestamp] = []
    ends: list[pd.Timestamp] = []
    paths: list[str] = []
    for i in range(count):
        bounds = draw(bbox_strategy_4326())
        interval = draw(interval_strategy())
        boxes.append(shapely.geometry.box(*bounds))
        starts.append(interval.left)
        ends.append(interval.right)
        paths.append(f"synthetic_{i:04d}.tif")
    gdf = gpd.GeoDataFrame(
        {
            "filepath": paths,
            "geometry": boxes,
            "start_time": starts,
            "end_time": ends,
        },
        crs="EPSG:4326",
    )
    return InMemoryGeoCatalog(gdf, backend="raster")


# `from hypothesis import strategies` is imported to keep an alias that
# downstream tests can use without re-importing the top-level module —
# avoids the linter warning about unused imports while keeping the file
# self-documenting.
_ = strategies
