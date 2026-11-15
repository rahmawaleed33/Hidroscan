"""One-image Arabic 'field card' (the WhatsApp deliverable). Built ONLY from the structured analysis result.
Arabic shaping relies on matplotlib >= 3.11 native text layout (do NOT pre-shape with arabic-reshaper)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch


FONT = "DejaVu Sans"  # ships with matplotlib and has Arabic glyphs
MONTHS_AR = ["ينا", "فبر", "مار", "أبر", "مايو", "يون", "يول", "أغس", "سبت", "أكت", "نوف", "ديس"]
PRI_AR = {"water": "توفير المياه", "soil": "تحسين التربة", "income": "زيادة الدخل"}
CLS_AR = {"bare_soil": "أرض عريانة", "sparse_veg": "غطاء خفيف", "dense_veg": "غطاء كثيف"}
COL = {"green": "#2e9e5b", "yellow": "#e0b020", "red": "#d04a3a", None: "#9aa3ad",
       "vegetated": "#6dbb63", "potential_bare_soil": "#b98a52", "unknown": "#c8ccd2"}
EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴", None: "⚪"}
CRIT_AR = {"water": "مية", "soil": "تربة", "income": "دخل", "resilience": "تحمّل"}


def ar(text):
    if not text:
        return ""
    # matplotlib >= 3.11 shapes and reorders Arabic natively (raqm); pre-shaping would double-process it.
    return str(text)


def _light(score, rules):
    if score is None:
        return None
    t = rules["status_thresholds"]
    return "green" if score >= t["green"] else "yellow" if score >= t["yellow"] else "red"


def cal_note(prof):
    ns = [c["n_years"] for c in prof["bare_soil"]["calendar"] if c["status"] != "unknown"]
    yrs = max(ns) if ns else 0
    return f"أخضر = مزروع | بني = عاري محتمل | رمادي = مش معروف. مبني على {yrs} سنة من صور Sentinel-2."


def make_field_card(result, path, scenario_label=None):
    from rotation.suitability import load_kb
    rules = load_kb()[2]
    prof, ranked, unc, inp = result["profile"], result["ranked"], result["uncertainty"], result["inputs"]
    fig = plt.figure(figsize=(7.2, 11), dpi=140, facecolor="#f6f8f5")
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 100); ax.set_ylim(0, 152); ax.axis("off")
    ax.add_patch(FancyBboxPatch((2, 140), 96, 10, boxstyle="round,pad=0.3", fc="#0b3d91", ec="none"))
    ax.text(50, 147, ar("كارت الحقل – HydroScan Rotate"), color="white", ha="center", va="center", fontsize=17, fontweight="bold", family=FONT)
    ax.text(50, 142.5, f"{prof['field']['latitude']:.4f}, {prof['field']['longitude']:.4f}", color="#cfe0ff", ha="center", fontsize=9, family=FONT)
    if scenario_label:
        ax.text(50, 137.5, ar("سيناريو افتراضي: " + scenario_label), ha="center", fontsize=10, color="#b3261e", family=FONT, fontweight="bold")

    # 1) current status
    v = prof["hydroscan"]["vegetation"]
    ax.text(97, 134, ar("١) وضع الحقل (من الصور)"), ha="right", fontsize=12, fontweight="bold", family=FONT)
    ax.text(97, 129.5, ar(f"الغالب: {CLS_AR.get(v['dominant_class'], v['dominant_class'])}   |   NDVI متوسط: {v['ndvi_mean']}"), ha="right", fontsize=10, family=FONT)
    ax.text(97, 125.5, ar("الري والمحصول: لسه مش بنصنّفهم (مفيش نموذج متحقق منه)"), ha="right", fontsize=9, color="#7a4b00", family=FONT)

    # 2) bare-soil calendar
    ax.text(97, 119, ar("٢) تقويم الأرض العارية (رمادي = مفيش بيانات)"), ha="right", fontsize=12, fontweight="bold", family=FONT)
    cal = prof["bare_soil"]["calendar"]
    for i, c in enumerate(cal):
        x = 3 + i * 7.9
        ax.add_patch(FancyBboxPatch((x, 107), 7, 8, boxstyle="round,pad=0.1", fc=COL[c["status"]], ec="white"))
        ax.text(x + 3.5, 104.5, ar(MONTHS_AR[i]), ha="center", fontsize=7, family=FONT)
    ax.text(97, 100, ar(cal_note(prof)), ha="right", fontsize=7.5, color="#555", family=FONT)

    # 3) rotations
    ax.text(97, 94, ar(f"٣) مقارنة ٣ دورات – أولويتك: {PRI_AR[inp['priority']]}"), ha="right", fontsize=12, fontweight="bold", family=FONT)
    y = 88
    for r in ranked:
        ax.add_patch(FancyBboxPatch((2, y - 14), 96, 14.5, boxstyle="round,pad=0.2", fc="white", ec="#d5dde8"))
        ax.text(97, y - 2.5, ar(f"#{r['rank']}  {r['rotation_name']['ar']}"), ha="right", fontsize=10.5, fontweight="bold", family=FONT)
        tag = "مبدئي" if r["provisional"] else ""
        ax.text(5, y - 2.5, ar(f"{r['overall']:.0f}/100 {tag}"), ha="left", fontsize=9, color="#444", family=FONT)
        for j, k in enumerate(["water", "soil", "income", "resilience"]):
            s = r["criteria"][k]["score"]; light = _light(s, rules)
            cx = 90 - j * 22
            ax.add_patch(plt.Circle((cx, y - 8), 2.0, color=COL[light]))
            ax.text(cx, y - 12.6, ar(CRIT_AR[k] + (" ؟" if s is None else "")), ha="center", fontsize=8, family=FONT)
        pos = r["positive_factors"][0]["ar"] if r["positive_factors"] else ""
        neg = (r["negative_factors"] + r["warnings"])[0]["ar"] if (r["negative_factors"] or r["warnings"]) else ""
        y -= 16.5
    # factor lines under the cards
    ax.text(97, y + 1.5, ar("(؟ = مش متقيَّم لأن بياناته ناقصة، مش معناه صفر)"), ha="right", fontsize=7.5, color="#555", family=FONT)
    yy = y - 3
    top = ranked[0]
    ax.text(97, yy, ar("ليه الأولى؟"), ha="right", fontsize=10, fontweight="bold", family=FONT)
    for f in top["positive_factors"][:2]:
        yy -= 3.6; ax.text(97, yy, ar("• " + f["ar"][:70]), ha="right", fontsize=7.8, family=FONT)
    for f in (top["negative_factors"] + top["warnings"])[:1]:
        yy -= 3.6; ax.text(97, yy, ar("⚠ " + f["ar"][:70]), ha="right", fontsize=7.8, color="#a33", family=FONT)

    # 4) confidence + disclaimer
    ax.add_patch(FancyBboxPatch((2, 3), 96, 17, boxstyle="round,pad=0.2", fc="#fff4e0", ec="#e0b020"))
    src = prof["sources"]
    def ok(k): return k in src and src[k]["status"] != "unavailable"
    names = [("ndvi_series", "صور Sentinel-2"), ("climate_power", "مناخ NASA POWER"), ("soil", "تربة SoilGrids"), ("gpm_imerg", "مطر GPM"), ("smap", "رطوبة SMAP")]
    line = "  ".join(("✔ " if ok(k) else "✖ ") + n for k, n in names)
    miss = [n for k, n in names if not ok(k)]
    if not inp.get("economic_inputs"):
        miss.append("أسعار وإنتاجية محلية")
    ax.text(97, 17.2, ar(f"٤) دعم البيانات: {unc['data_support_ar']} (مش نسبة صحة التوصية)"), ha="right", fontsize=9.5, fontweight="bold", family=FONT)
    ax.text(97, 13.6, ar(line), ha="right", fontsize=7.6, family=FONT)
    ax.text(97, 10.6, ar("ناقص: " + ("، ".join(miss) if miss else "لا شيء")), ha="right", fontsize=7.6, color="#8a1f11", family=FONT)
    ax.text(97, 7.0, ar("٥) راجع مهندس زراعي / الإرشاد الزراعي قبل أي قرار."), ha="right", fontsize=9, fontweight="bold", color="#8a1f11", family=FONT)
    ax.text(97, 4.3, ar("تقييم مبدئي بقواعد بسيطة، مش نصيحة معتمدة. التفاصيل والمصادر في وضع الخبير."), ha="right", fontsize=7.2, color="#555", family=FONT)
    fig.savefig(path, facecolor=fig.get_facecolor()); plt.close(fig)
    return path
