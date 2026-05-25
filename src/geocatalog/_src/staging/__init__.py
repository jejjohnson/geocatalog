"""Staging layer — resolve remote URIs into local files.

Catalog ingestion (`Source.query` → `SourceRow`) does *not* download
data: it records URIs. Staging is the explicit step that pulls bytes
into a local cache and rewrites a catalog to point at those local
copies, ready to be opened by `load_raster` / `load_vector` /
`load_xarray`.

Three pieces live here:

* `LocalCache` — fsspec-backed cache, keyed by ``(uri, asset)``.
* `stage` — orchestrator: walks a catalog, fans out asset downloads
  in parallel, returns a new catalog whose rows point at the cache.
* GEE-specific materialization (``staging/gee.py``) for the
  ``ee.Image.getDownloadURL`` path.

Scaffolding only — Phase 5 in the design's phasing.
"""

from __future__ import annotations

from geocatalog._src.staging._base import LocalCache, stage


__all__ = [
    "LocalCache",
    "stage",
]
