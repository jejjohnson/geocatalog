# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`geocatalog` is a queryable spatiotemporal index over geospatial files: build a catalog from a directory of rasters / vectors / NetCDF-Zarr stores (or a STAC/CMR search), query it by bbox + time via the `GeoSlice` contract, and materialise pixels only when a loader (`load_raster`, `load_vector`, `load_xarray`) is called. Two backends behind one `GeoCatalog` Protocol — an in-memory `GeoDataFrame` catalog (`InMemoryGeoCatalog`) and a lazy DuckDB backend for archive-scale artifacts — with GeoParquet as the persisted, schema-versioned interchange format (`to_geoparquet` / `from_geoparquet` / `migrate_geoparquet`). Discovery `Source` adapters (STAC, NASA earthaccess, CMR; GEE is scaffolding) feed `CatalogBundle.ingest`, which records per-query provenance; the `matchup` engine joins rows across sources with pluggable spatial/temporal strategies, and `staging.stage()` resolves remote URIs into a local cache (`field_for` bridges staged catalogs to `geopatcher` Fields). A `geocatalog` CLI (cyclopts) wraps build/query/stats/info/migrate/convert. Layout is hybrid: implementation in `src/geocatalog/_src/`, re-exported through facade sub-namespaces (`geocatalog.catalog`, `.types`, `.sources`, `.matchup`, `.bundle`, `.staging`) and the flat top level; optional dependencies are extras-gated with lazy imports (`[duckdb]`, `[stac]`, `[earthaccess]`, `[gee]`, `[xarray-raster]`, `[patch]`, `[full]`). Built with Python 3.12+, uv, pytest, and MkDocs.

## Common Commands

```bash
make install              # Install all deps (uv sync --all-groups --all-extras) + pre-commit hooks
make test                 # Run tests: uv run pytest -v
make format               # Auto-fix: ruff format . && ruff check --fix .
make lint                 # Lint code: ruff check .
make typecheck            # Type check: ty check src/geocatalog
make precommit            # Run pre-commit on all files
make docs-serve           # Local docs server
```

### Running a single test

```bash
uv run pytest tests/test_example.py::TestClass::test_method -v
```

### Pre-commit checklist (all four must pass)

```bash
uv run pytest -v                              # Tests
uv run --group lint ruff check .              # Lint — ENTIRE repo, not just src/geocatalog/
uv run --group lint ruff format --check .     # Format — ENTIRE repo
uv run --group typecheck ty check src/geocatalog  # Typecheck — package only
```

**Critical**: Always lint/format with `.` (repo root), not `src/geocatalog/`. CI runs `ruff check .` which includes `tests/` and `scripts/`.

## Architecture

### Package structure

All implementation lives in `src/geocatalog/`. The public API is re-exported through `src/geocatalog/__init__.py`.

### Key directories

| Path | Purpose |
|------|---------|
| `src/geocatalog/` | Main package source code |
| `tests/` | Test suite |
| `docs/` | Documentation (MkDocs) |
| `notebooks/` | Jupyter notebooks |
| `scripts/` | Example scripts |

## Documentation Examples

Example notebooks live in `docs/notebooks/` as jupytext percent-format `.py` files. The workflow:

1. Write the `.py` source (jupytext percent format)
2. Convert and execute: `jupytext --to notebook foo.py` then `jupyter nbconvert --execute --inplace foo.ipynb`
3. Delete the `.py` — the executed `.ipynb` is the committed source of truth
4. `mkdocs-jupyter` renders the pre-executed `.ipynb` with `execute: false`

Figures render inline via `plt.show()` — do **not** use `savefig` or commit separate PNG files. The `.ipynb` cell outputs are the single source of rendered figures.

See `.github/instructions/docs-examples.instructions.md` for full standards.

## Coding Conventions

- Google-style docstrings
- `dataclasses` or `attrs` for data containers
- Type hints on all public functions and methods
- Pure functions where possible; side effects isolated and explicit
- Surgical changes only — don't refactor adjacent code or add docstrings to unchanged code

## Plans

Plans and design documents go in `.plans/` (gitignored, never committed). Track work via GitHub issues instead.

## PR Review Comments

When addressing PR review comments, always resolve each review thread after fixing it via the GitHub GraphQL API (`resolveReviewThread` mutation). Do not leave addressed comments unresolved. To obtain the required `threadId`, first list the pull request's review threads via the GitHub GraphQL API (see the "Pull Request Review Comments" section in `AGENTS.md` for a minimal query and end-to-end workflow).

## Code Review

Follow the guidance in `/CODE_REVIEW.md` for all code review tasks.
