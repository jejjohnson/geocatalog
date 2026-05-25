"""Temporal matchup strategies.

A `TemporalStrategy` decides "does the secondary row temporally
match the primary?" Three families are persisted across the
``matchups.parquet`` ``strategy`` / ``tolerance_json`` columns:

* `NearestInTime` — pick the secondary nearest in time within Δt;
  produces at most one secondary per primary.
* `WithinWindow` — every secondary whose interval falls within a
  ``[t + start, t + end]`` window around the primary.
* `Synchronous` — overlapping observation intervals (within an
  optional tolerance).

Scaffolding only — Phase 2 PR fills in the implementations.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol, runtime_checkable


if TYPE_CHECKING:
    import pandas as pd


@runtime_checkable
class TemporalStrategy(Protocol):
    """A predicate / selector over two time intervals.

    Some strategies are *predicates* (yes/no, e.g. `Synchronous`);
    others are *selectors* (pick the best, e.g. `NearestInTime`).
    The engine treats both uniformly by asking the strategy to
    enumerate matching secondaries from a candidate list.
    """

    def filter(
        self,
        primary: pd.Interval,
        candidates: pd.IntervalIndex,
    ) -> pd.IntervalIndex:
        """Return the subset of candidates that match the primary."""
        ...


@dataclasses.dataclass(frozen=True)
class NearestInTime:
    """Pick the secondary nearest in time within ``dt``.

    "Nearest" is measured between interval midpoints. If the nearest
    is still further than ``dt`` away, no secondary is emitted.

    Args:
        dt: Maximum allowed time offset, e.g. ``timedelta(hours=6)``
            or the string ``"6h"`` (parsed via `pd.Timedelta`).
    """

    dt: timedelta | str

    def filter(
        self,
        primary: pd.Interval,
        candidates: pd.IntervalIndex,
    ) -> pd.IntervalIndex:
        raise NotImplementedError("Phase 2 PR — see design §4.6.")


@dataclasses.dataclass(frozen=True)
class WithinWindow:
    """All secondaries whose interval falls in ``[t + start, t + end]``.

    Useful for "give me everything within ±12 h of each primary".
    ``start`` is typically negative (look back); ``end`` positive
    (look forward).

    Args:
        start: Offset from primary interval start. Negative looks back.
        end: Offset from primary interval end. Positive looks forward.
    """

    start: timedelta | str
    end: timedelta | str

    def filter(
        self,
        primary: pd.Interval,
        candidates: pd.IntervalIndex,
    ) -> pd.IntervalIndex:
        raise NotImplementedError("Phase 2 PR — see design §4.6.")


@dataclasses.dataclass(frozen=True)
class Synchronous:
    """Overlapping intervals (within an optional tolerance).

    Equivalent to `WithinWindow(start=-tolerance, end=+tolerance)`
    but expressed as a single tolerance so it round-trips cleanly
    in the persisted ``tolerance_json``.

    Args:
        tolerance: Slack on either side of the primary interval.
            ``"0s"`` enforces strict overlap.
    """

    tolerance: timedelta | str = "0s"

    def filter(
        self,
        primary: pd.Interval,
        candidates: pd.IntervalIndex,
    ) -> pd.IntervalIndex:
        raise NotImplementedError("Phase 2 PR — see design §4.6.")
