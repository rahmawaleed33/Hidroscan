"""NASA SMAP surface soil moisture via Google Earth Engine (SPL3SMP_E, ~9 km). SATELLITE-derived and VERY COARSE:
one pixel covers many fields and irrigated Delta plots are not resolved. Used only as regional dryness context (monthly anomaly)."""
import config
from schemas import prov, unavailable
from data_sources._http import cached_call
from data_sources.gee_client import get_ee

SRC = "NASA SMAP L3 soil moisture (via Google Earth Engine)"


def monthly_anomaly(rows):
    """rows [{year, month, sm}] -> adds anomaly vs the same calendar month's mean (needs >= 3 years of that month)."""
    by = {}
    for r in rows:
        if r["sm"] is not None:
            by.setdefault(r["month"], []).append(r["sm"])
    out = []
    for r in rows:
        vals = by.get(r["month"], [])
        base = sum(vals) / len(vals) if len(vals) >= 3 and r["sm"] is not None else None
        out.append({**r, "anomaly": None if base is None else round(r["sm"] - base, 4)})
    return out


def get_smap_monthly(latitude, longitude, start_year=None, end_year=None, project=None):
    y0, y1 = start_year or config.SMAP_START_YEAR, end_year or config.SMAP_END_YEAR
    ee, err = get_ee(project)
    if ee is None:
        return unavailable(SRC, err)
    ids = config.GEE_IDS

    def query():
        pt = ee.Geometry.Point([longitude, latitude])
        rows = []
        for y in range(y0, y1 + 1):
            def f(i, y=y):
                s = ee.Date.fromYMD(y, 1, 1).advance(ee.Number(i), "month")
                col = ee.ImageCollection(ids["smap"]).filterDate(s, s.advance(1, "month")).select(ids["smap_band"])
                n = col.size()
                val = col.mean().reduceRegion(ee.Reducer.mean(), pt, 9000).get(ids["smap_band"])
                return ee.Feature(None, {"month": s.format("YYYY-MM"), "sm": ee.Algorithms.If(n.gt(0), val, -9999), "n": n})
            rows += [x["properties"] for x in ee.FeatureCollection(ee.List.sequence(0, 11).map(f)).getInfo()["features"]]
        return rows

    raw, status, reason, retrieved = cached_call(f"smap{latitude:.3f},{longitude:.3f},{y0},{y1}", query)
    if raw is None:
        return unavailable(SRC, reason)
    rows = [{"year": int(r["month"][:4]), "month": int(r["month"][5:7]),
             "sm": None if r.get("sm") is None or r["sm"] <= -9000 else round(float(r["sm"]), 4), "n_images": r.get("n")} for r in raw]
    return {"data": {"monthly": monthly_anomaly(rows)}, "provenance": prov(
        SRC, "SATELLITE", status, retrieved=retrieved, period=f"{y0}-01..{y1}-12", spatial_resolution="~9 km pixel (enhanced L3)",
        temporal_resolution="monthly mean of daily AM overpass retrievals", units="m3/m3 (volumetric), top ~5 cm",
        method="monthly mean at the pixel containing the field; anomaly vs same-month multi-year mean",
        note="Top ~5 cm only; a 9 km pixel cannot describe one field and does not represent irrigation. Regional dryness context ONLY.", reason=reason)}
