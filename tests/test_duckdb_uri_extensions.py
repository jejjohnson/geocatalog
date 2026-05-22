"""Unit tests for DuckDB URI extension setup."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import geocatalog._src.duckdb_backend as duckdb_backend
from geocatalog import DuckDBGeoCatalog


class _FakeConnection:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def execute(self, command: str) -> None:
        self.commands.append(command)

    def sql(self, query: str, *, params: dict[str, str]) -> object:
        _ = query
        return object()


@pytest.fixture
def fake_duckdb(monkeypatch: pytest.MonkeyPatch) -> _FakeConnection:
    con = _FakeConnection()
    monkeypatch.setattr(
        duckdb_backend,
        "duckdb",
        SimpleNamespace(
            connect=lambda: con,
            BinderException=Exception,
            IOException=Exception,
        ),
    )
    monkeypatch.setattr(
        duckdb_backend,
        "_read_geoparquet_crs",
        lambda source, *, default: default,
    )
    monkeypatch.setattr(
        duckdb_backend,
        "_read_backend_tag",
        lambda con, source, *, default: default,
    )
    monkeypatch.setattr(
        duckdb_backend, "_check_schema_version", lambda con, source: None
    )
    return con


@pytest.mark.parametrize(
    ("source", "scheme"),
    [
        ("s3://bucket/cat.parquet", "s3"),
        ("HTTPS://example.test/cat.parquet", "https"),
        ("az://container/cat.parquet", "az"),
        (Path("cat.parquet"), None),
        ("", None),
        ("://missing-scheme", None),
        ("C:/data/cat.parquet", None),
        ("C:\\data\\cat.parquet", None),
    ],
)
def test_scheme(source: str | Path, scheme: str | None) -> None:
    assert duckdb_backend._scheme(source) == scheme


@pytest.mark.parametrize(
    ("source", "extension_commands"),
    [
        ("s3://bucket/cat.parquet", ["INSTALL httpfs", "LOAD httpfs"]),
        ("gs://bucket/cat.parquet", ["INSTALL httpfs", "LOAD httpfs"]),
        ("gcs://bucket/cat.parquet", ["INSTALL httpfs", "LOAD httpfs"]),
        ("https://example.test/cat.parquet", ["INSTALL httpfs", "LOAD httpfs"]),
        ("http://example.test/cat.parquet", ["INSTALL httpfs", "LOAD httpfs"]),
        ("r2://bucket/cat.parquet", ["INSTALL httpfs", "LOAD httpfs"]),
        ("hf://datasets/org/cat.parquet", ["INSTALL httpfs", "LOAD httpfs"]),
        ("az://container/cat.parquet", ["INSTALL azure", "LOAD azure"]),
        ("azure://container/cat.parquet", ["INSTALL azure", "LOAD azure"]),
        ("foo://bucket/cat.parquet", []),
        (Path("cat.parquet"), []),
    ],
)
def test_open_loads_extension_for_supported_uri_schemes(
    source: str | Path,
    extension_commands: list[str],
    fake_duckdb: _FakeConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_source: list[str] = []

    def fake_sql(query: str, *, params: dict[str, str]) -> Any:
        _ = query
        captured_source.append(params["src"])
        return object()

    monkeypatch.setattr(fake_duckdb, "sql", fake_sql)

    cat = DuckDBGeoCatalog.open(source)

    assert isinstance(cat, DuckDBGeoCatalog)
    assert fake_duckdb.commands == [
        "INSTALL spatial",
        "LOAD spatial",
        *extension_commands,
    ]
    assert captured_source == [str(source)]
