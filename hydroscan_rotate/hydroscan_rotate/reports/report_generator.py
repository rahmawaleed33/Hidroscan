"""Field report: bilingual HTML (Arabic RTL works natively), English PDF and PNG overview. Arabic is kept out of PDF/PNG
because matplotlib/reportlab do not shape Arabic without extra libraries."""
import base64
import html
import io
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rotation.scoring import CRIT_LABEL, status_color
from rotation.suitability import load_kb

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COL = {"green": "#2e9e5b", "yellow": "#e0b020", "red": "#d04a3a", "vegetated": "#6dbb63", "potential_bare_soil": "#c9a06a", "unknown": "#c8ccd2"}
DISCLAIMER = ("Prototype decision support, not certified agricultural advice. Crop attributes are general knowledge and analyst assumptions "
              "not yet verified against Egyptian sources. Confirm with an agricultural engineer and a soil test before changing your cropping system.")


def overview_png(result, path):
    prof, ranked = result["profile"], result["ranked"]
    fig, ax = plt.subplots(2, 2, figsize=(12, 8))
    ndvi = [m for m in (prof["ndvi"] or {}).get("monthly", [])]
    ax[0, 0].plot([m["month"][5:] for m in ndvi], [m["ndvi"] for m in ndvi], marker="o", color="#2e9e5b")
    ax[0, 0].set(title="Monthly NDVI (area mean, observed)", ylim=(0, 0.8)); ax[0, 0].tick_params(axis="x", rotation=45)
    cal = (prof["bare_soil"] or {}).get("calendar", [])
    for c in cal:
        ax[0, 1].bar(c["month"], 1, color=COL[c["status"]])
    ax[0, 1].set(title="Bare-soil calendar (grey = unknown)", yticks=[], xticks=range(1, 13)); ax[0, 1].set_xticklabels(MONTHS, fontsize=7)
    cl = prof["climate"]
    if cl["available"]:
        ax[1, 0].plot(MONTHS, [r["temp_c"] for r in cl["monthly"]], color="#d04a3a"); ax[1, 0].set_ylabel("Temp C")
        ax2 = ax[1, 0].twinx(); ax2.bar(MONTHS, [r["rain_mm"] or 0 for r in cl["monthly"]], alpha=.4); ax2.set_ylabel("Rain mm")
        ax[1, 0].set_title("Climate" + (" - ILLUSTRATIVE, NOT OBSERVED" if cl["is_illustrative"] else " (NASA POWER)"))
    else:
        ax[1, 0].text(.5, .5, "Climate unavailable", ha="center"); ax[1, 0].axis("off")
    names = [r["rotation_id"] for r in ranked]
    for i, k in enumerate(["water", "soil", "resilience"]):
        ax[1, 1].bar([x + i * .25 for x in range(len(names))], [r["criteria"][k]["score"] for r in ranked], .25, label=CRIT_LABEL[k][0])
    ax[1, 1].set_xticks([x + .25 for x in range(len(names))]); ax[1, 1].set_xticklabels([f"Rotation {n}" for n in names])
    ax[1, 1].set(title="Criterion scores (economic not scored without inputs)", ylim=(0, 100)); ax[1, 1].legend(fontsize=7)
    fig.suptitle(f"HydroScan Rotate - field {prof['field']['latitude']:.4f}, {prof['field']['longitude']:.4f}", fontsize=13)
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)
    return path


def _b64(path):
    return base64.b64encode(open(path, "rb").read()).decode()


