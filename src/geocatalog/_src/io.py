"""Internal path resolution helpers for local paths and cloud URIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


_FSSPEC_SCHEMES = frozenset(
    {
        "s3",
        "gs",
        "gcs",
        "az",
        "azure",
        "http",
        "https",
        "hf",
    }
)


def _uri_scheme(path: str | Path) -> str:
    """Return the lower-case URI scheme for ``path`` if it has one."""
    return urlsplit(str(path)).scheme.lower()


def _is_fsspec_uri(path: str | Path) -> bool:
    """Return True for cloud/HTTP URI schemes handled through fsspec."""
    return _uri_scheme(path) in _FSSPEC_SCHEMES


def _uri_name(path: str | Path) -> str:
    """Return the filename component without mangling URI schemes."""
    parsed = urlsplit(str(path))
    if parsed.scheme:
        return Path(parsed.path).name
    return Path(path).name


def _resolve_uri(
    path: str | Path,
    *,
    storage_options: dict[str, Any] | None = None,
) -> str | Path | Any:
    """Resolve ``path`` to a local path or an fsspec binary file handle.

    Local paths pass through unchanged. Recognised cloud/HTTP URIs are opened
    with fsspec so downstream libraries can consume a normal seekable file-like
    object.
    """
    if not _is_fsspec_uri(path):
        return path
    try:
        import fsspec
    except ImportError as exc:
        scheme = _uri_scheme(path)
        raise ImportError(
            f"Reading {scheme!r} URIs requires the [fsspec] extra; install via "
            "`pip install 'geocatalog[fsspec]'`."
        ) from exc
    return fsspec.open(str(path), mode="rb", **(storage_options or {})).open()


def _close_resolved_uri(resolved: Any) -> None:
    """Close a resolved fsspec handle; local str/Path inputs are no-ops."""
    close = getattr(resolved, "close", None)
    if callable(close):
        close()
