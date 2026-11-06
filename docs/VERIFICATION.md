# Verification record — 6 November 2026

This is a **public software demonstration**, not a study estimating environmental change or independent radiometric accuracy. All example imagery comes from Copernicus Sentinel-2 L2A via the public Element 84 Earth Search catalog. No private doctoral data, configurations, or scripts are involved.

## 1. Offline unit/integration tests

**Authoring environment:** Python 3.13.5, NumPy 2.3.5, Rasterio 1.5.0, Requests 2.32.5, Matplotlib 3.10.8. The authoring environment did not have outbound DNS/network access.

The following commands were executed successfully in the source tree:

```bash
python -m unittest discover -s tests -v
python -m eoqa.demo --mode offline --out output/offline
```

All **12 unit/integration tests** in `tests/test_core.py` passed, including two cases for bounded STAC pagination and rejection of untrusted cross-origin pagination URLs. The offline workflow generated five georeferenced GeoTIFFs, an explicitly synthetic PNG and a JSON QA/provenance report.

A separate [public GitHub-hosted offline CI run #42161230433](https://github.com/angelicapalma0200-debug/synthetic-environmental-data-qa/actions/runs/42161230433) also finished **successfully** under Ubuntu 24.04 and Python 3.11. This GitHub-hosted run installed dependencies, completed **15 tests total** (12 EOQA tests plus 3 original numerical QA tests, as recorded in its job logs), and regenerated the synthetic rasters. The original numerical-only exercise and its older tests remain present but are not part of the 12-test count.

### Synthetic fixture, not observed data

- Grid: 120 x 100 pixels (12,000 fictional 10 m cells).
- Valid per-scene pixels: 11,200 (93.33%), by construction.
- Paired-valid pixels: 11,200.
- Mean paired NDVI difference: approximately +0.0356, **entirely synthetic**.

These numbers have no ecological interpretation.

## 2. Verified public-data Sentinel-2 processing

[**Live GitHub Actions run #42161351695 — SUCCESS**](https://github.com/angelicapalma0200-debug/synthetic-environmental-data-qa/actions/runs/42161351695) was executed on a standard public Ubuntu 24.04 runner with Python 3.11.18. The runner obtained STAC scene metadata, read the public remotely hosted Sentinel-2 COG assets, processed red and NIR with SCL masking, created aligned GeoTIFFs, and uploaded all seven outputs to its GitHub Actions artifact.

The independent [publication job #42161554602](https://github.com/angelicapalma0200-debug/synthetic-environmental-data-qa/actions/runs/42161554602) retrieved the exact successful artifact, validated the two scene identities, paired-valid count, expected filenames and nonempty files, then committed the example outputs to the public repository.

**Permanent inspectable results:**

- [NDVI two-date quicklook PNG](../examples/real/madrid-2024/ndvi_quicklook.png)
- [Machine-readable QA and provenance report](../examples/real/madrid-2024/report.json)
- [All five GeoTIFF outputs plus PNG and JSON](../examples/real/madrid-2024/)

### Independent scene identifiers and technical QA

| Field | Earlier observation | Later observation |
|---|---|---|
| Sentinel-2 item ID | `S2B_30TVK_20240417_0_L2A` | `S2B_30TVK_20240815_0_L2A` |
| Acquisition UTC | 2024-04-17 11:10:08 | 2024-08-15 11:10:10 |
| AOI pixel count | 10,163 | 10,163 |
| Valid NDVI pixels | 9,899 (97.40% of AOI) | 9,915 (97.56% of AOI) |
| SCL-excluded pixels | 264 | 248 |
| Spectral-invalid pixels | 0 | 0 |
| Mean valid NDVI | 0.57980 | 0.54428 |

There were **9,887 paired-valid pixels**, representing 97.28% of the AOI (or 94.11% of the rectangular raster grid including pixels outside the AOI). The mean *later minus earlier* NDVI calculated on paired-valid pixels was **−0.03521**. These are strictly **descriptive processing outcomes** from two acquisitions, not a temporal trend, degradation estimate, or causal ecological inference. The scene-level cloud metadata does not constitute cloud validation for this AOI.

The raw dataset and independently verified radiometric reference were **not** independently audited. The report records Earth Search item metadata SHA-256 values and effective per-band calibration choices, not the byte-level hash of the complete remotely hosted scene rasters.

**Copernicus attribution:** Contains modified Copernicus Sentinel data (2024).

## 3. Diagnostic history and fixes

Three earlier bounded runs stopped and are retained in GitHub Actions history:

1. [Run #42160844655](https://github.com/angelicapalma0200-debug/synthetic-environmental-data-qa/actions/runs/42160844655): HTTP 400 during STAC query.
2. [Run #42160958191](https://github.com/angelicapalma0200-debug/synthetic-environmental-data-qa/actions/runs/42160958191): confirmed that Earth Search required RFC3339 timestamps.
3. [Run #42161045883](https://github.com/angelicapalma0200-debug/synthetic-environmental-data-qa/actions/runs/42161045883): after timestamp repair, the provider returned paginated results; the original bounded code stopped rather than choosing from a partial inventory.

The query now enforces full timestamp bounds and bounded, same-origin STAC pagination. The subsequently successful run demonstrates that those immediate implementation defects were corrected **for the chosen example**.

## 4. Scope of verification and development transparency

The verified end-to-end run demonstrates processing of the two specified Sentinel-2 L2A acquisitions under the documented conditions. It does not establish portability to all dates or providers, independently validate SCL classification or reflectance calibration, or support ecological-change inference.

Development involved AI assistance. Code, methods, tests, execution logs, and example outputs are available for inspection. The demonstration does not require private research data, credentials, or scientific computing infrastructure.
