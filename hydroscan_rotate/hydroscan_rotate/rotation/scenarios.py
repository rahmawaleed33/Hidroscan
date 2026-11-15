"""What-if climate sensitivity analysis. Hypothetical, not a forecast. Historical observations are never modified."""
import copy

from rotation.scoring import rank_rotations

PRESETS = {"baseline": {"delta_t": 0.0, "rain_factor": 1.0, "label_en": "Baseline", "label_ar": "الوضع الحالي"},
           "warm_2c": {"delta_t": 2.0, "rain_factor": 1.0, "label_en": "+2 C temperature", "label_ar": "الحرارة +٢ درجة"},
           "dry_20": {"delta_t": 0.0, "rain_factor": 0.8, "label_en": "-20% rainfall", "label_ar": "المطر -٢٠٪"}}


def apply_scenario(profile, delta_t, rain_factor):
    """Return a COPY with the climate monthly values shifted (for charts). The input profile is untouched."""
    p = copy.deepcopy(profile)
    for r in (p.get("climate") or {}).get("monthly", []):
        if r["temp_c"] is not None:
            r["temp_c"] = round(r["temp_c"] + delta_t, 2)
        if r["rain_mm"] is not None:
            r["rain_mm"] = round(r["rain_mm"] * rain_factor, 2)
    p["scenario_applied"] = {"delta_t": delta_t, "rain_factor": rain_factor, "hypothetical": True}
    return p


def run_scenario(profile, scenario_parameters, farmer_priority, water_availability="unknown", economic_inputs=None):
    sp = {"delta_t": float(scenario_parameters.get("delta_t", 0.0)), "rain_factor": float(scenario_parameters.get("rain_factor", 1.0))}
    if not (0 <= sp["rain_factor"] <= 3) or abs(sp["delta_t"]) > 10:
        raise ValueError("Scenario out of sensible range (|dT| <= 10 C, 0 <= rain factor <= 3).")
    base = rank_rotations(profile, farmer_priority, water_availability, economic_inputs)
    scen = rank_rotations(profile, farmer_priority, water_availability, economic_inputs, scenario=sp)
    b = {r["rotation_id"]: r for r in base}
    rows, notes = [], []
    for r in scen:
        o = b[r["rotation_id"]]
        d = {k: (None if r["criteria"][k]["score"] is None else round(r["criteria"][k]["score"] - o["criteria"][k]["score"], 1)) for k in r["criteria"]}
        rows.append({"rotation_id": r["rotation_id"], "name": r["rotation_name"], "baseline_score": o["overall"], "scenario_score": r["overall"],
                     "delta": round(r["overall"] - o["overall"], 1), "baseline_rank": o["rank"], "scenario_rank": r["rank"], "criterion_delta": d})
        big = max((k for k in d if d[k] is not None), key=lambda k: abs(d[k]), default=None)
        if big and abs(d[big]) >= 0.1:
            notes.append({"en": f"Rotation {r['rotation_id']}: {big} score changes by {d[big]:+.1f} under this hypothetical scenario.",
                          "ar": f"دورة {r['rotation_id']}: درجة {big} اتغيرت {d[big]:+.1f} في السيناريو الافتراضي ده."})
    changed = [x["rotation_id"] for x in rows if x["baseline_rank"] != x["scenario_rank"]]
    return {"parameters": sp, "rows": sorted(rows, key=lambda x: x["scenario_rank"]), "ranking_changed": bool(changed), "rotations_changed_rank": changed,
            "explanations": notes, "baseline": base, "scenario": scen, "scenario_profile": apply_scenario(profile, **sp),
            "label": "Hypothetical sensitivity analysis, not a forecast. Rain loss is not translated into irrigation need.",
            "label_ar": "ده تحليل افتراضي مش توقع حقيقي."}
