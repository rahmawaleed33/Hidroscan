"""
app.py -- HydroScan Farm Monitor (draw a box -> real irrigated-land map + details).

Run with:   python -m streamlit run app.py
Install:    pip install streamlit streamlit-folium folium rasterio scipy scikit-learn shapely earthengine-api

Flow
  1. Draw a rectangle on the map (the rectangle tool, top-left). A new box replaces the old one.
  2. The coordinates are captured and copied into the sidebar automatically.
  3. With an Earth Engine project ID entered, Sentinel-2 is fetched for the box over a
     period (default: 1 year) and irrigated land is detected from each pixel's PEAK greenness:
     in dry regions anything that gets green is being watered. Water is excluded and small
     patches are removed. Polygons are drawn on the map; an NDVI layer can be switched on.
  4. Tabs under the map give the details: summary, patch table, NDVI view, method & data.
  5. Optional: "Run satellite analysis" shows VV / VH / NDVI (+ classification if model.joblib exists).

Without a project ID the app shows clearly-labelled DEMO polygons.
"""

import datetime as dt
import math
import os
import tempfile
import zlib

import folium
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
import streamlit as st
from branca.element import MacroElement, Template
from folium.plugins import Draw
from rasterio.features import shapes
from rasterio.transform import from_bounds
from scipy import ndimage
from streamlit_folium import st_folium

from model_training import NODATA, make_features

try:  # optional: smooth polygons. Without it the app falls back to a raster overlay.
    from shapely.geometry import mapping, shape
    HAVE_SHAPELY = True
except ImportError:  # pragma: no cover
    HAVE_SHAPELY = False

ACRE_M2 = 4046.8564224
DEFAULT_BBOX = (30.40, 30.50, 30.45, 30.55)  # west, south, east, north
MAX_POLYGONS = 1500
BASIS_PEAK = "Peak greenness over the period (best for irrigation)"
BASIS_MEDIAN = "Median (a typical snapshot)"

