# Design handoff: what the system will actually show

Channel: WhatsApp (primary), Egyptian Arabic, right-to-left. Web app = same content + **Judge/Expert mode**. This document describes the behaviour implemented in `bot/conversation.py`, `reports/field_card.py`, `reports/audio_summary.py`. Nothing here is aspirational unless marked **[TBD]**.

## 1. Farmer journey (6 steps, no more)
1. Share field location → 2. Tap main priority → 3. Tap water availability → 4. Wait (analysis) → 5. Receive **field card** (image) + **voice summary** → 6. Tap what-if buttons. Everything else lives in Expert mode.

## 2. Screens (WhatsApp messages)

| ID | Screen | Exact content | Actions |
|---|---|---|---|
| S0 | Welcome (first message or "ابدأ") | "أهلاً بيك في HydroScan Rotate 🌾 ابعتلي لوكيشن حقلك (📎 ← الموقع)، وأنا أقارنلك ٣ دورات زراعية. لو عايز تجرب: اكتب 30.525, 30.425" | Send location pin (or type "lat, lon") |
| S1 | Priority | "أهلاً بيك 🌾 استلمت موقع حقلك. إيه أهم حاجة عندك؟" | 3 buttons: 💧 مية / 💰 دخل / 🌱 تربة |
| S2 | Water question | "المية عندك كفاية للموسم ولا محدودة؟" | 3 buttons: كفاية / محدودة / مش عارف |
| S3 | Loading | **[TBD] not yet implemented**: send "ثواني، بحلل أرضك…" immediately (analysis can take seconds, minutes on first GEE run) | none |
| S4 | **Field card** (image) + caption | Card (§3). Caption: priority; top-ranked rotation and score "(مبدئي)"; data-support level + "مش نسبة صحة التوصية"; disclaimer "⚠️ تقييم مبدئي مش نصيحة زراعية معتمدة. راجع مهندس زراعي أو الإرشاد الزراعي قبل أي قرار." | – |
| S5 | **Voice summary** (audio, ≤ ~40 s) + the same script available as text | Script (§4) | play |
| S6 | What-if prompt | "تحب تجرب سيناريو؟" | 3 buttons: 🔥 لو الصيف أسخن / 🌧️ لو المطر قل / 🔊 ملخص صوتي |
| S7 | What-if result | Card re-rendered with red banner "سيناريو افتراضي: الحرارة +٢ درجة" (or "المطر -٢٠٪"); caption states whether the ranking changed ("الترتيب اتغيّر." / "الترتيب ماتغيّرش."), the label "ده تحليل افتراضي مش توقع حقيقي.", disclaimer; then "تحب تجرب حاجة تانية؟" with the same 3 buttons | same 3 buttons, or send a new location to restart |

Message limits: WhatsApp reply buttons max **3**, label ≤ **20 characters** (current labels fit).

## 3. The field card (one portrait image, 7.2 × 11 in, RTL; see `field_card_sample.png`)
Header band: "كارت الحقل – HydroScan Rotate" + coordinates. If a scenario: red line "سيناريو افتراضي: …".

| Block | Content | Rules |
|---|---|---|
| ١ Field status | Dominant cover: "غطاء خفيف / كثيف / أرض عريانة"; mean NDVI; fixed amber line "الري والمحصول: لسه مش بنصنّفهم (مفيش نموذج متحقق منه)" | **Never** show irrigated/rainfed or a crop name as detected |
| ٢ Bare-soil calendar | 12 month tiles (Jan→Dec labelled in Arabic short names). Green = planted/vegetated, brown = possibly bare, **grey = no data**. Footnote: "مبني على N سنة من صور Sentinel-2" (N computed) | Grey must stay visually distinct from brown; never infer bare from missing |
| ٣ Three rotations | Cards ranked #1–#3, each: Arabic name ("دورة بالبقوليات: قمح ← فول ← ذرة", "دورة بالبرسيم: …", "الدورة الحالية: قمح ← ذرة"), score "56/100 مبدئي", **4 traffic-light dots**: مية، تربة، دخل، تحمّل. Grey dot with "؟" = **not assessed (data missing), not zero**. Legend line under the list | Colours: green ≥ threshold, yellow, red (thresholds in `scoring_rules.json`); the current rotation is always one of the three |
| Why #1? | 2 positive reasons + 1 warning, each one short Arabic sentence (≤ ~70 chars on card) | Taken from the scoring rules, no numbers invented |
| ٤ Data support | "دعم البيانات: محدود / متوسط / قوي (مش نسبة صحة التوصية)"; one line of ✔/✖ per source: صور Sentinel-2، مناخ NASA POWER، تربة SoilGrids، مطر GPM، رطوبة SMAP; line "ناقص: …" listing every ✖ plus "أسعار وإنتاجية محلية" unless the farmer entered economics | **No percentage confidence anywhere.** The ✔/✖ and missing list are computed, never typed |
| ٥ Footer | "راجع مهندس زراعي / الإرشاد الزراعي قبل أي قرار." + "تقييم مبدئي بقواعد بسيطة، مش نصيحة معتمدة. التفاصيل والمصادر في وضع الخبير." | Always present |

