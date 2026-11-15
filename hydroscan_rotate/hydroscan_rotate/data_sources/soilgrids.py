"""ISRIC SoilGrids v2.0 (250 m gridded machine-learning estimates, NOT field measurements).
Access order (the REST API was PAUSED by ISRIC; verify its status at docs.isric.org/globaldata/soilgrids):
  1. WCS  https://maps.isric.org/mapserv?map=/map/<prop>.map  (ISRIC's recommended route for subsets; no key)
  2. Google Earth Engine community dataset projects/soilgrids-isric/<prop>_mean  (needs GEE setup)
  3. REST API (last resort, may be down; fair use 5 calls/min)
If all fail the result is 'unavailable'. No sample soil values are ever substituted."""
import config
from schemas import prov, unavailable
from data_sources._http import cached_call, get_json_meta
from data_sources.gee_client import get_ee

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPS = ["sand", "silt", "clay", "soc", "phh2o"]
DEPTHS = ["0-5cm", "5-15cm", "15-30cm"]


def parse_soilgrids(js):
    out = {}
    for layer in js["properties"]["layers"]:
        um = layer.get("unit_measure", {})
        d = um.get("d_factor") or 1
        for dep in layer["depths"]:
            v = dep["values"].get("mean")
            out.setdefault(layer["name"], {"units": um.get("target_units"), "depths": {}})["depths"][dep["label"]] = \
                None if v is None else round(v / d, 3)
    return out


def classify_texture(sand, silt, clay):
    """USDA texture triangle (simplified, standard class boundaries). Inputs in %."""
    if clay >= 40 and sand <= 45 and silt < 40: return "clay"
    if clay >= 40 and silt >= 40: return "silty clay"
    if clay >= 35 and sand > 45: return "sandy clay"
    if clay >= 27 and sand <= 20: return "silty clay loam"
    if clay >= 27 and sand <= 45: return "clay loam"
    if clay >= 20 and sand > 45 and silt < 28: return "sandy clay loam"
    if silt >= 80 and clay < 12: return "silt"
    if (silt >= 50 and clay >= 12) or (silt >= 80): return "silt loam"
    if clay >= 7 and sand <= 52 and silt >= 28: return "loam"
    if sand >= 85 and silt + 1.5 * clay < 15: return "sand"
    if sand >= 70 and silt + 2 * clay <= 30 or sand >= 85: return "loamy sand"
    return "sandy loam"



WCS_URL = "https://maps.isric.org/mapserv"
# Mapped integer values are scaled; dividing by d_factor gives the conventional unit.
SCALE = {"sand": (10, "%"), "silt": (10, "%"), "clay": (10, "%"), "soc": (10, "g/kg"), "phh2o": (10, "pH")}
SRC = "ISRIC SoilGrids v2.0"


