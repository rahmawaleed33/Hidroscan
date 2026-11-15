"""Transparent rule-based rotation scoring. All rules live in scoring_rules.json / crop_database.json."""
import copy

from rotation.suitability import income_per_year, load_kb, season_climate, v

CRITERIA = ["water", "soil", "income", "resilience"]
CRIT_LABEL = {"water": ("Water efficiency", "كفاءة المياه"), "soil": ("Soil health", "صحة التربة"),
              "income": ("Economic potential", "العائد الاقتصادي"), "resilience": ("Climate resilience", "المرونة المناخية")}


def _clamp(x):
    return max(0.0, min(100.0, x))


def _f(code, en, ar):
    return {"code": code, "en": en, "ar": ar}


def score_rotation(field_profile, rotation, farmer_priority, water_availability="unknown", economic_inputs=None,
                   scenario=None, income_ref_max=None, kb=None):
    crops, _, rules = kb or load_kb()
    if farmer_priority not in rules["weights"]:
        raise ValueError(f"Unknown priority '{farmer_priority}'. Use one of {list(rules['weights'])}")
    if water_availability not in ("sufficient", "limited", "unknown"):
        raise ValueError("water_availability must be sufficient | limited | unknown")
    for cid in rotation["stages"]:
        if cid not in crops:
            raise ValueError(f"Crop '{cid}' is not in the crop database")
    sc = scenario or {}
    dT, rf = sc.get("delta_t", 0.0), sc.get("rain_factor", 1.0)
    S = rules["scenario"]
    stages = rotation["stages"]
    pos, neg, gaps, warns = [], [], [], []
    crit = {}

    # ---- Water efficiency -------------------------------------------------------------------------------
    per_crop = []
    for cid in stages:
        dem = v(crops, cid, "water_demand_relative")
        s = rules["water_points"][dem]
        if water_availability == "limited":
            pen = rules["water_limited_extra_penalty"][dem]
            s -= pen
            if pen >= 15:
                warns.append(_f("water_limited_high", f"{crops[cid]['name_en']} has high relative water demand and the farmer reports limited water.",
                                f"{crops[cid]['name_ar']} محتاج مية كتير نسبيًا، وإنت قلت إن المية عندك محدودة."))
        if dT or rf != 1.0:
            months = v(crops, cid, "growing_months")
            t, p = season_climate(field_profile, months)
            if t is None:
                gaps.append(_f("scn_no_climate", "Scenario water effect cannot be computed without climate data.", "مفيش بيانات مناخ كفاية لحساب أثر السيناريو على المية."))
            else:
                pct = ((t + dT + S["hargreaves_offset_c"]) / (t + S["hargreaves_offset_c"]) - 1) * 100
                s -= pct * S["water_pts_per_pct_demand"][dem]
                if p is not None:
                    s -= (p * (1 - rf)) / 10 * S["rain_loss_pts_per_10mm"][dem]
        per_crop.append(_clamp(s))
    crit["water"] = {"score": round(sum(per_crop) / len(per_crop), 1), "evidence": "assumption (ordinal water-demand ratings, no measured requirements)",
                     "basis": [f"{crops[c]['name_en']}: {v(crops, c, 'water_demand_relative')} relative demand" for c in stages]}
    if water_availability == "unknown":
        gaps.append(_f("water_unknown", "Water availability not provided; no availability penalty applied.", "ماقلتش حالة المية عندك، فمحدش خُصم منه درجات بسبب كده."))
    gaps.append(_f("no_et", "No evapotranspiration or crop-water-requirement values are stored, so real irrigation need is not calculated.",
                   "مفيش بيانات تبخر-نتح أو احتياج مائي مقاس، فاحتياج الري الفعلي ماتحسبش."))

    # ---- Soil health ------------------------------------------------------------------------------------
    R = rules["soil"]
    fams = {v(crops, c, "family") for c in stages}
    legumes = [c for c in stages if v(crops, c, "nitrogen_fixation")]
    cover = [R["cover_bonus"][v(crops, c, "soil_cover_relative")] for c in stages]
    s = R["base"] + (R["legume_bonus"] if legumes else 0) + R["per_extra_family"] * (len(fams) - 1) + sum(cover) / len(cover)
    basis = [f"base {R['base']}"]
    if legumes:
        names = ", ".join(crops[c]["name_en"] for c in legumes)
        basis.append(f"+{R['legume_bonus']} legume N-fixation ({names})")
        pos.append(_f("legume", f"Includes a nitrogen-fixing legume ({names}), which can lower the nitrogen fertiliser need of the following crop (amount not quantified).",
                      "فيها محصول بقولي بيثبّت النيتروجين في التربة وممكن يقلل السماد للمحصول اللي بعده (من غير رقم محدد)."))
    if len(fams) > 1:
        basis.append(f"+{R['per_extra_family'] * (len(fams) - 1)} botanical diversity")
        pos.append(_f("diversity", "Breaks a cereal-after-cereal sequence, which helps limit cereal-specific pests and diseases.", "بتكسر تتابع الحبوب ورا بعض، وده بيقلل أمراض وآفات الحبوب."))
    else:
        neg.append(_f("monoculture", "Only cereals in sequence (same botanical family): no break crop, no nitrogen fixation.", "حبوب ورا حبوب (نفس العائلة النباتية) من غير محصول بقولي يكسر الدورة."))
    soil = field_profile.get("soil") or {}
    if soil.get("available"):
        if soil.get("texture_class") in ("sand", "loamy sand", "sandy loam"):
            warns.append(_f("sandy", f"Estimated texture '{soil['texture_class']}' suggests low water retention (SoilGrids estimate, confirm with a soil test).",
                            "التربة تقديريًا رملية وبتمسك المية أقل. أكّد بتحليل تربة."))
    else:
        gaps.append(_f("soil_missing", "Soil data unavailable: local soil limits (texture, organic carbon, pH) are not reflected in the soil score.", "بيانات التربة مش متاحة، فمحدش لاحظ قيود التربة المحلية في درجة صحة التربة."))
    crit["soil"] = {"score": round(_clamp(s), 1), "evidence": "mixed: N-fixation and rotation diversity are well established; point values are prototype rules", "basis": basis}

    # ---- Economic potential (only from farmer-supplied numbers) -----------------------------------------
    inc = income_per_year(rotation, economic_inputs)
    if inc is None or not income_ref_max or income_ref_max <= 0:
        crit["income"] = {"score": None, "evidence": "no yield/price/cost data supplied", "basis": []}
        gaps.append(_f("econ_missing", "No yield, price and cost inputs: economic potential is NOT scored (no verified Egyptian figures are stored).",
                       "مفيش أرقام إنتاجية وسعر وتكلفة، فالعائد الاقتصادي ماتقيّمش."))
    else:
        crit["income"] = {"score": round(_clamp(100 * inc / income_ref_max), 1), "evidence": "farmer-supplied inputs; relative to the best compared rotation",
                          "basis": [f"net income per year (input units): {inc:,.1f}"]}

    # ---- Climate resilience ----------------------------------------------------------------------------
    RR = rules["resilience"]
    h = [RR["heat_points"][v(crops, c, "heat_sensitivity")] - dT * S["heat_pts_per_degC"][v(crops, c, "heat_sensitivity")] for c in stages]
    s = sum(h) / len(h) + (RR["diversity_bonus"] if len(fams) > 1 else 0)
    crit["resilience"] = {"score": round(_clamp(s), 1), "evidence": "assumption (ordinal heat-sensitivity ratings)",
                          "basis": [f"{crops[c]['name_en']}: {v(crops, c, 'heat_sensitivity')} heat sensitivity" for c in stages]}
    hot = [c for c in stages if v(crops, c, "heat_sensitivity") == "high"]
    if hot:
        neg.append(_f("heat", f"{', '.join(crops[c]['name_en'] for c in hot)} is heat-sensitive at flowering.", f"{' و'.join(crops[c]['name_ar'] for c in hot)} حساس للحر وقت التزهير."))
    clim = field_profile.get("climate") or {}
    if not clim.get("available") or clim.get("is_illustrative"):
        gaps.append(_f("climate_illustr", "Climate inputs are not observations (illustrative fallback or unavailable); planting-window/climate conflicts cannot be checked.",
                       "بيانات المناخ مش قياسات حقيقية، فمقدرناش نتأكد من مواعيد الزراعة مع الجو."))
    gaps.append(_f("no_thresholds", "Crop temperature thresholds are not in the database, so planting-window conflicts are not scored.", "حدود الحرارة للمحاصيل مش متسجلة، فمواعيد الزراعة ماتقيّمتش."))
    if len(fams) > 1:
        pos.append(_f("resil_div", "Crop diversity spreads risk across seasons.", "تنوع المحاصيل بيوزّع المخاطرة على المواسم."))

    # ---- Weighted total (weights renormalised over scored criteria; never zero-filled) --------------------
    W = rules["weights"][farmer_priority]
    used = {k: W[k] for k in CRITERIA if crit[k]["score"] is not None}
    tot = sum(used.values())
    overall = 0.0
    for k in CRITERIA:
        if k in used:
            crit[k]["weight_nominal"] = W[k]
            crit[k]["weight_used"] = round(used[k] / tot, 4)
            crit[k]["contribution"] = round(crit[k]["score"] * used[k] / tot, 2)
            overall += crit[k]["contribution"]
        else:
            crit[k].update(weight_nominal=W[k], weight_used=0.0, contribution=None)
    provisional = len(used) < len(CRITERIA)
    if farmer_priority == "income" and crit["income"]["score"] is None:
        warns.append(_f("income_unscored", "You chose 'increase income' but no yield/price/cost data were entered, so income cannot influence this ranking. Enter your own figures to enable it.",
                        "إنت اخترت زيادة الدخل، بس من غير أرقام الإنتاجية والسعر والتكلفة العائد مش داخل في الترتيب. دخّل أرقامك عشان يشتغل."))
    return {"rotation_id": rotation["id"], "rotation_name": {"en": rotation["name_en"], "ar": rotation["name_ar"]},
            "overall": round(overall, 1), "provisional": provisional,
            "provisional_reason": "Criteria not scored: " + ", ".join(k for k in CRITERIA if k not in used) if provisional else None,
            "criteria": crit, "positive_factors": pos, "negative_factors": neg, "warnings": warns, "data_gaps": gaps,
            "evidence_refs": sorted({r for c in stages for r in crops[c]["source_refs"]}),
            "evidence_verified": all(crops[c]["verified_against_source"] for c in stages),
            "scenario": sc or None, "priority": farmer_priority}


def status_color(score, rules=None):
    t = (rules or load_kb()[2])["status_thresholds"]
    return None if score is None else "green" if score >= t["green"] else "yellow" if score >= t["yellow"] else "red"


def rank_rotations(field_profile, farmer_priority, water_availability="unknown", economic_inputs=None, scenario=None, rotations=None):
    kb = load_kb()
    rots = rotations or kb[1]
    incomes = [income_per_year(r, economic_inputs) for r in rots]
    ref = max([i for i in incomes if i is not None], default=None)
    res = [score_rotation(field_profile, r, farmer_priority, water_availability, economic_inputs, scenario, ref, kb) for r in rots]
    res.sort(key=lambda x: -x["overall"])
    for i, r in enumerate(res, 1):
        r["rank"] = i
    return res
