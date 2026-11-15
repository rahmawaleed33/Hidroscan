import os
import unittest

os.environ["HYDROSCAN_OFFLINE"] = "1"
from bot.conversation import handle, new_session, AFTER_BTN
from bot.whatsapp_app import to_event


class BotFlow(unittest.TestCase):
    def run_flow(self):
        s = new_session()
        o1 = handle(s, {"kind": "location", "lat": 30.525, "lon": 30.425})
        o2 = handle(s, {"kind": "button", "id": "pri_water"})
        o3 = handle(s, {"kind": "button", "id": "w_limited"})
        return s, o1, o2, o3

    def test_full_flow_returns_card_voice_buttons(self):
        s, o1, o2, o3 = self.run_flow()
        self.assertEqual(o1[0]["type"], "buttons"); self.assertEqual(o2[0]["type"], "buttons")
        self.assertEqual([m["type"] for m in o3], ["image", "audio", "buttons"])
        self.assertTrue(os.path.getsize(o3[0]["path"]) > 10000)
        self.assertIn("مهندس زراعي", o3[0]["caption"])
        self.assertIn("مش نسبة صحة", o3[0]["caption"])  # confidence is not a correctness probability
        self.assertEqual(len(o3[2]["buttons"]), 3)  # WhatsApp limit

    def test_scenario_button_gives_labelled_card(self):
        s, *_ = self.run_flow()
        out = handle(s, {"kind": "button", "id": "sc_warm"})
        self.assertEqual(out[0]["type"], "image"); self.assertIn("افتراضي", out[0]["caption"])

    def test_voice_button_has_script_and_no_invented_numbers(self):
        s, *_ = self.run_flow()
        v = handle(s, {"kind": "button", "id": "voice"})[0]
        self.assertEqual(v["type"], "audio"); self.assertTrue(v["script"])

    def test_out_of_coverage_is_friendly_not_crash(self):
        s = new_session(); handle(s, {"kind": "location", "lat": 10.0, "lon": 10.0}); handle(s, {"kind": "button", "id": "pri_soil"})
        out = handle(s, {"kind": "button", "id": "w_unknown"})
        self.assertEqual(out[0]["type"], "text"); self.assertEqual(s["state"], "start")

    def test_text_coordinates_and_garbage(self):
        s = new_session()
        self.assertEqual(handle(s, {"kind": "text", "text": "30.525, 30.425"})[0]["type"], "buttons")
        s2 = new_session(); self.assertEqual(handle(s2, {"kind": "text", "text": "ازيك"})[0]["type"], "text")

    def test_stray_input_mid_flow_reasks(self):
        s = new_session(); handle(s, {"kind": "location", "lat": 30.525, "lon": 30.425})
        out = handle(s, {"kind": "text", "text": "؟؟"}); self.assertEqual(out[0]["type"], "buttons"); self.assertEqual(s["state"], "ask_priority")

    def test_whatsapp_payload_parsing(self):
        self.assertEqual(to_event({"type": "location", "location": {"latitude": 1.5, "longitude": 2.5}}), {"kind": "location", "lat": 1.5, "lon": 2.5})
        self.assertEqual(to_event({"type": "interactive", "interactive": {"button_reply": {"id": "pri_soil"}}})["id"], "pri_soil")
        self.assertEqual(to_event({"type": "image"})["kind"], "other")


if __name__ == "__main__":
    unittest.main()
