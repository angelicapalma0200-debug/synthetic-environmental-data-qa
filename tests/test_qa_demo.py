"""Basic tests for a fully synthetic example."""

import unittest

from src.qa_demo import classify, generate_records, summarize


class SyntheticQualityTests(unittest.TestCase):
    def test_quality_categories(self):
        self.assertEqual(classify(None), "missing")
        self.assertEqual(classify(125.0), "out_of_range")
        self.assertEqual(classify(float("nan")), "out_of_range")
        self.assertEqual(classify(52.0), "valid")

    def test_fixed_seed_is_reproducible(self):
        self.assertEqual(generate_records(seed=8), generate_records(seed=8))
        self.assertNotEqual(generate_records(seed=8), generate_records(seed=9))

    def test_summary_counts_reconcile(self):
        records = generate_records()
        report = summarize(records)
        self.assertEqual(len(records), 72)
        self.assertEqual(len(report), 3)
        self.assertTrue(any(x["qa_status"] == "missing" for x in records))
        self.assertTrue(any(x["qa_status"] == "out_of_range" for x in records))
        for row in report:
            self.assertEqual(row["n_total"], row["n_valid"] + row["n_missing"] + row["n_out_of_range"])
            self.assertEqual(row["valid_fraction"], round(row["n_valid"] / row["n_total"], 4))


if __name__ == "__main__":
    unittest.main()
