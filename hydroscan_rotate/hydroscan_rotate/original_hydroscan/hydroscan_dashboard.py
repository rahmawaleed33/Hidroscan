"""
hydroscan_dashboard.py -- HydroScan AI hackathon dashboard (v2: real data + real model).

Run:  python -m streamlit run hydroscan_dashboard.py

Uses, when present in this folder:
  farm_stack.tif   (or an uploaded .tif)  -> VV / VH / NDVI stack
  model.joblib                             -> trained classifier (model_training.py)
  metrics.json                             -> honest accuracy numbers
  timeseries.csv                           -> monthly NDVI / radar / NASA SMAP trends

If no model is found the app falls back to a SIMULATED mask and says so on screen.
"""

import json
import os

import folium
import numpy as np
import pandas as pd
import rasterio
import streamlit as st
from folium.raster_layers import ImageOverlay
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds
from streamlit_folium import st_folium

from model_training import FEATURE_NAMES, NODATA, make_features

HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda name: os.path.join(HERE, name)  # noqa: E731

PIXEL_M = 10.0                 # 10 m / pixel
ACRE_M2 = 4046.8564224
DEFAULT_BOUNDS = (30.40, 30.50, 30.45, 30.55)
DEFAULT_SHAPE = (500, 500)
MAX_PIXELS = 4_000_000
BLUE = (30, 110, 255)

