"""Unified field profile: HydroScan output + every real source, each with provenance. Nothing is substituted when a source is missing."""
import json

import config
from analysis.bare_soil import bare_soil_calendar
from analysis.climate import build_climate_profile
from analysis.ndvi import summarize_series
from analysis.soil import build_soil_profile
from data_sources.gpm import get_imerg_monthly
from data_sources.nasa_power import get_power_data
from data_sources.sentinel import get_ndvi_history, load_monthly_series
from data_sources.smap import get_smap_monthly
from data_sources.soilgrids import get_soil_data
from hydroscan.model_adapter import analyze_field, read_stack
from schemas import prov


def build_field_profile(lat, lon, stack_path=None, radius_m=300, use_gpm=None, use_smap=None, use_gee_ndvi=None, _inject=None):
    """`_inject` lets tests/live-check supply pre-fetched source results by key (power, soil, gpm, smap, ndvi_gee)."""
    inj = _inject or {}
    gee_on = bool(config.GEE_PROJECT)
    use_gpm = gee_on if use_gpm is None else use_gpm
    use_smap = gee_on if use_smap is None else use_smap
    use_gee_ndvi = gee_on if use_gee_ndvi is None else use_gee_ndvi

    hs = analyze_field(lat, lon, stack_path=stack_path, radius_m=radius_m)
    # --- NDVI series: field-level multi-year GEE if available, otherwise the project's own 2026 area-mean CSV (labelled)
    gee_ndvi = inj.get("ndvi_gee") or (get_ndvi_history(lat, lon) if use_gee_ndvi else None)
    series = gee_ndvi if (gee_ndvi and gee_ndvi["data"] is not None) else load_monthly_series()
    ndvi = summarize_series(series["data"]) if series["data"] is not None else None
    if ndvi:
        hs["vegetation"]["ndvi_series"] = ndvi["monthly"]
        hs["vegetation"]["observation_dates"] = [m["month"] for m in ndvi["monthly"] if m["ndvi"] is not None]
    arr, _ = read_stack(stack_path or config.DEMO_STACK)
    frac = float((arr[2][arr[2] > -9000] < config.BARE_NDVI_THRESHOLD).mean())
    scope = f"NDVI source scope: {series['provenance']['spatial_resolution']}; period {series['provenance']['period']}." if series["data"] is not None else None
    bare = bare_soil_calendar(series["data"], composite_bare_fraction=round(frac, 3), scope_note=scope) if series["data"] is not None else None

    power = inj.get("power") or get_power_data(lat, lon)
    soil = inj.get("soil") or get_soil_data(lat, lon)
    gpm = inj.get("gpm") or (get_imerg_monthly(lat, lon) if use_gpm else None)
    smap = inj.get("smap") or (get_smap_monthly(lat, lon) if use_smap else None)
    climate, soil_p = build_climate_profile(power), build_soil_profile(soil)

    sources = {"hydroscan_model": hs["provenance"], "ndvi_series": series["provenance"], "climate_power": power["provenance"], "soil": soil["provenance"]}
    for k, v in (("gpm_imerg", gpm), ("smap", smap)):
        if v:
            sources[k] = v["provenance"]
    available = ["hydroscan_vegetation_class"]
    missing, warnings = list(hs["data_quality"]["missing"]), list(hs["data_quality"]["warnings"])
    if ndvi:
        available.append(f"ndvi_series ({ndvi['n_valid_months']} valid months, {series['provenance']['period']})")
    if climate["available"]:
        available.append(f"climate: NASA POWER daily ({climate['years_of_data']} years, {power['provenance']['status']})")
    else:
        missing.append(f"climate (NASA POWER): {climate['reason']}")
    if soil_p["available"]:
        available.append(f"soil: SoilGrids estimate ({soil['provenance']['source']})")
    else:
        missing.append(f"soil (SoilGrids): {soil_p['reason']}")
    for name, v, need in (("GPM IMERG rainfall", gpm, "needs a Google Earth Engine project"), ("SMAP soil moisture", smap, "needs a Google Earth Engine project")):
        if v and v["data"]:
            available.append(f"{name} ({v['provenance']['period']}, {v['provenance']['spatial_resolution']})")
        else:
            missing.append(f"{name}: " + ((v or {}).get("provenance", {}).get("reason") or need))
    if ndvi and ndvi["trend"]["status"] != "estimated":
        warnings.append("NDVI history covers <24 valid months: no multi-year trend or seasonality can be established.")
    if series["provenance"]["source"].startswith("Sentinel-2 SR NDVI + Sentinel-1"):
        warnings.append("NDVI comes from the project's 2026 area-mean file (not field-level, one year); multi-year field-level NDVI needs Google Earth Engine.")
    return {"field": hs["field"], "hydroscan": hs, "ndvi": ndvi, "ndvi_source": series["provenance"], "bare_soil": bare, "climate": climate, "soil": soil_p,
            "gpm": gpm, "smap": smap, "sources": sources, "data_quality": {"available": available, "missing": missing, "warnings": warnings}}


def save_profile(profile, path="field_profile.json"):
    with open(path, "w") as f:
        json.dump(profile, f, indent=2, default=str)
    return path