st.set_page_config(page_title="Farm Monitor", page_icon="💧", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.2rem; max-width: 1400px;}
      div[data-testid="stMetric"] {background:#fff; border:1px solid #e3ebf7; border-radius:14px;
             padding:.8rem 1rem; box-shadow:0 4px 12px rgba(20,60,140,.08);}
      div[data-testid="stMetricValue"] {color:#0b3d91;}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("💧 Farm Monitor")

# --------------------------------------------------------------------------- #
# State: the sidebar numbers are the single source of truth for the box.
# --------------------------------------------------------------------------- #
for k, v in zip(("west", "south", "east", "north"), DEFAULT_BBOX):
    st.session_state.setdefault(k, v)
st.session_state.setdefault("has_area", False)
st.session_state.setdefault("drawn_bbox", None)

pending = st.session_state.pop("pending_bbox", None)
if pending:
    st.session_state.update(west=pending[0], south=pending[1], east=pending[2], north=pending[3])

with st.sidebar:
    st.header("📍 Area")
    st.caption("Draw a rectangle on the map, or type coordinates:")
    c1, c2 = st.columns(2)
    c1.number_input("West", key="west", format="%.5f", step=0.001)
    c2.number_input("East", key="east", format="%.5f", step=0.001)
    c1.number_input("South", key="south", format="%.5f", step=0.001)
    c2.number_input("North", key="north", format="%.5f", step=0.001)
    b1, b2 = st.columns(2)
    if b1.button("Show overlay"):
        st.session_state["has_area"] = True
    if b2.button("Clear"):
        st.session_state["has_area"] = False
        st.session_state["drawn_bbox"] = None

    st.divider()
    st.header("🌱 Irrigated-land detection")
    project = st.text_input("Earth Engine project ID", help="Needed for real detection. "
                            "Leave empty to see demo polygons.")
    start = st.date_input("Period starts", value=dt.date.today() - dt.timedelta(days=365))
    days = st.slider("Period length (days)", 30, 730, 365, 5,
                     help="Longer = catches crops that are only green in some seasons.")
    basis = st.radio("Detection based on", [BASIS_PEAK, BASIS_MEDIAN],
                     help="Peak greenness finds every field that gets green at any time in the period. "
                          "Median only finds fields that are green most of the time.")
    ndvi_thr = st.slider("Green-vegetation threshold (NDVI)", 0.15, 0.70, 0.30, 0.01,
                         help="Higher = only dense, healthy crops. Lower = includes sparse vegetation.")
    excl_water = st.checkbox("Exclude water", value=True)
    min_acres = st.slider("Ignore patches smaller than (acres)", 0.2, 20.0, 1.0, 0.2)

    st.divider()
    st.header("🛰️ Satellite analysis")
    sat_start = st.date_input("Radar/NDVI window starts (30 days)", value=dt.date.today() - dt.timedelta(days=60))
    model_path = st.text_input("Model file (optional)", "model.joblib")
    run = st.button("Run satellite analysis", type="primary")

bbox = tuple(round(float(st.session_state[k]), 6) for k in ("west", "south", "east", "north"))


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #
def metres_per_degree(south, north):
    return 111_320 * math.cos(math.radians((south + north) / 2)), 110_540


def bbox_from_drawings(drawings):
    """Last drawn rectangle from st_folium's all_drawings -> (W, S, E, N) or None."""
    for d in reversed(drawings or []):
        geom = (d or {}).get("geometry") or {}
        if geom.get("type") == "Polygon":
            ring = geom["coordinates"][0]
            lons, lats = [p[0] for p in ring], [p[1] for p in ring]
            return (round(min(lons), 6), round(min(lats), 6), round(max(lons), 6), round(max(lats), 6))
    return None


# --------------------------------------------------------------------------- #
# REAL detection: Sentinel-2 NDVI/NDWI for the box (Earth Engine) -> irrigated polygons
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False, ttl=6 * 3600)
def fetch_indices(project, bbox, start_iso, days, peak):
    """Download a cloud-masked Sentinel-2 NDVI (+ NDWI) composite for bbox."""
    import gee_pipeline as gp

    ee = gp.ee
    ee.Initialize(project=project)
    region = gp.make_region(list(bbox))
    s, e = gp.date_range(start_iso, days)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(s, e)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 40)))
    n = col.size().getInfo()
    if n == 0:
        raise RuntimeError("No cloud-free Sentinel-2 scenes in this period. Try a longer period or other dates.")

    def indices(img):
        r = img.select(["B3", "B4", "B8"]).divide(10000)
        return (r.normalizedDifference(["B8", "B4"]).rename("NDVI")
                .addBands(r.normalizedDifference(["B3", "B8"]).rename("NDWI")))

    per_image = col.map(gp.mask_s2_clouds).map(indices)
    if peak:   # 90th-percentile greenness: robust to clouds, finds crops green at ANY time in the period
        ndvi = per_image.select("NDVI").reduce(ee.Reducer.percentile([90])).rename("NDVI")
    else:
        ndvi = per_image.select("NDVI").median()
    ndwi = per_image.select("NDWI").median()
    out = ndvi.addBands(ndwi).clip(region).toFloat().unmask(NODATA)

    mx, my = metres_per_degree(bbox[1], bbox[3])
    side_m = max((bbox[2] - bbox[0]) * mx, (bbox[3] - bbox[1]) * my)
    scale = max(10, math.ceil(side_m / 2000))  # keeps the download under Earth Engine's size limit

    path = os.path.join(tempfile.gettempdir(), "hydroscan_box.tif")
    gp.download_geotiff(out, region, list(bbox), path, scale=scale, n_bands=2)
    with rasterio.open(path) as ds:
        arr = ds.read().astype("float32")
        bounds = tuple(ds.bounds)
    arr[arr == NODATA] = np.nan
    return {"ndvi": arr[0], "ndwi": arr[1], "bounds": bounds, "scale": scale, "scenes": int(n),
            "period": (s, e), "peak": bool(peak)}


