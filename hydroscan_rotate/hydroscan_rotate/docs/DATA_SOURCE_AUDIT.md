# Data-source audit (state at hand-over)

**Evidence rule used:** "VERIFIED" = I executed the code against real data/files and inspected the result. "CODED, NOT VERIFIED LIVE" = code and parsers exist and pass tests on synthetic inputs, but the build sandbox blocks NASA, ISRIC and Google hosts (only PyPI is reachable), so no real response was ever received. The sandbox probe is in `docs/LIVE_CHECK_SANDBOX_RESULT.md`. **Real retrieval evidence will exist only after you run `python -m tools.live_check` (SETUP_GUIDE.md).**

| # | Source | Status | Date coverage | Spatial resolution | Access requirement |
|---|---|---|---|---|---|
| 1 | Supplied Sentinel-1/2 composite (`farm_stack.tif`) + HydroScan RF | **VERIFIED** (file read, 3,302 pixels at demo field). Not a live feed. | one composite, 2026 | ~9 m pixels, bbox ≈ 5 km | none (already in project) |
| 2 | Project `timeseries.csv` (real GEE output) | **VERIFIED** (10 monthly values, area mean) | Jan–Oct 2026 | 10 m averaged over ~5 km box | none |
| 3 | NASA POWER daily | CODED, NOT VERIFIED LIVE. Parsing, monthly aggregation, ET0 maths tested on synthetic fixtures | 1981 → near present (per POWER docs); tool requests last 10 full years | ~0.5° × 0.625° cell | none (no key, no account) |
| 4 | ISRIC SoilGrids | WCS route CODED, NOT VERIFIED LIVE (URL pattern and coverage ids `<prop>_<depth>_mean` written from ISRIC documentation, unconfirmed). **REST API is paused by ISRIC** (confirmed on docs.isric.org), so REST is only a last resort. GEE community dataset is the second route | static maps (2020 release) | 250 m | WCS: none. GEE route: GEE account |
| 5 | Sentinel-2 SR Harmonized NDVI via GEE (multi-year) | CODED, NOT RUN (needs GEE) | 2017 → present in catalogue; tool requests 2021–2025 | 10 m, mean within 150 m of the point | Google account + Earth Engine registration + Cloud project id + `earthengine authenticate` |
| 6 | NASA GPM IMERG V07 via GEE | CODED, NOT RUN (needs GEE; dataset id in `config.GEE_IDS`) | 2000 → present (catalogue); tool requests 2021–2025 | 0.1° (~11 km) | same GEE setup. (Direct Earthdata download is the alternative: free Earthdata login, not implemented) |
| 7 | NASA SMAP L3 (SPL3SMP_E) via GEE | CODED, NOT RUN (dataset id/version may need adjusting, in `config.GEE_IDS`) | 2015 → present; tool requests 2021–2025 | ~9 km | same GEE setup |
| 8 | SRTM, GRACE/GRACE-FO, ECOSTRESS, ERA5, FAO GAEZ, MODIS/VIIRS | **Not integrated** (not requested in this phase) | – | – | – |
| 9 | FAO crop water needs (Kc) | **Not used numerically.** No verified Egyptian crop coefficients, so crop water need (ETc) is NOT calculated | – | – | – |
| 10 | Egyptian crop literature | 16 sources recorded (`rotation/egypt_references.json`), read at abstract/excerpt level only | – | – | – |

## Which need an account / key / GEE
- **None needed:** POWER, SoilGrids WCS, the supplied project files.
- **Google Earth Engine needed:** Sentinel-2 multi-year NDVI, IMERG, SMAP (and the SoilGrids-on-GEE route). One-time setup, free for non-commercial use (check Google's current terms for your use).
- **Meta/WhatsApp Business account:** only for the real WhatsApp channel (separate, not data).

## Which current results are still illustrative / assumed
See `docs/ILLUSTRATIVE_VALUES_INVENTORY.md`. Short version: the hand-entered climate table was **removed from all results** this phase; what remains are labelled analyst assumptions (crop ratings, weights, thresholds, rotation cycle length) and the unvalidated HydroScan vegetation-density model.

## Findings from this audit
1. **Bug found and fixed:** the previous field card computed with an illustrative climate table without marking it, and its "missing data" line was hard-coded. Both fixed (card now shows ✔/✖ per source and a computed missing list).
2. The demo field (30.525 N, 30.425 E) appears to be north-west Delta desert-fringe land, not typical old-land Delta. Most Egyptian research found was done at Sakha (Kafr El-Sheikh, ~31.12 N, 30.95 E). `live_check` tests both sites; the full HydroScan pipeline only works where the supplied Sentinel stack exists.
3. Wheat, faba bean and berseem are **all winter crops**. A 3-stage sequence such as wheat → faba bean → maize cannot occur in one year; the project's 2-year cycle length is an assumption an agronomist must define.
