# Remaining limitations, missing data, assumptions, and what needs expert validation

## A. Not yet real (needs your action)
1. **No live retrieval has been observed.** POWER, SoilGrids, Sentinel-2/IMERG/SMAP via GEE are coded and unit-tested on synthetic inputs only. Run `tools/live_check` (SETUP_GUIDE.md) to produce real evidence; expect to fix small issues (SoilGrids WCS URL/coverage ids, GEE dataset ids/bands, which are all in one place: `data_sources/soilgrids.py`, `config.GEE_IDS`).
2. **Multi-year, field-level NDVI** exists only after GEE is set up. Until then NDVI is the project's 2026 area mean (10 months), so the bare-soil calendar is a single partial year.

## B. Data limits that apply even when everything connects
- **Resolution mismatch for small Egyptian holdings:** POWER ~50 km, SMAP ~9 km, IMERG ~11 km, SoilGrids 250 m, Sentinel-2 10 m. A field is far smaller than the first three. They describe the region, not the field. SMAP in particular cannot see irrigated plots.
- **Irrigation, not rain, drives Delta/Valley crops.** Satellite rainfall is mostly regional context; canal water supply and rotation (turn-based irrigation, *namaq*) are not observed anywhere.
- **SoilGrids** is a global ML map; alluvial, salinised and reclaimed soils are weakly represented. No salinity layer is used. A lab soil test is required.
- **Point, not boundary:** the farmer shares a point; neighbouring fields can contaminate the 150 m NDVI buffer.
- **Reanalysis ET0 (Hargreaves)** is a reference demand with a generic coefficient; **crop water need (ETc) is not computed** (no verified Egyptian Kc).
- **HydroScan model:** vegetation density only. **No irrigation or crop classification, no accuracy figure, no confidence percentage.** Labels were NDVI pseudo-labels.
- **No prices, yields, or costs** from any Egyptian source (Ministry of Agriculture economic statistics, CAPMAS, wholesale markets not integrated). Income criterion is "not scored" unless the farmer enters numbers.
- Not integrated: SRTM slope/erosion, GRACE, ECOSTRESS, ERA5, GAEZ, MODIS/VIIRS.

## C. Egyptian agronomy: what was found and how far to trust it
- 16 sources in `rotation/egypt_references.json`: mostly ARC research-station experiments (Sakha, Shandaweel, El-Bosaily, El-Karada, Giza/Dokki, El-Minia). **Read from abstracts/excerpts only**, not full texts; 2 are secondary citations and 1 is lecture material.
- They are **experiments, not official Ministry of Agriculture recommendations.** Water values are experiment-specific and not comparable between methods (e.g. wheat 1,606–2,124 applied vs 4,230–6,087 CROPWAT-modelled m³/feddan). **No single water requirement per crop is adopted.**
- Planting windows (research-indicated): wheat 15–30 Nov (north Delta, secondary citation); faba bean ~mid-Oct to mid-Nov with a yield vs broomrape trade-off; berseem 1–mid Oct; maize May (1–15 May best).
- **Rotation benefit evidence: none found** beyond maize being grown after berseem and after faba bean in trials. Nitrogen savings, pest-cycle breaks and soil-cover claims in the scoring are general agronomy/assumptions.
- **Structural problem for the expert:** wheat, faba bean and berseem are all winter crops; the three listed rotations mix them in ways that cannot fit one year. Cycle length and sequence definitions must be set by an agronomist.

## D. Must be validated by an agricultural expert before any farmer sees it
1. The three rotation definitions and `cycle_years`. 2. Every ordinal crop rating (water demand, heat sensitivity, soil cover, legume benefit). 3. Scoring weights and colour thresholds. 4. Planting windows per governorate/variety. 5. Water-need ranges and which to adopt (and Egyptian Kc). 6. NDVI bare-soil threshold (0.25) against local fields. 7. Faba bean broomrape (*Orobanche*) risk by region. 8. The Arabic wording of every farmer-facing sentence (dialect, clarity, safety).
