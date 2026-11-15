import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rotation.scoring import rank_rotations, score_rotation, status_color
from rotation.suitability import load_kb, income_per_year
from rotation.uncertainty import assess

PROFILE = {"climate": {"available": True, "monthly": [{"month": m, "temp_c": 10 + m * 1.5, "rain_mm": 3.0} for m in range(1, 13)]},
           "soil": {"available": False, "reason": "test"}, "ndvi": {"n_valid_months": 10},
           "data_quality": {"missing": ["a", "b", "c", "d"], "available": [], "warnings": []}}   # unit-test profile only


class TestScoring(unittest.TestCase):
    def test_three_rotations_ranked_and_deterministic(self):
        a, b = rank_rotations(PROFILE, "water", "limited"), rank_rotations(PROFILE, "water", "limited")
        self.assertEqual(len(a), 3); self.assertEqual([x["overall"] for x in a], [x["overall"] for x in b])
        self.assertEqual([x["rank"] for x in a], [1, 2, 3])

    def test_missing_economic_not_zero_filled(self):
        r = rank_rotations(PROFILE, "income")[0]
        self.assertIsNone(r["criteria"]["income"]["score"]); self.assertTrue(r["provisional"])
        self.assertAlmostEqual(sum(c["weight_used"] for c in r["criteria"].values()), 1.0, places=3)
        self.assertTrue(any(w["code"] == "income_unscored" for w in r["warnings"]))

    def test_priority_changes_weights(self):
        w = {p: rank_rotations(PROFILE, p)[0]["criteria"]["soil"]["weight_nominal"] for p in ("water", "soil", "income")}
        self.assertEqual(w, {"water": .20, "soil": .45, "income": .15})

    def test_limited_water_penalises_high_demand(self):
        rots = {r["id"]: r for r in load_kb()[1]}
        lim, suf = (score_rotation(PROFILE, rots["C"], "water", wa)["criteria"]["water"]["score"] for wa in ("limited", "sufficient"))
        self.assertLess(lim, suf)

    def test_legume_soil_benefit(self):
        s = {r["rotation_id"]: r["criteria"]["soil"]["score"] for r in rank_rotations(PROFILE, "soil")}
        self.assertGreater(s["B"], s["A"]); self.assertGreater(s["C"], s["A"])

    def test_income_inputs_enable_scoring(self):
        econ = {c: {"yield": 5, "price": 10, "cost": 20} for c in load_kb()[0]}
        econ["faba_bean"] = {"yield": 3, "price": 10, "cost": 20}
        r = rank_rotations(PROFILE, "income", economic_inputs=econ)
        self.assertTrue(all(x["criteria"]["income"]["score"] is not None for x in r))
        self.assertEqual(max(x["criteria"]["income"]["score"] for x in r), 100.0)

    def test_partial_economic_inputs_not_scored(self):
        self.assertIsNone(income_per_year(load_kb()[1][0], {"wheat": {"yield": 1, "price": 1, "cost": None}, "maize": {"yield": 1, "price": 1, "cost": 1}}))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError): rank_rotations(PROFILE, "fun")
        with self.assertRaises(ValueError): rank_rotations(PROFILE, "water", "plenty")
        with self.assertRaises(ValueError): score_rotation(PROFILE, {"id": "X", "stages": ["rice"], "cycle_years": 1, "name_en": "", "name_ar": ""}, "water")

    def test_no_invented_crop_numbers(self):
        for c in load_kb()[0].values():
            for k in ("yield", "price", "production_cost"): self.assertIsNone(c[k]["value"])
            self.assertFalse(c["verified_against_source"])

    def test_data_support_never_high_without_verification(self):
        r = rank_rotations(PROFILE, "water"); self.assertEqual(assess(PROFILE, r)["data_support"], "Limited data support")

    def test_status_colours(self):
        self.assertEqual((status_color(75), status_color(55), status_color(10), status_color(None)), ("green", "yellow", "red", None))


if __name__ == "__main__":
    unittest.main()
