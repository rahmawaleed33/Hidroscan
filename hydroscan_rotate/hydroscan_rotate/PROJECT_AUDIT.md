# PROJECT_AUDIT.md — HydroScan → HydroScan Rotate

Audit date: 2026-11-14. Method: read every uploaded file; ran the model and read the rasters in a sandbox.
Status labels: **VERIFIED** (I ran it) · **NOT VERIFIED** (read in code only) · **PARTIAL** · **MISSING** · **BLOCKED**.

## 1. Files received (16)

| File | Role |
|---|---|
| `gee_pipeline.py` | GEE → 3-band GeoTIFF (VV, VH, NDVI), Sentinel-1 + Sentinel-2 |
| `timeseries.py` | GEE monthly NDVI / VV / VH / SMAP → `timeseries.csv` |
| `make_labels.py` | Generates **pseudo-labels from NDVI thresholds** → `labels.csv` |
| `label_tool.py` | Streamlit map tool for manual labels → `labels_real.csv` |
| `model_training.py` | RandomForest training, shared `make_features()` |
| `hydroscan_dashboard.py` | Streamlit v2: stack + model → mask, trends tab |
| `app.py` | Streamlit "Farm Monitor": draw box → GEE NDVI/NDWI → irrigated polygons (rule-based) |
| `hydroscan_universal.py` | Streamlit generic raster tool (train / cluster / map / download SMAP, Landsat) |
| `farm_stack.tif`, `sentinel-2_202608.tif` | 557×558 px, 3 bands, EPSG:4326, ~10 m |
| `model.joblib` / `model.pkl` | Byte-identical (same MD5) RandomForest |
| `labels.csv` (300 pts), `labels_real.csv` (header only) | Labels |
| `timeseries.csv` | 10 months of 2026 |
| `README.txt` | Run instructions |

Also supplied as context: NASA data-source list and the master prompt.

## 2. Stack
Python; Streamlit, folium/streamlit-folium, rasterio, scikit-learn, pandas, numpy, scipy, matplotlib, earthengine-api, joblib. Optional: shapely.
Sandbox note: `rasterio` and network access are **not available here**, so GEE/NASA calls cannot be run in this session. I read the TIFFs with `tifffile` instead.

## 3. Findings that change the plan (most important)

1. **There is no irrigation model and no crop model.** `model.joblib` is a RandomForest with classes `bare_soil`, `dense_veg`, `sparse_veg`. Those are vegetation-density classes, not irrigation status and not crop type.
2. **The model is effectively the NDVI threshold rule.** Trained on `labels.csv`, which `make_labels.py` itself describes as pseudo-labels from NDVI (<0.20 / <0.45). Verified: on `farm_stack.tif` its predictions agree with the plain NDVI rule on **99.07 %** of the 310,806 pixels; NDVI carries 71 % of feature importance. Any accuracy figure from it (e.g. the ~100 % CV the dashboard would show) would be circular and must not be presented as validation.
3. **`labels_real.csv` is empty** (header only) — no ground-truth labels exist, and `metrics.json` was not supplied.
4. **The only "irrigation" logic is a rule in `app.py`** (`classify()`): 90th-percentile Sentinel-2 NDVI over a period ≥ threshold, optional NDWI water exclusion, morphological cleaning, minimum patch size. It is a heuristic ("green in a dry region ⇒ irrigated"), not a trained or validated classifier. It requires live GEE.
5. **No GPM/IMERG, NASA POWER, SoilGrids or crop-type code anywhere.** SMAP appears in `timeseries.py` and `hydroscan_universal.py`, but `timeseries.csv` has an **empty `soil_moisture` column** — SMAP never returned data.
6. **Historical depth is one year** (Jan–Oct 2026), not the 3–5 years targeted. Monthly NDVI is 0.33–0.38 throughout: very flat, so seasonal peaks and bare-soil periods will be hard to distinguish at field-mean scale.
7. Possible defects (not run, flag only): `app.py` calls `json.dumps` (~line 429) but its import block shows no `import json`; `hydroscan_dashboard.py` expects `metrics.json`, which is missing; `model_training.py` imports are fine but `rasterio` is required everywhere.
8. The two TIFFs have identical grid/bounds but different values (mean NDVI 0.318 vs 0.363). The file named `…202608` and the stack dated from 2026-09-01 are different composites; the app should record which one is used.

## 4. Feature classification

