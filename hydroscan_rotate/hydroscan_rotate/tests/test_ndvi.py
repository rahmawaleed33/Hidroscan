import os, sys, unittest
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.ndvi import ndvi_from_bands, summarize_series
from analysis.bare_soil import bare_soil_calendar


class TestNDVI(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(float(ndvi_from_bands(0.5, 0.1)), 0.6667, places=3)
        self.assertTrue(np.isnan(ndvi_from_bands(0, 0)))
        self.assertAlmostEqual(float(ndvi_from_bands(0.1, 0.5)), -0.6667, places=3)

    def test_summary_and_trend_guard(self):  # synthetic unit-test inputs, never shown in the app
        df = pd.DataFrame({"month": [f"2026-{m:02d}" for m in range(1, 7)], "ndvi": [.2, .3, .6, .5, None, 1.7]})
        s = summarize_series(df)
        self.assertEqual(s["n_valid_months"], 4); self.assertEqual(s["outliers_removed"], 1)
        self.assertEqual(s["trend"]["status"], "insufficient_history"); self.assertEqual(s["peak"]["month"], "2026-03")

    def test_bare_soil_unknown_not_bare(self):
        df = pd.DataFrame({"month": ["2026-01", "2026-02", "2026-03"], "ndvi": [0.1, 0.5, None]})
        cal = {c["month"]: c["status"] for c in bare_soil_calendar(df)["calendar"]}
        self.assertEqual(cal[1], "potential_bare_soil"); self.assertEqual(cal[2], "vegetated")
        self.assertEqual(cal[3], "unknown"); self.assertEqual(cal[12], "unknown")

    def test_threshold_configurable(self):
        df = pd.DataFrame({"month": ["2026-01"], "ndvi": [0.3]})
        self.assertEqual(bare_soil_calendar(df, threshold=0.35)["calendar"][0]["status"], "potential_bare_soil")
        self.assertEqual(bare_soil_calendar(df, threshold=0.25)["calendar"][0]["status"], "vegetated")


if __name__ == "__main__":
    unittest.main()