Design notes: the card must stay readable on a phone at WhatsApp image size; the current render is 1008 × 1540 px. Colour must not be the only cue (dots carry Arabic labels; "؟" for unknown).

## 4. Recommendation format (per rotation, farmer view)
Name · score (relative, "مبدئي" if any criterion unscored) · 4 lights · one benefit sentence · one risk sentence. Never: yield, income, litres, or "% confidence". Voice script structure (verbatim template): greeting "بص يا حاج…" → dominant cover → priority → top rotation + its main benefit → "الترتيب ده مبدئي" if provisional → data-support level + computed list of missing data → "راجع مهندس زراعي…".

## 5. States
| State | Trigger | What the farmer sees |
|---|---|---|
| Loading | analysis running | S3 message **[TBD]**; web: spinner |
| Outside coverage | location not inside the supplied satellite stack (currently only the demo area) | "للأسف الموقع ده برا تغطية صور HydroScan الحالية (حقول تجريبية بس). جرب الحقل التجريبي: 30.525, 30.425". **Design must plan a future wider-coverage message [TBD]** |
| Climate/soil/rain source down | source `unavailable` | Card still renders; that source shows ✖ and appears in "ناقص:"; scores that need it show grey "؟" or a data-gap note. No numbers replaced |
| Cached data | live call failed, older copy used | Farmer: no change. Expert mode: status "cached" + original retrieval date |
| TTS unavailable | no internet for Arabic TTS | Voice message replaced by the same script as text prefixed "🔊" |
| Unrecognised input mid-flow | text instead of button | Re-ask the same question with the same buttons |
| Invalid/empty location | no coordinates | "ابعتلي لوكيشن حقلك…" (S0) |
| Analysis failure | unexpected error **[TBD: generic apology message not yet written]** | – |
| Scenario needs climate | climate unavailable | Scenario still runs as a rule-based sensitivity (labelled hypothetical); expert mode shows climate unavailable |

## 6. Judge / Expert mode (web only; hidden from farmers)
Toggle "🔬 Judge / Expert mode". Extra page "المصادر والتتبّع" with the **traceability table**: Input · Source · Status (ok/cached/unavailable) · Retrieved date · Period · Spatial resolution · Nature (farmer-provided / satellite-derived / modelled / model prediction (not validated) / analyst assumption / hypothetical scenario / unavailable) · Limitations or failure reason. Plus: NDVI chart, bare-soil calendar with threshold, climate/ET0 monthly, soil values, per-rotation criteria with weights/evidence/basis, data-gap lists, "needs expert validation" list, Egyptian references (R-numbers), and a downloadable Markdown evidence report (`SAMPLE_FIELD_REPORT.md` shows it). Maps (Leaflet/Folium) exist in the prototype page; final map design **[TBD]**.

## 7. Content rules the UI must enforce
1. Never show irrigation or crop type as detected. 2. Never show a confidence percentage. 3. Unknown ≠ zero ≠ bad (grey/“؟”). 4. Satellite coarse data (SMAP 9 km, IMERG 11 km, POWER 50 km) is labelled as regional, never as the field's own measurement. 5. Scenarios are labelled hypothetical. 6. The expert-check reminder is on every card and every voice message. 7. Arabic strings above are drafts: **an agronomist and a native farmer-facing copy editor must approve them.**
