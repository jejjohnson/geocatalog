"""Lightweight CMR REST adapter — no `earthaccess` dependency.

Direct calls to NASA's Common Metadata Repository search API. Useful
when:

- You don't want the full `earthaccess` dependency (no token broker,
  no DAAC presets) but still need to enumerate granules.
- You need fine-grained control over the CMR query parameters that
  `earthaccess` doesn't surface (provider, version, etc.).

Most users should prefer `EarthAccessSource`. Scaffolding only.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from geocatalog._src.sources._base import AuthStatus, Bounds, Source, SourceRow


if TYPE_CHECKING:
    import pandas as pd


# CMR public search root. Granule and collection endpoints branch
# off this path. The adapter uses `urllib` so no extras are needed.
_CMR_ROOT = "https://cmr.earthdata.nasa.gov/search"


class CMRSource(Source):
    """Direct CMR REST adapter.

    Construct without arguments. Anonymous queries cover most public
    collections; restricted ones need an EDL bearer token via the
    ``token`` argument.

    Args:
        token: Optional EDL bearer token for protected collections.
        endpoint: CMR root URL — override for non-prod environments.
    """

    name = "cmr"

    def __init__(
        self,
        *,
        token: str | None = None,
        endpoint: str = _CMR_ROOT,
    ) -> None:
        self.token = token
        self.endpoint = endpoint

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
            "CMRSource.query is scaffolding — see "
            "docs/design/query-matchup.md §4.2 and the Phase 1 PR."
        )

    def auth_status(self) -> AuthStatus:
        raise NotImplementedError(
            "CMRSource.auth_status is scaffolding — see Phase 1 PR."
        )
