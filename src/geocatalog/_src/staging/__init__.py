"""Staging layer — resolve remote URIs into local files.

Catalog ingestion (`Source.query` → `SourceRow`) does *not* download
data: it records URIs. Staging is the explicit step that pulls bytes
into a local cache and rewrites a catalog to point at those local
copies, ready to be opened by `load_raster` / `load_vector` /
`load_xarray`.

Current scaffolding (this PR):

* `LocalCache` — config carrier (root, ttl). Body is a plain
  dataclass; the documented default-root resolution lands in
  Phase 5.
* `stage` — orchestrator entry point. Raises `NotImplementedError`
  until Phase 5.

Planned modules (Phase 5, see ``docs/design/query-matchup.md`` §4.7):

* `staging/cache.py` — fsspec-backed cache, keyed by ``(uri, asset)``.
* `staging/download.py` — parallel fetch + retry / backoff (shared
  with the raster loaders' machinery from PR #51).
* `staging/gee.py` — `ee.Image.getDownloadURL` materialization.
"""

from __future__ import annotations

from geocatalog._src.staging._base import LocalCache, stage


__all__ = [
    "LocalCache",
    "stage",
]
