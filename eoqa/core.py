"""Selected-scene NDVI with explicit provenance and pixel-level QA.

This independent teaching example is not derived from any unpublished project.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import rasterio
import requests
from rasterio.crs import CRS
from rasterio.features import geometry_mask
from rasterio.transform import Affine, from_origin
from rasterio.warp import Resampling, reproject, transform_bounds, transform_geom

STAC_API = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
SCL_CLEAR_LAND = frozenset({4, 5})  # vegetated and not vegetated; excludes water
QA_OUTSIDE = 0
QA_SCL_EXCLUDED = 1
QA_SPECTRAL_INVALID = 2
QA_VALID = 3
QA_NAMES = {
    str(QA_OUTSIDE): "outside_area_of_interest",
    str(QA_SCL_EXCLUDED): "excluded_by_scene_classification",
    str(QA_SPECTRAL_INVALID): "invalid_reflectance_or_denominator",
    str(QA_VALID): "valid_terrestrial_ndvi",
}


class InputError(ValueError):
    """Input configuration or STAC metadata cannot be used safely."""


@dataclass(frozen=True)
class Grid:
    crs: CRS
    transform: Affine
    width: int
    height: int
    aoi_mask: np.ndarray

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width


def make_grid(bbox: list[float], epsg: int = 32630, resolution: float = 10.0) -> Grid:
    """Align a bounded WGS84 rectangular AOI to a fixed metric pixel grid."""
    if (len(bbox) != 4 or not all(math.isfinite(v) for v in bbox)
            or not (-180 <= bbox[0] < bbox[2] <= 180)
            or not (-90 <= bbox[1] < bbox[3] <= 90)):
        raise InputError("bbox must be [west, south, east, north] in EPSG:4326")
    if resolution <= 0 or not math.isfinite(resolution):
        raise InputError("resolution must be positive and finite")
    crs = CRS.from_epsg(epsg)
    left, bottom, right, top = transform_bounds(
        "EPSG:4326", crs, *bbox, densify_pts=21
    )
    x0 = math.floor(left / resolution) * resolution
    y0 = math.floor(bottom / resolution) * resolution
    x1 = math.ceil(right / resolution) * resolution
    y1 = math.ceil(top / resolution) * resolution
    width = int(round((x1 - x0) / resolution))
    height = int(round((y1 - y0) / resolution))
    if width < 1 or height < 1 or width * height > 1_000_000:
        raise InputError("AOI must contain 1..1,000,000 pixels at selected resolution")
    transform = from_origin(x0, y1, resolution, resolution)
    poly = {"type": "Polygon", "coordinates": [[
        [bbox[0], bbox[1]], [bbox[2], bbox[1]],
        [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]],
    ]]}
    poly_utm = transform_geom("EPSG:4326", crs, poly)
    aoi_mask = geometry_mask(
        [poly_utm], out_shape=(height, width), transform=transform, invert=True
    )
    if not np.any(aoi_mask):
        raise InputError("AOI does not contain any target pixel centers")
    return Grid(crs, transform, width, height, aoi_mask)


def search_items(bbox: list[float], interval: str, cloud_max: float,
                 session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Bounded, paginated STAC query with deterministic client-side selection."""
    if not (0 <= cloud_max <= 100):
        raise InputError("cloud_max must be within [0, 100]")
    request = {
        "collections": [COLLECTION], "bbox": bbox,
        "datetime": interval, "limit": 60,
        "query": {"eo:cloud_cover": {"lte": cloud_max}},
    }
    client = session or requests.Session()
    page_url = STAC_API
    method = "POST"
    body = request
    results: list[dict[str, Any]] = []
    seen_links: set[tuple[str, str, str]] = set()
    for _ in range(10):  # explicit bound, rather than silently truncating candidates
        response = (client.post(page_url, json=body, timeout=40)
                    if method == "POST" else client.get(page_url, timeout=40))
        if not response.ok:
            raise InputError(f"STAC search HTTP {response.status_code}: {response.text[:1200]}")
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
            raise InputError("STAC response is not a FeatureCollection")
        results.extend(payload["features"])
        if len(results) > 600:
            raise InputError("STAC safety limit: more than 600 candidate items")
        nxt = next((link for link in payload.get("links", [])
                    if link.get("rel") == "next"), None)
        if nxt is None:
            return results
        page_url = urljoin(page_url, nxt.get("href", ""))
        if (urlparse(page_url).scheme != "https"
                or urlparse(page_url).netloc != urlparse(STAC_API).netloc
                or not urlparse(page_url).path.startswith("/v1/")):
            raise InputError("STAC pagination URL is not a trusted Earth Search v1 endpoint")
        method = str(nxt.get("method", "GET")).upper()
        if method not in ("GET", "POST"):
            raise InputError("STAC pagination method is unsupported")
        if method == "POST":
            body = nxt.get("body")
            if not isinstance(body, dict):
                raise InputError("STAC next POST link lacks its request body")
        else:
            body = None
        marker = (method, page_url, json.dumps(body, sort_keys=True))
        if marker in seen_links:
            raise InputError("STAC pagination repeated the same page")
        seen_links.add(marker)
    raise InputError("STAC search exceeded the 10-page safety bound")


