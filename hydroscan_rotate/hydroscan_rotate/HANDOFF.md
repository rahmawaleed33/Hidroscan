# HANDOFF.md
**State:** offline prototype: engine, Arabic field card, WhatsApp conversation logic and Streamlit UI all run offline (45 tests). Live data and the real WhatsApp channel are not connected.

## Run
```
pip install -r requirements.txt
python -m unittest discover -s tests -t .
python -m streamlit run app.py
# optional live data:  set HYDROSCAN_GEE_PROJECT=your-project ; earthengine authenticate
```
Env vars: `HYDROSCAN_GEE_PROJECT` (optional), `HYDROSCAN_OFFLINE=1` (never call network).

## Architecture
`pipeline.run_analysis` → `analysis.field_profile` (hydroscan adapter + data_sources + analysis) → `rotation.scoring/uncertainty/scenarios` → `reports/*`. UI: `app.py`.

## Next steps (priority order)
1. Run `app.py`, fix any UI errors. 2. Run with internet: confirm POWER + SoilGrids live (fallback disappears). 3. Add a GEE project; verify `data_sources/gpm.py` and `sentinel.fetch_ndvi_history` (3-5 yr NDVI). 4. Have an agronomist verify/replace every `analyst_assumption` and fill yields/water needs from ARC/FAO-56/FAOSTAT; then set `verified_against_source`. 5. Collect real irrigation/crop labels (label_tool.py) before any irrigation/crop claim. 6. Arabic review; Arabic PDF (needs arabic-reshaper + python-bidi). 7. Optional: SMAP, SRTM, GAEZ, WhatsApp-style simulation.

## Blockers
No GEE project; no ground-truth labels; no verified Egyptian crop data; sandbox had no network.


## WhatsApp bot
Simulate: `python -m bot.simulate --demo` (or without `--demo` for interactive). Real channel: set `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `VERIFY_TOKEN`, run `python -m bot.whatsapp_app`, point the Meta webhook at `/webhook`. Never tested against Meta.

## Start here (real-data phase)
1. `docs/SETUP_GUIDE.md` -> run `python -m tools.live_check` and send back `LIVE_CHECK_EVIDENCE.md`.
2. `docs/DATA_SOURCE_AUDIT.md`, `docs/LIMITATIONS.md`, `docs/ILLUSTRATIVE_VALUES_INVENTORY.md`.
3. `docs/DESIGN_HANDOFF.md` for UI/UX design; `docs/SAMPLE_FIELD_REPORT.md` for the evidence report format.
