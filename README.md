# Environmental Data QA: a reproducible Sentinel-2 example

**A small, independent example of geospatial data acquisition and quality assessment.** The previous synthetic-only exercise remains available in [`src/qa_demo.py`](src/qa_demo.py). This repository now also contains a more substantial Earth-observation workflow in [`eoqa/`](eoqa/).

**Two modes:** an **offline, deterministic raster fixture** (runs without internet) and an **optional real-data mode** using public Sentinel-2 Level-2A imagery from Element 84 Earth Search STAC. The example area is a small urban mosaic in Madrid, Spain, outside the author's doctoral study region.

> **Verification status:** the offline mode and unit/integration tests have been executed locally. The live STAC acquisition and cloud-hosted raster reads have **not** been executed in the authoring environment, which has no outbound internet access. Do not treat the live path as verified until running it in an internet-connected environment.

## What the workflow does

1. Selects two scenes in declared time windows. In live mode, the deterministic criterion is lowest scene-wide reported cloud cover among items with required assets and bounding-box coverage.
2. Reads red (B04), NIR (B08), and 20 m SCL scene-classification layers; aligns them onto a fixed 10 m grid with nearest-neighbour resampling.
3. Converts digital numbers to reflectance **without silently double-applying Sentinel-2 processing-baseline offsets**. If the provider's calibration metadata is ambiguous, the pipeline stops instead of guessing.
4. Classifies valid land pixels (SCL 4 and 5), rejects clouds/shadows/water/uncertain classes, and computes NDVI only with valid observations.
5. Exports per-scene NDVI, per-pixel QA, paired-date NDVI difference, and a JSON provenance/quality report. No imputation is performed.

## Quick start (Python 3.10+)

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m eoqa.demo --mode offline --out output/offline
```

Outputs appear in `output/offline/results/`. To attempt a small real-data example (requires internet and GDAL HTTP range access):

```bash
python -m eoqa.demo --mode live --config config/madrid_demo.json --out output/live
```

Each run writes `ndvi_earlier.tif`, `ndvi_later.tif`, `qa_earlier.tif`, `qa_later.tif`, `ndvi_difference.tif`, `ndvi_quicklook.png`, and `report.json` (the filenames are generated from period labels). The `output/` folder is excluded from version control.

## Scientific cautions

**This is a software demonstration, not an ecological-change analysis.** Two acquisitions cannot establish a temporal trend. Scene-wide cloud cover does not guarantee clear pixels in a specific AOI. Sentinel-2 SCL is an imperfect classification, and nearest-neighbour resampling preserves classes but cannot restore subpixel detail. The paired difference is calculated only on pixels valid in *both* scenes; support varies, and reported means are descriptive rather than inferential. No accuracy, classification or cross-sensor validation is claimed.

The live selection tests only bounding-box containment, not exact pixel-footprint coverage. A scene may therefore have incomplete local coverage, which must be evaluated through the final QA counts. The calibration policy specifically addresses a documented Earth Search metadata ambiguity (see [methods and sources](docs/METHODS.md)).

## Transparency and privacy

All source code in this repository is a fresh standalone demonstration prepared with AI assistance. It is not copied from, and does not contain data, algorithms, credentials, site coordinates, or unpublished results from, any private research repository. Local execution and tests demonstrate software behavior; **they do not establish independent programming proficiency** or validate remote data availability.

## Methods and references

- [Methods, assumptions, reproducibility and authoritative sources](docs/METHODS.md)
- [Offline test and execution verification record](docs/VERIFICATION.md)
- [`config/madrid_demo.json`](config/madrid_demo.json) specifies the public example location, resolution and search windows.
- [Original synthetic numerical QA exercise](src/qa_demo.py) remains available for comparison.

**Attribution for source imagery when live mode is used:** Contains modified Copernicus Sentinel data (2024), processed with this demonstration software. No original satellite data are redistributed here.
