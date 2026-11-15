import ast, hashlib, os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from hydroscan import model_adapter as ma
from schemas import InvalidCoordinates, OutsideCoverage


class TestHydroScan(unittest.TestCase):
    def test_valid_schema(self):
        r = ma.analyze_field(30.525, 30.425)
        for k in ("field", "irrigation", "crop", "vegetation", "data_quality", "model", "provenance"):
            self.assertIn(k, r)
        self.assertIsNone(r["irrigation"]["classification"]); self.assertIsNone(r["crop"]["classification"])
        self.assertIsNone(r["model"]["validated_accuracy"])
        self.assertAlmostEqual(sum(r["vegetation"]["class_fractions"].values()), 1, places=2)

    def test_invalid_and_outside(self):
        for bad in [(95, 30), ("x", 1), (30, 200), (float("nan"), 30)]:
            with self.assertRaises(InvalidCoordinates): ma.analyze_field(*bad)
        with self.assertRaises(OutsideCoverage): ma.analyze_field(30.5, 10.0)

    def test_band_order_and_range(self):
        arr, geo = ma.read_stack(config.DEMO_STACK)
        self.assertEqual(arr.shape[0], 3)
        self.assertTrue(-1 <= arr[2].min() and arr[2].max() <= 1)      # band 3 is NDVI
        self.assertTrue(arr[0].mean() > arr[1].mean())                  # VV (dB) > VH (dB)
        w, s, e, n = ma.bounds_of(arr, geo)
        self.assertAlmostEqual(w, 30.40, 2); self.assertAlmostEqual(n, 30.55, 2)

    def test_features_match_original_function(self):
        src = open(os.path.join(config.ROOT, "original_hydroscan", "model_training.py")).read()
        fn = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "make_features"][0]
        ns = {"np": np}; exec(ast.get_source_segment(src, fn), ns)
        x = np.random.default_rng(0).normal(size=(50, 3)).astype("float32")
        np.testing.assert_allclose(ns["make_features"](x), ma.make_features(x))

    def test_original_model_untouched(self):
        h = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()
        self.assertEqual(h(config.MODEL_PATH), h(os.path.join(config.ROOT, "original_hydroscan", "model.joblib")))
        self.assertEqual(h(config.MODEL_PATH), "923cd3e9576f7e6e2ebb2a1e5c3ab078")

    def test_comparison_stack_differs(self):
        a = ma.analyze_field(30.525, 30.425)["vegetation"]["ndvi_mean"]
        b = ma.analyze_field(30.525, 30.425, stack_path=config.COMPARISON_STACK)["vegetation"]["ndvi_mean"]
        self.assertNotAlmostEqual(a, b, places=3)

    def test_missing_files(self):
        with self.assertRaises(Exception): ma.analyze_field(30.5, 30.4, stack_path="/nonexistent.tif")


if __name__ == "__main__":
    unittest.main()
