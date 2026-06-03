# Exact grid alignment

`GeoSlice` carries everything a loader needs — bounds, interval,
resolution, CRS — but the derived `shape` and `transform` use a
bare `round(length / resolution)`. That hides subpixel
misregistration: a bbox 40,000 m wide at 30 m resolution silently
becomes a 1,333-pixel grid that's 10 m short of the requested
extent. The error only surfaces later, as an off-by-one against a
co-registered label tile or in a matchup join.

`geocatalog` exposes three opt-in escape hatches for callers that
want loud failures instead.

## `divide_evenly`

```python
from geocatalog import divide_evenly

n = divide_evenly(length=100.0, step=10.0, label="x-extent")  # → 10
divide_evenly(length=100.5, step=10.0, label="x-extent")
# ValueError: x-extent=100.5 is not an integer multiple of step=10.0
# (nearest is 10 -> residual -0.5). Use align='snap' to round
# outward, or fix the bounds/resolution.
```

Default `tol` is tied to the project's `PIXEL_PRECISION` constant
(`10 ** -PIXEL_PRECISION`). Pass `tol=` explicitly when you need
tighter checks.

## `GeoSlice.aligned_shape()`

Strict counterpart to `.shape`. Returns the same `(height, width)`
pair when bounds align, raises with the residual otherwise.

```python
sl = GeoSlice(
    bounds=(0.0, 0.0, 105.0, 100.0),   # x-extent 105 at 10m → not whole
    interval=...,
    resolution=(10.0, 10.0),
    crs="EPSG:32629",
)
sl.shape          # (10, 11)        — round-based, silent
sl.aligned_shape()                    # raises ValueError on x-extent
```

`.shape` stays `round`-based for backwards compatibility with all
existing loaders. `aligned_shape()` is the explicit strict path.

## `align=` constructor modes

| Mode      | Behaviour                                                          |
| --------- | ------------------------------------------------------------------ |
| `"off"`   | Skip the check (default; today's behaviour).                       |
| `"warn"`  | Log a `WARNING` via loguru, keep bounds as-is.                     |
| `"error"` | Raise `ValueError` on the first misaligned axis.                   |
| `"snap"`  | Round `xmax`/`ymax` outward to the nearest whole pixel; log INFO.  |

```python
GeoSlice(..., resolution=(30.0, 30.0), align="error")  # raises
GeoSlice(..., resolution=(30.0, 30.0), align="snap")   # mutates xmax
```

Snap mode adjusts the **max edges only** so the origin (`xmin`,
`ymin`) and therefore the affine stays put. The resulting bounds
fully cover the requested AOI (`xmax_new ≥ xmax_old`). If you need
snap-to-nearest-grid-lattice instead (shifting `xmin` too), do it
yourself and pass `align="error"` to verify.

The `align` field is **not part of slice identity**:

```python
a = GeoSlice(..., align="off")
b = GeoSlice(..., align="error")
assert a == b
assert hash(a) == hash(b)
```

This preserves `set[GeoSlice]`, dict-key usage, and the frozen
dataclass's hash contract.

## `is_grid_aligned`

For matchup co-registration: predicate, not exception.

```python
from geocatalog import is_grid_aligned

if not is_grid_aligned(chip_slice, label_slice):
    report = is_grid_aligned(chip_slice, label_slice, explain=True)
    raise ValueError(f"chip/label grids differ: {report}")
```

Two slices are aligned iff their resolutions match (within `tol`)
and their per-axis origins are congruent modulo resolution, in the
same CRS. CRS mismatch returns `False` — reproject one side via
`GeoSlice.to_crs` first.

`explain=True` returns a dict with `aligned`, `crs_match`,
`x_res_match`, `y_res_match`, `x_origin_residual`,
`y_origin_residual`.

## What this does *not* check

- **Reprojection accuracy.** `to_crs` rescales resolution to
  preserve output shape, so reprojected slices generically have
  non-integer multiples. The reprojected child always carries
  `align="off"` so a strict parent doesn't cause `to_crs` to raise
  on its own output. Validate after reconstruction if you need it.
- **`iter_slices` row footprints.** Both
  `InMemoryGeoCatalog.iter_slices` and `DuckDBGeoCatalog.iter_slices`
  build slices from arbitrary footprint polygons at a user-supplied
  resolution; those are almost never integer multiples. Emitted
  slices carry `align="off"`. Call `aligned_shape()` on the result
  (or reconstruct with `align="error"`) when you need a guarantee.
- **Temporal alignment.** xreader's `_divide_evenly` has a
  `timedelta64` branch; we haven't ported it. The `pd.Interval`
  index isn't checked for uniform sampling.

## Attribution

`divide_evenly` is derived from
[`terrax.xreader.stencils._divide_evenly`](https://github.com/neuralgcm/terrax)
(Apache-2.0, © Google LLC; original author Stephan Hoyer).
Modifications © 2026 J. Emmanuel Johnson, licensed MIT under
geocatalog's overall MIT licence. The Apache header in
`src/geocatalog/_src/_align.py` carries the upstream notice.
