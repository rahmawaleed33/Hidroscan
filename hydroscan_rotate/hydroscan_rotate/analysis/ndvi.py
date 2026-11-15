"""NDVI helpers: correct formula, seasonal aggregation, honest trend handling."""
import numpy as np
import pandas as pd

SEASONS = {"winter": (12, 1, 2), "spring": (3, 4, 5), "summer": (6, 7, 8), "autumn": (9, 10, 11)}


def ndvi_from_bands(nir, red):
    """NDVI = (NIR - RED) / (NIR + RED); 0/0 -> NaN."""
    nir, red = np.asarray(nir, float), np.asarray(red, float)
    den = nir + red
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(den == 0, np.nan, (nir - red) / den)
    return out


def summarize_series(df):
    """df: columns month 'YYYY-MM', ndvi. Returns monthly list, seasonal means, annual means, peak, trend status."""
    d = df[["month", "ndvi"]].copy()
    d["ndvi"] = pd.to_numeric(d["ndvi"], errors="coerce")
    outliers = d[(d.ndvi < -0.2) | (d.ndvi > 1.0)]
    d.loc[outliers.index, "ndvi"] = np.nan
    d["year"] = d.month.str[:4].astype(int)
    d["m"] = d.month.str[5:7].astype(int)
    valid = d.dropna(subset=["ndvi"])
    seasonal = {s: (round(float(valid[valid.m.isin(ms)].ndvi.mean()), 4) if valid.m.isin(ms).any() else None)
                for s, ms in SEASONS.items()}
    annual = {int(y): round(float(g.ndvi.mean()), 4) for y, g in valid.groupby("year")}
    peak = None if valid.empty else valid.loc[valid.ndvi.idxmax(), ["month", "ndvi"]].to_dict()
    n_months = len(valid)
    if n_months >= 24 and valid.year.nunique() >= 3:
        slope = np.polyfit(np.arange(n_months), valid.ndvi.values, 1)[0] * 12
        trend = {"status": "estimated", "ndvi_change_per_year": round(float(slope), 4)}
    else:
        trend = {"status": "insufficient_history", "months_available": int(n_months),
                 "reason": "A multi-year trend needs >= 24 valid months spanning >= 3 years."}
    return {"monthly": [{"month": r.month, "ndvi": None if np.isnan(r.ndvi) else round(float(r.ndvi), 4)} for r in d.itertuples()],
            "seasonal_mean": seasonal, "annual_mean": annual, "peak": peak, "trend": trend,
            "n_valid_months": int(n_months), "outliers_removed": int(len(outliers)),
            "range": None if valid.empty else [round(float(valid.ndvi.min()), 4), round(float(valid.ndvi.max()), 4)]}