def _bbox_contained(candidate: dict[str, Any], bbox: list[float]) -> bool:
    """Conservative containment check using item bounding boxes (not exact footprints)."""
    scene = candidate.get("bbox")
    return bool(scene and len(scene) == 4 and scene[0] <= bbox[0]
                and scene[1] <= bbox[1] and scene[2] >= bbox[2]
                and scene[3] >= bbox[3])


def choose_item(items: list[dict[str, Any]], bbox: list[float]) -> dict[str, Any]:
    """Deterministically choose the lowest scene-cloud candidate covering the bbox."""
    qualified = []
    for item in items:
        assets = item.get("assets", {})
        cover = item.get("properties", {}).get("eo:cloud_cover")
        if (not _bbox_contained(item, bbox) or not all(
                name in assets and assets[name].get("href")
                for name in ("red", "nir", "scl"))):
            continue
        if not isinstance(cover, (int, float)) or not math.isfinite(cover):
            continue
        qualified.append(item)
    if not qualified:
        raise InputError("No complete candidate with red/nir/SCL assets covers the AOI")
    return min(qualified, key=lambda i: (
        i["properties"]["eo:cloud_cover"],
        i["properties"].get("datetime", ""), i["id"],
    ))


def reflectance_calibration(item: dict[str, Any], asset_name: str) -> tuple[float, float]:
    """Avoid double-applying a Sentinel-2 processing-baseline BOA offset.

    Provider's item-level earthsearch:boa_offset_applied has precedence;
    raster:bands.offset can conflict with it (Earth Search issue #71).
    Reject baseline >= 04.00 when the item-level flag is absent.
    """
    asset = item["assets"][asset_name]
    band_meta = asset.get("raster:bands")
    if not isinstance(band_meta, list) or not band_meta:
        raise InputError(f"{asset_name}: missing raster:bands calibration")
    try:
        scale = float(band_meta[0]["scale"])
    except (KeyError, ValueError, TypeError) as exc:
        raise InputError(f"{asset_name}: missing numeric scale") from exc
    if not 0 < scale <= 1:
        raise InputError(f"{asset_name}: invalid scale {scale}")
    props = item.get("properties", {})
    flag = props.get("earthsearch:boa_offset_applied")
    baseline = props.get("s2:processing_baseline")
    baseline_value = None
    if baseline is not None:
        try:
            baseline_value = float(baseline)
        except (ValueError, TypeError) as exc:
            raise InputError("Invalid s2:processing_baseline") from exc
    if flag is True:
        offset = 0.0
    elif flag is False:
        if baseline_value is None:
            raise InputError("Offset not applied, but processing baseline is unknown")
        offset = (-1000.0 * scale) if baseline_value >= 4.0 else 0.0
    elif baseline_value is not None and baseline_value < 4.0:
        offset = 0.0
    else:
        raise InputError("BOA offset state ambiguous; refusing silent calibration")
    return scale, offset


def read_to_grid(href: str, grid: Grid, *, categorical: bool) -> np.ndarray:
    """Use nearest-neighbour alignment to avoid mixing QA classes or cloud edges."""
    dst = np.full(grid.shape, 255, dtype=np.uint8) if categorical else np.full(
        grid.shape, np.nan, dtype=np.float32
    )
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        with rasterio.open(href) as source:
            if source.count < 1 or not source.crs:
                raise InputError("Raster source lacks band or CRS")
            reproject(
                source=rasterio.band(source, 1), destination=dst,
                src_transform=source.transform, src_crs=source.crs,
                src_nodata=source.nodata, dst_transform=grid.transform,
                dst_crs=grid.crs, dst_nodata=255 if categorical else np.nan,
                resampling=Resampling.nearest,
            )
    return dst


