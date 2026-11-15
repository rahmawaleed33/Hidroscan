# HydroScan Rotate: field evidence report
Field point: **30.5250, 30.4250** (radius 300 m, 3302 pixels). Farmer priority: **saving water**. Water availability (farmer): **limited**.

> Decision support, not agricultural advice. Every item below is labelled with where it came from; anything unavailable is stated as unavailable and was NOT replaced by sample data.

## 1. Inputs actually used

| Input | Source | Status | Retrieved | Period | Spatial resolution | Nature of value | Limitations / reason |
|---|---|---|---|---|---|---|---|
| Field location | farmer's shared location pin | ok | at request time | - | point | farmer-provided | A point, not field boundaries. |
| Main priority | farmer's button choice | ok | at request time | - | - | farmer-provided | Changes the criterion weights only. |
| Water availability | farmer's answer | ok | at request time | - | - | farmer-provided | Not verified; no satellite or gauge measure of irrigation water is used. |
| Vegetation density class (bare / sparse / dense) | Sentinel-1/2 composite via Google Earth Engine (supplied GeoTIFF) + HydroScan RF | ok | supplied GeoTIFF composite (exact acquisition dates not stored in the file) | - | 9 m | model prediction (not validated) | Random-forest trained on NDVI-threshold pseudo-labels (99 % agreement with a plain NDVI rule, no validated accuracy). It says nothing about irrigation or crop type. |
| NDVI series and bare-soil calendar | Sentinel-2 SR NDVI + Sentinel-1 GRD VV/VH, area mean over the HydroScan bbox (project's original GEE output) | cached | 2026-11 (file supplied with the project) | 2026-01..2026-10 | 10 m pixels, averaged over a ~5 km box | satellite-derived | Whole-area mean, not field-specific; one year only. Its SMAP column is empty. |
| Temperature, humidity, radiation, rainfall (climate) | NASA POWER daily (AG) | unavailable | - | - | - | unavailable | offline mode (HYDROSCAN_OFFLINE=1) |
| Reference evapotranspiration (ET0) | NASA POWER daily (AG) | unavailable | - | - | - | unavailable | offline mode (HYDROSCAN_OFFLINE=1) |
| Satellite rainfall (GPM IMERG) | not requested | unavailable | - | - | - | unavailable | not requested |
| Soil moisture (SMAP) | not requested | unavailable | - | - | - | unavailable | not requested |
| Soil texture, organic carbon, pH | ISRIC SoilGrids v2.0 | unavailable | - | - | - | unavailable | WCS failed: WCS sand 0-5cm: offline mode (HYDROSCAN_OFFLINE=1) / REST failed: REST: offline mode (HYDROSCAN_OFFLINE=1) |
| Crop attributes used in scoring (water demand, heat sensitivity, legume benefit, soil cover) | rotation/crop_database.json (ordinal ratings) | ok | static | - | - | analyst assumption (unverified) | Ordinal ratings, not measured values. Egyptian literature found is listed in egypt_references.json but has not yet replaced these ratings. |
| Rotation scores and ranking | rotation/scoring.py + scoring_rules.json | ok | computed now | - | - | derived by this tool | Prototype weights; scores are relative, not probabilities, yields or incomes. Income is not scored without farmer-supplied numbers. |
| What-if scenarios | scenarios.py | ok | computed now | - | - | hypothetical scenario | Rule-based sensitivity (+2 C, -20 % rain); not a forecast and not driven by local climate model output. |

## 2. What the data say about this field

- **Vegetation density (HydroScan model):** dominant class `sparse_veg`, class fractions {'bare_soil': 0.3313, 'dense_veg': 0.1705, 'sparse_veg': 0.4982}, mean NDVI 0.2746 (±0.1473). This is a vegetation-density result. **Irrigation and crop type are NOT classified** (no validated model, no labels).
- **NDVI series:** 10 valid months, range [0.32, 0.3769], trend: insufficient_history.
- **Bare-soil calendar (NDVI < 0.25, an adjustable assumption):** 1:vegetated, 2:vegetated, 3:vegetated, 4:vegetated, 5:vegetated, 6:vegetated, 7:vegetated, 8:vegetated, 9:vegetated, 10:vegetated, 11:unknown, 12:unknown
- **Climate:** UNAVAILABLE (offline mode (HYDROSCAN_OFFLINE=1)).
- **Soil (SoilGrids estimate, 0-30 cm):** UNAVAILABLE (WCS failed: WCS sand 0-5cm: offline mode (HYDROSCAN_OFFLINE=1) | REST failed: REST: offline mode (HYDROSCAN_OFFLINE=1))
- **GPM IMERG:** UNAVAILABLE (not requested)
- **SMAP:** UNAVAILABLE (not requested)

## 3. Three rotations and the reasoning

### #1 Legume: wheat -> faba bean -> maize — overall 55.8/100 (provisional: Criteria not scored: income)
- **water**: 43.3 (weight used 0.5333); evidence: assumption (ordinal water-demand ratings, no measured requirements); basis: Wheat: medium relative demand; Faba (fava) bean: medium relative demand; Maize: high relative demand
- **soil**: 80.0 (weight used 0.2667); evidence: mixed: N-fixation and rotation diversity are well established; point values are prototype rules; basis: base 40; +25 legume N-fixation (Faba (fava) bean); +10 botanical diversity
- **income**: not scored (weight used 0.0); evidence: no yield/price/cost data supplied; basis: none
- **resilience**: 56.7 (weight used 0.2); evidence: assumption (ordinal heat-sensitivity ratings); basis: Wheat: medium heat sensitivity; Faba (fava) bean: high heat sensitivity; Maize: medium heat sensitivity
- Benefits: Includes a nitrogen-fixing legume (Faba (fava) bean), which can lower the nitrogen fertiliser need of the following crop (amount not quantified).; Breaks a cereal-after-cereal sequence, which helps limit cereal-specific pests and diseases.; Crop diversity spreads risk across seasons.
- Risks: Faba (fava) bean is heat-sensitive at flowering.; Maize has high relative water demand and the farmer reports limited water.
- Information gaps: No evapotranspiration or crop-water-requirement values are stored, so real irrigation need is not calculated.; Soil data unavailable: local soil limits (texture, organic carbon, pH) are not reflected in the soil score.; No yield, price and cost inputs: economic potential is NOT scored (no verified Egyptian figures are stored).; Climate inputs are not observations (illustrative fallback or unavailable); planting-window/climate conflicts cannot be checked.; Crop temperature thresholds are not in the database, so planting-window conflicts are not scored.

  - *Wheat (Egyptian literature, unverified, abstract-level)*: planting 15-30 November (northern Nile Delta) [R02]; water: 4230.0 to 6086.51 m3/feddan/season (CROPWAT-8 modelled requirement; lowest for sowing in the first week of November 2022, highest for the first week of January 2023) [R01] | 1606.19 to 2123.93 m3/feddan applied (applied irrigation, three irrigation regimes at the 5 December sowing date (a different, experimental regime; cultivar Shandaweel 1, Upper Egypt)) [R03]
  - *Faba (fava) bean (Egyptian literature, unverified, abstract-level)*: planting about mid-October to mid-November; yield fell when sowing was delayed beyond 1 November in the North Delta [R06, R07, R08]; water: 609.41 (rainfed after planting irrigation) to 1601.46 m3/feddan applied (4 irrigations excl. planting) (seasonal applied water incl. rainfall, Sakha) [R04] | 790 to 1982 m3/feddan applied (four irrigation treatments, Sakha; each extra cm of applied water added ~10.5 kg seed/feddan) [R05]
  - *Maize (Egyptian literature, unverified, abstract-level)*: planting May (1-15 May gave the best results; later sowing reduced yield) [R13, R14]; water: 1834 / 2139 / 2445 m3/feddan applied at 60 / 70 / 80 % of ETc (SC10, El-Minia (Middle Egypt)) [R16] | 6171 to 7321 m3/ha applied (= about 2592 to 3075 m3/feddan) (deficit-irrigation regimes, SC10) [R15]

### #2 Fodder: wheat -> berseem -> maize — overall 53.0/100 (provisional: Criteria not scored: income)
- **water**: 31.7 (weight used 0.5333); evidence: assumption (ordinal water-demand ratings, no measured requirements); basis: Wheat: medium relative demand; Berseem clover: high relative demand; Maize: high relative demand
- **soil**: 81.7 (weight used 0.2667); evidence: mixed: N-fixation and rotation diversity are well established; point values are prototype rules; basis: base 40; +25 legume N-fixation (Berseem clover); +10 botanical diversity
- **income**: not scored (weight used 0.0); evidence: no yield/price/cost data supplied; basis: none
- **resilience**: 71.7 (weight used 0.2); evidence: assumption (ordinal heat-sensitivity ratings); basis: Wheat: medium heat sensitivity; Berseem clover: low heat sensitivity; Maize: medium heat sensitivity
- Benefits: Includes a nitrogen-fixing legume (Berseem clover), which can lower the nitrogen fertiliser need of the following crop (amount not quantified).; Breaks a cereal-after-cereal sequence, which helps limit cereal-specific pests and diseases.; Crop diversity spreads risk across seasons.
- Risks: Berseem clover has high relative water demand and the farmer reports limited water.; Maize has high relative water demand and the farmer reports limited water.
- Information gaps: No evapotranspiration or crop-water-requirement values are stored, so real irrigation need is not calculated.; Soil data unavailable: local soil limits (texture, organic carbon, pH) are not reflected in the soil score.; No yield, price and cost inputs: economic potential is NOT scored (no verified Egyptian figures are stored).; Climate inputs are not observations (illustrative fallback or unavailable); planting-window/climate conflicts cannot be checked.; Crop temperature thresholds are not in the database, so planting-window conflicts are not scored.

  - *Wheat (Egyptian literature, unverified, abstract-level)*: planting 15-30 November (northern Nile Delta) [R02]; water: 4230.0 to 6086.51 m3/feddan/season (CROPWAT-8 modelled requirement; lowest for sowing in the first week of November 2022, highest for the first week of January 2023) [R01] | 1606.19 to 2123.93 m3/feddan applied (applied irrigation, three irrigation regimes at the 5 December sowing date (a different, experimental regime; cultivar Shandaweel 1, Upper Egypt)) [R03]
  - *Berseem clover (Egyptian literature, unverified, abstract-level)*: planting 1 to mid-October best; mid-September to end of October acceptable [R09, R10]; water: 2215.05 to 2615.01 m3/feddan applied (incl. 618.87 m3 rainfall)  (clay soils, North Delta, cut-off irrigation trial) [R12] | about 2766 to 3014 m3/feddan/season applied (two sowing methods, Kafr El-Sheikh (3013.94 = average of the wet-sowing method)) [R11]
  - *Maize (Egyptian literature, unverified, abstract-level)*: planting May (1-15 May gave the best results; later sowing reduced yield) [R13, R14]; water: 1834 / 2139 / 2445 m3/feddan applied at 60 / 70 / 80 % of ETc (SC10, El-Minia (Middle Egypt)) [R16] | 6171 to 7321 m3/ha applied (= about 2592 to 3075 m3/feddan) (deficit-irrigation regimes, SC10) [R15]

### #3 Baseline: wheat -> maize — overall 44.0/100 (provisional: Criteria not scored: income)
- **water**: 37.5 (weight used 0.5333); evidence: assumption (ordinal water-demand ratings, no measured requirements); basis: Wheat: medium relative demand; Maize: high relative demand
- **soil**: 45.0 (weight used 0.2667); evidence: mixed: N-fixation and rotation diversity are well established; point values are prototype rules; basis: base 40
- **income**: not scored (weight used 0.0); evidence: no yield/price/cost data supplied; basis: none
- **resilience**: 60.0 (weight used 0.2); evidence: assumption (ordinal heat-sensitivity ratings); basis: Wheat: medium heat sensitivity; Maize: medium heat sensitivity
- Benefits: none identified
- Risks: Only cereals in sequence (same botanical family): no break crop, no nitrogen fixation.; Maize has high relative water demand and the farmer reports limited water.
- Information gaps: No evapotranspiration or crop-water-requirement values are stored, so real irrigation need is not calculated.; Soil data unavailable: local soil limits (texture, organic carbon, pH) are not reflected in the soil score.; No yield, price and cost inputs: economic potential is NOT scored (no verified Egyptian figures are stored).; Climate inputs are not observations (illustrative fallback or unavailable); planting-window/climate conflicts cannot be checked.; Crop temperature thresholds are not in the database, so planting-window conflicts are not scored.

  - *Wheat (Egyptian literature, unverified, abstract-level)*: planting 15-30 November (northern Nile Delta) [R02]; water: 4230.0 to 6086.51 m3/feddan/season (CROPWAT-8 modelled requirement; lowest for sowing in the first week of November 2022, highest for the first week of January 2023) [R01] | 1606.19 to 2123.93 m3/feddan applied (applied irrigation, three irrigation regimes at the 5 December sowing date (a different, experimental regime; cultivar Shandaweel 1, Upper Egypt)) [R03]
  - *Maize (Egyptian literature, unverified, abstract-level)*: planting May (1-15 May gave the best results; later sowing reduced yield) [R13, R14]; water: 1834 / 2139 / 2445 m3/feddan applied at 60 / 70 / 80 % of ETc (SC10, El-Minia (Middle Egypt)) [R16] | 6171 to 7321 m3/ha applied (= about 2592 to 3075 m3/feddan) (deficit-irrigation regimes, SC10) [R15]

## 4. Data support (descriptive, not a probability)
**Limited data support**. Levels describe how well the inputs support the comparison. They are not the probability that a recommendation is correct.

- model_prediction_confidence: Limited data support: HydroScan's classifier has no validated accuracy and mostly reproduces NDVI thresholds.
- satellite_observation_quality: Limited data support: 10 valid monthly NDVI values; 10 m pixels, averaged over a ~5 km box.
- environmental_completeness: Limited data support: climate observed: False; soil estimate: False; GPM: False; SMAP: False
- agricultural_evidence_quality: Limited data support: Crop attributes are qualitative general knowledge/assumptions, not yet checked against Egyptian sources.

## 5. Missing data

- irrigation_classification (no trained/validated irrigation model)
- crop_classification (no crop model or crop labels)
- climate (NASA POWER): offline mode (HYDROSCAN_OFFLINE=1)
- soil (SoilGrids): WCS failed: WCS sand 0-5cm: offline mode (HYDROSCAN_OFFLINE=1) | REST failed: REST: offline mode (HYDROSCAN_OFFLINE=1)
- GPM IMERG rainfall: needs a Google Earth Engine project
- SMAP soil moisture: needs a Google Earth Engine project

## 6. Limitations and warnings

- HydroScan's model separates bare_soil / sparse_veg / dense_veg. It was trained on NDVI-threshold pseudo-labels (audit: 99% agreement with the plain NDVI rule), so it carries no independent information beyond vegetation density and has no validated accuracy.
- NDVI history covers <24 valid months: no multi-year trend or seasonality can be established.
- NDVI comes from the project's 2026 area-mean file (not field-level, one year); multi-year field-level NDVI needs Google Earth Engine.

## 7. Needs expert validation

- All crop attributes and ordinal ratings
- Soil suitability (lab soil test)
- Economic figures
- Planting calendar for the governorate

## 8. Rotation evidence in Egyptian literature
Only that SC10 maize was grown after Egyptian clover (R15) and after faba bean (R16) in these experiments. This shows the sequences are practised; it is NOT evidence of the size of any soil, nitrogen, water or income benefit.

**Gap:** No Egyptian source quantifying benefits of wheat -> faba bean -> maize or wheat -> berseem -> maize was found in this pass. Wheat, faba bean and berseem are ALL winter crops (sown Oct-Nov), so the three-stage sequences cannot fit one calendar year: the 2-year cycle length used in the project is an analyst assumption that an agronomist must define.

## 9. Reference list

- **R01** Ismail, M. et al. (2024). Wheat water requirements by planting date using CROPWAT-8. Menoufia J. Soil Sci. (ARC authors). (peer-reviewed, modelled (CROPWAT-8)) https://mjss.journals.ekb.eg/article_390074_6fb2c284fdb7a6f6511aef78b2db49de.pdf
- **R02** Taha et al. (2017), as CITED inside R01 (secondary citation; original not read). (secondary citation) https://mjss.journals.ekb.eg/article_390074_6fb2c284fdb7a6f6511aef78b2db49de.pdf
- **R03** Wheat sowing date x irrigation regimes, Shandaweel Agricultural Research Station, ARC, seasons 2012/13-2014/15. Assiut Univ./ARC journal (Egypt). (peer-reviewed field experiment) https://ajas.journals.ekb.eg/article_3869_d2760e5e2c9e3d8ee01907190314d2be.pdf
- **R04** Kassab, M.M. (2010). Faba bean productivity as affected by number of irrigations in Nile Delta. J. Soil Sci. Agric. Eng., Mansoura Univ. 1(7): 643-651. Sakha station, 2008/09-2009/10. (peer-reviewed field experiment) https://journals.ekb.eg/article_75116_2a2992fcfb8ada56e562a070019ea873.pdf
- **R05** El-Bably, A.Z. & Abo-Mostafa, R.A.I. (2008). Effect of irrigation on productivity and water use efficiency of faba bean cultivars in North Delta. J. Agric. Sci. Mansoura Univ. 33(1): 925-939. Sakha, 2005/06-2006/07. (peer-reviewed field experiment) https://journals.ekb.eg/article_166865_d023c04026a78e7fce0c15d1d0978b88.pdf
- **R06** Fayed, T.B., Abdrabbo, M.A.A., Hamada, M.M.A., Hashem, F.A. & Hegab, A.S.A. (2018). Irrigation requirements of faba bean under two climatic locations in Egypt. Egypt. J. Agric. Res. 96(2). El-Bosaily (Behaira) & Dokki (Giza), drip irrigation. (peer-reviewed field experiment (CLAC, ARC)) https://ejar.journals.ekb.eg/article_135777_bec3388b226be0bae0be5819ded97e62.pdf
- **R07** Hegab, A.S.A. & Fayed, M.T.B. Productivity and irrigation requirements of faba bean in North Delta in relation to planting dates. Annals of Agric. Sci. (Ain Shams). El-Bosaily, 2011/12-2012/13. (peer-reviewed field experiment (abstract read)) https://manuscript.isc.ac/Inventory/10/2542988.htm
- **R08** Mohamed, M.Kh.A. & El-Sayed, A.F. Effect of sowing date on six faba bean genotypes and Orobanche crenata (broomrape). Food Legumes Res. Dept., FCRI, ARC. Sakha, 2015/16-2016/17. (peer-reviewed field experiment) https://alexja.journals.ekb.eg/article_28568_787bd2447fd7a68c0d58b348dd6c8f77.pdf
- **R09** Sharief, A.E. Egyptian clover (berseem), Chapter 4. Faculty of Agriculture, Mansoura Univ. (lecture/teaching material hosted on Scribd). (teaching material (NOT peer-reviewed; weakest evidence)) https://www.scribd.com/document/1012321939/02
- **R10** Ramadan et al. (1994), as CITED inside Bakheit, Teama, Mohamed & Fathy, 'Forage yield stability of some Egyptian clover genotypes under different sowing dates' (secondary citation). (secondary citation) https://journals.ekb.eg/article_4502_08ead2a5be02605d063292bb4047306c.pdf
- **R11** Mady, A.A. & Meleha, M.I. Increasing water use efficiency of berseem as affected by methods of sowing and nitrogen. Egypt. J. Agron. El-Karada station, Kafr El-Sheikh, 2003/04-2004/05. (peer-reviewed field experiment (abstract read)) https://manuscript.isc.ac/Inventory/10/2620962.htm
- **R12** Kassab, M.M., Darwesh, R.Kh. & Ibrahim, M.A.M. (2012). Response of Egyptian clover to cut-off irrigation on clay soils at North Nile Delta. Alexandria Sci. Exch. J. 33(3). (peer-reviewed field experiment) https://asejaiqjsae.journals.ekb.eg/article_3155_2b3150036a4506bc9a03c6040dda7cff.pdf
- **R13** Maize sowing dates (15 May, 15 Jun, 15 Jul) x hybrids SC131, SC168, TWC324, Sakha Agricultural Research Farm, 2023-2024. Egyptian J. Botany (ejbo). (peer-reviewed field experiment) https://ejbo.journals.ekb.eg/article_431323_eb18351b1c7c0066f5edbfc44c76a117.pdf
- **R14** Hegab, A., Fayed, M., Hamada, M. & Abdrabbo, M. (2019). Growth parameters, irrigation requirements and productivity of maize in relation to sowing dates under North-Delta of Egypt conditions. Arab Univ. J. Agric. Sci. 27(1). El-Bosaily, SC10, drip, 2015-2016. (peer-reviewed field experiment (abstract read)) https://doaj.org/article/ab259e90b2df41a7b69ef3b59ee766c3
- **R15** Gharib, H.S. et al. (2016). Deficit irrigation of maize SC10. Egypt. J. Agron. 38(3). Preceding crop: Egyptian clover. (peer-reviewed field experiment) https://journals.ekb.eg/article_1297_c956e32ac96917d33a09a177fa5514fb.pdf
- **R16** SC10 maize at 60/70/80% of ETc under El-Minia conditions, 2019-2020. Bull. Natl. Res. Cent. (Springer). Preceding crop: faba bean. (peer-reviewed field experiment) https://link.springer.com/10.1186/s42269-022-00934-6