def classify(ind, thr, excl_water, min_acres):
    """NDVI/NDWI arrays -> cleaned irrigated mask, polygons (GeoJSON), patch table and stats."""
    ndvi, ndwi = ind["ndvi"], ind["ndwi"]
    H, W = ndvi.shape
    west, south, east, north = ind["bounds"]
    mx, my = metres_per_degree(south, north)
    px_area = ((east - west) / W * mx) * ((north - south) / H * my)

    valid = np.isfinite(ndvi)
    mask = valid & (np.nan_to_num(ndvi, nan=-1) >= thr)
    if excl_water:
        mask &= ~(np.nan_to_num(ndwi, nan=-1) > 0.1)
    mask = ndimage.binary_closing(mask, np.ones((3, 3), bool))   # fill pinholes
    mask = ndimage.binary_opening(mask, np.ones((3, 3), bool))   # remove speckle
    lab, n = ndimage.label(mask)
    if n:
        sizes = ndimage.sum(mask, lab, np.arange(1, n + 1))
        keep = np.where(sizes * px_area / ACRE_M2 >= min_acres)[0] + 1
        mask = np.isin(lab, keep)
        lab, n = ndimage.label(mask)

    # patch table (works with or without shapely)
    patches = []
    if n:
        ids = np.arange(1, n + 1)
        cnt = ndimage.sum(mask, lab, ids)
        cy, cx = zip(*ndimage.center_of_mass(mask, lab, ids))
        for i in np.argsort(cnt)[::-1][:MAX_POLYGONS]:
            patches.append({"patch": len(patches) + 1, "acres": round(float(cnt[i] * px_area / ACRE_M2), 1),
                            "mean NDVI": round(float(np.nanmean(ndvi[lab == ids[i]])), 2),
                            "lat": round(north - (cy[i] + 0.5) / H * (north - south), 5),
                            "lon": round(west + (cx[i] + 0.5) / W * (east - west), 5)})

    features = []
    if HAVE_SHAPELY and mask.any():
        tol = 0.6 * (east - west) / W
        polys = []
        for geom, val in shapes(mask.astype("uint8"), mask=mask, transform=from_bounds(west, south, east, north, W, H)):
            if val != 1:
                continue
            g = shape(geom).simplify(tol, preserve_topology=True)
            if not g.is_empty:
                polys.append((g.area * mx * my / ACRE_M2, g))
        polys.sort(key=lambda t: t[0], reverse=True)
        for i, (acres, g) in enumerate(polys[:MAX_POLYGONS]):
            features.append({"type": "Feature", "properties": {"field": i + 1, "acres": round(acres, 1)},
                             "geometry": mapping(g)})

    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[mask] = (30, 110, 255, 150)
    nd_rgba = (matplotlib.colormaps["RdYlGn"](np.clip((np.nan_to_num(ndvi, nan=-0.1) + 0.1) / 1.0, 0, 1)) * 255).astype(np.uint8)
    nd_rgba[..., 3] = np.where(valid, 170, 0)
    hist, edges = np.histogram(ndvi[valid], bins=np.round(np.arange(-0.2, 1.01, 0.05), 2)) if valid.any() else ([], [])
    return {
        "geojson": {"type": "FeatureCollection", "features": features} if features else None,
        "rgba": rgba, "ndvi_rgba": nd_rgba, "bounds": ind["bounds"], "ndvi": ndvi, "mask": mask,
        "hist": (hist, edges), "patches": patches,
        "irrigated_acres": float(mask.sum() * px_area / ACRE_M2),
        "total_acres": float(valid.sum() * px_area / ACRE_M2),
        "n_fields": int(n),
        "ndvi_in": float(np.nanmean(ndvi[mask])) if mask.any() else float("nan"),
        "ndvi_all": float(np.nanmean(ndvi)) if valid.any() else float("nan"),
    }


