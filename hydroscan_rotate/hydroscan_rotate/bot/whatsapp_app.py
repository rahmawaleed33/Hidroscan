"""WhatsApp Cloud API webhook (Flask). UNVERIFIED LIVE: needs a Meta app, WHATSAPP_TOKEN, WHATSAPP_PHONE_ID, VERIFY_TOKEN.
Run: python -m bot.whatsapp_app   (expose with a tunnel; set the webhook URL in the Meta dashboard).
Media upload is required to send images/audio: see send_image/send_audio (Graph API /media)."""
import mimetypes
import os

import requests
from flask import Flask, request

from bot.conversation import handle, new_session

app = Flask(__name__)
SESSIONS = {}
TOKEN = os.environ.get("WHATSAPP_TOKEN", ""); PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", ""); VERIFY = os.environ.get("VERIFY_TOKEN", "hydroscan")
GRAPH = "https://graph.facebook.com/v20.0"
H = lambda: {"Authorization": f"Bearer {TOKEN}"}


def _post(payload):
    return requests.post(f"{GRAPH}/{PHONE_ID}/messages", headers=H(), json={"messaging_product": "whatsapp", **payload}, timeout=20)


def _upload(path):
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        r = requests.post(f"{GRAPH}/{PHONE_ID}/media", headers=H(), data={"messaging_product": "whatsapp"}, files={"file": (os.path.basename(path), f, mime)}, timeout=60)
    return r.json()["id"]


def send(to, msg):
    if msg["type"] == "text":
        _post({"to": to, "type": "text", "text": {"body": msg["text"]}})
    elif msg["type"] == "buttons":  # WhatsApp allows max 3 reply buttons, title <= 20 chars
        _post({"to": to, "type": "interactive", "interactive": {"type": "button", "body": {"text": msg["text"]},
               "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": t[:20]}} for i, t in msg["buttons"][:3]]}}})
    elif msg["type"] == "image":
        _post({"to": to, "type": "image", "image": {"id": _upload(msg["path"]), "caption": msg["caption"][:1000]}})
    elif msg["type"] == "audio":
        if msg.get("path"):
            _post({"to": to, "type": "audio", "audio": {"id": _upload(msg["path"])}})
        else:  # no TTS available: send the script as text instead
            _post({"to": to, "type": "text", "text": {"body": "🔊 " + msg["script"]}})


def to_event(m):
    t = m.get("type")
    if t == "location":
        return {"kind": "location", "lat": m["location"]["latitude"], "lon": m["location"]["longitude"]}
    if t == "interactive":
        return {"kind": "button", "id": m["interactive"]["button_reply"]["id"]}
    if t == "text":
        return {"kind": "text", "text": m["text"]["body"]}
    return {"kind": "other"}


@app.get("/webhook")
def verify():
    if request.args.get("hub.verify_token") == VERIFY:
        return request.args.get("hub.challenge", ""), 200
    return "forbidden", 403


@app.post("/webhook")
def incoming():
    data = request.get_json(silent=True) or {}
    for entry in data.get("entry", []):
        for ch in entry.get("changes", []):
            for m in ch.get("value", {}).get("messages", []):
                s = SESSIONS.setdefault(m["from"], new_session())
                for out in handle(s, to_event(m)):
                    send(m["from"], out)
    return "ok", 200


if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 8080)))
