"""Public API of the staging layer — scaffolding only.

The implementation will compose:

* `fsspec` for the URI -> local-file fetch, transparently handling
  ``s3://`` / ``gs://`` / ``https://``.
* The retry/backoff machinery from raster loaders (PR #51, in flight).
* A `concurrent.futures.ThreadPoolExecutor` for asset-level parallelism.

See ``docs/design/query-matchup.md`` §4.7.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from os import PathLike

    from geocatalog._src.base import GeoCatalog


@dataclasses.dataclass
class LocalCache:
    """fsspec-backed cache keyed by ``(uri, asset)``.

    Scaffolding stage: the constructor stores the values as-is.
    Phase 5 wires up the documented default-root resolution
    (``$GEOCATALOG_CACHE`` → ``~/.cache/geocatalog/``); until then,
    ``root`` stays whatever the caller passes (``None`` if omitted)
    and `stage()` is the gate that fails fast on the unimplemented
    backend.

    Args:
        root: Directory the cache lives under. ``None`` in the
            scaffolding phase; Phase 5 will resolve a default of
            ``$GEOCATALOG_CACHE`` or ``~/.cache/geocatalog/`` when
            not supplied.
        ttl_days: Optional lifetime; cache entries older than this
            are refetched. ``None`` means cache forever.
    """

    root: PathLike[str] | str | None = None
    ttl_days: int | None = None


def stage(
    catalog: GeoCatalog,
    *,
    dest: PathLike[str] | str,
    assets: list[str] | None = None,
    parallel: int = 8,
    cache: LocalCache | None = None,
    retries: int = 3,
) -> GeoCatalog:
    """Resolve every URI in ``catalog`` into a local file.

    Args:
        catalog: Catalog whose rows reference remote URIs.
        dest: Destination directory under which the cache lives.
        assets: Asset keys to fetch (``["red", "nir", "scl"]``).
            ``None`` means all assets present in the catalog.
        parallel: Max concurrent fetches.
        cache: Override the default cache location / policy.
        retries: Per-asset retry budget (passed to the retry/backoff
            machinery shared with the raster loaders).

    Returns:
        A new catalog whose ``assets`` column points at local paths,
        with the original URIs preserved under
        ``properties["_staged_from"]``.
    """
    raise NotImplementedError("stage() is scaffolding — Phase 5 PR; see design §4.7.")