# --------------------------------------------------------------------------- #
# DEMO fallback (random polygons) when no Earth Engine project is entered
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def demo_area(bbox):
    west, south, east, north = bbox
    rng = np.random.default_rng(zlib.crc32(repr(bbox).encode()))
    w, h = east - west, north - south
    mx, my = metres_per_degree(south, north)
    feats, irr = [], 0.0
    for i in range(int(rng.integers(5, 10))):
        cx, cy = west + w * rng.uniform(0.12, 0.88), south + h * rng.uniform(0.12, 0.88)
        r = min(w, h) * rng.uniform(0.07, 0.18)
        ang = np.sort(rng.uniform(0, 2 * np.pi, int(rng.integers(12, 20))))
        rad = r * rng.uniform(0.65, 1.0, len(ang))
        xs, ys = np.clip(cx + 1.3 * rad * np.cos(ang), west, east), np.clip(cy + rad * np.sin(ang), south, north)
        X, Y = (xs - west) * mx, (ys - south) * my
        a = 0.5 * abs(np.sum(X * np.roll(Y, -1) - np.roll(X, -1) * Y))
        irr += a
        ring = [[float(x), float(y)] for x, y in zip(xs, ys)]
        feats.append({"type": "Feature", "properties": {"field": i + 1, "acres": round(a / ACRE_M2, 1)},
                      "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]}})
    return {"geojson": {"type": "FeatureCollection", "features": feats}, "rgba": None, "ndvi_rgba": None,
            "bounds": bbox, "irrigated_acres": irr / ACRE_M2, "total_acres": w * mx * h * my / ACRE_M2,
            "n_fields": len(feats), "patches": [], "ndvi": None, "mask": None, "hist": ([], []),
            "ndvi_in": float("nan"), "ndvi_all": float("nan")}


# --------------------------------------------------------------------------- #
# Map: satellite by default, ONE rectangle at a time, no pop-up alerts.
# The BASE map never changes between runs, so the user's drawing and view are kept.
# --------------------------------------------------------------------------- #
class SingleRectangle(MacroElement):
    """Keeps only the newest drawn rectangle and removes the default click-to-alert."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        {{ this._parent.get_name() }}.on('draw:created', function(e) {
            var group = drawnItems_{{ this.draw_name }};
            e.layer.off('click');
            group.eachLayer(function(l) { if (l !== e.layer) { group.removeLayer(l); } });
        });
        {% endmacro %}
        """
    )

    def __init__(self, draw):
        super().__init__()
        self._name = "SingleRectangle"
        self.draw_name = draw.get_name()


def base_map():
    cx, cy = (DEFAULT_BBOX[0] + DEFAULT_BBOX[2]) / 2, (DEFAULT_BBOX[1] + DEFAULT_BBOX[3]) / 2
    m = folium.Map(location=[cy, cx], zoom_start=12, tiles=None, control_scale=True)
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satellite photo (older, for reference)", max_zoom=19).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street map", show=False).add_to(m)
    draw = Draw(
        export=False, position="topleft",
        draw_options={
            "rectangle": {"shapeOptions": {"color": "#19c3e6", "weight": 2, "fillOpacity": 0.05}},
            "polyline": False, "polygon": False, "circle": False, "marker": False, "circlemarker": False,
        },
        edit_options={"edit": True, "remove": True},
    )
    draw.add_to(m)
    SingleRectangle(draw).add_to(m)
    return m


# --------------------------------------------------------------------------- #
# Compute the result for the current box (cached per settings)
# --------------------------------------------------------------------------- #
result = None
if st.session_state["has_area"]:
    peak = basis == BASIS_PEAK
    sig = (bbox, project.strip(), start.isoformat(), int(days), peak, round(ndvi_thr, 3), excl_water,
           round(min_acres, 2))
    if st.session_state.get("res_sig") == sig:
        result = st.session_state.get("res")
    else:
        try:
            if project.strip():
                with st.spinner("Fetching Sentinel-2 for your box from Google Earth Engine (can take ~1 min)..."):
                    ind = fetch_indices(project.strip(), bbox, start.isoformat(), int(days), peak)
                with st.spinner("Detecting irrigated land..."):
                    result = classify(ind, ndvi_thr, excl_water, min_acres)
                result.update(mode="real", scale=ind["scale"], scenes=ind["scenes"], period=ind["period"], peak=peak)
            else:
                result = dict(demo_area(bbox), mode="demo")
        except Exception as exc:
            st.error(f"Could not process this area: {exc}")
            result = None
        st.session_state["res_sig"], st.session_state["res"] = sig, result

fg = folium.FeatureGroup(name="Irrigated land (detected)")
fg_ndvi = folium.FeatureGroup(name="NDVI greenness (what the satellite saw)", show=False)
if result:
    west, south, east, north = bbox
    folium.Rectangle([[south, west], [north, east]], color="#19c3e6", weight=2, dash_array="6",
                     fill=False).add_to(fg)
    if result["geojson"]:
        folium.GeoJson(
            result["geojson"],
            style_function=lambda _f: {"color": "#ffffff", "weight": 1, "fillColor": "#1e6eff", "fillOpacity": 0.55},
            highlight_function=lambda _f: {"weight": 2.5, "fillOpacity": 0.8},
            tooltip=folium.GeoJsonTooltip(fields=["acres"], aliases=["Irrigated patch (acres)"]),
        ).add_to(fg)
    elif result["rgba"] is not None:
        w_, s_, e_, n_ = result["bounds"]
        folium.raster_layers.ImageOverlay(result["rgba"], bounds=[[s_, w_], [n_, e_]], opacity=1).add_to(fg)
    if result.get("ndvi_rgba") is not None:
        w_, s_, e_, n_ = result["bounds"]
        folium.raster_layers.ImageOverlay(result["ndvi_rgba"], bounds=[[s_, w_], [n_, e_]], opacity=1).add_to(fg_ndvi)

