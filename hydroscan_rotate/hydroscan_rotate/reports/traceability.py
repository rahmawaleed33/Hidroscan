"""Traceability table: for every input behind a result -> source, retrieval date, spatial resolution, nature of the value, limitations.
Built only from the profile's provenance blocks; nothing here is invented."""
TYPE_LABEL = {"SATELLITE": "satellite-derived", "MODELLED": "modelled (reanalysis / ML estimate)", "MODEL_PREDICTION": "model prediction (not validated)",
              "OBSERVATION": "observation", "DERIVED": "derived by this tool", "FARMER": "farmer-provided", "ASSUMPTION": "analyst assumption (unverified)",
              "EXTERNAL_REFERENCE": "literature reference", "SCENARIO": "hypothetical scenario"}


def _row(item, p, limits=None):
    if p is None:
        return {"item": item, "source": "not requested", "status": "unavailable", "retrieved": None, "period": None, "resolution": None,
                "type": "unavailable", "limitations": limits or "not requested"}
    unavailable = p["status"] == "unavailable"
    return {"item": item, "source": p["source"], "status": p["status"], "retrieved": p.get("retrieved") if not unavailable else None,
            "period": p.get("period"), "resolution": p.get("spatial_resolution"),
            "type": "unavailable" if unavailable else TYPE_LABEL.get(p["kind"], p["kind"]),
            "limitations": (p.get("reason") if unavailable else (p.get("note") or "")) or ""}


def build_traceability(result):
    prof, inp = result["profile"], result["inputs"]
    src = prof["sources"]
    rows = [
        {"item": "Field location", "source": "farmer's shared location pin", "status": "ok", "retrieved": "at request time", "period": None, "resolution": "point",
         "type": "farmer-provided", "limitations": "A point, not field boundaries."},
        {"item": "Main priority", "source": "farmer's button choice", "status": "ok", "retrieved": "at request time", "period": None, "resolution": None,
         "type": "farmer-provided", "limitations": "Changes the criterion weights only."},
        {"item": "Water availability", "source": "farmer's answer", "status": "ok" if inp["water_availability"] != "unknown" else "unavailable",
         "retrieved": "at request time", "period": None, "resolution": None, "type": "farmer-provided" if inp["water_availability"] != "unknown" else "unavailable",
         "limitations": "Not verified; no satellite or gauge measure of irrigation water is used."},
        {**_row("Vegetation density class (bare / sparse / dense)", src["hydroscan_model"]),
         "retrieved": "supplied GeoTIFF composite (exact acquisition dates not stored in the file)",
         "limitations": "Random-forest trained on NDVI-threshold pseudo-labels (99 % agreement with a plain NDVI rule, no validated accuracy). It says nothing about irrigation or crop type."},
        _row("NDVI series and bare-soil calendar", src["ndvi_series"]),
        _row("Temperature, humidity, radiation, rainfall (climate)", src["climate_power"]),
        _row("Reference evapotranspiration (ET0)", {**src["climate_power"], "kind": "MODELLED", "note": "Hargreaves-Samani from POWER temperatures; generic coefficient; reference demand, not crop water use."} if src["climate_power"]["status"] != "unavailable" else src["climate_power"]),
        _row("Satellite rainfall (GPM IMERG)", src.get("gpm_imerg")),
        _row("Soil moisture (SMAP)", src.get("smap")),
        _row("Soil texture, organic carbon, pH", src["soil"]),
    ]
    rows += [
        {"item": "Crop attributes used in scoring (water demand, heat sensitivity, legume benefit, soil cover)", "source": "rotation/crop_database.json (ordinal ratings)",
         "status": "ok", "retrieved": "static", "period": None, "resolution": None, "type": "analyst assumption (unverified)",
         "limitations": "Ordinal ratings, not measured values. Egyptian literature found is listed in egypt_references.json but has not yet replaced these ratings."},
        {"item": "Rotation scores and ranking", "source": "rotation/scoring.py + scoring_rules.json", "status": "ok", "retrieved": "computed now", "period": None, "resolution": None,
         "type": "derived by this tool", "limitations": "Prototype weights; scores are relative, not probabilities, yields or incomes. Income is not scored without farmer-supplied numbers."},
        {"item": "What-if scenarios", "source": "scenarios.py", "status": "ok", "retrieved": "computed now", "period": None, "resolution": None, "type": "hypothetical scenario",
         "limitations": "Rule-based sensitivity (+2 C, -20 % rain); not a forecast and not driven by local climate model output."},
    ]
    return rows


def traceability_markdown(result):
    rows = build_traceability(result)
    out = ["| Input | Source | Status | Retrieved | Period | Spatial resolution | Nature of value | Limitations / reason |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append("| " + " | ".join(str(x if x not in (None, "") else "-").replace("|", "/").replace("\n", " ") for x in
                   (r["item"], r["source"], r["status"], r["retrieved"], r["period"], r["resolution"], r["type"], r["limitations"])) + " |")
    return "\n".join(out)