def report_html(result, png_path):
    e = html.escape
    prof, ranked, unc = result["profile"], result["ranked"], result["uncertainty"]
    rules = load_kb()[2]
    rows = ""
    for r in ranked:
        cells = "".join(f"<td style='color:{COL.get(status_color(r['criteria'][k]['score'], rules), '#888')}'>"
                        f"{'not scored' if r['criteria'][k]['score'] is None else r['criteria'][k]['score']}</td>" for k in CRIT_LABEL)
        rows += (f"<tr><td>#{r['rank']}</td><td>{e(r['rotation_name']['en'])}<br><span dir=rtl>{e(r['rotation_name']['ar'])}</span></td>"
                 f"<td><b>{r['overall']}</b>{' (provisional)' if r['provisional'] else ''}</td>{cells}</tr>")
    why = "".join(f"<h3>{e(r['rotation_name']['en'])}</h3><ul>" + "".join(f"<li>+ {e(f['en'])}</li>" for f in r["positive_factors"]) +
                  "".join(f"<li>- {e(f['en'])}</li>" for f in r["negative_factors"] + r["warnings"]) + "</ul><p><i>Data gaps:</i> " +
                  e(" ".join(g["en"] for g in r["data_gaps"][:3])) + "</p>" for r in ranked)
    risks = "".join(f"<li><b>{k}</b>: {v['level']} - {e(v['en'])}</li>" for k, v in unc["risks"].items())
    srcs = "".join(f"<li><b>{k}</b>: {e(str(v['source']))} [{v['kind']}, {v['status']}]" + (f" - {e(v['reason'])}" if v.get("reason") else "") + "</li>" for k, v in prof["sources"].items())
    dq = prof["data_quality"]
    soil = prof["soil"]
    soil_txt = (f"texture {soil['texture_class']}, values {soil['values']} (estimate)") if soil["available"] else f"unavailable: {e(str(soil['reason'])[:120])}"
    return f"""<!doctype html><html lang=en><meta charset=utf-8><title>HydroScan Rotate report</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:960px;margin:2rem auto;color:#12263f}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #d5dfee;padding:.4rem .6rem;text-align:left}}h2{{color:#0b3d91;border-bottom:2px solid #19c3e6}}.warn{{background:#fff6e0;padding:.6rem;border-radius:8px}}</style>
<h1>HydroScan Rotate - Field report</h1>
<h2>1. Field</h2><p>Lat {prof['field']['latitude']:.5f}, Lon {prof['field']['longitude']:.5f} | raster {e(prof['field']['stack'])} | window {prof['field']['radius_m']} m | priority: {result['inputs']['priority']} | water: {result['inputs']['water_availability']}</p>
<h2>2. HydroScan results</h2><p>{e(prof['hydroscan']['model']['explanation'])}</p><p>Irrigation: <b>not classified</b> ({e(prof['hydroscan']['irrigation']['source'])}). Crop: <b>not classified</b>.</p>
<img style="width:100%" src="data:image/png;base64,{_b64(png_path)}">
<h2>3-5. NDVI, bare-soil calendar, climate</h2><p>Seasonal NDVI: {prof['ndvi']['seasonal_mean'] if prof['ndvi'] else 'n/a'}; trend: {prof['ndvi']['trend']['status'] if prof['ndvi'] else 'n/a'}.</p>
<p>{'; '.join(e(c) for c in (prof['bare_soil'] or {}).get('caveats', []))}</p>
<h2>6. Soil</h2><p>{soil_txt}</p>
<h2>7. Rotation comparison</h2><table><tr><th>Rank</th><th>Rotation</th><th>Overall</th><th>Water</th><th>Soil</th><th>Income</th><th>Resilience</th></tr>{rows}</table>
<h2>8. Why this ranking</h2>{why}
<h2>9. Risks</h2><ul>{risks}</ul>
<h2>10. Data quality</h2><p><b>{unc['data_support']}</b> ({unc['data_support_ar']}). {e(unc['indicator_note'])}</p><p>Available: {e(', '.join(dq['available']))}</p><p>Missing: {e('; '.join(m[:90] for m in dq['missing']))}</p>
<h2>11. Sources and assumptions</h2><ul>{srcs}</ul><p>Reference documents to consult: FAO Irrigation and Drainage Paper 56; FAO GAEZ; Egypt ARC / MALR bulletins; FAOSTAT.</p>
<h2>12. Disclaimer</h2><p class=warn>{DISCLAIMER}</p></html>"""


def report_pdf(result, png_path, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    st = getSampleStyleSheet(); P = lambda t, s="BodyText": Paragraph(html.escape(t), st[s])
    prof, ranked, unc = result["profile"], result["ranked"], result["uncertainty"]
    el = [P("HydroScan Rotate - Field report", "Title"), P(f"Field: {prof['field']['latitude']:.5f}, {prof['field']['longitude']:.5f} | priority {result['inputs']['priority']} | water {result['inputs']['water_availability']}"),
          P(prof["hydroscan"]["model"]["explanation"]), P("Irrigation and crop type: NOT classified (no validated model)."), Image(png_path, 480, 320),
          P("Rotation comparison", "Heading2")]
    data = [["Rank", "Rotation", "Overall", "Water", "Soil", "Income", "Resil."]]
    for r in ranked:
        data.append([r["rank"], r["rotation_name"]["en"][:34], f"{r['overall']}{'*' if r['provisional'] else ''}"] + [("n/s" if r["criteria"][k]["score"] is None else r["criteria"][k]["score"]) for k in CRIT_LABEL])
    t = Table(data); t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .5, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    el += [t, P("* provisional: some criteria not scored (n/s) for lack of data."), Spacer(1, 8), P("Why", "Heading2")]
    for r in ranked:
        el.append(P(f"{r['rotation_name']['en']}: " + " ".join(["+ " + f["en"] for f in r["positive_factors"]] + ["- " + f["en"] for f in r["negative_factors"] + r["warnings"]])))
    el += [P("Risks", "Heading2")] + [P(f"{k}: {v['level']} - {v['en']}") for k, v in unc["risks"].items()]
    el += [P("Data quality", "Heading2"), P(f"{unc['data_support']}. {unc['indicator_note']}"), P("Missing: " + "; ".join(m[:80] for m in prof["data_quality"]["missing"])),
           P("Sources", "Heading2")] + [P(f"{k}: {v['source']} [{v['kind']}/{v['status']}]") for k, v in prof["sources"].items()] + [P("Disclaimer", "Heading2"), P(DISCLAIMER)]
    SimpleDocTemplate(path, pagesize=A4).build(el)
    return path


def generate_report(result, outdir="reports_out"):
    os.makedirs(outdir, exist_ok=True)
    png = overview_png(result, os.path.join(outdir, "field_overview.png"))
    h = os.path.join(outdir, "field_report.html"); open(h, "w", encoding="utf-8").write(report_html(result, png))
    return {"png": png, "html": h, "pdf": report_pdf(result, png, os.path.join(outdir, "field_report.pdf"))}