if st.session_state["has_area"]:
    st.caption("Drag the box's handles to adjust it, or draw a new one (it replaces the old one). Use the layer button "
               "(top-right of the map) to switch layers, including **NDVI greenness**. The satellite photo is an "
               "older reference image, so compare detection against the NDVI layer, not only the photo.")
else:
    st.info("👆 Click the **▭ rectangle tool** at the top-left of the map and drag over your farm.")

out = st_folium(base_map(), feature_group_to_add=[fg, fg_ndvi], layer_control=folium.LayerControl(collapsed=True),
                height=620, use_container_width=True, returned_objects=["all_drawings"], key="draw_map")

# --- capture the drawn box ---------------------------------------------------
drawn = bbox_from_drawings((out or {}).get("all_drawings"))
if drawn and drawn != st.session_state["drawn_bbox"]:
    st.session_state["drawn_bbox"] = drawn
    st.session_state["pending_bbox"] = drawn
    st.session_state["has_area"] = True
    st.rerun()
if drawn is None and st.session_state["drawn_bbox"] is not None and out and out.get("all_drawings") == []:
    st.session_state["drawn_bbox"] = None  # user deleted the rectangle
    st.session_state["has_area"] = False
    st.rerun()

# --------------------------------------------------------------------------- #
# Details (tabs under the map)
# --------------------------------------------------------------------------- #
if result:
    real = result["mode"] == "real"
    if not real:
        st.warning("DEMO MODE: these blue shapes are random. Enter your Earth Engine project ID in the "
                   "sidebar to detect real irrigated land for this box.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Selected area", f"{result['total_acres']:,.0f} acres")
    m2.metric("💧 Irrigated land", f"{result['irrigated_acres']:,.0f} acres")
    m3.metric("Irrigated share", f"{100 * result['irrigated_acres'] / max(result['total_acres'], 1e-9):.1f} %")
    m4.metric("Patches found", f"{result['n_fields']:,}")

    t_sum, t_patch, t_ndvi, t_method = st.tabs(["📊 Summary", "🌾 Patches", "🌿 NDVI view", "ℹ️ Method & data"])

    with t_sum:
        st.code(f"bbox (W, S, E, N) = {bbox}", language="text")
        if real:
            a, b, c = st.columns(3)
            a.metric("Mean NDVI, irrigated patches", f"{result['ndvi_in']:.2f}")
            b.metric("Mean NDVI, whole box", f"{result['ndvi_all']:.2f}")
            c.metric("Sentinel-2 scenes used", result["scenes"])
            hist, edges = result["hist"]
            if len(hist):
                st.subheader("How green is the box? (NDVI distribution)")
                st.bar_chart(pd.Series(hist, index=[f"{x:.2f}" for x in edges[:-1]]))
                st.caption(f"Pixels to the right of {ndvi_thr:.2f} count as irrigated. Bare desert is about 0.05-0.15; "
                           "healthy crops reach 0.5-0.8.")
            if result["irrigated_acres"] / max(result["total_acres"], 1e-9) < 0.05:
                st.info("Very little was detected. Try: a longer period, 'Peak greenness', or a lower NDVI threshold. "
                        "Turn on the **NDVI greenness** layer on the map to see what the satellite measured.")

    with t_patch:
        if result["patches"]:
            df = pd.DataFrame(result["patches"])
            st.dataframe(df, width="stretch", hide_index=True)
            d1, d2 = st.columns(2)
            d1.download_button("⬇️ Patches (CSV)", df.to_csv(index=False), "irrigated_patches.csv")
            if result["geojson"]:
                import json
                d2.download_button("⬇️ Polygons (GeoJSON)", json.dumps(result["geojson"]), "irrigated_land.geojson")
        else:
            st.info("No patch table in demo mode, or nothing was detected.")

    with t_ndvi:
        if real and result["ndvi"] is not None:
            fig, ax = plt.subplots(figsize=(9, 6))
            im = ax.imshow(result["ndvi"], cmap="RdYlGn", vmin=-0.1, vmax=0.9)
            ax.contour(result["mask"].astype(float), levels=[0.5], colors="#1e6eff", linewidths=1.2)
            ax.set_title("NDVI with detected irrigated land outlined in blue")
            ax.axis("off")
            fig.colorbar(im, ax=ax, shrink=0.8, label="NDVI (greenness)")
            st.pyplot(fig)
        else:
            st.info("NDVI view needs real detection (enter your Earth Engine project ID).")

    with t_method:
        if real:
            s_, e_ = result["period"]
            st.markdown(
                f"""
**Data:** Sentinel-2 surface reflectance, cloud/shadow masked, **{result['scenes']} scenes**,
{s_} to {e_}, at **{result['scale']} m** resolution.

**Rule:** a pixel counts as irrigated when its {'**peak (90th-percentile) NDVI** over the whole period' if result['peak'] else '**median NDVI**'}
is at least **{ndvi_thr:.2f}**{', it is not water (NDWI > 0.1 is removed)' if excl_water else ''}, and it belongs to a patch of at
least **{min_acres:g} acres**.

**Why peak greenness?** In dry regions crops cannot grow without water, so any pixel that becomes green at some point
in the year is being irrigated. A single snapshot misses fields that are fallow or harvested on that date.

**Limits:** outside dry regions, green pixels can also be rain-fed crops, forest or natural vegetation. Very small
fields and fields under cloud all year can be missed. This is an estimate from satellite greenness, not a field survey.
                """
            )
        else:
            st.info("Method details appear for real detection.")


