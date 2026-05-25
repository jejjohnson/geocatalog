"""STAC API adapter — generic, with named-provider factory helpers.

A single ``STACSource(endpoint=...)`` covers any STAC-compliant
catalog: Microsoft Planetary Computer, Earth Search, the
USGS Landsat Look catalog, NASA HLS, in-house deployments. Two
class-method factories — ``STACSource.planetary_computer()`` and
``STACSource.earth_search()`` — are conveniences for the most common
endpoints and arrange any provider-specific auth (e.g. the Planetary
Computer SAS-token signing).

Scaffolding only — `query` raises `NotImplementedError`. The Phase 1
PR fills in the `pystac-client` ``search`` call, CQL-2 filter
forwarding, and asset URL signing.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from geocatalog._src.sources._base import AuthStatus, Bounds, Source, SourceRow
from geocatalog._src.sources._extras import _missing_extra


if TYPE_CHECKING:
    import pandas as pd


try:
    import pystac_client
except ImportError:
    pystac_client = None  # type: ignore[assignment]


# Public well-known STAC endpoints. Kept here so the factory methods
# stay readable; users can always pass a custom URL.
_PC_ENDPOINT = "https://planetarycomputer.microsoft.com/api/stac/v1"
_EARTH_SEARCH_ENDPOINT = "https://earth-search.aws.element84.com/v1"


class STACSource(Source):
    """STAC API data discovery.

    Args:
        endpoint: Root STAC API URL (the catalog landing page).
        sign_assets: If ``True``, sign asset URLs on access (needed
            for Planetary Computer's blob-storage tokens). Defaults
            to whatever the factory method sets.
        name: Stable adapter identifier. Defaults to ``"stac"``;
            factories override with ``"stac.pc"``, ``"stac.es"``.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        sign_assets: bool = False,
        name: str = "stac",
    ) -> None:
        if pystac_client is None:
            raise _missing_extra(
                "STACSource", "stac", "pystac-client>=0.7 planetary-computer>=1.0"
            )
        self.endpoint = endpoint
        self.sign_assets = sign_assets
        self.name = name

    @classmethod
    def planetary_computer(cls) -> STACSource:
        """Microsoft Planetary Computer — signs blob URLs automatically."""
        return cls(_PC_ENDPOINT, sign_assets=True, name="stac.pc")

    @classmethod
    def earth_search(cls) -> STACSource:
        """Element 84 Earth Search — public AWS-hosted Sentinel/Landsat."""
        return cls(_EARTH_SEARCH_ENDPOINT, sign_assets=False, name="stac.es")

    def query(
        self,
        bounds: Bounds,
        interval: pd.Interval | None = None,
        *,
        collection: str | None = None,
        filters: Mapping[str, Any] | None = None,
        limit: int | None = None,
    ) -> Iterator[SourceRow]:
        raise NotImplementedError(
            "STACSource.query is scaffolding — see "
            "docs/design/query-matchup.md §4.2 and the Phase 1 PR."
        )

    def auth_status(self) -> AuthStatus:
        raise NotImplementedError(
            "STACSource.auth_status is scaffolding — see Phase 1 PR."
        )
