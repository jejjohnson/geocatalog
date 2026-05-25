"""Lightweight CMR REST adapter — no `earthaccess` dependency.

Direct calls to NASA's Common Metadata Repository search API. Useful
when:

- You don't want the full `earthaccess` dependency (no token broker,
  no DAAC presets) but still need to enumerate granules.
- You need fine-grained control over the CMR query parameters that
  `earthaccess` doesn't surface (provider, version, etc.).

Most users should prefer `EarthAccessSource`. This adapter trades
features (DAAC auto-discovery, S3 credentials) for footprint
(stdlib `urllib` + JSON).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import shapely.geometry
from loguru import logger

from geocatalog._src.sources._base import AuthStatus, Bounds, Source, SourceRow


# CMR public search root. Granule and collection endpoints branch
# off this path. The adapter uses `urllib` so no extras are needed.
_CMR_ROOT = "https://cmr.earthdata.nasa.gov/search"

# CMR caps a single request at 2000 results; for `limit=None` we
# paginate via `search-after` until exhausted.
_CMR_PAGE_SIZE = 2000


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
        self.endpoint = endpoint.rstrip("/")

    def query(
        self,
        bounds: Bounds,
        interval: pd.Interval | None = None,
        *,
        collection: str | None = None,
        filters: Mapping[str, Any] | None = None,
        limit: int | None = None,
    ) -> Iterator[SourceRow]:
        """Yield `SourceRow`s for CMR granules.

        Args:
            bounds: ``(xmin, ymin, xmax, ymax)`` in EPSG:4326.
            interval: Optional time window → ``temporal`` parameter.
            collection: CMR ``short_name``.
            filters: Forwarded directly as URL parameters. Useful for
                ``version``, ``provider``, ``platform``,
                ``cloud_cover[min]`` / ``cloud_cover[max]``, etc.
            limit: Cap on rows. ``None`` paginates all results.

        Yields:
            `SourceRow` per matching granule. Streamed via pagination
            so a large collection doesn't materialise in one chunk.
        """
        query_id = uuid.uuid4().hex
        fetched_at = datetime.now(tz=UTC)

        params: dict[str, Any] = {
            "bounding_box": ",".join(str(x) for x in bounds),
        }
        if collection is not None:
            params["short_name"] = collection
        if interval is not None:
            params["temporal"] = (
                f"{pd.Timestamp(interval.left).isoformat()},"
                f"{pd.Timestamp(interval.right).isoformat()}"
            )
        if filters:
            for k, v in filters.items():
                params[k] = v

        # Stream pages via the `search-after` header until done or
        # the user's limit is reached.
        emitted = 0
        search_after: str | None = None
        while True:
            page_size = (
                _CMR_PAGE_SIZE
                if limit is None
                else min(_CMR_PAGE_SIZE, max(limit - emitted, 1))
            )
            params["page_size"] = page_size
            url = f"{self.endpoint}/granules.umm_json?" + urllib.parse.urlencode(
                params, doseq=True
            )
            logger.debug("CMR GET: {!r}", url)
            data, next_search_after = _fetch_page(
                url, token=self.token, search_after=search_after
            )
            items = data.get("items", [])
            for item in items:
                row = _cmr_item_to_source_row(
                    item,
                    source_name=self.name,
                    query_id=query_id,
                    fetched_at=fetched_at,
                )
                if row is not None:
                    yield row
                    emitted += 1
                    if limit is not None and emitted >= limit:
                        return
            if not next_search_after or not items:
                break
            search_after = next_search_after

    def auth_status(self) -> AuthStatus:
        """Probe the CMR root.

        Anonymous queries against public collections always work,
        so "authenticated" here means "we can reach the endpoint".
        Token presence is reported via `detail`.
        """
        try:
            req = urllib.request.Request(
                f"{self.endpoint}/granules.umm_json?page_size=1"
            )
            if self.token:
                req.add_header("Authorization", f"Bearer {self.token}")
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                ok = resp.status == 200
        except Exception as exc:
            return AuthStatus(
                source=self.name,
                authenticated=False,
                detail=f"could not reach {self.endpoint}: {exc}",
            )
        return AuthStatus(
            source=self.name,
            authenticated=ok,
            detail=f"reachable at {self.endpoint}"
            + (" (token set)" if self.token else " (anonymous)"),
        )


# ---------------------------------------------------------------------------
# HTTP + UMM mapping helpers
# ---------------------------------------------------------------------------


def _fetch_page(
    url: str, *, token: str | None, search_after: str | None
) -> tuple[dict[str, Any], str | None]:
    """GET one CMR UMM-JSON page; return (body, next-search-after)."""
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if search_after:
        req.add_header("CMR-Search-After", search_after)
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        # CMR uses both Mixed-Case and lower-case header names
        # depending on the proxy in front; httplib normalises but
        # we accept either.
        next_after = resp.headers.get("CMR-Search-After") or resp.headers.get(
            "cmr-search-after"
        )
    return body, next_after


def _cmr_item_to_source_row(
    item: Mapping[str, Any],
    *,
    source_name: str,
    query_id: str,
    fetched_at: datetime,
) -> SourceRow | None:
    """Map a CMR UMM-JSON `items[...]` entry to a `SourceRow`.

    Uses the same geometry / interval / asset extraction logic as
    the `earthaccess` adapter; this mirrors the path because the
    UMM schema is the same regardless of which client you use to
    fetch it. We re-implement here to keep the adapters
    independent (no cross-import).
    """
    umm = item.get("umm")
    if not isinstance(umm, Mapping):
        return None
    granule_ur = str(umm.get("GranuleUR") or "<no-id>")
    geometry = _granule_geometry(umm)
    if geometry is None or geometry.is_empty:
        return None
    interval = _granule_interval(umm)
    if interval is None:
        return None

    # CMR's umm_json keeps download URLs under `RelatedUrls` with
    # Type == "GET DATA".
    assets: dict[str, str] = {}
    for link in umm.get("RelatedUrls", []) or []:
        if not isinstance(link, Mapping):
            continue
        if link.get("Type") != "GET DATA":
            continue
        url = link.get("URL")
        if not url:
            continue
        key = _asset_key_from_url(str(url))
        if key in assets:
            key = f"{key}__{len(assets)}"
        assets[key] = url

    collection_short_name = ""
    coll_ref = umm.get("CollectionReference", {})
    if isinstance(coll_ref, Mapping):
        collection_short_name = str(coll_ref.get("ShortName", "")) or ""

    properties: dict[str, Any] = {"umm": _umm_essentials(umm)}
    cloud_cover = _extract_cloud_cover(umm)
    if cloud_cover is not None:
        properties["eo:cloud_cover"] = cloud_cover

    return SourceRow(
        id=granule_ur,
        source=source_name,
        collection=collection_short_name,
        geometry=geometry,
        interval=interval,
        assets=assets,
        properties=properties,
        provenance={
            "query_id": query_id,
            "fetched_at": fetched_at.isoformat(),
            "source_version": "cmr/umm_json",
        },
    )


# Local copies of the helpers used by `earthaccess.py`. We
# deliberately don't reach across modules so the two adapters can
# evolve their granule decoders independently if CMR ever diverges
# from earthaccess's view.


def _granule_geometry(
    umm: Mapping[str, Any],
) -> shapely.geometry.base.BaseGeometry | None:
    spatial = umm.get("SpatialExtent")
    if not isinstance(spatial, Mapping):
        return None
    h = spatial.get("HorizontalSpatialDomain")
    if not isinstance(h, Mapping):
        return None
    geom = h.get("Geometry")
    if not isinstance(geom, Mapping):
        return None
    gpolys = geom.get("GPolygons")
    if gpolys:
        polys = []
        for poly in gpolys:
            boundary = poly.get("Boundary", {}) if isinstance(poly, Mapping) else {}
            points = boundary.get("Points") if isinstance(boundary, Mapping) else None
            if not points:
                continue
            ring = [(pt["Longitude"], pt["Latitude"]) for pt in points]
            if len(ring) >= 3:
                polys.append(shapely.geometry.Polygon(ring))
        if polys:
            return shapely.geometry.MultiPolygon(polys) if len(polys) > 1 else polys[0]
    rects = geom.get("BoundingRectangles")
    if rects:
        boxes = []
        for r in rects:
            if not isinstance(r, Mapping):
                continue
            try:
                boxes.append(
                    shapely.geometry.box(
                        r["WestBoundingCoordinate"],
                        r["SouthBoundingCoordinate"],
                        r["EastBoundingCoordinate"],
                        r["NorthBoundingCoordinate"],
                    )
                )
            except KeyError:
                continue
        if boxes:
            return shapely.geometry.MultiPolygon(boxes) if len(boxes) > 1 else boxes[0]
    points = geom.get("Points")
    if points:
        shapes = [
            shapely.geometry.Point(pt["Longitude"], pt["Latitude"])
            for pt in points
            if isinstance(pt, Mapping)
        ]
        if shapes:
            return shapely.geometry.MultiPoint(shapes) if len(shapes) > 1 else shapes[0]
    return None


def _granule_interval(umm: Mapping[str, Any]) -> pd.Interval | None:
    temporal = umm.get("TemporalExtent")
    if not isinstance(temporal, Mapping):
        return None
    rng = temporal.get("RangeDateTime")
    if isinstance(rng, Mapping):
        start = rng.get("BeginningDateTime")
        end = rng.get("EndingDateTime")
        if start and end:
            return pd.Interval(_to_utc(start), _to_utc(end), closed="both")
    single = temporal.get("SingleDateTime")
    if single:
        ts = _to_utc(single)
        return pd.Interval(ts, ts, closed="both")
    return None


def _to_utc(value: str | datetime) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _asset_key_from_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    leaf = (parsed.path.rstrip("/").rsplit("/", 1) or [""])[-1]
    if "." in leaf:
        stem, ext = leaf.rsplit(".", 1)
        if stem and len(stem) <= 64:
            return stem
        return ext or leaf
    return leaf or url[-32:]


def _extract_cloud_cover(umm: Mapping[str, Any]) -> float | None:
    if "CloudCover" in umm:
        try:
            return float(umm["CloudCover"])
        except (TypeError, ValueError):
            pass
    extras = umm.get("AdditionalAttributes", [])
    if isinstance(extras, list):
        for attr in extras:
            if isinstance(attr, Mapping) and attr.get("Name", "").lower().startswith(
                "cloud"
            ):
                values = attr.get("Values", [])
                if values:
                    try:
                        return float(values[0])
                    except (TypeError, ValueError):
                        pass
    return None


def _umm_essentials(umm: Mapping[str, Any]) -> dict[str, Any]:
    keep = (
        "GranuleUR",
        "CollectionReference",
        "DataGranule",
        "TemporalExtent",
        "ProviderDates",
        "Platforms",
        "AdditionalAttributes",
        "CloudCover",
        "MetadataSpecification",
    )
    return {k: umm[k] for k in keep if k in umm}
