"""Egyptian Arabic summary built ONLY from the structured results. Audio is optional (gTTS needs internet)."""
PRI = {"water": "توفير المية", "soil": "تحسين التربة", "income": "زيادة الدخل"}


def arabic_script(result):
    ranked, unc, prof = result["ranked"], result["uncertainty"], result["profile"]
    top = ranked[0]
    veg = prof["hydroscan"]["vegetation"]
    cls = {"bare_soil": "أرض عريانة", "sparse_veg": "غطاء نباتي خفيف", "dense_veg": "غطاء نباتي كثيف"}.get(veg["dominant_class"], veg["dominant_class"])
    parts = [f"بص يا حاج، حللنا بيانات أرضك من صور الأقمار الصناعية، ولقينا إن الغالب عليها {cls}.",
             f"وعلى حسب اختيارك ({PRI[result['inputs']['priority']]})، أعلى دورة في التقييم هي: {top['rotation_name']['ar']}."]
    if top["positive_factors"]:
        parts.append(top["positive_factors"][0]["ar"])
    if top["provisional"]:
        parts.append("بس الترتيب ده مبدئي، لأن بعض المعايير ماتقيّمتش من غير بيانات كفاية.")
    src = result["profile"]["sources"]
    names = [("soil", "التربة"), ("climate_power", "المناخ"), ("gpm_imerg", "المطر من الأقمار"), ("smap", "رطوبة التربة")]
    miss = [n for k, n in names if k not in src or src[k]["status"] == "unavailable"]
    if not result["inputs"].get("economic_inputs"):
        miss.append("الأسعار والإنتاجية")
    parts.append(f"{unc['data_support_ar']}" + (f"، وفيه بيانات ناقصة زي {' و'.join(miss[:3])}." if miss else "."))
    parts.append("الأفضل تراجع مهندس زراعي قبل ما تغيّر نظام الزراعة، ده تقييم مبدئي مش نصيحة زراعية معتمدة.")
    return " ".join(parts)


def make_audio(script, path="summary_ar.mp3"):
    try:
        from gtts import gTTS
        gTTS(script, lang="ar").save(path)
        return path
    except Exception:
        return None
