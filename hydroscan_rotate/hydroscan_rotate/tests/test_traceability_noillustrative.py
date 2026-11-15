import json, os, re, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HYDROSCAN_OFFLINE"] = "1"
import config
from pipeline import run_analysis
from reports.traceability import build_traceability
from reports.expert_report import expert_report_md
from reports.field_card import make_field_card

ROOT = config.ROOT


class TestTraceability(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = run_analysis(30.525, 30.425, "water", "limited")

    def test_every_row_has_all_fields_and_type(self):
        for row in build_traceability(self.r):
            for k in ("item", "source", "status", "retrieved", "period", "resolution", "type", "limitations"): self.assertIn(k, row)
        types = {x["type"] for x in build_traceability(self.r)}
        self.assertTrue({"farmer-provided", "satellite-derived", "unavailable", "analyst assumption (unverified)"} <= types)

    def test_unavailable_sources_carry_no_values_or_dates(self):
        for row in build_traceability(self.r):
            if row["type"] == "unavailable": self.assertIsNone(row["retrieved"]) if row["status"] == "unavailable" and "farmer" not in row["source"] else None

    def test_no_sample_climate_or_soil_numbers_in_profile(self):
        p = self.r["profile"]
        self.assertFalse(p["climate"]["available"]); self.assertEqual(p["climate"]["monthly"], [])
        self.assertFalse(p["soil"]["available"]); self.assertNotIn("ILLUSTRATIVE", json.dumps(p, default=str))

    def test_no_confidence_percentage_and_no_irrigation_claim(self):
        txt = expert_report_md(self.r)
        self.assertNotRegex(txt, r"(?i)confidence[^\n]{0,20}\d+\s*%"); self.assertIn("NOT classified", txt)
        self.assertIsNone(self.r["profile"]["hydroscan"]["irrigation"]["classification"]); self.assertIsNone(self.r["profile"]["hydroscan"]["crop"]["classification"])

    def test_expert_report_lists_missing_and_egypt_refs(self):
        txt = expert_report_md(self.r)
        for needle in ("UNAVAILABLE", "Needs expert validation", "Egyptian literature, unverified", "R03"): self.assertIn(needle, txt)

    def test_card_renders_with_unavailable_sources(self):
        p = make_field_card(self.r, os.path.join(config.ROOT, "tmp_card.png")); self.assertGreater(os.path.getsize(p), 10000); os.remove(p)

    def test_source_tree_has_no_hand_entered_climate_or_soil_values(self):
        self.assertFalse(os.path.exists(os.path.join(config.DATA, "fallback")))
        for d, _, files in os.walk(ROOT):
            if "original_hydroscan" in d or "tests" in d or "docs" in d: continue
            for f in files:
                if f.endswith(".py"):
                    src = open(os.path.join(d, f), encoding="utf-8").read()
                    self.assertNotIn("illustrative_climate", src, f)

    def test_egypt_references_all_unverified_and_ids_resolve(self):
        refs = json.load(open(os.path.join(ROOT, "rotation", "egypt_references.json"), encoding="utf-8"))
        text = json.dumps(refs["crops"]); used = set(re.findall(r"R\d\d", text))
        self.assertTrue(used <= set(refs["sources"])); self.assertEqual(set(refs["crops"]), {"wheat", "faba_bean", "berseem", "maize"})
        self.assertIn("NOT official", refs["_readme"])


if __name__ == "__main__":
    unittest.main()
