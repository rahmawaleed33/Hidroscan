"""Field-suitability helpers shared by scoring and scenarios."""
import json
import os

import config

_HERE = os.path.dirname(os.path.abspath(__file__))


def load_kb():
    with open(os.path.join(_HERE, "crop_database.json"), encoding="utf-8") as f:
        crops = json.load(f)["crops"]
    with open(os.path.join(_HERE, "rotation_library.json"), encoding="utf-8") as f:
        rots = json.load(f)["rotations"]
    with open(os.path.join(_HERE, "scoring_rules.json"), encoding="utf-8") as f:
        rules = json.load(f)
    return crops, rots, rules


def v(crops, cid, attr):
    return crops[cid][attr]["value"]


def season_climate(profile, months):
    """Mean temperature and total rain over the given calendar months, or (None, None) if unavailable."""
    clim = (profile or {}).get("climate") or {}
    if not clim.get("available"):
        return None, None
    rows = [r for r in clim["monthly"] if r["month"] in months]
    t = [r["temp_c"] for r in rows if r["temp_c"] is not None]
    p = [r["rain_mm"] for r in rows if r["rain_mm"] is not None]
    return (sum(t) / len(t) if t else None), (sum(p) if p else None)


def income_per_year(rotation, econ_inputs):
    """Net income per area unit per year from FARMER-SUPPLIED yield, price, cost. None if anything is missing."""
    if not econ_inputs:
        return None
    total = 0.0
    for cid in rotation["stages"]:
        e = econ_inputs.get(cid) or {}
        if any(e.get(k) is None for k in ("yield", "price", "cost")):
            return None
        total += e["yield"] * e["price"] - e["cost"]
    return total / rotation["cycle_years"]
