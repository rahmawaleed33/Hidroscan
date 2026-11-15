"""NASA GPM IMERG (V07) monthly rainfall via Google Earth Engine. SATELLITE-derived, 0.1 deg (~11 km) pixels:
one pixel spans many fields, so it is regional rainfall context, not a field rain-gauge reading."""
import config
from schemas import prov, unavailable
from data_sources._http import cached_call
from data_sources.gee_client import get_ee

SRC = "NASA GPM IMERG V07 (via Google Earth Engine)"


def parse_monthly(rows):
    """FeatureCollection properties -> sorted [{year, month, precip_mm|None}]. -9999 marks months with no images."""
    out = []
    for r in rows:
        y, m = int(r["month"][:4]), int(r["month"][5:7])
        v = r.get("precip_mm")
        out.append({"year": y, "month": m, "precip_mm": None if v is None or v <= -9000 else round(float(v), 2), "n_images": r.get("n")})
    return sorted(out, key=lambda r: (r["year"], r["month"]))


def get_imerg_monthly(latitude, longitude, start_year=None, end_year=None, project=None):
    y0, y1 = start_year or config.IMERG_START_YEAR, end_year or config.IMERG_END_YEAR
    ee, err = get_ee(project)
    if ee is None:
        return unavailable(SRC, err)
    ids = config.GEE_IDS

    def query():
        pt = ee.Geometry.Point([longitude, latitude])
        rows = []
        for y in range(y0, y1 + 1):  # one request per year keeps each call small
            def f(i, y=y):
                s = ee.Date.fromYMD(y, 1, 1).advance(ee.Number(i), "month")
                col = ee.ImageCollection(ids["imerg"]).filterDate(s, s.advance(1, "month")).select(ids["imerg_band"])
                n = col.size()
                val = col.sum().multiply(0.5).reduceRegion(ee.Reducer.mean(), pt, 11132).get(ids["imerg_band"])  # mm/hr per 30 min -> mm
                return ee.Feature(None, {"month": s.format("YYYY-MM"), "precip_mm": ee.Algorithms.If(n.gt(0), val, -9999), "n": n})
            rows += [x["properties"] for x in ee.FeatureCollection(ee.List.sequence(0, 11).map(f)).getInfo()["features"]]
        return rows

    raw, status, reason, retrieved = cached_call(f"imerg{latitude:.3f},{longitude:.3f},{y0},{y1}", query)
    if raw is None:
        return unavailable(SRC, reason)
    rows = parse_monthly(raw)
    return {"data": {"monthly": rows}, "provenance": prov(
        SRC, "SATELLITE", status, retrieved=retrieved, period=f"{y0}-01..{y1}-12", spatial_resolution="0.1 deg (~11 km) pixel",
        temporal_resolution="monthly total from 30-minute estimates", units="mm/month",
        method="sum of half-hourly rates x 0.5 h, pixel containing the field point",
        note="Satellite rainfall estimate; light rain and very local storms are under-/mis-estimated. Not a gauge.", reason=reason)}
