"""Tests for the grid-alignment feature (geopatcher#59).

Covers:

- `divide_evenly`: aligned passes, misaligned raises with the
  residual surfaced, custom ``tol`` honoured.
- `GeoSlice.align` modes: ``"off"`` is silent, ``"warn"`` logs,
  ``"error"`` raises, ``"snap"`` rounds outward.
- The `align` field does not participate in equality or hashing.
- `to_crs` does not self-trip the check even with ``align="error"``
  on the parent.
- `iter_slices` (in-memory backend) emits zero warnings on a
  misaligned catalog.
- `is_grid_aligned`: true / false / CRS-mismatch / ``explain``
  paths.
- `aligned_shape()` raises on misalignment regardless of mode.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest
from loguru import logger
from shapely.geometry import box

from geocatalog import (
    Align,
    GeoSlice,
    InMemoryGeoCatalog,
    divide_evenly,
    is_grid_aligned,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_slice(
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 100.0, 100.0),
    resolution: tuple[float, float] = (10.0, 10.0),
    *,
    align: Align = "off",
    crs: str = "EPSG:32629",
) -> GeoSlice:
    return GeoSlice(
        bounds=bounds,
        interval=pd.Interval(
            pd.Timestamp("2024-01-01"),
            pd.Timestamp("2024-01-02"),
            closed="both",
        ),
        resolution=resolution,
        crs=crs,
        align=align,
    )


@pytest.fixture
def loguru_sink():
    """Attach an in-memory loguru sink; yield (buf, sink_id)."""
    buf = io.StringIO()
    logger.enable("geocatalog")
    sink_id = logger.add(buf, level="TRACE", format="{level} | {message}")
    yield buf
    logger.remove(sink_id)
    logger.disable("geocatalog")


# ---------------------------------------------------------------------------
# divide_evenly
# ---------------------------------------------------------------------------


class TestDivideEvenly:
    def test_exact_returns_quotient(self) -> None:
        assert divide_evenly(100.0, 10.0) == 10

    def test_subpixel_misalignment_raises(self) -> None:
        with pytest.raises(ValueError, match="residual"):
            divide_evenly(100.5, 10.0, label="x-extent")

    def test_error_message_carries_label_and_step(self) -> None:
        with pytest.raises(ValueError, match=r"x-extent.*step=10\.0"):
            divide_evenly(100.5, 10.0, label="x-extent")

    def test_within_default_tol_passes(self) -> None:
        # PIXEL_PRECISION=3 → default tol = 1e-3, so residual 5e-4 passes.
        assert divide_evenly(100.0005, 10.00005) == 10

    def test_custom_tol_tightens(self) -> None:
        # 100.0005 / 10 = 10.00005 → round = 10; residual = -5e-4.
        # The default tol (1e-3) accepts it; a tight tol must reject.
        assert divide_evenly(100.0005, 10.0) == 10
        with pytest.raises(ValueError):
            divide_evenly(100.0005, 10.0, tol=1e-9)


# ---------------------------------------------------------------------------
# GeoSlice.align modes
# ---------------------------------------------------------------------------


class TestAlignModes:
    def test_off_is_silent_and_keeps_bounds(self) -> None:
        sl = _make_slice((0.0, 0.0, 105.0, 100.0), (10.0, 10.0), align="off")
        assert sl.bounds == (0.0, 0.0, 105.0, 100.0)

    def test_error_raises_on_misalignment(self) -> None:
        with pytest.raises(ValueError, match="x-extent"):
            _make_slice((0.0, 0.0, 105.0, 100.0), (10.0, 10.0), align="error")

    def test_warn_logs_and_keeps_bounds(
        self, loguru_sink: io.StringIO
    ) -> None:
        sl = _make_slice(
            (0.0, 0.0, 105.0, 100.0), (10.0, 10.0), align="warn"
        )
        assert sl.bounds == (0.0, 0.0, 105.0, 100.0)
        output = loguru_sink.getvalue()
        assert "WARNING" in output
        assert "x-extent" in output

    def test_warn_silent_when_aligned(
        self, loguru_sink: io.StringIO
    ) -> None:
        _make_slice((0.0, 0.0, 100.0, 100.0), (10.0, 10.0), align="warn")
        assert loguru_sink.getvalue() == ""

    def test_snap_rounds_outward(self) -> None:
        # 105 wide at 10m → ceil(10.5) = 11 → snap to 110.
        sl = _make_slice(
            (0.0, 0.0, 105.0, 100.0), (10.0, 10.0), align="snap"
        )
        assert sl.bounds == (0.0, 0.0, 110.0, 100.0)
        # The snapped slice must be aligned per the strict path.
        assert sl.aligned_shape() == (10, 11)

    def test_snap_preserves_origin(self) -> None:
        # snap mutates max edges only, never the origin.
        sl = _make_slice(
            (50.0, 50.0, 155.0, 100.0), (10.0, 10.0), align="snap"
        )
        assert sl.bounds[0] == 50.0
        assert sl.bounds[1] == 50.0


# ---------------------------------------------------------------------------
# align field does not participate in identity
# ---------------------------------------------------------------------------


class TestAlignNotInIdentity:
    def test_equal_across_modes(self) -> None:
        a = _make_slice(align="off")
        b = _make_slice(align="error")
        assert a == b

    def test_hash_equal_across_modes(self) -> None:
        a = _make_slice(align="off")
        b = _make_slice(align="warn")
        assert hash(a) == hash(b)

    def test_works_as_dict_key_after_switching_align(self) -> None:
        a = _make_slice(align="off")
        d = {a: "value"}
        b = _make_slice(align="error")
        assert d[b] == "value"

    def test_align_omitted_from_repr(self) -> None:
        sl = _make_slice(align="error")
        assert "align" not in repr(sl)


# ---------------------------------------------------------------------------
# to_crs interaction
# ---------------------------------------------------------------------------


class TestToCrsDoesNotSelfTrip:
    def test_to_crs_strict_parent_does_not_raise(self) -> None:
        sl = GeoSlice(
            bounds=(-10.0, 40.0, -8.0, 42.0),
            interval=pd.Interval(
                pd.Timestamp("2024-01-01"),
                pd.Timestamp("2024-01-02"),
                closed="both",
            ),
            resolution=(0.01, 0.01),
            crs="EPSG:4326",
            align="error",
        )
        # Reprojection generically yields non-integer multiples — must
        # not raise on its own output.
        out = sl.to_crs("EPSG:32629")
        # And the reprojected slice carries align="off" so further use
        # is silent too.
        assert out.align == "off"


# ---------------------------------------------------------------------------
# iter_slices emits zero warnings on misaligned catalogs
# ---------------------------------------------------------------------------


class TestIterSlicesQuiet:
    def test_inmemory_iter_slices_silent(
        self, loguru_sink: io.StringIO
    ) -> None:
        import geopandas as gpd

        # Arbitrary footprints that don't divide evenly at 30m.
        gdf = gpd.GeoDataFrame(
            {
                "filepath": ["a.tif", "b.tif"],
                "geometry": [
                    box(0.0, 0.0, 12345.6, 9876.5),
                    box(100.0, 100.0, 234.5, 678.9),
                ],
            },
            crs="EPSG:32629",
        )
        gdf.index = pd.IntervalIndex.from_tuples(
            [
                (pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")),
                (pd.Timestamp("2024-02-01"), pd.Timestamp("2024-02-02")),
            ],
            closed="both",
        )
        cat = InMemoryGeoCatalog(gdf, backend="raster")
        slices = list(cat.iter_slices(resolution=(30.0, 30.0)))
        assert len(slices) == 2
        # All emitted slices must carry align="off" so they are
        # silent and do not raise downstream.
        assert all(s.align == "off" for s in slices)
        assert "misalignment" not in loguru_sink.getvalue()


# ---------------------------------------------------------------------------
# is_grid_aligned
# ---------------------------------------------------------------------------


class TestIsGridAligned:
    def test_identical_slices_are_aligned(self) -> None:
        a = _make_slice((0.0, 0.0, 100.0, 100.0), (10.0, 10.0))
        b = _make_slice((0.0, 0.0, 100.0, 100.0), (10.0, 10.0))
        assert is_grid_aligned(a, b) is True

    def test_same_lattice_different_extent(self) -> None:
        # Origins differ by an integer multiple of resolution → aligned.
        a = _make_slice((0.0, 0.0, 100.0, 100.0), (10.0, 10.0))
        b = _make_slice((30.0, 20.0, 80.0, 90.0), (10.0, 10.0))
        assert is_grid_aligned(a, b) is True

    def test_origin_off_by_subpixel_not_aligned(self) -> None:
        a = _make_slice((0.0, 0.0, 100.0, 100.0), (10.0, 10.0))
        b = _make_slice((0.5, 0.0, 100.5, 100.0), (10.0, 10.0))
        assert is_grid_aligned(a, b) is False

    def test_resolution_mismatch_not_aligned(self) -> None:
        a = _make_slice((0.0, 0.0, 100.0, 100.0), (10.0, 10.0))
        b = _make_slice((0.0, 0.0, 100.0, 100.0), (5.0, 5.0))
        assert is_grid_aligned(a, b) is False

    def test_crs_mismatch_returns_false(self) -> None:
        a = _make_slice(crs="EPSG:32629")
        b = _make_slice(crs="EPSG:32630")
        assert is_grid_aligned(a, b) is False

    def test_explain_returns_diagnostic_dict(self) -> None:
        a = _make_slice((0.0, 0.0, 100.0, 100.0), (10.0, 10.0))
        b = _make_slice((0.5, 0.0, 100.5, 100.0), (10.0, 10.0))
        report = is_grid_aligned(a, b, explain=True)
        assert isinstance(report, dict)
        assert report["aligned"] is False
        assert report["x_res_match"] is True
        assert report["y_res_match"] is True
        # x origin off by a 0.5 subpixel residual (sign depends on
        # which side of the lattice the offset falls on).
        assert abs(abs(report["x_origin_residual"]) - 0.5) < 1e-9
        assert abs(report["y_origin_residual"]) < 1e-9

    def test_explain_flags_crs_mismatch(self) -> None:
        a = _make_slice(crs="EPSG:32629")
        b = _make_slice(crs="EPSG:32630")
        report = is_grid_aligned(a, b, explain=True)
        assert report["crs_match"] is False
        assert report["aligned"] is False


# ---------------------------------------------------------------------------
# aligned_shape
# ---------------------------------------------------------------------------


class TestAlignedShape:
    def test_passes_when_aligned(self) -> None:
        sl = _make_slice((0.0, 0.0, 100.0, 80.0), (10.0, 10.0), align="off")
        # (height, width) = (y/ry, x/rx)
        assert sl.aligned_shape() == (8, 10)

    def test_raises_regardless_of_align_off(self) -> None:
        sl = _make_slice((0.0, 0.0, 105.0, 100.0), (10.0, 10.0), align="off")
        with pytest.raises(ValueError, match="x-extent"):
            sl.aligned_shape()

    def test_matches_round_shape_when_aligned(self) -> None:
        sl = _make_slice((0.0, 0.0, 100.0, 80.0), (10.0, 10.0))
        assert sl.aligned_shape() == sl.shape


# ---------------------------------------------------------------------------
# Hybrid layout: new symbols available via geocatalog.types
# ---------------------------------------------------------------------------


class TestHybridLayoutExports:
    def test_types_subnamespace_reexports(self) -> None:
        import geocatalog
        from geocatalog import types as types_ns

        assert types_ns.divide_evenly is geocatalog.divide_evenly
        assert types_ns.is_grid_aligned is geocatalog.is_grid_aligned
        assert types_ns.Align is geocatalog.Align