# --------------------------------------------------------------------------- #
# Optional: satellite maps for the same box (VV / VH / NDVI + classification)
# --------------------------------------------------------------------------- #
@st.cache_resource
def load_model(path):
    import joblib
    return joblib.load(path)


def show_map(ax, data, title, cmap, vmin=None, vmax=None):
    ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_title(title)
    ax.axis("off")


if run:
    if not project.strip():
        st.error("Enter your Earth Engine project ID in the sidebar.")
        st.stop()
    import gee_pipeline as gp  # loaded only when needed

    tif = os.path.join(tempfile.gettempdir(), "farm_stack.tif")
    with st.spinner("Fetching data from Google Earth Engine..."):
        try:
            gp.export_stack(project.strip(), list(bbox), sat_start.isoformat(), tif)
        except Exception as exc:
            st.error(f"Earth Engine error: {exc}")
            st.stop()

    with rasterio.open(tif) as ds:
        arr = ds.read().astype("float32")  # (3, H, W) = VV, VH, NDVI
    h, w = arr.shape[1:]
    valid = ~(arr == NODATA).any(axis=0)

    vv = np.where(valid, arr[0], np.nan)
    vh = np.where(valid, arr[1], np.nan)
    ndvi = np.where(valid, arr[2], np.nan)

    pred, codes = None, None
    if os.path.exists(model_path):
        clf = load_model(model_path)
        codes = {c: i for i, c in enumerate(clf.classes_)}
        res = np.full(h * w, np.nan)
        mask = valid.ravel()
        res[mask] = [codes[p] for p in clf.predict(make_features(arr)[mask])]
        pred = res.reshape(h, w)
    else:
        st.info("No model found, showing satellite maps only.")

    n = 4 if pred is not None else 3
    fig, axs = plt.subplots(1, n, figsize=(5 * n, 5))
    show_map(axs[0], vv, "VV (dB)", "gray")
    show_map(axs[1], vh, "VH (dB)", "gray")
    show_map(axs[2], ndvi, "NDVI", "RdYlGn", -0.1, 0.9)
    if pred is not None:
        show_map(axs[3], pred, "Predicted class", "tab10")
    st.pyplot(fig)

    if codes:
        st.caption("Classes: " + ", ".join(f"{i}={c}" for c, i in codes.items()))
    st.metric("Mean NDVI", f"{np.nanmean(ndvi):.2f}")

    with open(tif, "rb") as f:
        st.download_button("Download stack (.tif)", f, "farm_stack.tif")
