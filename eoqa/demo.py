"""Public demonstration CLI with both offline and optional network execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from .core import (Grid, choose_item, make_grid, process_item, save_results,
                   search_items)


def _write_fixture(path: Path, arr: np.ndarray, crs: CRS, transform) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[1],
                       height=arr.shape[0], count=1, crs=crs, transform=transform,
                       dtype=arr.dtype, nodata=0, compress="deflate") as dst:
        dst.write(arr, 1)


def make_synthetic_fixture(folder: Path) -> tuple[Grid, dict[str, dict]]:
    """Create two fictional scenes; no real location or measurement implied."""
    width, height = 120, 100
    crs = CRS.from_epsg(32630)
    transform = from_origin(450000, 4480000, 10, 10)
    grid = Grid(crs, transform, width, height, np.ones((height, width), dtype=bool))
    y, x = np.mgrid[0:height, 0:width]
    items = {}
    for index, label in enumerate(("earlier", "later")):
        red = np.asarray(650 + x * 2 + y, dtype=np.uint16)
        nir = np.asarray(2400 + x * 3 + y + index * 280, dtype=np.uint16)
        scl = np.full((height // 2, width // 2), 4, dtype=np.uint8)
        scl[4:14, 12:22] = 9 if index == 1 else 3
        scl[18:30, 31:40] = 5
        scl[30:38, 3:13] = 6
        red[20:28, 80:90] = 0
        nir[20:28, 80:90] = 0
        assets = {}
        for name, data, affine in (
            ("red", red, transform), ("nir", nir, transform),
            ("scl", scl, from_origin(450000, 4480000, 20, 20)),
        ):
            path = folder / f"{label}_{name}.tif"
            _write_fixture(path, data, crs, affine)
            assets[name] = {"href": str(path)}
            if name != "scl":
                assets[name]["raster:bands"] = [{"scale": 0.0001, "offset": -0.1}]
        items[label] = {
            "id": f"SYNTHETIC_{label.upper()}", "assets": assets,
            "properties": {
                "datetime": f"2024-{4 if index == 0 else 9:02d}-15T10:00:00Z",
                "eo:cloud_cover": 10 + index * 4,
                "s2:processing_baseline": "05.11",
                "earthsearch:boa_offset_applied": True,
            },
        }
    return grid, items


def run_offline(outdir: Path) -> dict:
    grid, items = make_synthetic_fixture(outdir / "synthetic_sources")
    records = {name: process_item(item, grid) for name, item in items.items()}
    return save_results(grid, records, outdir / "results")


def run_live(outdir: Path, config_path: Path) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    bbox = config["bbox"]
    grid = make_grid(bbox, epsg=config["target_epsg"], resolution=config["resolution_m"])
    records = {}
    for label, interval in config["intervals"].items():
        items = search_items(bbox, interval, config["max_scene_cloud_pct"])
        chosen = choose_item(items, bbox)
        records[label] = process_item(chosen, grid)
    return save_results(grid, records, outdir / "results", run_config=config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Small Sentinel-2 NDVI QA demonstration")
    parser.add_argument("--mode", choices=("offline", "live"), default="offline")
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument("--config", type=Path, default=Path("config/madrid_demo.json"))
    args = parser.parse_args()
    result = run_offline(args.out) if args.mode == "offline" else run_live(args.out, args.config)
    print(json.dumps({"mode": args.mode, "report": str(args.out / "results/report.json"),
                      "min_valid_pass": result["both_periods_meet_minimum_valid_fraction"],
                      "difference": result["difference"]}, indent=2))


if __name__ == "__main__":
    main()
