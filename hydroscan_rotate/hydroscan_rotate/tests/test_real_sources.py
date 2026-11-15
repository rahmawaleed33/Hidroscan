import io, os, sys, tempfile, unittest
import numpy as np
import tifffile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from data_sources import soilgrids, gpm, smap


class TestWCSAndGEEParsers(unittest.TestCase):
    """Parsing/scaling logic with SYNTHETIC inputs. Proves the code path, NOT that ISRIC/GEE return these values live."""
    def setUp(self):
        self._c, self._o = config.CACHE, config.ONLINE
        config.CACHE = tempfile.mkdtemp(); config.ONLINE = True

    def tearDown(self): config.CACHE, config.ONLINE = self._c, self._o

    def _transport(self, url, params):
        d = {k: v for k, v in params if k != "SUBSET"}
        base = {"clay": 312, "sand": 250, "silt": 438, "soc": 95, "phh2o": 79}[d["COVERAGEID"].split("_")[0]]
        arr = np.full((4, 4), base, dtype="int16"); arr[0, 0] = -32768       # nodata pixel must be ignored
        b = io.BytesIO(); tifffile.imwrite(b, arr)
        return soilgrids.tiff_median(b.getvalue())

    def test_wcs_values_scaled_and_labelled(self):
        r = soilgrids.get_soil_data(30.5, 30.4, wcs_transport=self._transport)
        self.assertEqual(r["data"]["clay"]["depths"]["0-5cm"], 31.2); self.assertEqual(r["data"]["phh2o"]["depths"]["5-15cm"], 7.9)
        self.assertEqual(r["data"]["soc"]["units"], "g/kg"); self.assertEqual(r["provenance"]["spatial_resolution"], "250 m")
        self.assertEqual(r["provenance"]["kind"], "MODELLED"); self.assertIn("WCS", r["provenance"]["source"])
        from analysis.soil import build_soil_profile
        self.assertEqual(build_soil_profile(r)["texture_class"], "clay loam")

    def test_wcs_failure_reports_each_route_and_no_numbers(self):
        def boom(u, p): raise ConnectionError("blocked")
        config.GEE_PROJECT = ""
        r = soilgrids.get_soil_data(30.51, 30.41, wcs_transport=boom, getter=None, use_gee=False) if False else soilgrids.get_soil_data(30.51, 30.41, wcs_transport=boom)
        self.assertEqual(r["provenance"]["status"], "unavailable"); self.assertIsNone(r["data"]); self.assertIn("WCS", r["provenance"]["reason"])

    def test_imerg_parse_nodata_and_order(self):
        rows = gpm.parse_monthly([{"month": "2021-02", "precip_mm": 3.2, "n": 1344}, {"month": "2021-01", "precip_mm": -9999, "n": 0}])
        self.assertEqual([r["month"] for r in rows], [1, 2]); self.assertIsNone(rows[0]["precip_mm"]); self.assertEqual(rows[1]["precip_mm"], 3.2)

    def test_smap_anomaly_needs_three_years(self):
        rows = [{"year": y, "month": 1, "sm": v} for y, v in ((2021, .10), (2022, .12), (2023, .14), (2024, None))]
        out = smap.monthly_anomaly(rows)
        self.assertAlmostEqual(out[0]["anomaly"], -0.02, places=3); self.assertIsNone(out[3]["anomaly"])
        self.assertIsNone(smap.monthly_anomaly(rows[:2])[0]["anomaly"])          # only 2 years -> no anomaly claimed

    def test_gee_sources_unavailable_without_project(self):
        config.GEE_PROJECT = ""
        for r in (gpm.get_imerg_monthly(30.5, 30.4), smap.get_smap_monthly(30.5, 30.4)):
            self.assertEqual(r["provenance"]["status"], "unavailable"); self.assertIn("HYDROSCAN_GEE_PROJECT", r["provenance"]["reason"])


if __name__ == "__main__":
    unittest.main()
