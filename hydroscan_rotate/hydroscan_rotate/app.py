"""HydroScan Rotate - Streamlit app (Arabic farmer-facing UI, English technical notes).
Run:  python -m streamlit run app.py"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import streamlit as st

import config
from hydroscan.model_adapter import bounds_of, read_stack
from pipeline import run_analysis
from reports.audio_summary import arabic_script, make_audio
from reports.field_card import make_field_card
from reports.report_generator import generate_report
from rotation.scenarios import PRESETS, run_scenario
from rotation.scoring import CRIT_LABEL, status_color
from rotation.suitability import load_kb
from schemas import HydroScanError

st.set_page_config(page_title="HydroScan Rotate", page_icon="🌾", layout="wide")
st.markdown("""<style>
.block-container{max-width:1200px;padding-top:1.2rem} .ar{direction:rtl;text-align:right}
.hero{background:linear-gradient(120deg,#0b3d91,#1e8f5a);color:#fff;padding:1.4rem 2rem;border-radius:16px;margin-bottom:1rem}
.hero h1{margin:0}.card{border:1px solid #dbe7fb;border-radius:14px;padding:1rem 1.2rem;background:#fff;margin-bottom:.8rem}
.tag{display:inline-block;padding:.1rem .6rem;border-radius:10px;font-size:.8rem;color:#fff}
.green{background:#2e9e5b}.yellow{background:#c9a010}.red{background:#d04a3a}.grey{background:#8a93a0}
</style>""", unsafe_allow_html=True)

CRIT_AR = {k: v[1] for k, v in CRIT_LABEL.items()}
PRI = {"💧 توفير المياه": "water", "🌱 تحسين التربة": "soil", "💰 زيادة الدخل": "income"}
WATER = {"كفاية": "sufficient", "محدودة": "limited", "مش عارف": "unknown"}
ss = st.session_state
ss.setdefault("lat", config.DEMO_FIELD["lat"]); ss.setdefault("lon", config.DEMO_FIELD["lon"])
ss.setdefault("result", None)

st.markdown('<div class="hero"><h1>🌾 HydroScan Rotate</h1><p class="ar">ساعدك تقارن دورات زراعية مناسبة لأرضك، بالأقمار الصناعية وبيانات ناسا. تقييم مبدئي، مش نصيحة زراعية معتمدة.</p></div>', unsafe_allow_html=True)
expert = st.sidebar.toggle("🔬 Judge / Expert mode", value=False, help="Shows data sources, retrieval dates, resolutions, scientific indicators and limitations. Farmers do not need it.")
PAGES = ["١. الحقل", "٢. أولوياتك", "٣. تحليل الأرض", "٤. الدورات المقترحة", "٥. ماذا لو؟", "٦. التقرير"] + (["٧. المصادر والتتبّع (خبير)"] if expert else [])
page = st.radio("الخطوات", PAGES, horizontal=True, label_visibility="collapsed")


def badge(score):
    c = status_color(score)
    return f'<span class="tag {c or "grey"}">{"غير مقيَّم" if score is None else f"{score:.0f}"}</span>'


if page.startswith("١"):
    st.subheader("اختار الحقل")
    c1, c2 = st.columns([2, 1])
    with c2:
        if st.button("استخدم الحقل التجريبي"):
            ss.lat, ss.lon = config.DEMO_FIELD["lat"], config.DEMO_FIELD["lon"]
        ss.lat = st.number_input("خط العرض (lat)", value=float(ss.lat), format="%.5f")
        ss.lon = st.number_input("خط الطول (lon)", value=float(ss.lon), format="%.5f")
    with c1:
        try:
            import folium
            from streamlit_folium import st_folium
            arr, geo = read_stack(config.DEMO_STACK)
            w, s, e, n = bounds_of(arr, geo)
            m = folium.Map(location=[ss.lat, ss.lon], zoom_start=13, tiles=None)
            folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri", name="Satellite").add_to(m)
            folium.Rectangle([[s, w], [n, e]], color="#19c3e6", fill=False, tooltip="تغطية صورة HydroScan").add_to(m)
            folium.Marker([ss.lat, ss.lon]).add_to(m)
            out = st_folium(m, height=420, width="stretch", returned_objects=["last_clicked"])
            if out and out.get("last_clicked"):
                ss.lat, ss.lon = out["last_clicked"]["lat"], out["last_clicked"]["lng"]
                st.rerun()
        except ImportError:
            st.info("الخريطة التفاعلية محتاجة: pip install folium streamlit-folium. تقدر تدخل الإحداثيات يدويًا.")
    st.success(f"الحقل المختار: {ss.lat:.5f}, {ss.lon:.5f}")

elif page.startswith("٢"):
    st.subheader("إيه أهم حاجة عندك؟")
    ss.pri_label = st.radio("الأولوية", list(PRI), index=list(PRI).index(ss.get("pri_label", "💧 توفير المياه")))
    ss.water_label = st.radio("حالة المية", list(WATER), index=list(WATER).index(ss.get("water_label", "مش عارف")), horizontal=True)
    with st.expander("اختياري: أرقامك الاقتصادية (الإنتاجية والسعر والتكلفة بنفس الوحدات لكل المحاصيل)"):
        st.caption("من غير الأرقام دي العائد الاقتصادي ماتقيّمش. مفيش أسعار مخزنة في النظام.")
        crops = load_kb()[0]
        econ = {}
        for cid, c in crops.items():
            a, b, d = st.columns(3)
            y = a.number_input(f"{c['name_ar']} - إنتاجية", 0.0, key=f"y_{cid}"); p = b.number_input("سعر", 0.0, key=f"p_{cid}"); k = d.number_input("تكلفة", 0.0, key=f"c_{cid}")
            econ[cid] = {"yield": y or None, "price": p or None, "cost": k or None}
        ss.econ = econ if all(all(v is not None for v in e.values()) for e in econ.values()) else None

elif page.startswith("٣"):
    st.subheader("تحليل الأرض")
    if st.button("🚀 حلّل الحقل", type="primary"):
        with st.spinner("بنحلل..."):
            try:
                ss.result = run_analysis(ss.lat, ss.lon, PRI[ss.get("pri_label", "💧 توفير المياه")], WATER[ss.get("water_label", "مش عارف")], ss.get("econ"))
            except HydroScanError as exc:
                ss.result = None
                st.error(f"مقدرناش نحلل الحقل: {exc}")
    r = ss.result
    if r:
        p = r["profile"]; v = p["hydroscan"]["vegetation"]
        if not expert:
            st.success("تم تحليل الحقل. كمّل لخطوة «الدورات المقترحة». (التفاصيل العلمية في وضع الخبير)")
        a, b, c, d = st.columns(4) if expert else (st.container(),) * 4
        if expert: a.metric("متوسط NDVI", v["ndvi_mean"]); b.metric("الغطاء السائد", v["dominant_class"]); c.metric("الري", "غير مصنَّف", help=p["hydroscan"]["irrigation"]["source"]); d.metric("المحصول", "غير مصنَّف")
        if expert: st.caption(p["hydroscan"]["model"]["explanation"])
        x1, x2 = st.columns(2)
        with x1:
          if expert:
            fig, ax = plt.subplots(figsize=(5, 3)); nd = p["ndvi"]["monthly"]
            ax.plot([m["month"] for m in nd], [m["ndvi"] for m in nd], marker="o"); ax.set(title="NDVI (Sentinel-2)", ylim=(0, .8)); ax.tick_params(axis="x", labelrotation=90, labelsize=5); st.pyplot(fig)
        with x2:
          if expert:
            cal = p["bare_soil"]["calendar"]; fig, ax = plt.subplots(figsize=(5, 3))
            col = {"vegetated": "#6dbb63", "potential_bare_soil": "#c9a06a", "unknown": "#c8ccd2"}
            ax.bar([c["month"] for c in cal], [1] * 12, color=[col[c["status"]] for c in cal]); ax.set(title="Bare-soil calendar (grey = unknown)", yticks=[]); st.pyplot(fig)
        cl = p["climate"]
        if not cl["available"]:
            st.warning("بيانات المناخ من ناسا مش متاحة دلوقتي، فمفيش أي أرقام مناخ معروضة (مش بنستخدم بيانات بديلة).")
        if expert:
          st.caption("Soil: " + (str(p["soil"]["values"]) + " (SoilGrids estimate)" if p["soil"]["available"] else "unavailable - " + str(p["soil"]["reason"])[:160]))
        with st.expander("جودة البيانات والمصادر", expanded=False) if expert else st.container():
          if expert:
            st.write("**متاح:**", p["data_quality"]["available"]); st.write("**ناقص:**", p["data_quality"]["missing"]); st.write("**تنبيهات:**", p["data_quality"]["warnings"])
            st.json(p["sources"])
    else:
        st.info("اضغط تحليل.")

elif page.startswith("٤"):
    r = ss.result
    if not r:
        st.info("حلّل الحقل الأول (خطوة ٣).")
    else:
        u = r["uncertainty"]
        st.subheader("الدورات الزراعية المقترحة")
        st.markdown(f'<div class="card ar"><b>{u["data_support_ar"]}</b> — {u["indicator_note"]}</div>', unsafe_allow_html=True)
        if any(x["provisional"] for x in r["ranked"]):
            st.warning("الترتيب مبدئي: " + r["ranked"][0]["provisional_reason"])
        for x in r["ranked"]:
            with st.container(border=True):
                st.markdown(f"### #{x['rank']} {x['rotation_name']['ar']}  \n{x['rotation_name']['en']} — **{x['overall']}**")
                cols = st.columns(4)
                for col, k in zip(cols, CRIT_LABEL):
                    col.markdown(f"{CRIT_AR[k]}<br>{badge(x['criteria'][k]['score'])}", unsafe_allow_html=True)
                for f in x["positive_factors"]:
                    st.markdown(f"✅ {f['ar']}")
                for f in x["negative_factors"] + x["warnings"]:
                    st.markdown(f"⚠️ {f['ar']}")
                with st.expander("ليه الترتيب ده؟ والأدلة والبيانات الناقصة") if expert else st.container():
                  if expert:
                    for k, cv in x["criteria"].items():
                        st.write(f"**{CRIT_LABEL[k][0]}**: {cv['score']} | weight used {cv['weight_used']} | contribution {cv['contribution']} | evidence: {cv['evidence']}")
                        st.caption("; ".join(cv["basis"]))
                    st.write("**Data gaps:**", [g["en"] for g in x["data_gaps"]]); st.write("**References to consult:**", x["evidence_refs"], "(not yet verified against them)")
        st.subheader("المخاطر")
        for k, rv in u["risks"].items():
            st.markdown(f"- **{k}** ({rv['level_ar']}): {rv['ar']}")

elif page.startswith("٥"):
    r = ss.result
    if not r:
        st.info("حلّل الحقل الأول.")
    else:
        names = {v["label_ar"]: k for k, v in PRESETS.items()}
        pick = st.radio("السيناريو (افتراضي)", list(names), horizontal=True)
        dT = st.slider("زيادة الحرارة (°C)", 0.0, 5.0, PRESETS[names[pick]]["delta_t"], .5)
        rf = st.slider("معامل المطر", 0.5, 1.2, PRESETS[names[pick]]["rain_factor"], .05)
        inp = r["inputs"]
        sc = run_scenario(r["profile"], {"delta_t": dT, "rain_factor": rf}, inp["priority"], inp["water_availability"], inp["economic_inputs"])
        st.caption(sc["label"] + " — " + sc["label_ar"])
        st.dataframe([{"rotation": x["name"]["en"], "baseline": x["baseline_score"], "scenario": x["scenario_score"], "Δ": x["delta"], "rank base→scen": f"{x['baseline_rank']}→{x['scenario_rank']}"} for x in sc["rows"]])
        st.write("الترتيب اتغيّر." if sc["ranking_changed"] else "الترتيب ماتغيّرش.")
        for n in sc["explanations"]:
            st.markdown(f"- {n['ar']}")

else:
    r = ss.result
    if not r:
        st.info("حلّل الحقل الأول.")
    else:
        st.subheader("التقرير والملخص الصوتي")
        if st.button("📄 جهّز التقرير"):
            ss.files = generate_report(r, os.path.join(config.ROOT, "reports_out"))
        for kind, mime in (("pdf", "application/pdf"), ("html", "text/html"), ("png", "image/png")):
            if ss.get("files"):
                st.download_button(f"⬇️ {kind.upper()}", open(ss.files[kind], "rb").read(), os.path.basename(ss.files[kind]), mime)
        if st.button("🪪 كارت الحقل (زي اللي بيتبعت على واتساب)"):
            os.makedirs(os.path.join(config.ROOT, "reports_out"), exist_ok=True)
            ss.card = make_field_card(r, os.path.join(config.ROOT, "reports_out", "field_card.png"))
        if ss.get("card"):
            st.image(ss.card, width=420)
            st.download_button("⬇️ حمّل الكارت", open(ss.card, "rb").read(), "field_card.png", "image/png")
        script = arabic_script(r)
        st.markdown(f'<div class="card ar">{script}</div>', unsafe_allow_html=True)
        if st.button("🔊 ولّد صوت (محتاج gTTS ونت)"):
            path = make_audio(script, os.path.join(config.ROOT, "reports_out", "summary_ar.mp3"))
            st.audio(path) if path else st.info("التحويل لصوت مش متاح هنا؛ النص فوق جاهز.")


if expert and page.startswith("٧"):
    r = ss.result
    if not r:
        st.info("حلّل الحقل الأول (خطوة ٣).")
    else:
        from reports.traceability import build_traceability
        st.subheader("Traceability: source, date, resolution, nature, limits")
        st.dataframe(build_traceability(r), width="stretch")
        st.subheader("Missing data and limitations")
        st.write(r["profile"]["data_quality"]["missing"]); st.write(r["profile"]["data_quality"]["warnings"])
        st.subheader("Needs expert validation"); st.write(r["uncertainty"]["needs_expert_validation"])
        st.caption("Egyptian crop references (abstract-level, unverified): rotation/egypt_references.json")
