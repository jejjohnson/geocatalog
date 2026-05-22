"""Tests for internal URI resolution helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from geocatalog._src.io import _close_resolved_uri, _resolve_uri, _uri_name


def test_resolve_uri_local_path_passthrough(tmp_path: Path) -> None:
    path = tmp_path / "tile.tif"

    assert _resolve_uri(path) == path


def test_resolve_uri_requires_fsspec_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "fsspec", None)

    with pytest.raises(ImportError, match=r"geocatalog\[fsspec\]"):
        _resolve_uri("s3://bucket/key.tif")


def test_resolve_uri_forwards_storage_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    class DummyFile:
        closed = False

        def close(self) -> None:
            self.closed = True

    handle = DummyFile()

    class DummyOpenFile:
        def open(self) -> DummyFile:
            return handle

    def fake_open(path: str, mode: str, **kwargs: object) -> DummyOpenFile:
        calls.append((path, mode, kwargs))
        return DummyOpenFile()

    monkeypatch.setitem(sys.modules, "fsspec", SimpleNamespace(open=fake_open))

    resolved = _resolve_uri("s3://bucket/key.tif", storage_options={"anon": True})

    assert resolved is handle
    assert calls == [("s3://bucket/key.tif", "rb", {"anon": True})]
    _close_resolved_uri(resolved)
    assert handle.closed


def test_uri_name_handles_cloud_paths() -> None:
    assert _uri_name("s3://bucket/prefix/S2_T29SND_20240115.tif") == (
        "S2_T29SND_20240115.tif"
    )
