import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import run_analysis
from reports.audio_summary import arabic_script
from reports.report_generator import generate_report


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.r = run_analysis(30.525, 30.425, "soil", "limited")

    def test_result_complete(self):
        self.assertEqual(len(self.r["ranked"]), 3); self.assertEqual(set(self.r["scenarios"]), {"warm_2c", "dry_20"})
        self.assertIsNone(self.r["profile"]["hydroscan"]["irrigation"]["classification"])

    def test_report_files(self):
        with tempfile.TemporaryDirectory() as d:
            f = generate_report(self.r, d)
            for k in ("png", "html", "pdf"): self.assertGreater(os.path.getsize(f[k]), 1000)
            h = open(f["html"], encoding="utf-8").read()
            self.assertIn("Disclaimer", h); self.assertIn("not classified", h); self.assertIn("not certified", h)
            self.assertTrue(open(f["pdf"], "rb").read(5) == b"%PDF-")

    def test_arabic_script_no_invented_numbers(self):
        s = arabic_script(self.r)
        self.assertIn("مهندس زراعي", s); self.assertNotIn("%", s)
        self.assertIn(self.r["ranked"][0]["rotation_name"]["ar"], s)


if __name__ == "__main__":
    unittest.main()
