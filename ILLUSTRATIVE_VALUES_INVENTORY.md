# Every hard-coded, simulated, estimated or illustrative value

| Value | Where | Action this phase | Current label in output |
|---|---|---|---|
| Hand-entered monthly climate table (T, rain) | was `data/fallback/…json`, used silently by card/scenarios | **Removed from runtime.** Moved to `tests/fixtures/`. `prov()` now rejects kind ILLUSTRATIVE and status "fallback" | climate shows "unavailable" |
| Card line "missing: soil, measured climate, prices" | `reports/field_card.py` | Replaced by a list computed from real source status | ✔/✖ per source |
| Card/report "based on 1 year" text | card | Now computed from the calendar's year count | computed |
| Crop ratings (water demand, soil cover, heat sensitivity…) | `rotation/crop_database.json` | **Kept**, flagged `analyst_assumption`; Egyptian literature added beside them, not yet used to replace them | "analyst assumption (unverified)" |
| Criteria weights, thresholds, point rules | `rotation/scoring_rules.json` | Kept; prototype weights | "derived by this tool" |
| Rotation `cycle_years` and the 3 rotations themselves | `rotation_library.json` | Kept; **agronomically questionable** (all winter crops), needs expert | flagged in limitations |
| Bare-soil NDVI threshold 0.25 | `config.py` | Kept; adjustable | caveat printed |
| Hot-day 35 °C, frost-day 0 °C, buffer 150 m, NDVI outlier bounds | `config.py`, `ndvi.py` | Kept; analyst-chosen | stated in provenance method |
| Hargreaves coefficient 0.0023 (generic) | `nasa_power.py` | Kept; real published formula, not Egypt-calibrated | "modelled" |
| Scenario deltas (+2 °C, −20 % rain) | `scenarios.py` | Kept by design | "hypothetical scenario" |
| HydroScan RF (trained on NDVI pseudo-labels; 99 % agreement with a plain NDVI rule) | `hydroscan/` | Kept; irrigation/crop classes remain **null** | "model prediction (not validated)" |
| Demo field coordinates and stack | `config.DEMO_FIELD` | Kept; it is real satellite data, but one location | – |
| Arabic voice-script wording | `reports/audio_summary.py` | Template text; numbers come from results | – |
| Income | – | **Not scored** unless the farmer supplies yield, price, cost | "not scored" |
| Prices, yields, costs | – | **No values stored** (null); no Egyptian source integrated | unavailable |
