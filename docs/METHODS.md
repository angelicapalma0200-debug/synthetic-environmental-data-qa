# Methods, provenance, and limits

## Study scope

A deliberately small public example, independent of any research project, uses a rectangular AOI in Madrid, Spain, configured in `config/madrid_demo.json`. The live path queries the free Earth Search STAC v1 API for Sentinel-2 L2A scenes in two time windows. The offline path creates two fictional, deterministic rasters with a 10 m red/NIR grid and a 20 m SCL grid; the synthetic fixture is explicitly marked as not observed data.

## Selection and spatial alignment

Live candidates are filtered by scene-level `eo:cloud_cover`, the availability of `red`, `nir`, and `scl` assets, and STAC bounding-box containment. STAC results are collected through at most 10 pages (maximum 600 candidates); only same-origin HTTPS pagination URLs are allowed and repeated links are rejected. Exceeding the bound fails explicitly instead of selecting from a partial inventory. Sorting by (cloud percentage, acquisition timestamp, item ID) makes selection independent of API order. The entire scene footprint is not geometrically verified, and there is no automatic second-best scene substitution if the selected scene has poor AOI coverage. Raster coverage is quantified *after reading*.

The geographical AOI is projected to EPSG:32630, with a 10 m pixel grid anchored to multiples of the pixel size. Nearest-neighbour reprojection aligns the 10 m reflectance bands and the 20 m SCL without mixing categorical classes. An AOI mask excludes target pixels outside the requested geographic rectangle. Reprojection cannot recover information missing from the source or improve the actual native resolution.

## Reproducible public imagery example

The [permanent example folder](../examples/real/madrid-2024/) includes five small GeoTIFFs (two NDVI, two QA-classification outputs, and one paired-date difference), a [PNG quicklook](../examples/real/madrid-2024/ndvi_quicklook.png), and [JSON provenance](../examples/real/madrid-2024/report.json).

The [public real-data workflow run](https://github.com/angelicapalma0200-debug/synthetic-environmental-data-qa/actions/runs/42161351695) completed retrieval and processing with Earth Search STAC. The [publication workflow](https://github.com/angelicapalma0200-debug/synthetic-environmental-data-qa/actions/runs/42161554602) verified and committed those exact seven outputs, independent of the private research repository. Scene IDs, calibration metadata, grid extent, valid support and asset URLs are recorded in the JSON report; the full external source-asset bytes were not independently hashed.

The demo was executed with acquisitions from 17 April and 15 August 2024. Neither the two-scene contrast nor the small AOI is intended as a test of environmental trends, ecosystem condition or satellite measurement accuracy.

## Reflectance calibration safeguard

Sentinel-2 Level-2A processing baseline 04.00 introduced a BOA offset to stored digital numbers. Some Earth Search COGs already have that offset applied. Moreover, the `raster:bands.offset` attribute may disagree with the item-level `earthsearch:boa_offset_applied` flag. Applying the offset twice biases spectral indices.

For each red/NIR asset, the code requires `raster:bands[0].scale` and derives an **effective** offset by inspecting `earthsearch:boa_offset_applied` plus `s2:processing_baseline`:

- `earthsearch:boa_offset_applied == true`: offset 0, even when the asset's raster metadata says `-0.1`.
- `earthsearch:boa_offset_applied == false` and baseline >= 4: effective offset `-1000 * scale`.
- Baseline < 4: no offset when the flag is absent.
- Ambiguous recent/unknown baseline: stop with an explicit error. No silent assumption.

This is a narrow defensive implementation for the publicly indexed Earth Search collection, not a universal Sentinel-2 radiometric harmonization library. Per-band vendor metadata should be checked before generalizing to another provider or processing baseline.

## QA policy and descriptive estimands

Only SCL class 4 (vegetation) and class 5 (not vegetated) are included in this terrestrial example. Classes 0-3 and 6-11, plus unknown/NoData, are excluded. This is a conservative illustrative policy, **not** ground-truth verification or a scientifically universal cloud mask.

NDVI = (NIR - RED) / (NIR + RED), with reflectance values used only when both are finite and nonnegative, the denominator is > 1e-6, and the derived index is finite within [-1, 1]. Every AOI pixel is labeled as SCL-excluded, spectral-invalid or valid; pixels outside are distinct. No smoothing or interpolation fills gaps. The two-date difference is `later - earlier` only where both dates are valid. The resulting mean is conditional on that intersection; it does not estimate overall land-condition change or temporal trend.

The JSON report records source item IDs, acquisition timestamps, item-metadata SHA-256 (not a hash of full remote raster bytes), asset URLs, effective band calibrations, per-period QA counts and paired valid support. A minimum valid-fraction flag is informational; no automatic scene replacement or false QA pass is triggered by it.

## Limitations and reproducibility

Tests cover deterministic scene selection, ambiguous radiometry handling, pixel QA semantics, missing values and end-to-end georeferenced raster outputs using the offline synthetic fixture. Those tests **cannot validate** network availability, metadata completeness for all acquisition dates, cloud-mask accuracy, physical calibration of a live scene or ecological interpretation. The sample periods are separated in time, but their difference is descriptive only and is affected by sampling and phenology.

## References (public primary/technical documentation)

1. Element 84, [Earth Search STAC API](https://github.com/Element84/earth-search) (accessed 2026-11-06). Provider description, publicly accessible imagery index, and no guaranteed service uptime.
2. Element 84, [Offset handling in Sentinel-2 COGs, discussion #26](https://github.com/Element84/earth-search/discussions/26) (2023). COG offset behavior and known choices.
3. Element 84, [Sentinel-2 L2A offset anomaly, issue #71](https://github.com/Element84/earth-search/issues/71). Caution about internally inconsistent `raster:bands.offset` values.
4. ESA/Copernicus, [Sentinel-2 Level-2A scene classification](https://s2.pages.eopf.copernicus.eu/msi/s2msi/main/PDFS_ADFS/L2/PDFS_S2_MSI_L2.html). Official SCL definitions.
5. stac-utils, [pystac-client quickstart](https://pystac-client.readthedocs.io/en/stable/quickstart.html). Confirms Earth Search STAC endpoint and collection naming; this project makes a direct bounded HTTP STAC query instead of requiring pystac-client.
