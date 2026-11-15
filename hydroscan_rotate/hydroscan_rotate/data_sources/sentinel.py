"""Sentinel-2 NDVI series. Two sources, never mixed silently:
 (a) GEE field-level multi-year monthly NDVI (S2 SR HARMONIZED, cloud/shadow-masked, small buffer around the point) - preferred;
 (b) the project's own timeseries.csv (real GEE output, 2026 only, area mean over the ~5 km HydroScan box)."""
import os

import pandas as pd

import config
from schemas import prov, unavailable
from data_sources._http import cached_call
from data_sources.gee_client import get_ee

COLS = ["ndvi", "vv", "vh", "soil_moisture"]
SRC_GEE = "Sentinel-2 SR HARMONIZED NDVI (via Google Earth Engine)"


def load_monthly_series(path=None):
    path = path or config.TIMESERIES_CSV
    if not os.path.exists(path):
        return unavailable("Sentinel-1/2 monthly series", f"{path} not found")
    df = pd.read_csv(path)
    df["month"] = df["month"].astype(str)
    for c in COLS:
        if c not in df:
            df[c] = None
    n_sm = int(df["soil_moisture"].notna().sum())
    return {"data": df, "provenance": prov(
        "Sentinel-2 SR NDVI + Sentinel-1 GRD VV/VH, area mean over the HydroScan bbox (project's original GEE output)",
        "SATELLITE", "cached", retrieved="2026-11 (file supplied with the project)", period=f"{df['month'].iloc[0]}..{df['month'].iloc[-1]}",
        spatial_resolution="10 m pixels, averaged over a ~5 km box", temporal_resolution="monthly", units="NDVI unitless; VV/VH dB",
        method="timeseries.py (original project output)",
        note=("Whole-area mean, not field-specific; one year only. " + ("Its SMAP column is empty." if n_sm == 0 else "")).strip())}


def get_ndvi_history(latitude, longitude, start_year=None, end_year=None, project=None):
    """Field-level monthly NDVI, multi-year. Returns {'data': DataFrame[month, ndvi, n_images, vv, vh, soil_moisture], ...}."""
    y0, y1 = start_year or config.NDVI_START_YEAR, end_year or config.NDVI_END_YEAR
    ee, err = get_ee(project)
    if ee is None:
        return unavailable(SRC_GEE, err)
    ids = config.GEE_IDS

    def query():
        region = ee.Geometry.Point([longitude, latitude]).buffer(config.FIELD_BUFFER_M)
        n_months = (y1 - y0 + 1) * 12

        def mask_ndvi(img):
            scl = img.select("SCL")
            ok = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))  # shadow, cloud (med/high), cirrus, snow
            return img.updateMask(ok).normalizedDifference(["B8", "B4"]).rename("ndvi")

        def f(i):
            s = ee.Date.fromYMD(y0, 1, 1).advance(ee.Number(i), "month")
            col = ee.ImageCollection(ids["s2"]).filterBounds(region).filterDate(s, s.advance(1, "month"))
            n = col.size()
            val = col.map(mask_ndvi).median().reduceRegion(ee.Reducer.mean(), region, 10, maxPixels=1e8).get("ndvi")
            return ee.Feature(None, {"month": s.format("YYYY-MM"), "ndvi": ee.Algorithms.If(n.gt(0), val, -9999), "n": n})
        rows = []
        for a in range(0, n_months, 12):
            rows += [x["properties"] for x in ee.FeatureCollection(ee.List.sequence(a, a + 11).map(f)).getInfo()["features"]]
        return rows

    raw, status, reason, retrieved = cached_call(f"s2ndvi{latitude:.4f},{longitude:.4f},{y0},{y1},{config.FIELD_BUFFER_M}", query)
    if raw is None:
        return unavailable(SRC_GEE, reason)
    df = pd.DataFrame([{"month": r["month"], "ndvi": None if r.get("ndvi") is None or r["ndvi"] <= -9000 else round(float(r["ndvi"]), 4),
                        "n_images": r.get("n"), "vv": None, "vh": None, "soil_moisture": None} for r in raw]).sort_values("month")
    return {"data": df, "provenance": prov(
        SRC_GEE, "SATELLITE", status, retrieved=retrieved, period=f"{y0}-01..{y1}-12", spatial_resolution=f"10 m pixels, mean within {config.FIELD_BUFFER_M} m of the point",
        temporal_resolution="monthly median composite", units="NDVI unitless",
        method="SCL cloud/shadow mask, NDVI=(B8-B4)/(B8+B4), monthly median, buffer mean",
        note="Mean inside a small circle: a mixed or neighbouring field can bias it. Months with no clear image are null, not interpolated.", reason=reason)}
