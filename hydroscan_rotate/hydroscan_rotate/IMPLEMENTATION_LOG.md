# IMPLEMENTATION_LOG.md
| # | Milestone | Files | Result |
|---|---|---|---|
| 0 | Audit | PROJECT_AUDIT.md | model = vegetation density ≈ NDVI rule (99.07%); no irrigation/crop model; labels_real.csv empty |
| 1 | HydroScan adapter | hydroscan/model_adapter.py, schemas.py, config.py | `analyze_field(lat, lon)` works; irrigation/crop returned as `null` with reason |
| 2 | Data adapters | data_sources/* | cache → fallback → unavailable; live paths untested |
| 3 | Field analysis | analysis/* | NDVI summary, bare-soil calendar (Nov/Dec unknown), climate, soil, `field_profile` |
| 4 | Knowledge base | rotation/crop_database.json, rotation_library.json, scoring_rules.json | qualitative only; all quantitative fields null; `verified_against_source=false` |
| 5 | Scoring + uncertainty + scenarios | rotation/*.py | transparent, economic unscored without farmer inputs |
| 6 | App, report, Arabic summary | app.py, reports/*, pipeline.py | report generated and checked visually; app not executed |
| 7 | Tests | tests/* | 38/38 pass |

## Decisions / assumptions (reversible)
- Irrigation status is never claimed. Water availability comes from the farmer.
- Rotations B and C list two winter crops, so `cycle_years = 2` is assumed (editable in rotation_library.json).
- Hargreaves-style (T+17.8) factor is used only as a RELATIVE evaporative-demand proxy in scenarios; scenario point values are assumptions in scoring_rules.json.
- Illustrative climate fallback is hand-entered approximate data, flagged everywhere, treated as low evidence.
- Original files are kept unmodified in `original_hydroscan/`; `data/` holds copies used by the app.
| 8 | Arabic field card | reports/field_card.py | one PNG: status, 12-month bare calendar, 3 rotations with 🟢🟡🔴, data-support level, expert disclaimer. Arabic via matplotlib>=3.11 native shaping (pre-shaping with arabic-reshaper breaks it) |
| 9 | WhatsApp bot | bot/conversation.py, bot/whatsapp_app.py, bot/simulate.py | location → priority buttons → water buttons → card + voice script → what-if buttons. Logic tested offline; Meta Cloud API sender NOT tested live |
| 10 | Verification pass | tests/test_bot_card.py | 45/45 tests; Streamlit app executed headlessly (AppTest) on all 6 pages, 0 exceptions |
| 11 | Real-data phase | data_sources/{nasa_power,soilgrids,gpm,smap,sentinel,gee_client}.py, tools/live_check.py | POWER daily + ET0; SoilGrids WCS->GEE->REST; Sentinel-2 multi-year, IMERG, SMAP via GEE. Illustrative climate removed from runtime. NOT verified live (sandbox blocks hosts) |
| 12 | Traceability + Egypt references | reports/traceability.py, expert_report.py, rotation/egypt_references.json | provenance table per result; 16 Egyptian sources at abstract level |
| 13 | Docs | docs/ | audit, illustrative inventory, setup guide, limitations, design handoff, sample report |
