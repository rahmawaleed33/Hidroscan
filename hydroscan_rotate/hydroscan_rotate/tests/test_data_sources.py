import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from data_sources import nasa_power, soilgrids, _http
from data_sources.sentinel import load_monthly_series
from analysis.climate import build_climate_profile
from analysis.soil import build_soil_profile

# Shape fixtures mimicking the documented API formats. They test PARSING only and are never displayed as data.
# Shape fixture mimicking the documented POWER DAILY format. Tests PARSING/AGGREGATION only; never displayed as data.
def _daily(year=2020, month=1, n=5):
    t, tx, tn, pr = {}, {}, {}, {}
    for d in range(1, n + 1):
        k = f"{year}{month:02d}{d:02d}"; t[k] = 14.0; tx[k] = 36.0 if d == 1 else 20.0; tn[k] = -1.0 if d == 1 else 8.0; pr[k] = 0.5
    t[f"{year}{month:02d}{n:02d}"] = -999
    return {"properties": {"parameter": {"T2M": t, "T2M_MAX": tx, "T2M_MIN": tn, "PRECTOTCORR": pr}},
            "parameters": {"T2M": {"units": "C"}, "PRECTOTCORR": {"units": "mm/day"}}}
POWER = _daily()
SOIL = {"properties": {"layers": [{"name": "clay", "unit_measure": {"d_factor": 10, "target_units": "g/kg"}, "depths": [{"label": "0-5cm", "values": {"mean": 300}}]}]}}


class TestSources(unittest.TestCase):
    def setUp(self): self._on = config.ONLINE

    def tearDown(self): config.ONLINE = self._on

    def test_power_daily_parse_and_aggregate(self):
        days, units = nasa_power.parse_power_daily(POWER)
        rows = nasa_power.aggregate_daily(days, 30.5)
        self.assertEqual(len(rows), 1); r = rows[0]
        self.assertEqual(r["n_days"], 5); self.assertEqual(r["T2M"], 14.0)            # -999 excluded, not averaged in
        self.assertEqual(r["heat_days"], 1); self.assertEqual(r["frost_days"], 1)
        self.assertAlmostEqual(r["rain_total_mm"], 2.5); self.assertEqual(units["PRECTOTCORR"], "mm/day")
        self.assertIsNotNone(r["et0_hargreaves_mm"])

    def test_et0_is_physically_plausible(self):
        self.assertTrue(6 < nasa_power.hargreaves_et0(28, 36, 21, 30.5, 180) < 8)
        self.assertTrue(1 < nasa_power.hargreaves_et0(13, 19, 8, 30.5, 15) < 3)
        self.assertIsNone(nasa_power.hargreaves_et0(None, 30, 20, 30.5, 100))

    def test_soil_parse_dfactor(self):
        self.assertEqual(soilgrids.parse_soilgrids(SOIL)["clay"]["depths"]["0-5cm"], 30.0)

    def test_texture(self):
        self.assertEqual(soilgrids.classify_texture(90, 5, 5), "sand"); self.assertEqual(soilgrids.classify_texture(20, 20, 60), "clay")
        self.assertEqual(soilgrids.classify_texture(40, 40, 20), "loam")

    def test_offline_never_returns_sample_data(self):
        config.ONLINE = False
        r = nasa_power.get_power_data(29.123, 29.321)        # a location that cannot be in any cache
        self.assertEqual(r["provenance"]["status"], "unavailable"); self.assertIsNone(r["data"])
        c = build_climate_profile(r); self.assertFalse(c["available"]); self.assertEqual(c["monthly"], [])
        self.assertFalse(os.path.exists(os.path.join(config.DATA, "fallback")))

    def test_schema_refuses_illustrative_or_fallback(self):
        from schemas import prov
        with self.assertRaises(AssertionError): prov("x", "ILLUSTRATIVE")
        with self.assertRaises(AssertionError): prov("x", "OBSERVATION", "fallback")

    def test_soil_unavailable_offline(self):
        config.ONLINE = False
        s = soilgrids.get_soil_data(11.111, 22.222)
        self.assertEqual(s["provenance"]["status"], "unavailable"); self.assertIsNone(s["data"])
        self.assertFalse(build_soil_profile(s)["available"])

    def test_injected_transport_live_path(self):
        config.ONLINE = True
        r = nasa_power.get_power_data(31.1, 31.1, getter=lambda u, p: POWER)
        self.assertEqual(r["provenance"]["status"], "ok"); self.assertEqual(r["provenance"]["kind"], "MODELLED")
        self.assertEqual(r["provenance"]["retrieved"], __import__("time").strftime("%Y-%m-%d"))
        c = build_climate_profile(r); self.assertEqual(c["monthly"][0]["temp_c"], 14.0); self.assertIn("0.5 deg", r["provenance"]["spatial_resolution"])

    def test_bad_response_does_not_crash(self):
        config.ONLINE = True
        r = nasa_power.get_power_data(32.2, 32.2, getter=lambda u, p: {"oops": 1})
        self.assertEqual(r["provenance"]["status"], "unavailable")

    def test_real_timeseries_metadata(self):
        s = load_monthly_series()
        self.assertEqual(len(s["data"]), 10); self.assertEqual(s["provenance"]["kind"], "SATELLITE"); self.assertIn("empty", s["provenance"]["note"]); self.assertIn("not field-specific", s["provenance"]["note"])


if __name__ == "__main__":
    unittest.main()
