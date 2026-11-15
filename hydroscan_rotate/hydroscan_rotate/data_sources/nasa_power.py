"""NASA POWER DAILY point data (AG community) -> monthly aggregates + derived indicators.
Daily endpoint: https://power.larc.nasa.gov/api/temporal/daily/point  (no account/key needed).
Never substitutes sample data: if POWER cannot be reached and nothing is cached, the result is 'unavailable'."""
import datetime as dt
import math

import config
from schemas import prov, unavailable
from data_sources._http import get_json_meta

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "ALLSKY_SFC_SW_DWN", "WS2M"]


def ra_mm_day(lat_deg, doy):
    """Extraterrestrial radiation in mm/day of evaporation equivalent (FAO-56 eq. 21)."""
    phi = math.radians(lat_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi / 365 * doy)
    d = 0.409 * math.sin(2 * math.pi / 365 * doy - 1.39)
    ws = math.acos(max(-1, min(1, -math.tan(phi) * math.tan(d))))
    ra_mj = 24 * 60 / math.pi * 0.0820 * dr * (ws * math.sin(phi) * math.sin(d) + math.cos(phi) * math.cos(d) * math.sin(ws))
    return ra_mj * 0.408


def hargreaves_et0(tmean, tmax, tmin, lat, doy):
    """Hargreaves-Samani reference ET (mm/day). MODELLED, generic coefficient 0.0023, not calibrated to Egypt."""
    if None in (tmean, tmax, tmin) or tmax < tmin:
        return None
    return max(0.0, 0.0023 * (tmean + 17.8) * math.sqrt(tmax - tmin) * ra_mm_day(lat, doy))


def parse_power_daily(js):
    par = js["properties"]["parameter"]
    units = {k: v.get("units") for k, v in js.get("parameters", {}).items()}
    days = {}
    for name, series in par.items():
        for ymd, val in series.items():
            days.setdefault(ymd, {})[name] = None if val in (-999, -999.0) else float(val)
    return days, units


def aggregate_daily(days, lat):
    """days: {'YYYYMMDD': {param: value}} -> list of monthly rows (T2M/T2M_MAX/T2M_MIN/RH2M/radiation = mean,
    PRECTOTCORR = mean mm/day, rain_total_mm = sum, et0_hargreaves_mm = sum, heat_days, frost_days, n_days)."""
    by = {}
    for ymd, d in sorted(days.items()):
        by.setdefault((int(ymd[:4]), int(ymd[4:6])), []).append((ymd, d))
    rows = []
    for (y, m), items in by.items():
        def col(k): return [d[k] for _, d in items if d.get(k) is not None]
        def mean(k):
            c = col(k); return round(sum(c) / len(c), 3) if c else None
        et0 = []
        for ymd, d in items:
            doy = dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])).timetuple().tm_yday
            e = hargreaves_et0(d.get("T2M"), d.get("T2M_MAX"), d.get("T2M_MIN"), lat, doy)
            if e is not None: et0.append(e)
        rain = col("PRECTOTCORR")
        rows.append({"year": y, "month": m, "n_days": len(items), "T2M": mean("T2M"), "T2M_MAX": mean("T2M_MAX"), "T2M_MIN": mean("T2M_MIN"),
                     "PRECTOTCORR": mean("PRECTOTCORR"), "rain_total_mm": round(sum(rain), 2) if rain else None,
                     "RH2M": mean("RH2M"), "ALLSKY_SFC_SW_DWN": mean("ALLSKY_SFC_SW_DWN"), "WS2M": mean("WS2M"),
                     "et0_hargreaves_mm": round(sum(et0), 1) if et0 else None,
                     "heat_days": sum(1 for v in col("T2M_MAX") if v >= config.HEAT_DAY_TMAX_C),
                     "frost_days": sum(1 for v in col("T2M_MIN") if v <= config.FROST_DAY_TMIN_C)})
    return rows


def get_power_data(latitude, longitude, start_date=None, end_date=None, getter=None):
    last_full = dt.date.today().year - 1
    y1 = int(str(end_date)[:4]) if end_date else last_full
    y0 = int(str(start_date)[:4]) if start_date else y1 - config.CLIMATE_YEARS + 1
    params = {"parameters": ",".join(PARAMS), "community": "AG", "longitude": round(longitude, 3), "latitude": round(latitude, 3),
              "start": f"{y0}0101", "end": f"{y1}1231", "format": "JSON"}
    js, status, reason, retrieved = get_json_meta(URL, params, getter=getter)
    if js is None:
        return unavailable("NASA POWER daily (AG)", reason or "no data", kind="MODELLED")
    try:
        days, units = parse_power_daily(js)
        rows = aggregate_daily(days, latitude)
        if not rows:
            raise ValueError("no daily records")
    except (KeyError, ValueError, TypeError) as exc:
        return unavailable("NASA POWER daily (AG)", f"unexpected response format: {exc}", kind="MODELLED")
    n_valid = sum(r["n_days"] for r in rows)
    return {"data": {"monthly": rows, "units": units, "daily_records": n_valid}, "provenance": prov(
        "NASA POWER daily (AG community)", "MODELLED", status, retrieved=retrieved, period=f"{y0}-01-01..{y1}-12-31",
        spatial_resolution="~0.5 deg x 0.625 deg grid cell (MERRA-2 / CERES-based)", temporal_resolution="daily, aggregated to monthly here",
        units=units, method="daily values aggregated to monthly; ET0 = Hargreaves-Samani (generic coefficient); heat/frost day counts use config thresholds",
        note="Gridded reanalysis/satellite-model product for a ~50 km cell, NOT a weather-station or field measurement. Delta/desert-fringe microclimate can differ.",
        reason=reason)}
