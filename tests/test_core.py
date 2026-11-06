import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio

from eoqa.core import (InputError, QA_SCL_EXCLUDED, QA_SPECTRAL_INVALID,
                       QA_VALID, choose_item, compare_dates, compute_ndvi,
                       make_grid, process_item, reflectance_calibration, search_items)
from eoqa.demo import run_offline


class TestCalibration(unittest.TestCase):
    def setUp(self):
        self.item = {
            "assets": {"red": {"raster:bands": [{"scale": 0.0001, "offset": -0.1}]}},
            "properties": {"s2:processing_baseline": "05.11",
                           "earthsearch:boa_offset_applied": True},
        }

    def test_offset_already_applied_ignores_conflicting_asset_metadata(self):
        self.assertEqual(reflectance_calibration(self.item, "red"), (0.0001, 0.0))

    def test_offset_not_applied(self):
        self.item["properties"]["earthsearch:boa_offset_applied"] = False
        self.assertAlmostEqual(reflectance_calibration(self.item, "red")[1], -0.1)

    def test_ambiguous_new_baseline_is_rejected(self):
        self.item["properties"].pop("earthsearch:boa_offset_applied")
        with self.assertRaises(InputError):
            reflectance_calibration(self.item, "red")

    def test_historical_baseline_without_flag(self):
        self.item["properties"].pop("earthsearch:boa_offset_applied")
        self.item["properties"]["s2:processing_baseline"] = "03.01"
        self.assertEqual(reflectance_calibration(self.item, "red"), (0.0001, 0.0))


class TestPixelQA(unittest.TestCase):
    def test_distinguishes_scl_exclusion_and_invalid_spectrum(self):
        red = np.array([[0.2, 0.2, 0.0, 0.2]], dtype=np.float32)
        nir = np.array([[0.6, 0.6, 0.0, 0.6]], dtype=np.float32)
        scl = np.array([[4, 9, 5, 4]], dtype=np.uint8)
        aoi = np.array([[True, True, True, False]])
        ndvi, qa, report = compute_ndvi(red, nir, scl, aoi)
        self.assertAlmostEqual(float(ndvi[0, 0]), 0.5, places=6)
        self.assertTrue(np.isnan(ndvi[0, 1]))
        self.assertEqual(qa.tolist(), [[QA_VALID, QA_SCL_EXCLUDED, QA_SPECTRAL_INVALID, 0]])
        self.assertEqual(report["n_aoi_pixels"], 3)
        self.assertEqual(report["n_valid_pixels"], 1)

    def test_no_automatic_imputation(self):
        arr = np.array([[np.nan, 0.2]], dtype=np.float32)
        diff, report = compare_dates(arr, np.array([[0.3, 0.4]], dtype=np.float32))
        self.assertTrue(np.isnan(diff[0, 0]))
        self.assertAlmostEqual(float(diff[0, 1]), 0.2)
        self.assertEqual(report["n_overlap_pixels"], 1)


class TestSelection(unittest.TestCase):
    def test_scene_sort_independent_of_input_order(self):
        bbox = [-4, 40, -3.9, 40.1]
        def item(name, cloud):
            return {"id": name, "bbox": [-4.5, 39.5, -3.5, 40.5],
                    "properties": {"eo:cloud_cover": cloud, "datetime": "2024-01-01"},
                    "assets": {k: {"href": f"x_{k}"} for k in ("red", "nir", "scl")}}
        a, b = item("A", 30), item("B", 15)
        self.assertEqual(choose_item([a, b], bbox)["id"], "B")
        self.assertEqual(choose_item([b, a], bbox)["id"], "B")

    def test_partial_footprint_bbox_rejected(self):
        bbox = [-4, 40, -3.9, 40.1]
        invalid = {"id": "x", "bbox": [-4, 40, -3.95, 40.1],
                   "properties": {"eo:cloud_cover": 1},
                   "assets": {k: {"href": "x"} for k in ("red", "nir", "scl")}}
        with self.assertRaises(InputError):
            choose_item([invalid], bbox)

    def test_grid_is_bounded(self):
        grid = make_grid([-3.691, 40.412, -3.679, 40.421])
        self.assertGreater(int(grid.aoi_mask.sum()), 100)
        with self.assertRaises(InputError):
            make_grid([-4, 40, -2, 42])


class TestSTACPagination(unittest.TestCase):
    def test_two_pages_without_network(self):
        class Response:
            ok = True
            def __init__(self, payload):
                self.payload = payload
            def json(self):
                return self.payload
        class Session:
            def __init__(self):
                self.calls = []
            def post(self, url, json, timeout):
                self.calls.append((url, json))
                if "token" not in json:
                    return Response({"features": [{"id": "first"}], "links": [{
                        "rel": "next", "href": "https://earth-search.aws.element84.com/v1/search",
                        "method": "POST", "body": {"token": "page-2"},
                    }]})
                return Response({"features": [{"id": "second"}], "links": []})
        session = Session()
        items = search_items([-3.7, 40.4, -3.6, 40.5],
                             "2024-01-01T00:00:00Z/2024-01-31T23:59:59Z",
                             50, session=session)
        self.assertEqual([i["id"] for i in items], ["first", "second"])
        self.assertEqual(len(session.calls), 2)

    def test_blocks_external_pagination_url(self):
        class Response:
            ok = True
            def json(self):
                return {"features": [{"id": "first"}], "links": [{
                    "rel": "next", "href": "https://untrusted.example.org/leak",
                    "method": "GET",
                }]}
        class Session:
            def post(self, *args, **kwargs):
                return Response()
        with self.assertRaises(InputError):
            search_items([-3.7, 40.4, -3.6, 40.5],
                         "2024-01-01T00:00:00Z/2024-01-31T23:59:59Z",
                         50, session=Session())


class TestIntegration(unittest.TestCase):
    def test_offline_fixture_including_scl_20m_reprojection(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            report = run_offline(out)
            self.assertEqual(report["n_grid_pixels"], 12000)
            self.assertEqual(set(report["periods"]), {"earlier", "later"})
            self.assertTrue((out / "results/ndvi_difference.tif").exists())
            self.assertTrue((out / "results/qa_later.tif").exists())
            self.assertTrue((out / "results/report.json").exists())
            self.assertTrue((out / "results/ndvi_quicklook.png").exists())
            self.assertGreater(report["difference"]["n_overlap_pixels"], 10000)
            self.assertTrue(report["both_periods_meet_minimum_valid_fraction"])
            for period in report["periods"].values():
                self.assertEqual(period["n_aoi_pixels"], period["n_valid_pixels"] + period["n_scl_excluded"] + period["n_spectral_invalid"])
                self.assertIn("9", period["scl_class_counts"] if period["item_id"].endswith("LATER") else {"9": "not expected"})
            with rasterio.open(out / "results/ndvi_difference.tif") as ds:
                difference = ds.read(1, masked=True)
                self.assertEqual(ds.crs.to_epsg(), 32630)
                self.assertLess(float(difference.mean()), 0.12)
                self.assertGreater(float(difference.mean()), 0)


if __name__ == "__main__":
    unittest.main()
