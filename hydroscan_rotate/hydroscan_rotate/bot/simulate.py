"""Local WhatsApp-style simulator (no Meta account, no network). Interactive CLI:
   python -m bot.simulate        -> type coordinates, then 1/2/3 to press buttons
   python -m bot.simulate --demo -> scripted demo run, writes cards to ./sim_out/"""
import os
import shutil
import sys

from bot.conversation import handle, new_session


def show(msgs, outdir):
    last = None
    for m in msgs:
        if m["type"] == "text": print("🤖", m["text"])
        elif m["type"] == "buttons":
            print("🤖", m["text"]); [print(f"   [{i+1}] {t}") for i, (_, t) in enumerate(m["buttons"])]; last = m
        elif m["type"] == "image":
            os.makedirs(outdir, exist_ok=True); dst = os.path.join(outdir, os.path.basename(m["path"])); shutil.copy(m["path"], dst)
            print(f"🖼️  [card saved: {dst}]\n   {m['caption']}")
        elif m["type"] == "audio":
            print("🔊 [audio file]" if m["path"] else "🔊 [no TTS here, script as text]:", m["script"])
    return last


def main():
    s, outdir, last = new_session(), "sim_out", None
    if "--demo" in sys.argv:
        last = show(handle(s, {"kind": "location", "lat": 30.525, "lon": 30.425}), outdir)
        last = show(handle(s, {"kind": "button", "id": "pri_water"}), outdir)
        last = show(handle(s, {"kind": "button", "id": "w_limited"}), outdir)
        show(handle(s, {"kind": "button", "id": "sc_warm"}), outdir); return
    show(handle(s, {"kind": "text", "text": "ابدأ"}), outdir)
    while True:
        t = input("👤 ").strip()
        if last and t.isdigit() and 1 <= int(t) <= len(last["buttons"]):
            ev = {"kind": "button", "id": last["buttons"][int(t) - 1][0]}
        else:
            ev = {"kind": "text", "text": t}
        last = show(handle(s, ev), outdir) or last


if __name__ == "__main__":
    main()
