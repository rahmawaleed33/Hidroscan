"""
Bare-soil calendar. The NDVI threshold is a configurable starting point, NOT a validated value for Egypt:
it ignores crop phenology, soil colour and residue. Months without observations stay 'unknown'.
"""
import config
import pandas as pd

VEG, BARE, UNK = "vegetated", "potential_bare_soil", "unknown"


def bare_soil_calendar(series_df, threshold=None, min_obs=None, composite_bare_fraction=None, scope_note=None):
    thr = config.BARE_NDVI_THRESHOLD if threshold is None else threshold
    min_obs = config.MIN_OBS_FOR_MONTH if min_obs is None else min_obs
    d = series_df[["month", "ndvi"]].copy()
    d["ndvi"] = pd.to_numeric(d["ndvi"], errors="coerce")
    d["m"] = d.month.str[5:7].astype(int)
    d["year"] = d.month.str[:4].astype(int)
    cal = []
    for m in range(1, 13):
        g = d[(d.m == m) & d.ndvi.notna()]
        if len(g) < min_obs:
            cal.append({"month": m, "status": UNK, "ndvi": None, "n_years": 0,
                        "note": "no valid observation for this calendar month"})
            continue
        v = float(g.ndvi.mean())
        cal.append({"month": m, "status": BARE if v < thr else VEG, "ndvi": round(v, 4), "n_years": int(g.year.nunique()),
                    "note": "based on a single year" if g.year.nunique() < 2 else ""})
    return {"calendar": cal, "threshold": thr,
            "caveats": [f"Threshold NDVI < {thr} is an adjustable assumption, not validated locally.",
                        scope_note or "Values are area means, so a mixed area can look 'vegetated' while single fields are bare.",
                        "Months with no observation are 'unknown', never 'bare'."],
            "composite_bare_fraction": composite_bare_fraction}
