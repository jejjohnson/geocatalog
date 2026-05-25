"""`field_for()` — bridge a staged catalog to geopatcher `Field`s.

A staged catalog (the output of `stage()`) has its ``filepath`` /
``assets`` columns rewritten to local paths. The downstream pattern
in the design doc (§7) is to hand that catalog to ``geopatcher`` so
a `SpatialPatcher` can read patches:

    cat = stage(bundle.catalog)
    fields = field_for(cat, "red")          # one RasterField per row
    patcher.split(fields[0])

This helper saves the user from writing the per-row
``RasterioReader(...) → RasterField(...)`` shim by hand. It lives
under ``geocatalog._src.staging`` because the staged-asset column
rewrite is the precondition that makes path-based Field construction
meaningful.

`geopatcher` is a soft dependency — imports happen inside
`field_for` so a base `pip install geocatalog` is unaffected.
Users opt in via ``pip install 'geocatalog[patch]'`` (or by
installing geopatcher directly).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from geocatalog._src.base import GeoCatalog


_GEOPATCHER_HINT = (
    "field_for() requires geopatcher. Install with "
    "`pip install 'geocatalog[patch]'` or `pip install geopatcher`."
)


def field_for(
    catalog: GeoCatalog,
    asset: str | None = None,
    *,
    mode: str = "raster",
) -> list[Any]:
    """Build one geopatcher `Field` per row of a staged catalog.

    Args:
        catalog: A catalog whose rows reference local files. Typically
            the output of `stage()` — its ``filepath`` column (and
            ``assets`` JSON map, when present) point at cached copies
            already on disk.
        asset: Which asset key to read for each row. ``None`` falls
            back to the row's ``filepath`` column — the right default
            for catalogs built by `build_raster_catalog` (which don't
            carry an asset map). When a string is passed, the per-row
            ``assets`` JSON dict is consulted; rows that do not carry
            that key raise `KeyError`.
        mode: Field flavor. ``"raster"`` (the only value supported
            today) wraps each path in a `RasterioReader` and then a
            `RasterField`. Reserved for future expansion to vector /
            xarray fields.

    Returns:
        A list of geopatcher `Field` instances in catalog row order.
        Single-row catalogs return a single-element list; the caller
        unpacks. A future multi-raster `Field` constructor in
        geopatcher would let this return one composite Field; the
        list-of-Fields shape is the truthful bridge until then.

    Raises:
        ImportError: If geopatcher is not installed.
        ValueError: If ``mode`` is not a supported flavor, or if the
            catalog is empty.
        KeyError: If ``asset`` is a string and any row's asset map
            does not contain that key. Catalogs where staging dropped
            a key under ``on_error="skip"`` will still surface here —
            the row's local path simply isn't available.
    """
    try:
        from geopatcher import RasterField
        from georeader.rasterio_reader import RasterioReader
    except ImportError as exc:  # pragma: no cover - exercised via patched sys.modules
        raise ImportError(_GEOPATCHER_HINT) from exc

    if mode != "raster":
        raise ValueError(f"field_for(mode={mode!r}): only 'raster' is supported today.")
    if len(catalog) == 0:
        raise ValueError("field_for: catalog is empty; nothing to wrap.")

    paths = _resolve_paths(catalog, asset=asset)
    return [RasterField(RasterioReader(p)) for p in paths]


def _resolve_paths(catalog: GeoCatalog, *, asset: str | None) -> list[str]:
    """Pull one local path per row, either ``filepath`` or assets[asset].

    When ``asset is None`` the function returns the ``filepath`` column
    verbatim; when ``asset`` is a string it decodes each row's JSON
    asset map and pulls the matching key, raising `KeyError` on the
    first row that is missing it.
    """
    gdf = catalog.gdf
    if asset is None:
        if "filepath" not in gdf.columns:
            raise KeyError(
                "field_for(asset=None) needs a 'filepath' column; "
                f"catalog columns: {list(gdf.columns)}"
            )
        return [str(p) for p in gdf["filepath"].tolist()]

    if "assets" not in gdf.columns:
        raise KeyError(
            f"field_for(asset={asset!r}) needs an 'assets' column on "
            "the catalog; did you forget to stage() first, or pass "
            "`asset=None` to use `filepath`?"
        )

    out: list[str] = []
    for row_idx, blob in enumerate(gdf["assets"].tolist()):
        if not isinstance(blob, str) or not blob:
            raise KeyError(
                f"field_for: row {row_idx} has no asset map; "
                f"can't resolve asset {asset!r}."
            )
        try:
            decoded = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise KeyError(
                f"field_for: row {row_idx} asset map is not valid JSON "
                f"({exc}); can't resolve asset {asset!r}."
            ) from exc
        if not isinstance(decoded, dict) or asset not in decoded:
            available = sorted(decoded) if isinstance(decoded, dict) else []
            raise KeyError(
                f"field_for: row {row_idx} has no asset {asset!r}; "
                f"available: {available}"
            )
        out.append(str(decoded[asset]))
    return out


__all__ = ["field_for"]