def compute_ndvi(red: np.ndarray, nir: np.ndarray, scl: np.ndarray,
                 aoi: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Apply terrestrial SCL and spectral/numerical checks; never fill gaps."""
    if red.shape != nir.shape or red.shape != scl.shape or red.shape != aoi.shape:
        raise InputError("All arrays must share one target grid")
    classified_clear = np.isin(scl, tuple(SCL_CLEAR_LAND))
    finite_nonnegative = (np.isfinite(red) & np.isfinite(nir)
                          & (red >= 0) & (nir >= 0))
    denominator = red + nir
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        ratio = (nir - red) / denominator
    spectral_ok = (finite_nonnegative & np.isfinite(ratio)
                   & (denominator > 1e-6) & (np.abs(ratio) <= 1))
    valid = aoi & classified_clear & spectral_ok
    qa = np.zeros(aoi.shape, dtype=np.uint8)
    qa[aoi & ~classified_clear] = QA_SCL_EXCLUDED
    qa[aoi & classified_clear & ~spectral_ok] = QA_SPECTRAL_INVALID
    qa[valid] = QA_VALID
    ndvi = np.full(red.shape, np.nan, dtype=np.float32)
    ndvi[valid] = ratio[valid].astype(np.float32)
    n_aoi = int(np.count_nonzero(aoi))
    categories, counts = np.unique(scl[aoi], return_counts=True)
    summary = {
        "n_aoi_pixels": n_aoi,
        "n_valid_pixels": int(np.count_nonzero(valid)),
        "valid_fraction": round(float(np.count_nonzero(valid)) / n_aoi, 6),
        "n_scl_excluded": int(np.count_nonzero(qa == QA_SCL_EXCLUDED)),
        "n_spectral_invalid": int(np.count_nonzero(qa == QA_SPECTRAL_INVALID)),
        "scl_class_counts": {str(int(k)): int(v) for k, v in zip(categories, counts)},
        "mean_valid_ndvi": float(np.mean(ndvi[valid])) if np.any(valid) else None,
    }
    return ndvi, qa, summary


def process_item(item: dict[str, Any], grid: Grid) -> tuple[np.ndarray, np.ndarray, dict]:
    """Read three bands; translate integer DN to reflectance before NDVI."""
    bands = {}
    calibration = {}
    for name in ("red", "nir"):
        asset = item["assets"][name]
        scale, offset = reflectance_calibration(item, name)
        raw = read_to_grid(asset["href"], grid, categorical=False)
        bands[name] = raw * scale + offset
        calibration[name] = {"scale": scale, "effective_offset": offset}
    scl = read_to_grid(item["assets"]["scl"]["href"], grid, categorical=True)
    ndvi, qa, report = compute_ndvi(bands["red"], bands["nir"], scl, grid.aoi_mask)
    digest = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
    report.update({
        "item_id": item["id"],
        "item_datetime": item.get("properties", {}).get("datetime"),
        "scene_cloud_percentage": item.get("properties", {}).get("eo:cloud_cover"),
        "stac_item_metadata_sha256": digest,
        "asset_hrefs": {name: item["assets"][name]["href"] for name in ("red", "nir", "scl")},
        "calibration": calibration,
    })
    return ndvi, qa, report


def write_geotiff(path: Path, grid: Grid, values: np.ndarray, *, qa: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path, "w", driver="GTiff", width=grid.width, height=grid.height,
        count=1, crs=grid.crs, transform=grid.transform,
        dtype="uint8" if qa else "float32",
        nodata=0 if qa else np.nan, compress="deflate",
        predictor=2 if qa else 3,
    ) as dest:
        dest.write(values, 1)
        dest.update_tags(description="QA class" if qa else "NDVI on eligible land pixels")


def compare_dates(a: np.ndarray, b: np.ndarray, min_overlap: float = 0.05
                  ) -> tuple[np.ndarray, dict[str, Any]]:
    """Descriptive difference only; no attribution, trend or significance test."""
    if a.shape != b.shape:
        raise InputError("Difference requires identical grids")
    overlap = np.isfinite(a) & np.isfinite(b)
    result = np.full(a.shape, np.nan, dtype=np.float32)
    result[overlap] = b[overlap] - a[overlap]
    fraction = float(np.count_nonzero(overlap)) / a.size
    return result, {
        "n_overlap_pixels": int(np.count_nonzero(overlap)),
        "overlap_fraction_of_grid": round(fraction, 6),
        "mean_difference_on_overlap": float(np.mean(result[overlap])) if np.any(overlap) else None,
        "overlap_below_descriptive_threshold": fraction < min_overlap,
        "interpretation": "Descriptive difference, not a temporal trend or causal estimate",
    }


def save_results(grid: Grid, records: dict[str, tuple[np.ndarray, np.ndarray, dict]],
                 output: Path, *, min_valid_fraction: float = 0.05,
                 run_config: dict[str, Any] | None = None) -> dict:
    """Save maps plus machine-readable provenance; no opaque auto-replacement."""
    output.mkdir(parents=True, exist_ok=True)
    labels = sorted(records)
    if len(labels) != 2:
        raise InputError("Demo requires exactly two period labels")
    for label in labels:
        ndvi, qa, _ = records[label]
        write_geotiff(output / f"ndvi_{label}.tif", grid, ndvi)
        write_geotiff(output / f"qa_{label}.tif", grid, qa, qa=True)
    comparison, compare_report = compare_dates(records[labels[0]][0], records[labels[1]][0])
    write_geotiff(output / "ndvi_difference.tif", grid, comparison)
    min_valid_pass = all(r[2]["valid_fraction"] >= min_valid_fraction for r in records.values())
    report = {
        "purpose": "Independent demonstration; not evidence of ecological change",
        "software_versions": {"python": platform.python_version(),
                              "numpy": np.__version__,
                              "rasterio": rasterio.__version__,
                              "matplotlib": matplotlib.__version__,
                              "requests": requests.__version__},
        "run_config": run_config,
        "period_order": labels,
        "n_grid_pixels": int(grid.width * grid.height),
        "grid_epsg": grid.crs.to_epsg(),
        "grid_transform": list(grid.transform)[:6],
        "scl_eligible_classes": sorted(SCL_CLEAR_LAND),
        "qa_codes": QA_NAMES,
        "periods": {k: v[2] for k, v in records.items()},
        "difference": compare_report,
        "both_periods_meet_minimum_valid_fraction": min_valid_pass,
        "caution": ("No inferential analysis. Scene-wide cloud screening and two acquisitions "
                    "cannot establish ecological change or long-term trends."),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    plot_quicklook(records[labels[0]][0], records[labels[1]][0],
                   comparison, output / "ndvi_quicklook.png",
                   synthetic=all(x[2]["item_id"].startswith("SYNTHETIC_") for x in records.values()))
    return report


def plot_quicklook(first: np.ndarray, second: np.ndarray,
                   difference: np.ndarray, path: Path, *, synthetic: bool) -> None:
    """Visual aid; nodata remains grey and is not interpolated."""
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout="constrained")
    ndvi_cmap = plt.get_cmap("RdYlGn").copy()
    delta_cmap = plt.get_cmap("BrBG").copy()
    ndvi_cmap.set_bad("#cccccc")
    delta_cmap.set_bad("#cccccc")
    panels = (
        (first, "Earlier NDVI", ndvi_cmap, -1, 1),
        (second, "Later NDVI", ndvi_cmap, -1, 1),
        (difference, "Later minus earlier", delta_cmap, -0.3, 0.3),
    )
    for ax, (data, label, cmap, vmin, vmax) in zip(axes, panels):
        image = ax.imshow(np.ma.masked_invalid(data), cmap=cmap, vmin=vmin,
                          vmax=vmax, interpolation="nearest")
        ax.set_title(label, fontsize=10)
        ax.set_axis_off()
        fig.colorbar(image, ax=ax, shrink=0.7)
    fig.suptitle("SYNTHETIC FIXTURE - NOT OBSERVATIONS" if synthetic
                 else "Sentinel-2 L2A: illustrative, non-inferential", fontsize=12)
    fig.savefig(path, dpi=150)
    plt.close(fig)
