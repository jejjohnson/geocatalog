"""NASA `earthaccess` adapter — CMR-backed granule discovery.

Wraps the upstream `earthaccess` library so a single
``EarthAccessSource(...).query(bounds, interval)`` call returns
normalized `SourceRow` instances regardless of collection.

Scaffolding only — `query` raises `NotImplementedError`. The Phase 1
PR fills in the upstream `earthaccess.search_data` call, footprint
decoding, and pagination. See ``docs/design/query-matchup.md`` §4.2.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any

from geocatalog._src.sources._base import AuthStatus, Bounds, Source, SourceRow
from geocatalog._src.sources._extras import _missing_extra


if TYPE_CHECKING:
    import pandas as pd


try:
    import earthaccess
except ImportError:
    earthaccess = None  # type: ignore[assignment]


class EarthAccessSource(Source):
    """NASA CMR / earthaccess data discovery.

    Construct without arguments; authentication is handled by the
    underlying `earthaccess` library (`earthaccess.login()` or a
    netrc / token in the standard locations). Call ``auth_status``
    to check whether credentials are usable.

    Args:
        daac: Optional DAAC short-name filter (e.g. ``"LPDAAC"``).
            Defaults to None (search all DAACs).
    """

    name = "earthaccess"

    def __init__(self, *, daac: str | None = None) -> None:
        if earthaccess is None:
            raise _missing_extra(
                "EarthAccessSource", "earthaccess", "earthaccess>=0.10"
            )
        self.daac = daac

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
            "EarthAccessSource.query is scaffolding — see "
            "docs/design/query-matchup.md §4.2 and the Phase 1 PR."
        )

    def auth_status(self) -> AuthStatus:
        raise NotImplementedError(
            "EarthAccessSource.auth_status is scaffolding — see Phase 1 PR."
        )
