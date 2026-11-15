"""Transport-independent WhatsApp conversation logic (location -> priority -> water -> card + voice -> what-if).
handle() takes a session dict and ONE incoming event, returns a list of outgoing messages:
  {"type":"text","text":..} | {"type":"buttons","text":..,"buttons":[(id,label),..]} | {"type":"image","path":..,"caption":..} | {"type":"audio","path":..,"script":..}
No network calls here, so it is fully unit-testable."""
import os
import re
import tempfile

import config
from pipeline import run_analysis
from reports.audio_summary import arabic_script, make_audio
from reports.field_card import make_field_card, PRI_AR
from rotation.scenarios import PRESETS
from schemas import HydroScanError

OUT_DIR = os.path.join(tempfile.gettempdir(), "hydroscan_bot")
DISCLAIMER = "⚠️ تقييم مبدئي مش نصيحة زراعية معتمدة. راجع مهندس زراعي أو الإرشاد الزراعي قبل أي قرار."
PRI_BTN = [("pri_water", "💧 مية"), ("pri_income", "💰 دخل"), ("pri_soil", "🌱 تربة")]
WATER_BTN = [("w_sufficient", "كفاية"), ("w_limited", "محدودة"), ("w_unknown", "مش عارف")]
AFTER_BTN = [("sc_warm", "🔥 لو الصيف أسخن"), ("sc_dry", "🌧️ لو المطر قل"), ("voice", "🔊 ملخص صوتي")]
SCN_KEY = {"sc_warm": "warm_2c", "sc_dry": "dry_20"}


def new_session():
    return {"state": "start", "lat": None, "lon": None, "priority": None, "water": None, "result": None}


def _text(t): return {"type": "text", "text": t}


def _parse_latlon(text):
    m = re.search(r"(-?\d{1,2}\.\d+)\s*[,،\s]\s*(-?\d{1,3}\.\d+)", text or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def _card(session, scenario_key=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    r = session["result"]
    label = None
    if scenario_key:
        sc = r["scenarios"][scenario_key]
        label = PRESETS[scenario_key]["label_ar"]
        # rebuild a result view whose ranking is the scenario ranking
        view = dict(r); view["ranked"] = sc["scenario"]
    else:
        view = r
    path = os.path.join(OUT_DIR, f"card_{abs(hash((session['lat'], session['lon'], scenario_key))) % 10**8}.png")
    make_field_card(view, path, scenario_label=label)
    return path, view


def handle(session, event):
    """event: {"kind":"text","text":..} | {"kind":"location","lat":..,"lon":..} | {"kind":"button","id":..}"""
    kind, st = event.get("kind"), session["state"]
    if kind == "text" and event["text"].strip() in ("ابدأ", "start", "/start", "مرحبا", "السلام عليكم"):
        session.update(new_session())
        st = "start"
    # --- location (any state): restart analysis with a new field
    loc = None
    if kind == "location":
        loc = (event["lat"], event["lon"])
    elif kind == "text":
        loc = _parse_latlon(event["text"])
    if loc:
        session.update(lat=loc[0], lon=loc[1], priority=None, water=None, result=None, state="ask_priority")
        return [{"type": "buttons", "text": "أهلاً بيك 🌾 استلمت موقع حقلك.\nإيه أهم حاجة عندك؟", "buttons": PRI_BTN}]

    if st == "start":
        return [_text("أهلاً بيك في HydroScan Rotate 🌾\nابعتلي لوكيشن حقلك (📎 ← الموقع)، وأنا أقارنلك ٣ دورات زراعية.\nلو عايز تجرب: اكتب  30.525, 30.425")]

    if kind == "button":
        bid = event["id"]
        if st == "ask_priority" and bid in dict(PRI_BTN):
            session["priority"] = bid[4:]; session["state"] = "ask_water"
            return [{"type": "buttons", "text": "المية عندك كفاية للموسم ولا محدودة؟", "buttons": WATER_BTN}]
        if st == "ask_water" and bid in dict(WATER_BTN):
            session["water"] = bid[2:]
            return _analyze(session)
        if st == "done" and bid in SCN_KEY:
            path, view = _card(session, SCN_KEY[bid])
            sc = session["result"]["scenarios"][SCN_KEY[bid]]
            note = "الترتيب اتغيّر." if sc["ranking_changed"] else "الترتيب ماتغيّرش."
            return [{"type": "image", "path": path, "caption": f"سيناريو افتراضي: {PRESETS[SCN_KEY[bid]]['label_ar']} — {note}\n{sc['label_ar']}\n{DISCLAIMER}"},
                    {"type": "buttons", "text": "تحب تجرب حاجة تانية؟", "buttons": AFTER_BTN}]
        if st == "done" and bid == "voice":
            return [_voice(session), {"type": "buttons", "text": "تحب تجرب حاجة تانية؟", "buttons": AFTER_BTN}]
    if st == "ask_priority":
        return [{"type": "buttons", "text": "اختار من الأزرار: إيه أهم حاجة عندك؟", "buttons": PRI_BTN}]
    if st == "ask_water":
        return [{"type": "buttons", "text": "اختار من الأزرار: حالة المية؟", "buttons": WATER_BTN}]
    if st == "done":
        return [{"type": "buttons", "text": "تحب تجرب إيه؟ أو ابعت لوكيشن حقل تاني.", "buttons": AFTER_BTN}]
    return [_text("ابعتلي لوكيشن حقلك عشان نبدأ.")]


def _analyze(session):
    try:
        session["result"] = run_analysis(session["lat"], session["lon"], session["priority"], session["water"])
    except HydroScanError as exc:
        session.update(state="start", result=None)
        return [_text(f"للأسف الموقع ده برا تغطية صور HydroScan الحالية (حقول تجريبية بس). جرب الحقل التجريبي: {config.DEMO_FIELD['lat']}, {config.DEMO_FIELD['lon']}")]
    session["state"] = "done"
    path, _ = _card(session)
    r = session["result"]; top = r["ranked"][0]
    cap = (f"أولويتك: {PRI_AR[session['priority']]}\nأعلى دورة في التقييم: {top['rotation_name']['ar']} ({top['overall']:.0f}/100، مبدئي)\n"
           f"{r['uncertainty']['data_support_ar']} — مش نسبة صحة التوصية.\n{DISCLAIMER}")
    return [{"type": "image", "path": path, "caption": cap}, _voice(session), {"type": "buttons", "text": "تحب تجرب سيناريو؟", "buttons": AFTER_BTN}]


def _voice(session):
    script = arabic_script(session["result"])
    os.makedirs(OUT_DIR, exist_ok=True)
    audio = make_audio(script, os.path.join(OUT_DIR, "summary_ar.mp3"))  # None when gTTS/internet unavailable
    return {"type": "audio", "path": audio, "script": script}
