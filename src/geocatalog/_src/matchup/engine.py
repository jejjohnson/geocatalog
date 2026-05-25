"""Matchup engine and `MatchupRow` carrier.

The engine takes a populated `GeoCatalog`, a primary / secondary
selector, and spatial + temporal strategies; it emits `MatchupRow`
instances ready to be persisted into ``matchups.parquet`` next to
``items.parquet``.

Scaffolding only — see ``docs/design/query-matchup.md`` §4.4 / §4.6.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Mapping
from typing import TYPE_CHECKING, Any, Literal


if TYPE_CHECKING:
    from datetime import datetime

    import shapely.geometry.base

    from geocatalog._src.base import GeoCatalog
    from geocatalog._src.matchup.spatial import SpatialStrategy
    from geocatalog._src.matchup.temporal import TemporalStrategy


# A `Selector` filters the catalog before joining: ``{"source":
# "earthaccess", "collection": "MOD09GA"}``. Empty dict matches all.
Selector = Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class MatchupRow:
    """A single matched tuple persisted to ``matchups.parquet``.

    The catalog of MatchupRows is itself a `GeoCatalog` — its
    geometry column is the common-footprint intersection, and its
    interval is the union of member intervals — so downstream code
    can query it with the same ``query(bounds, interval)`` calls as
    any other catalog. See design §4.4.

    Attributes:
        matchup_id: Stable identifier (uuid4 hex).
        strategy: Concise label naming the spatial + temporal
            strategies used (``"iou>=0.2 & nearest_in_time<=6h"``).
        member_ids: Parallel arrays with ``member_sources`` and
            ``member_roles``. ``member_ids[0]`` is always the primary.
        member_sources: ``SourceRow.source`` values for each member.
        member_roles: Role tags — ``"primary"``, ``"secondary"``, or
            user-defined names for N-way matchups.
        geometry_intersect: Common footprint (in catalog target CRS).
        time_reference: Reference timestamp the offsets are measured
            from — by convention the primary's interval midpoint.
        time_offset_sec: Parallel to ``member_ids``; offset of each
            member's interval midpoint relative to ``time_reference``.
        tolerance: Serialized strategy parameters, suitable for
            re-running the matchup deterministically.
        query_set: Optional user label, persisted as the
            ``query_set`` column in ``matchups.parquet`` so
            ``geocatalog stage --matchup-tag <name>`` can select a
            named set. Mirrors the ``tag`` argument of `matchup()`.
    """

    matchup_id: str
    strategy: str
    member_ids: tuple[str, ...]
    member_sources: tuple[str, ...]
    member_roles: tuple[str, ...]
    geometry_intersect: shapely.geometry.base.BaseGeometry
    time_reference: datetime
    time_offset_sec: tuple[float, ...]
    tolerance: Mapping[str, Any] = dataclasses.field(default_factory=dict)
    query_set: str | None = None


def matchup(
    catalog: GeoCatalog,
    *,
    primary: Selector,
    secondary: Selector | list[Selector],
    spatial: SpatialStrategy,
    temporal: TemporalStrategy,
    join: Literal["all", "any"] = "all",
    tag: str | None = None,
) -> Iterator[MatchupRow]:
    """Find matching tuples of catalog rows.

    Args:
        catalog: Populated catalog to join against itself.
        primary: Filter dict picking the primary rows
            (e.g. ``{"source": "earthaccess", "collection": "MOD09GA"}``).
        secondary: One filter (pairwise matchup) or a list (N-way).
        spatial: Strategy deciding spatial matches.
        temporal: Strategy deciding temporal matches.
        join: ``"all"`` requires every secondary group to contribute;
            ``"any"`` emits rows missing some members (handy for
            opportunistic fusion).
        tag: Optional user label persisted as ``query_set`` so a CLI
            user can ``--matchup-tag foo`` later.

    Yields:
        `MatchupRow` instances. The caller persists them to
        ``matchups.parquet`` via the catalog's writer.
    """
    raise NotImplementedError("matchup() is scaffolding — Phase 2 PR; see design §4.6.")
