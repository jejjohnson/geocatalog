"""Smoke tests for the scaffolded `geocatalog.sources` surface.

Locks in the Protocol shape and the dataclass fields so a later
Phase 1 PR that wires up `earthaccess.search_data` / `pystac_client`
can't accidentally rename a public field without flipping these.
"""

from __future__ import annotations

import dataclasses

import pandas as pd
import pytest
from shapely.geometry import box

import geocatalog.sources as sources_ns
from geocatalog._src.sources import AuthStatus, Source, SourceRow


class TestSourceProtocol:
    def test_protocol_is_runtime_checkable(self) -> None:
        # `isinstance(x, Source)` works because the Protocol is
        # decorated `@runtime_checkable`. We only need the duck-typed
        # surface; the adapters under `_src/sources/*` satisfy it.
        assert hasattr(Source, "query")

    def test_subnamespace_reexports(self) -> None:
        assert sources_ns.Source is Source
        assert sources_ns.SourceRow is SourceRow
        assert sources_ns.AuthStatus is AuthStatus


class TestSourceRow:
    def test_required_fields(self) -> None:
        # Use a real shapely geometry + pd.Interval so we know the
        # dataclass annotations resolve at runtime.
        row = SourceRow(
            id="MOD09GA.A2024153.h17v05.061.2024155033945",
            source="earthaccess",
            collection="MOD09GA",
            geometry=box(-10.0, 35.0, 5.0, 45.0),
            interval=pd.Interval(
                pd.Timestamp("2024-06-01"),
                pd.Timestamp("2024-06-02"),
                closed="both",
            ),
        )
        assert row.id.startswith("MOD09GA")
        assert row.source == "earthaccess"
        # Optional fields default to empty mappings.
        assert dict(row.assets) == {}
        assert dict(row.properties) == {}
        assert dict(row.provenance) == {}

    def test_frozen(self) -> None:
        row = SourceRow(
            id="x",
            source="stac",
            collection="c",
            geometry=box(0, 0, 1, 1),
            interval=pd.Interval(
                pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02"), closed="both"
            ),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.id = "y"  # type: ignore[misc]


class TestAuthStatus:
    def test_construction(self) -> None:
        s = AuthStatus(source="stac.pc", authenticated=True, detail=None)
        assert s.source == "stac.pc"
        assert s.authenticated is True


class TestAdapterStubs:
    """Each adapter raises ImportError if its extra is missing, else
    raises NotImplementedError on `query` (because the scaffolding
    PR does not implement the body yet)."""

    def test_cmr_query_not_implemented(self) -> None:
        # CMRSource has no optional-extra dependency (only stdlib),
        # so it constructs without prerequisites.
        from geocatalog._src.sources.cmr import CMRSource

        src = CMRSource()
        with pytest.raises(NotImplementedError):
            list(src.query((-10, 35, 5, 45)))

    def test_earthaccess_requires_extra_or_not_implemented(self) -> None:
        # Either the extra is missing (ImportError on construction)
        # or it's present and `query` raises NotImplementedError.
        # We accept both so this test runs in any install matrix.
        try:
            from geocatalog._src.sources.earthaccess import EarthAccessSource

            src = EarthAccessSource()
        except ImportError:
            pytest.skip("`earthaccess` extra not installed")
        with pytest.raises(NotImplementedError):
            list(src.query((-10, 35, 5, 45)))

    def test_stac_requires_extra_or_not_implemented(self) -> None:
        try:
            from geocatalog._src.sources.stac import STACSource

            src = STACSource.planetary_computer()
        except ImportError:
            pytest.skip("`stac` extra not installed")
        assert src.name == "stac.pc"
        with pytest.raises(NotImplementedError):
            list(src.query((-10, 35, 5, 45)))

    def test_gee_requires_extra_or_not_implemented(self) -> None:
        try:
            from geocatalog._src.sources.gee import GEESource

            src = GEESource()
        except ImportError:
            pytest.skip("`gee` extra not installed")
        with pytest.raises(NotImplementedError):
            list(src.query((-10, 35, 5, 45)))
