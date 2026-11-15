"""Data-support levels and risk categories. Descriptive levels only; no fake probabilities."""
LEVELS = ["Limited data support", "Moderate data support", "High data support"]
AR = {"Limited data support": "دعم البيانات محدود", "Moderate data support": "دعم البيانات متوسط", "High data support": "دعم البيانات قوي",
      "low": "منخفضة", "moderate": "متوسطة", "high": "عالية", "unknown": "غير معروفة"}


def assess(profile, ranked, water_availability="unknown", economic_inputs=None):
    from rotation.suitability import load_kb
    crops, _, _ = load_kb()
    nd = profile.get("ndvi") or {}
    n_months = nd.get("n_valid_months", 0)
    clim, soil = profile.get("climate") or {}, profile.get("soil") or {}
    clim_obs = clim.get("available") and not clim.get("is_illustrative")
    comp = {
        "model_prediction_confidence": ("Limited data support", "HydroScan's classifier has no validated accuracy and mostly reproduces NDVI thresholds."),
        "satellite_observation_quality": (LEVELS[0] if n_months < 12 else LEVELS[1] if n_months < 36 else LEVELS[2],
                                          f"{n_months} valid monthly NDVI values; {(profile.get('ndvi_source') or {}).get('spatial_resolution', 'scope unknown')}."),
        "environmental_completeness": (LEVELS[2] if (clim_obs and soil.get("available") and (profile.get("gpm") or {}).get("data")) else
                                       LEVELS[1] if (clim_obs and soil.get("available")) else LEVELS[0],
                                       f"climate observed: {bool(clim_obs)}; soil estimate: {bool(soil.get('available'))}; GPM: {bool((profile.get('gpm') or {}).get('data'))}; SMAP: {bool((profile.get('smap') or {}).get('data'))}"),
        "agricultural_evidence_quality": (LEVELS[2] if all(c["verified_against_source"] for c in crops.values()) else LEVELS[0],
                                          "Crop attributes are qualitative general knowledge/assumptions, not yet checked against Egyptian sources."),
    }
    lv = min(LEVELS.index(c[0]) for k, c in comp.items() if k != "model_prediction_confidence")
    if not economic_inputs:
        lv = min(lv, 0)
    overall = LEVELS[lv]
    risks = {}
    top_stages = {s for r in ranked for s in r["rotation_name"]["en"].lower().split()}
    risks["water_availability"] = (
        ("high", "Farmer reports limited water; high-demand crops (maize, berseem) are exposed.", "المية عندك محدودة، والذرة والبرسيم محتاجين مية كتير.") if water_availability == "limited" else
        ("unknown", "Water availability was not provided.", "حالة المية ماتحددتش.") if water_availability == "unknown" else
        ("moderate", "Water reported sufficient, but real irrigation need was not calculated (no ET data).", "المية كفاية حسب كلامك، بس احتياج الري الفعلي ماتحسبش."))
    risks["climate_exposure"] = (("unknown", "Climate inputs are not observations.", "بيانات المناخ مش قياسات حقيقية.") if not clim_obs else
                                 ("moderate", "Heat-sensitive crops are in some rotations; see scenarios.", "فيه محاصيل حساسة للحر، شوف السيناريوهات."))
    risks["soil_suitability"] = (("unknown", "No soil data retrieved; local soil limits unassessed.", "بيانات التربة مش متاحة.") if not soil.get("available") else
                                 ("moderate", "SoilGrids is an estimate; a lab test is needed.", "بيانات التربة تقديرية، محتاجة تحليل معملي."))
    risks["economic"] = (("high", "No price/yield/cost data: profitability is unquantified.", "مفيش أرقام عن السعر والإنتاجية والتكلفة، فالربحية مش معروفة.") if not economic_inputs else
                         ("moderate", "Based on farmer-supplied numbers; prices are volatile.", "الحساب على أرقامك إنت، والأسعار بتتغير."))
    miss = len(profile["data_quality"]["missing"])
    risks["missing_data"] = ("high" if miss >= 4 else "moderate" if miss >= 2 else "low", f"{miss} inputs missing: " + "; ".join(m.split(":")[0] for m in profile["data_quality"]["missing"]),
                             f"فيه {miss} مدخلات ناقصة.")
    return {"data_support": overall, "data_support_ar": AR[overall], "components": {k: {"level": a, "why": b} for k, (a, b) in comp.items()},
            "risks": {k: {"level": a, "en": b, "ar": c, "level_ar": AR[a]} for k, (a, b, c) in risks.items()},
            "needs_expert_validation": ["All crop attributes and ordinal ratings", "Soil suitability (lab soil test)", "Economic figures", "Planting calendar for the governorate"],
            "indicator_note": "Levels describe how well the inputs support the comparison. They are not the probability that a recommendation is correct."}
