"""
label_tool.py -- click on the map to create REAL training labels.

Run:  python -m streamlit run label_tool.py

1. Pick a class (e.g. irrigated / not_irrigated).
2. Click a field on the satellite map -> a point is added.
   Tip: switch the layer to "Street map" or use Google Earth in another tab to
   double-check what the field is. Only label fields you are sure about.
3. Press "Save labels" -> labels_real.csv (columns lon, lat, label).
4. Train:  python model_training.py --stack farm_stack.tif --labels labels_real.csv

Aim for 30+ points per class, spread over the whole area.
"""

import os

import folium
import matplotlib
import numpy as np
import pandas as pd
import rasterio
import streamlit as st
from folium.raster_layers import ImageOverlay
from rasterio.warp import transform_bounds
from streamlit_folium import st_folium

HERE = os.path.dirname(os.path.abspath(__file__))
STACK = os.path.join(HERE, "farm_stack.tif")
OUT = os.path.join(HERE, "labels_real.csv")
NODATA = -9999.0
PALETTE = ["#1e6eff", "#ff8c00", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]

st.set_page_config(page_title="HydroScan Label Tool", page_icon="📍", layout="wide")
st.title("📍 HydroScan label tool")

if not os.path.exists(STACK):
    st.error("farm_stack.tif not found. Run gee_pipeline.py first.")
    st.stop()


@st.cache_data
def load_stack(path):
    with rasterio.open(path) as ds:
        arr = ds.read().astype("float32")
        b = ds.bounds
        if ds.crs and ds.crs.to_epsg() != 4326:
            b = transform_bounds(ds.crs, "EPSG:4326", *b)
    return arr, tuple(b)


arr, (west, south, east, north) = load_stack(STACK)
valid = ~(arr == NODATA).any(axis=0)

# ---- session state ---------------------------------------------------------
if "points" not in st.session_state:
    st.session_state.points = (
        pd.read_csv(OUT).to_dict("records") if os.path.exists(OUT) else []
    )
st.session_state.setdefault("last_click", None)
st.session_state.setdefault("view", {"center": [(south + north) / 2, (west + east) / 2], "zoom": 14})

# ---- sidebar ---------------------------------------------------------------
with st.sidebar:
    st.header("Classes")
    names = st.text_input("Class names (comma separated)", "irrigated, not_irrigated")
    classes = [c.strip() for c in names.split(",") if c.strip()]
    current = st.radio("Label for the next click", classes)
    show_ndvi = st.checkbox("Show NDVI overlay", value=True)

    df = pd.DataFrame(st.session_state.points, columns=["lon", "lat", "label"])
    st.subheader("Points collected")
    st.write(df["label"].value_counts().to_dict() or "none yet")

    c1, c2 = st.columns(2)
    if c1.button("↩️ Undo last") and st.session_state.points:
        st.session_state.points.pop()
    if c2.button("🗑️ Clear all"):
        st.session_state.points = []
    if st.button("💾 Save labels", type="primary"):
        pd.DataFrame(st.session_state.points, columns=["lon", "lat", "label"]).to_csv(OUT, index=False)
        st.success(f"Saved {len(st.session_state.points)} points to labels_real.csv")

# ---- map ---------------------------------------------------------------------
v = st.session_state.view
m = folium.Map(location=v["center"], zoom_start=v["zoom"], tiles=None)
folium.TileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri World Imagery", name="Satellite",
).add_to(m)
folium.TileLayer("OpenStreetMap", name="Street map").add_to(m)

if show_ndvi:
    cmap = matplotlib.colormaps["RdYlGn"]
    rgba = (cmap(np.clip((arr[2] + 0.1) / 1.0, 0, 1)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 130, 0)
    ImageOverlay(rgba, bounds=[[south, west], [north, east]], opacity=1,
                 name="NDVI", interactive=False).add_to(m)

color_of = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(classes)}
for p in st.session_state.points:
    folium.CircleMarker(
        [p["lat"], p["lon"]], radius=6, weight=2, color="white", fill=True,
        fill_color=color_of.get(p["label"], "#888"), fill_opacity=1, tooltip=p["label"],
    ).add_to(m)
folium.LayerControl().add_to(m)

st.caption("Click a field to add a point with the selected class.")
out = st_folium(m, height=620, use_container_width=True,
                returned_objects=["last_clicked", "center", "zoom"], key="labelmap")

if out:
    if out.get("center") and out.get("zoom"):
        st.session_state.view = {"center": [out["center"]["lat"], out["center"]["lng"]], "zoom": out["zoom"]}
    click = out.get("last_clicked")
    if click:
        key = (round(click["lat"], 6), round(click["lng"], 6))
        if key != st.session_state.last_click:
            st.session_state.last_click = key
            if west <= click["lng"] <= east and south <= click["lat"] <= north:
                st.session_state.points.append(
                    {"lon": click["lng"], "lat": click["lat"], "label": current}
                )
                st.rerun()
            else:
                st.warning("That click is outside the satellite file's area.")
