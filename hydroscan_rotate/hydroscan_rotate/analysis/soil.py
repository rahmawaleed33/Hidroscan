"""Soil profile from SoilGrids (gridded estimate)."""
from data_sources.soilgrids import classify_texture

_W = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}


def _wmean(depths):
    vals = [(depths[k], w) for k, w in _W.items() if depths.get(k) is not None]
    return None if not vals else round(sum(v * w for v, w in vals) / sum(w for _, w in vals), 2)


def build_soil_profile(soil):
    data, prov = soil["data"], soil["provenance"]
    if data is None:
        return {"available": False, "provenance": prov, "reason": prov["reason"]}
    g = {k: _wmean(v["depths"]) for k, v in data.items()}
    units = {k: v["units"] for k, v in data.items()}
    texture = None
    if all(g.get(k) is not None for k in ("sand", "silt", "clay")):
        # SoilGrids reports sand/silt/clay in g/kg -> % = /10
        s, si, c = (g[k] / 10 if units.get(k) in ("g/kg", None) else g[k] for k in ("sand", "silt", "clay"))
        texture = classify_texture(s, si, c)
    return {"available": True, "depth_range": "0-30 cm (thickness-weighted mean of 0-5, 5-15, 15-30 cm)",
            "values": g, "units": units, "texture_class": texture, "provenance": prov,
            "limitations": ["250 m gridded machine-learning estimate, not a field measurement.",
                            "Irrigated Nile-valley/Delta soils are often poorly captured; confirm with a laboratory soil test."]}