def _wcs_params(prop, depth, lat, lon, half=0.004):
    return [("map", f"/map/{prop}.map"), ("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
            ("COVERAGEID", f"{prop}_{depth}_mean"), ("FORMAT", "image/tiff"),
            ("SUBSETTINGCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"), ("OUTPUTCRS", "http://www.opengis.net/def/crs/EPSG/0/4326"),
            ("SUBSET", f"long({lon - half:.5f},{lon + half:.5f})"), ("SUBSET", f"lat({lat - half:.5f},{lat + half:.5f})")]


def tiff_median(content):
    """GeoTIFF bytes -> median of valid pixels (SoilGrids nodata = -32768)."""
    import io
    import numpy as np
    import tifffile
    a = tifffile.imread(io.BytesIO(content)).astype(float)
    a = a[a > -30000]
    return None if a.size == 0 else float(np.median(a))


def _wcs_fetch(prop, depth, lat, lon, transport=None):
    if transport is not None:
        return {"raw": transport(WCS_URL, _wcs_params(prop, depth, lat, lon))}
    import requests
    r = requests.get(WCS_URL, params=_wcs_params(prop, depth, lat, lon), timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    if not r.content[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00"):  # not a TIFF: ISRIC returned an XML exception
        raise ValueError("WCS returned a non-TIFF response: " + r.text[:160].replace("\n", " "))
    return {"raw": tiff_median(r.content)}


def _assemble(raw):
    """{(prop, depth): raw scaled value|None} -> parse_soilgrids-like structure."""
    out = {}
    for (prop, depth), v in raw.items():
        f, unit = SCALE[prop]
        out.setdefault(prop, {"units": unit, "depths": {}})["depths"][depth] = None if v is None else round(v / f, 3)
    return out


def _from_wcs(lat, lon, transport=None):
    raw, status_all, reasons, saved = {}, [], [], []
    for prop in PROPS:
        for depth in DEPTHS:
            d, st, rs, dt_ = get_json_meta(WCS_URL, _wcs_params(prop, depth, lat, lon), key=f"wcs{prop}{depth}{lat:.4f},{lon:.4f}",
                                           getter=lambda u, p, a=(prop, depth): _wcs_fetch(a[0], a[1], lat, lon, transport))
            if d is None:
                return None, None, f"WCS {prop} {depth}: {rs}", None
            raw[(prop, depth)] = d["raw"]; status_all.append(st); saved.append(dt_); reasons.append(rs)
    status = "ok" if all(x == "ok" for x in status_all) else "cached"
    return _assemble(raw), status, next((r for r in reasons if r), None), min(saved)


def _from_gee(lat, lon, project=None):
    ee, err = get_ee(project)
    if ee is None:
        return None, None, err, None

    def query():
        pt = ee.Geometry.Point([lon, lat]); res = {}
        for prop in PROPS:
            img = ee.Image(config.GEE_IDS["soilgrids_prefix"] + f"{prop}_mean")
            vals = img.reduceRegion(ee.Reducer.mean(), pt.buffer(125), 250).getInfo()
            for depth in DEPTHS:
                res[f"{prop}|{depth}"] = vals.get(f"{prop}_{depth}_mean")
        return res
    d, st, rs, dt_ = cached_call(f"sgee{lat:.4f},{lon:.4f}", query)
    if d is None:
        return None, None, f"GEE: {rs}", None
    return _assemble({tuple(k.split("|")): v for k, v in d.items()}), st, rs, dt_


def _from_rest(lat, lon, getter=None):
    params = [("lon", round(lon, 4)), ("lat", round(lat, 4)), ("value", "mean")]
    params += [("property", p) for p in PROPS] + [("depth", d) for d in DEPTHS]
    js, status, reason, saved = get_json_meta(URL, params, key=f"soil{lat:.3f},{lon:.3f}", getter=(lambda u, p: getter(u, p)) if getter else None)
    if js is None:
        return None, None, f"REST: {reason}", None
    try:
        return parse_soilgrids(js), status, reason, saved
    except (KeyError, TypeError) as exc:
        return None, None, f"REST unexpected format: {exc}", None


def get_soil_data(latitude, longitude, getter=None, wcs_transport=None, use_wcs=True, use_gee=True):
    """`getter` (REST transport) and `wcs_transport` exist for tests only. With `getter` given, only REST is tried."""
    attempts, tried = [], []
    if getter is None:
        if use_wcs: attempts.append(("WCS", lambda: _from_wcs(latitude, longitude, wcs_transport)))
        if use_gee and config.GEE_PROJECT: attempts.append(("GEE", lambda: _from_gee(latitude, longitude)))
    attempts.append(("REST", lambda: _from_rest(latitude, longitude, getter)))
    for name, fn in attempts:
        data, status, reason, saved = fn()
        if data is not None:
            return {"data": data, "provenance": prov(
                f"{SRC} via {name}", "MODELLED", status, retrieved=saved, period="static map (2020 release)", spatial_resolution="250 m",
                temporal_resolution="static", units={k: v["units"] for k, v in data.items()},
                method="mean prediction at the field point (median of ~0.008 deg window via WCS); depths 0-5, 5-15, 15-30 cm",
                note="Machine-learning gridded estimate, not a measurement. Irrigated Nile Delta/Valley soils are poorly represented in training data; confirm with a laboratory soil test.",
                reason="; ".join(tried) or reason)}
        tried.append(f"{name} failed: {reason}")
    return unavailable(SRC, " | ".join(tried), kind="MODELLED")
