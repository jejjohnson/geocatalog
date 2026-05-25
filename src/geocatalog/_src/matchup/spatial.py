"""Spatial matchup strategies.

A `SpatialStrategy` decides "does the secondary row spatially match
the primary?" given two footprints. Strategies are dataclasses so
they round-trip through the persisted ``matchups.parquet`` table's
``tolerance_json`` column without bespoke serialization code.

Scaffolding only — the ``match`` method raises `NotImplementedError`
until the Phase 2 engine PR fills in the shapely + DuckDB
implementations.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Protocol, runtime_checkable


if TYPE_CHECKING:
    import shapely.geometry.base


@runtime_checkable
class SpatialStrategy(Protocol):
    """A predicate over two footprints.

    The engine calls ``match(primary, secondary)`` for each candidate
    pair. Strategies that translate cleanly to SQL (e.g. plain
    intersection) expose a ``sql_predicate`` template that the
    engine prefers over the Python path for performance; the
    Protocol's contract is just ``match``.
    """

    def match(
        self,
        primary: shapely.geometry.base.BaseGeometry,
        secondary: shapely.geometry.base.BaseGeometry,
    ) -> bool: ...


@dataclasses.dataclass(frozen=True)
class Intersects:
    """Non-zero geometric intersection (the cheapest predicate)."""

    def match(self, primary, secondary) -> bool:
        raise NotImplementedError("Phase 2 PR — see design §4.6.")


@dataclasses.dataclass(frozen=True)
class IouAtLeast:
    """Intersection-over-union ≥ ``threshold``.

    Stricter than plain intersection — useful when you want the
    secondary to *substantially* overlap the primary (e.g. for
    training-data quality gates).

    Args:
        threshold: Minimum IoU in ``[0, 1]``.
    """

    threshold: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(
                f"IouAtLeast.threshold must be in [0, 1]; got {self.threshold!r}"
            )

    def match(self, primary, secondary) -> bool:
        raise NotImplementedError("Phase 2 PR — see design §4.6.")


@dataclasses.dataclass(frozen=True)
class CentroidWithin:
    """Secondary centroid falls within a buffered primary footprint.

    Args:
        buffer: Buffer applied to the primary footprint before the
            point-in-polygon test. A float is taken to be in the
            catalog's CRS units; a string like ``"5km"`` is parsed
            into a distance using `pyproj`.
    """

    buffer: float | str

    def match(self, primary, secondary) -> bool:
        raise NotImplementedError("Phase 2 PR — see design §4.6.")


@dataclasses.dataclass(frozen=True)
class Contains:
    """Secondary footprint is fully contained in the primary."""

    def match(self, primary, secondary) -> bool:
        raise NotImplementedError("Phase 2 PR — see design §4.6.")
