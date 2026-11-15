"""Monthly climate profile from NASA POWER daily data. No illustrative fallback exists: if POWER is unavailable the profile is unavailable."""
import calendar as cal
import numpy as np
import pandas as pd


def build_climate_profile(power):
    data, prov = power["data"], power["provenance"]
    if data is None:
        return {"available": False, "provenance": prov, "monthly": [], "reason": prov["reason"]}
    df = pd.DataFrame(data["monthly"])
    illustrative = False  # kept for backward compatibility of consumers; sample data can no longer enter the profile
    years = sorted(df.year.unique())
    monthly = []
    for m in range(1, 13):
        g = df[df.month == m]
        t = g["T2M"].dropna()
        p = g["PRECTOTCORR"].dropna() * cal.monthrange(2001, m)[1] if "PRECTOTCORR" in g else pd.Series(dtype=float)
        def mm(c):
            x = g[c].dropna() if c in g else pd.Series(dtype=float)
            return None if x.empty else round(float(x.mean()), 2)
        monthly.append({"month": m, "tmax_c": mm("T2M_MAX"), "tmin_c": mm("T2M_MIN"), "rh_pct": mm("RH2M"), "radiation_kwh_m2_day": mm("ALLSKY_SFC_SW_DWN"),
                        "et0_mm": mm("et0_hargreaves_mm"), "heat_days_per_month": mm("heat_days"), "frost_days_per_month": mm("frost_days"),
                        "temp_c": None if t.empty else round(float(t.mean()), 2),
                        "rain_mm": None if p.empty else round(float(p.mean()), 2),
                        "rain_cv": None if len(p) < 5 or p.mean() == 0 else round(float(p.std() / p.mean()), 2)})
    temps = [r["temp_c"] for r in monthly if r["temp_c"] is not None]
    rain = [r["rain_mm"] for r in monthly if r["rain_mm"] is not None]
    anomaly = None
    if not illustrative and len(years) >= 10 and "T2M" in df:
        ann = df.groupby("year")["T2M"].mean().dropna()
        if len(ann) >= 10:
            anomaly = {"year": int(ann.index[-1]), "anomaly_c": round(float(ann.iloc[-1] - ann.iloc[:-1].mean()), 2)}
    return {"available": True, "monthly": monthly, "annual_rain_mm": round(float(np.sum(rain)), 1) if rain else None,
            "mean_temp_c": round(float(np.mean(temps)), 2) if temps else None, "temp_anomaly_latest_year": anomaly,
            "years_of_data": len(years), "daily_records": (data.get("daily_records")), "is_illustrative": illustrative, "provenance": prov,
            "et0_note": "ET0 is Hargreaves-Samani (modelled, generic coefficient) from POWER temperatures: a REFERENCE evaporative demand, not measured crop water use. "
                            "Crop water need (ETc) is not calculated because no Egyptian crop coefficients have been verified."}
