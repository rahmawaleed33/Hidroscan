import copy, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rotation.scenarios import PRESETS, run_scenario
from tests.test_scoring import PROFILE


class TestScenarios(unittest.TestCase):
    def test_baseline_equals_no_change(self):
        s = run_scenario(PROFILE, PRESETS["baseline"], "water", "limited")
        self.assertTrue(all(r["delta"] == 0 for r in s["rows"])); self.assertFalse(s["ranking_changed"])

    def test_warming_lowers_scores_and_preserves_input(self):
        before = copy.deepcopy(PROFILE)
        s = run_scenario(PROFILE, PRESETS["warm_2c"], "water", "limited")
        self.assertEqual(before, PROFILE)                                    # historical profile untouched
        self.assertTrue(all(r["delta"] < 0 for r in s["rows"]))
        self.assertEqual(s["scenario_profile"]["climate"]["monthly"][0]["temp_c"], round(PROFILE["climate"]["monthly"][0]["temp_c"] + 2, 2))
        self.assertTrue(s["scenario_profile"]["scenario_applied"]["hypothetical"])

    def test_rain_decrease(self):
        s = run_scenario(PROFILE, PRESETS["dry_20"], "water", "limited")
        self.assertTrue(all(r["delta"] <= 0 for r in s["rows"])); self.assertIn("not a forecast", s["label"])

    def test_out_of_range(self):
        with self.assertRaises(ValueError): run_scenario(PROFILE, {"delta_t": 30}, "water")

    def test_no_climate_gives_gap_not_crash(self):
        p = {**PROFILE, "climate": {"available": False}}
        s = run_scenario(p, PRESETS["warm_2c"], "water")
        self.assertTrue(any(g["code"] == "scn_no_climate" for g in s["scenario"][0]["data_gaps"]))


if __name__ == "__main__":
    unittest.main()