st.set_page_config(page_title="HydroScan AI", page_icon="💧", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.4rem; max-width: 1300px;}
      .hero {background: linear-gradient(120deg,#0b3d91 0%,#1e6eff 55%,#19c3e6 100%);
             padding: 1.6rem 2rem; border-radius: 18px; color: white;
             box-shadow: 0 10px 30px rgba(30,110,255,.25); margin-bottom: 1.2rem;}
      .hero h1 {margin:0; font-size:2.2rem;} .hero p {margin:.35rem 0 0; opacity:.92; font-size:1.05rem;}
      div[data-testid="stMetric"] {background:#fff; border:1px solid #e3ebf7; border-radius:16px;
             padding:1rem 1.2rem; box-shadow:0 4px 14px rgba(20,60,140,.08);}
      div[data-testid="stMetricValue"] {color:#0b3d91;}
      .stButton > button {background: linear-gradient(90deg,#1e6eff,#19c3e6); color:white; border:0;
             border-radius:12px; padding:.7rem 1.4rem; font-weight:700; font-size:1.05rem; width:100%;
             box-shadow:0 6px 16px rgba(30,110,255,.35);}
      .stButton > button:hover {filter:brightness(1.07); color:white;}
      .team {background:#f2f7ff; border-radius:12px; padding:.8rem 1rem; border:1px solid #dbe7fb; font-size:.92rem;}
    </style>
    <div class="hero"><h1>💧 HydroScan AI</h1>
    <p>Radar + optical + NASA SMAP satellite data, classified by AI, to map irrigated fields.</p></div>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
@st.cache_resource
def load_model(path, mtime):
    import joblib
    return joblib.load(path)


def read_stack(source):
    """source: UploadedFile or path -> (array (bands,H,W), bounds in EPSG:4326)."""
    def _read(ds):
        arr = ds.read().astype("float32")
        b = ds.bounds
        if ds.crs and ds.crs.to_epsg() != 4326:
            b = transform_bounds(ds.crs, "EPSG:4326", *b)
        return arr, tuple(b)

    if isinstance(source, str):
        with rasterio.open(source) as ds:
            return _read(ds)
    with MemoryFile(source.getvalue()) as mem, mem.open() as ds:
        return _read(ds)


def simulate_mask(shape):
    rng = np.random.default_rng()
    h, w = shape
    block = max(4, min(h, w) // 25)
    coarse = rng.random((h // block + 1, w // block + 1)) > 0.55
    return np.kron(coarse, np.ones((block, block), dtype=bool))[:h, :w].astype(np.uint8)


def predict_mask(arr, model, irrigated_classes):
    """Classify every valid pixel; 1 where the predicted class is 'irrigated'."""
    h, w = arr.shape[1:]
    valid = ~(arr == NODATA).any(axis=0) & ~np.isnan(arr).any(axis=0)
    mask = np.zeros(h * w, dtype=np.uint8)
    feats = make_features(arr)
    v = valid.ravel()
    if v.any():
        pred = model.predict(feats[v])
        mask[v] = np.isin(pred, list(irrigated_classes)).astype(np.uint8)
    return mask.reshape(h, w)


def to_overlay(mask):
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[mask == 1] = (*BLUE, 170)
    return rgba


def build_map(bounds, mask=None):
    west, south, east, north = bounds
    m = folium.Map(location=[(south + north) / 2, (west + east) / 2], zoom_start=13,
                   tiles=None, control_scale=True)
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satellite").add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street map").add_to(m)
    folium.Rectangle([[south, west], [north, east]], color="#19c3e6", weight=2,
                     fill=False, tooltip="Area of interest").add_to(m)
    if mask is not None:
        ImageOverlay(to_overlay(mask), bounds=[[south, west], [north, east]],
                     opacity=0.75, name="Irrigated area (AI)", interactive=False).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.fit_bounds([[south, west], [north, east]])
    return m


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
model_file = P("model.joblib")
has_model = os.path.exists(model_file)
local_stack = P("farm_stack.tif")

with st.sidebar:
    st.header("📁 Input data")
    uploaded = st.file_uploader("Upload a GeoTIFF (.tif)", type=["tif", "tiff"])
    st.caption("No upload? farm_stack.tif from this folder is used.")
    st.markdown(
        f"{'✅' if os.path.exists(local_stack) else '⚪'} farm_stack.tif  \n"
        f"{'✅' if has_model else '⚪'} model.joblib  \n"
        f"{'✅' if os.path.exists(P('metrics.json')) else '⚪'} metrics.json  \n"
        f"{'✅' if os.path.exists(P('timeseries.csv')) else '⚪'} timeseries.csv"
    )

    model, irrigated_classes = None, set()
    if has_model:
        model = load_model(model_file, os.path.getmtime(model_file))
        st.subheader("🏷️ Which classes count as irrigated?")
        default = [c for c in model.classes_ if "irrig" in str(c).lower() and "not" not in str(c).lower()]
        irrigated_classes = set(st.multiselect("Irrigated classes", list(model.classes_), default=default
                                               or list(model.classes_)[:1]))

    st.divider()
    st.header("👥 Team")
    st.markdown(
        """<div class="team"><b>Team HydroScan</b><br>🛰️ Remote sensing &amp; GEE<br>
        🤖 AI / ML modelling<br>💻 Dashboard &amp; deployment<br><small>Hackathon 2026</small></div>""",
        unsafe_allow_html=True,
    )

# --------------------------------------------------------------------------- #
# Load input
# --------------------------------------------------------------------------- #
arr, bounds, source = None, DEFAULT_BOUNDS, "Demo area"
try:
    if uploaded is not None:
        arr, bounds = read_stack(uploaded)
        source = uploaded.name
    elif os.path.exists(local_stack):
        arr, bounds = read_stack(local_stack)
        source = "farm_stack.tif"
except Exception as exc:
    st.sidebar.error(f"Could not read this file as a GeoTIFF: {exc}")
    st.stop()

shape = arr.shape[1:] if arr is not None else DEFAULT_SHAPE
if shape[0] * shape[1] > MAX_PIXELS:
    st.error("Raster too large for the demo. Use a smaller area.")
    st.stop()
if arr is not None and arr.shape[0] != 3:
    st.error("The stack must have 3 bands: VV, VH, NDVI.")
    st.stop()

if st.session_state.get("source") != source:
    st.session_state.update(source=source, mask=None, mode=None)

# --------------------------------------------------------------------------- #
# Controls + analysis
# --------------------------------------------------------------------------- #
left, right = st.columns([1, 3])
with left:
    st.markdown(f"**Source:** {source}")
    st.markdown(f"**Grid:** {shape[1]} x {shape[0]} px")
    run = st.button("🚀 Run HydroScan Analysis")

if run:
    with st.spinner("Running HydroScan model..."):
        if arr is not None and model is not None:
            if not irrigated_classes:
                st.warning("Pick at least one irrigated class in the sidebar.")
            else:
                st.session_state.mask = predict_mask(arr, model, irrigated_classes)
                st.session_state.mode = "real"
        else:
            st.session_state.mask = simulate_mask(shape)
            st.session_state.mode = "simulated"

mask, mode = st.session_state.get("mask"), st.session_state.get("mode")

# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
metrics = json.load(open(P("metrics.json"))) if os.path.exists(P("metrics.json")) else None
total_px = shape[0] * shape[1]
irrigated_px = int(mask.sum()) if mask is not None else 0
acres = irrigated_px * PIXEL_M**2 / ACRE_M2
total_acres = total_px * PIXEL_M**2 / ACRE_M2

c1, c2, c3, c4 = st.columns(4)
c1.metric("💧 Estimated irrigated area", f"{acres:,.1f} acres" if mask is not None else "—")
c2.metric("🌍 Total area scanned", f"{total_acres:,.1f} acres")
c3.metric("📊 Irrigated share", f"{100 * irrigated_px / total_px:.1f} %" if mask is not None else "—")
c4.metric("🎯 Model accuracy (CV)",
          f"{metrics['cv_accuracy_mean']:.0%}" if metrics else "—",
          help="5-fold cross-validated accuracy on labelled points" if metrics else "Train a model first")

# --------------------------------------------------------------------------- #
# Tabs
# --------------------------------------------------------------------------- #
tab_map, tab_trend, tab_model = st.tabs(["🗺️ Irrigation map", "📈 Trends (NASA SMAP)", "🧠 Model"])

with tab_map:
    st_folium(build_map(bounds, mask), height=560, use_container_width=True, returned_objects=[])
    if mask is None:
        st.info("Click **Run HydroScan Analysis** to overlay the AI prediction.")
    elif mode == "simulated":
        st.warning("DEMO MODE: no trained model.joblib / farm_stack.tif found, so this mask is simulated.")
    else:
        st.caption("Blue = pixels the trained model classed as irrigated. "
                   "Area assumes 10 m per pixel; 1 acre = 4,046.86 m².")

with tab_trend:
    if os.path.exists(P("timeseries.csv")):
        ts = pd.read_csv(P("timeseries.csv")).set_index("month")
        a, b = st.columns(2)
        with a:
            st.subheader("Vegetation (NDVI, Sentinel-2)")
            st.line_chart(ts[["ndvi"]])
        with b:
            st.subheader("Soil moisture (NASA SMAP, mm)")
            st.line_chart(ts[["soil_moisture"]])
        st.subheader("Radar backscatter (Sentinel-1, dB)")
        st.line_chart(ts[["vv", "vh"]])
        st.caption("SMAP has a ~10 km pixel, so it shows regional moisture, not single fields.")
    else:
        st.info("No timeseries.csv yet. Run:  python timeseries.py --project YOUR_ID "
                "--bbox W S E N --start 2026-01-01 --months 10")

with tab_model:
    if metrics:
        a, b, c = st.columns(3)
        a.metric("Labelled points", metrics["n_samples"])
        b.metric("Held-out test accuracy", f"{metrics['test_accuracy']:.0%}")
        c.metric(f"{metrics['cv_folds']}-fold CV accuracy",
                 f"{metrics['cv_accuracy_mean']:.0%}", f"± {metrics['cv_accuracy_std']:.0%}", delta_color="off")
        st.subheader("Training points per class")
        st.bar_chart(pd.Series(metrics["classes"]))
        st.subheader("What the model relies on")
        st.bar_chart(pd.Series(metrics["feature_importance"], index=metrics["features"]))
    else:
        st.info("No metrics.json yet. Train with model_training.py to see accuracy and feature importance.")
