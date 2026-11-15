"""Full evidence report (Markdown) for judges / experts: real inputs, analysis, three rotations with reasoning, traceability, limitations."""
import json
import os

from reports.traceability import traceability_markdown
from rotation.suitability import load_kb

PRI = {"water": "saving water", "soil": "improving soil", "income": "income"}
_REFS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rotation", "egypt_references.json")


def _fmt(x):
    return "not scored" if x is None else f"{x}"


def expert_report_md(result):
    prof, ranked, unc, inp = result["profile"], result["ranked"], result["uncertainty"], result["inputs"]
    refs = json.load(open(_REFS, encoding="utf-8"))
    crops = load_kb()[0]
    f, v = prof["field"], prof["hydroscan"]["vegetation"]
    L = [f"# HydroScan Rotate: field evidence report", f"Field point: **{f['latitude']:.4f}, {f['longitude']:.4f}** (radius {f['radius_m']} m, {f['pixels_used']} pixels). "
         f"Farmer priority: **{PRI[inp['priority']]}**. Water availability (farmer): **{inp['water_availability']}**.", "",
         "> Decision support, not agricultural advice. Every item below is labelled with where it came from; anything unavailable is stated as unavailable and was NOT replaced by sample data.", "",
         "## 1. Inputs actually used", "", traceability_markdown(result), "",
         "## 2. What the data say about this field", ""]
    L.append(f"- **Vegetation density (HydroScan model):** dominant class `{v['dominant_class']}`, class fractions {v['class_fractions']}, mean NDVI {v['ndvi_mean']} (±{v['ndvi_std']}). "
             f"This is a vegetation-density result. **Irrigation and crop type are NOT classified** (no validated model, no labels).")
    nd = prof["ndvi"]
    if nd:
        L.append(f"- **NDVI series:** {nd['n_valid_months']} valid months, range {nd['range']}, trend: {nd['trend']['status']}.")
    cal = (prof["bare_soil"] or {}).get("calendar", [])
    if cal:
        L.append("- **Bare-soil calendar (NDVI < %s, an adjustable assumption):** " % prof["bare_soil"]["threshold"] + ", ".join(f"{c['month']}:{c['status']}" for c in cal))
    c = prof["climate"]
    if c["available"]:
        L.append(f"- **Climate (NASA POWER daily, {c['years_of_data']} years):** mean temp {c['mean_temp_c']} °C, annual rain {c['annual_rain_mm']} mm, "
                 f"monthly ET0 (Hargreaves, modelled): " + ", ".join(f"{r['month']}:{r['et0_mm']}" for r in c["monthly"]))
    else:
        L.append(f"- **Climate:** UNAVAILABLE ({c['reason']}).")
    s = prof["soil"]
    L.append("- **Soil (SoilGrids estimate, 0-30 cm):** " + (f"{s['values']} {s['units']}, texture class {s['texture_class']}" if s["available"] else f"UNAVAILABLE ({s['reason']})"))
    for k, name in (("gpm", "GPM IMERG"), ("smap", "SMAP")):
        d = prof.get(k)
        L.append(f"- **{name}:** " + (f"{len(d['data']['monthly'])} months retrieved ({d['provenance']['spatial_resolution']})" if d and d["data"] else "UNAVAILABLE (" + ((d or {}).get('provenance', {}).get('reason') or 'not requested') + ")"))
    L += ["", "## 3. Three rotations and the reasoning", ""]
    for r in ranked:
        L.append(f"### #{r['rank']} {r['rotation_name']['en']} — overall {r['overall']}/100 ({'provisional: ' + r['provisional_reason'] if r['provisional'] else 'complete'})")
        for k, cv in r["criteria"].items():
            L.append(f"- **{k}**: {_fmt(cv['score'])} (weight used {cv['weight_used']}); evidence: {cv['evidence']}; basis: {'; '.join(cv['basis']) or 'none'}")
        L += [f"- Benefits: " + ("; ".join(x["en"] for x in r["positive_factors"]) or "none identified"),
              f"- Risks: " + ("; ".join(x["en"] for x in r["negative_factors"] + r["warnings"]) or "none identified"),
              f"- Information gaps: " + "; ".join(x["en"] for x in r["data_gaps"]), ""]
        stages = next(x for x in load_kb()[1] if x["id"] == r["rotation_id"])["stages"]
        for cid in stages:
            cr = refs["crops"].get(cid)
            if cr:
                L.append(f"  - *{crops[cid]['name_en']} (Egyptian literature, unverified, abstract-level)*: planting {cr['planting_window']['value']} [{', '.join(cr['planting_window']['refs'])}]; "
                         f"water: " + " | ".join(f"{w['value']} ({w['what']}) [{', '.join(w['refs'])}]" for w in cr["water"]))
        L.append("")
    L += ["## 4. Data support (descriptive, not a probability)", f"**{unc['data_support']}**. {unc['indicator_note']}", ""]
    for k, cv in unc["components"].items():
        L.append(f"- {k}: {cv['level']}: {cv['why']}")
    L += ["", "## 5. Missing data", ""] + [f"- {m}" for m in prof["data_quality"]["missing"]]
    L += ["", "## 6. Limitations and warnings", ""] + [f"- {w}" for w in prof["data_quality"]["warnings"]]
    L += ["", "## 7. Needs expert validation", ""] + [f"- {x}" for x in unc["needs_expert_validation"]]
    L += ["", "## 8. Rotation evidence in Egyptian literature", refs["rotation_evidence"]["found"], "", "**Gap:** " + refs["rotation_evidence"]["gap"], "", "## 9. Reference list", ""]
    L += [f"- **{k}** {v['citation']} ({v['type']}) {v['url']}" for k, v in refs["sources"].items()]
    return "\n".join(L)
