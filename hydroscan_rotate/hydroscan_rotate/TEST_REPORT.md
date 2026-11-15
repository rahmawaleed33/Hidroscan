# TEST_REPORT.md
Run: `python -m unittest discover -s tests -t . -v` — **60 tests, 60 passed** (sandbox: no network, no rasterio, no streamlit).

| Area | Verified |
|---|---|
| HydroScan adapter | valid/invalid/out-of-coverage coordinates, output schema, band order & NDVI range, features identical to original `make_features`, original model hash unchanged, comparison TIFF differs from demo TIFF, missing raster |
| Data sources | POWER and SoilGrids **parsing** (missing -999, units, d_factor) using shape fixtures; texture classes; offline fallback labelled ILLUSTRATIVE; soil unavailable offline; bad response doesn't crash; real `timeseries.csv` metadata |
| NDVI / bare soil | NDVI formula (incl. 0/0), outlier removal, trend guard (<24 months), unknown months never "bare", configurable threshold |
| Scoring | 3 rotations, determinism, missing economics not zero-filled and weights renormalised, priority weights, limited-water penalty, legume benefit, farmer income inputs, partial inputs, invalid inputs, no invented crop numbers, data support never "High" without verified sources |
| Scenarios | baseline = no change, +2 C and -20% rain, input profile unmodified, range check, missing climate handled |
| End to end | pipeline → PDF/HTML/PNG generated, disclaimer present, Arabic script has no invented numbers |

## NOT tested / unverified
- `app.py` (Streamlit): executed headlessly with `streamlit.testing.AppTest` offline: all 6 pages, analysis and card button, 0 exceptions. NOT checked in a real browser (folium map needs `streamlit-folium`; layout/RTL look unseen).
- Live NASA POWER, SoilGrids, GPM IMERG, GEE multi-year NDVI: **never called live** (no network/credentials). Only parsers and offline behaviour are tested.
- Arabic audio (gTTS), Arabic wording quality (needs native review), Arabic in PDF/PNG (not supported; HTML only).
- Scientific validity of every ordinal rating and weight: unvalidated prototype rules.

| Bot / card | full conversation flow, scenario card, voice step, out-of-coverage reply, text coordinates, stray input, WhatsApp payload parsing |

- NOT tested: real WhatsApp Cloud API sending/media upload (needs Meta credentials); gTTS audio (needs internet); live NASA POWER / SoilGrids / GPM.

## Real-data phase
- 60/60 pass offline. New: POWER daily parsing/aggregation, ET0 sanity, WCS tiff parsing+scaling (synthetic GeoTIFF), IMERG/SMAP parsers, schema refuses illustrative/fallback data, traceability rows, no sample numbers in profile, Egyptian reference ids resolve.
- Streamlit executed headlessly in farmer and expert mode, all pages, 0 exceptions.
- **Not verified: any live NASA / ISRIC / GEE response.** Sandbox probe in docs/LIVE_CHECK_SANDBOX_RESULT.md.