| Feature | Status |
|---|---|
| Sentinel-1 VV/VH + Sentinel-2 NDVI GEE pipeline | IMPLEMENTED, NOT VERIFIED (needs GEE; output TIFFs exist and read correctly: bands VV, VH, NDVI, nodata −9999, no nodata pixels present) |
| 3-band stack read + band order (VV, VH, NDVI) | **VERIFIED** |
| Vegetation-density classifier (bare/sparse/dense) | **VERIFIED** runs; ≈ NDVI rule |
| Irrigation classification (trained) | **NOT IMPLEMENTED** |
| Irrigation heuristic (NDVI peak rule) | IMPLEMENTED, NOT VERIFIED (needs GEE) |
| Crop-type classification | **NOT IMPLEMENTED** |
| Ground-truth labels | **MISSING** |
| Monthly NDVI/VV/VH series (1 yr) | PARTIAL (data present, real-looking, 10 months) |
| SMAP soil moisture | BLOCKED/empty (no values returned) |
| GPM/IMERG, NASA POWER, SoilGrids | NOT IMPLEMENTED |
| Streamlit UIs, label tool | IMPLEMENTED, NOT VERIFIED (no streamlit/rasterio here) |
| Egyptian crop DB, rotation scoring, scenarios, report, Arabic UI | NOT IMPLEMENTED |

## 5. Reusable components
- `model_training.make_features`, `NODATA`; `model.joblib` (keep untouched).
- Raster reading/georeferencing logic (bounds from EPSG:4326 transform; ~10 m px).
- `gee_pipeline`: `make_region`, `date_range`, `mask_s2_clouds`, `add_ndvi`, `init_earth_engine` (reuse for historical NDVI rather than rewrite).
- `timeseries.month_row` (extend to more years).
- `app.classify()` as the "irrigation heuristic" if a live GEE session is available.

## 6. Fastest way to expose HydroScan as a function
`hydroscan_adapter.analyze_field(lat, lon, stack_path=…, radius_m=…)`: read the stack (lazy, no rasterio dependency with a `tifffile` fallback), check lon/lat inside bounds, window around the point, call `make_features` + `model.predict`, return the schema in the master prompt. It must report **vegetation-density class** (not "irrigated") and fill `irrigation`/`crop` with `null` + reason, plus an optional, clearly labelled NDVI-heuristic irrigation hint.

## 7. Recommended architecture
Follow the master prompt's layout, adding `hydroscan/model_adapter.py` (wrapping existing files unchanged), `data_sources/*` adapters each returning `{source, retrieved, period, resolution, units, status, method}`, offline-first: cached/real files when present, otherwise an explicit `demo`/`unavailable` flag. No synthetic data is shown as real.

## 8. Risks / blockers
1. No trained irrigation/crop model → rotation scoring must not claim "irrigated/crop X detected". Decision needed from you (see below).
2. GEE project ID + authentication (needed for multi-year NDVI); not possible in this sandbox.
3. Network for NASA POWER / SoilGrids / IMERG: unavailable here; adapters will be written and tested with mocked responses, and marked unverified live.
4. Crop-database numbers (yields, water use, calendars, prices) must come from cited sources; I will leave unverifiable fields as `null`.
5. Short, flat NDVI history limits bare-soil calendar reliability (months will often be "unknown").

---
## 9. Status after implementation (2026-11-14)
| Feature | Status |
|---|---|
| `analyze_field(lat, lon)` over original model | IMPLEMENTED AND VERIFIED (tests) |
| Irrigation / crop classification | NOT IMPLEMENTED (no model, no labels); returned as `null` with reason |
| Monthly NDVI summary, bare-soil calendar | IMPLEMENTED AND VERIFIED on the supplied 10-month series (Nov/Dec unknown; no multi-year trend) |
| NASA POWER, SoilGrids | IMPLEMENTED, parsers verified; live calls NOT VERIFIED; offline = illustrative climate / soil unavailable |
| GPM IMERG, multi-year Sentinel via GEE | IMPLEMENTED BUT NOT VERIFIED; BLOCKED BY GEE PROJECT |
| Crop DB (4 crops, 3 rotations) | IMPLEMENTED; qualitative, unverified against Egyptian sources, quantitative fields null |
| Scoring / uncertainty / scenarios | IMPLEMENTED AND VERIFIED (unit tests); weights and ratings are unvalidated prototype assumptions |
| Streamlit app | IMPLEMENTED, compiles, NOT EXECUTED |
| Report PDF/HTML/PNG, Arabic script | IMPLEMENTED AND VERIFIED (generation); Arabic only in HTML + script |
| Arabic audio | NOT VERIFIED (needs gTTS + internet) |
| WhatsApp-style simulation, SMAP, SRTM, GAEZ, MODIS | NOT IMPLEMENTED |
