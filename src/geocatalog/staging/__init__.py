"""`geocatalog.staging` — resolve remote URIs into local files.

Hybrid-layout sub-namespace. Re-exports the `stage` orchestrator
and the `LocalCache` configuration carrier.

See ``docs/design/query-matchup.md`` §4.7.
"""

from __future__ import annotations

from geocatalog._src.staging import LocalCache, stage


__all__ = [
    "LocalCache",
    "stage",
]
