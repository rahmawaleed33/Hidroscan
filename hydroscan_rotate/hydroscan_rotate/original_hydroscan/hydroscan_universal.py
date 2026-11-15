"""
hydroscan_universal.py -- HydroScan AI: works with ANY GeoTIFF(s).

Run:  python -m streamlit run hydroscan_universal.py

Tabs
  Files      : what is inside each file (bands, size, projection, stats, background warnings)
  Map        : view any band / RGB composite / analysis result on a satellite map
  Indices    : create NDVI, NDWI, NDMI or any normalized difference
  Train      : click fields on the map, label them, train a model on ALL bands of the raster
  Analysis   : threshold rule, K-means clustering, or the built-in Sentinel model
  Compare    : change between two dates + time series across files
  Get data   : download satellite images (Sentinel, Landsat, NASA SMAP) straight into data/
  Export     : GeoTIFF / CSV downloads
"""

import glob
import os
import datetime as dt

import folium
import matplotlib
import numpy as np
import pandas as pd
import rasterio
import streamlit as st
from folium.raster_layers import ImageOverlay
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.warp import reproject
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from streamlit_folium import st_folium

from model_training import NODATA, make_features

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
ACRE_M2 = 4046.8564224
DEFAULT_BOUNDS = (30.40, 30.50, 30.45, 30.55)
PALETTE = [tuple(int(255 * c) for c in matplotlib.colormaps["tab10"](i)[:3]) for i in range(10)]
BAND_PRESETS = {
    "(none)": None,
    "Landsat 8/9 SR (6 bands)": ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"],
    "Sentinel-2 (6 bands)": ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"],
    "Sentinel-2 + NDVI (7 bands)": ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2", "NDVI"],
    "HydroScan stack (VV, VH, NDVI)": ["VV", "VH", "NDVI"],
}

st.set_page_config(page_title="HydroScan AI - Universal", page_icon="💧", layout="wide")
st.markdown(
    """
    <style>
      .block-container {padding-top: 1.2rem; max-width: 1350px;}
      .hero {background: linear-gradient(120deg,#0b3d91 0%,#1e6eff 55%,#19c3e6 100%);
             padding: 1.3rem 1.8rem; border-radius: 18px; color: white; margin-bottom: 1rem;
             box-shadow: 0 10px 30px rgba(30,110,255,.25);}
      .hero h1 {margin:0; font-size:2rem;} .hero p {margin:.3rem 0 0; opacity:.92;}
      div[data-testid="stMetric"] {background:#fff; border:1px solid #e3ebf7; border-radius:16px;
             padding:.9rem 1.1rem; box-shadow:0 4px 14px rgba(20,60,140,.08);}
      div[data-testid="stMetricValue"] {color:#0b3d91;}
      .stButton > button {background: linear-gradient(90deg,#1e6eff,#19c3e6); color:white; border:0;
             border-radius:12px; font-weight:700; box-shadow:0 6px 16px rgba(30,110,255,.3);}
      .stButton > button:hover {filter:brightness(1.07); color:white;}
    </style>
    <div class="hero"><h1>💧 HydroScan AI</h1>
    <p>Get satellite images, label examples, train a model, and map irrigated land.</p></div>
    """,
    unsafe_allow_html=True,
)


# =========================================================================== #
# Raster loading (any CRS / bands / dtype, downsampled, always EPSG:4326)
# =========================================================================== #
@st.cache_data(show_spinner="Reading raster...")
def load_raster(_source, key, max_dim, bg_mode, bg_value):
    """-> dict(arr (B,H,W) float32 with NaN nodata, bounds (W,S,E,N) lat/lon, meta, ...)."""
    mem = None
    if isinstance(_source, (bytes, bytearray)):
        mem = MemoryFile(_source)
        src = mem.open()
    else:
        src = rasterio.open(_source)
    vrt = None
    try:
        georef = src.crs is not None
        meta = {
            "bands": src.count, "native_size": f"{src.width} x {src.height}",
            "dtype": src.dtypes[0], "crs": src.crs.to_string() if src.crs else "none",
            "native_res": f"{abs(src.res[0]):.6g} x {abs(src.res[1]):.6g}",
            "nodata": src.nodata,
        }
        names = [d if d else f"Band {i + 1}" for i, d in enumerate(src.descriptions)]

        # "Engineering" CRS (e.g. Pseudo Mercator, unknown datum) cannot be converted:
        # its coordinates are Web Mercator metres, so treat it as EPSG:3857.
        wkt = src.crs.to_wkt().upper() if georef else ""
        engineering = georef and src.crs.to_epsg() is None and ("LOCAL_CS" in wkt or "ENGCRS" in wkt)
        if engineering:
            meta["crs"] = "Pseudo Mercator (treated as EPSG:3857)"
        ds = src

        def read_from(dataset):
            s = min(1.0, max_dim / max(dataset.height, dataset.width))
            oh, ow = max(1, int(dataset.height * s)), max(1, int(dataset.width * s))
            return oh, ow, dataset.read(masked=True, out_shape=(dataset.count, oh, ow),
                                        resampling=Resampling.bilinear)

        if georef and (engineering or src.crs.to_epsg() != 4326):
            vrt = WarpedVRT(src, src_crs="EPSG:3857" if engineering else None,
                            crs="EPSG:4326", resampling=Resampling.bilinear)
            ds = vrt
        try:
            oh, ow, data = read_from(ds)
        except Exception:
            if vrt is not None or not georef:
                raise
            vrt = WarpedVRT(src, src_crs="EPSG:3857", crs="EPSG:4326", resampling=Resampling.bilinear)
            ds = vrt
            meta["crs"] = f"{meta['crs'][:30]}... (treated as EPSG:3857)"
            oh, ow, data = read_from(ds)

        arr = data.astype("float32").filled(np.nan)
        arr[arr == NODATA] = np.nan
        arr[~np.isfinite(arr)] = np.nan

        # ---- background (e.g. empty area around a clipped watershed) -------------
        def all_equal(vec):
            return np.all(arr == np.asarray(vec, dtype="float32")[:, None, None], axis=0)

        bg_info, suspect = None, None
        if bg_mode == "auto":
            corners = np.stack([arr[:, 0, 0], arr[:, 0, -1], arr[:, -1, 0], arr[:, -1, -1]])
            if np.isfinite(corners).all() and np.allclose(corners, corners[0]):
                m = all_equal(corners[0])
                if m.mean() >= 0.02:
                    arr[:, m] = np.nan
                    bg_info = {"value": [float(v) for v in corners[0]], "share": float(m.mean())}
        elif bg_mode == "value":
            m = np.all(arr == bg_value, axis=0)
            if m.any():
                arr[:, m] = np.nan
                bg_info = {"value": [float(bg_value)], "share": float(m.mean())}
        if bg_info is None:
            v0 = arr[0][np.isfinite(arr[0])]
            if v0.size:
                vals, cnt = np.unique(v0, return_counts=True)
                i = int(cnt.argmax())
                if cnt[i] / v0.size >= 0.15:
                    yx = np.argwhere(arr[0] == vals[i])[0]
                    ref = arr[:, yx[0], yx[1]]
                    m = all_equal(ref)
                    if m.mean() >= 0.15:
                        suspect = {"value": [float(v) for v in ref], "share": float(m.mean())}

        bounds = tuple(ds.bounds) if georef else DEFAULT_BOUNDS
        west, south, east, north = bounds
        lat = (south + north) / 2
        dx = (east - west) / ow * 111_320 * np.cos(np.radians(lat))
        dy = (north - south) / oh * 110_540
        return {
            "arr": arr, "bounds": bounds, "names": names, "meta": meta, "georef": georef,
            "pixel_area_m2": float(dx * dy), "native_wh": (src.width, src.height),
            "bg_info": bg_info, "suspect": suspect,
        }
    finally:
        if vrt is not None:
            vrt.close()
        src.close()
        if mem is not None:
            mem.close()


@st.cache_resource
def load_model(path, mtime):
    import joblib
    return joblib.load(path)


# =========================================================================== #
# Rendering helpers
# =========================================================================== #
def stretch(a, lo=2, hi=98):
    ok = np.isfinite(a)
    if not ok.any():
        return np.full(a.shape, np.nan, dtype="float32")
    p1, p2 = np.percentile(a[ok], [lo, hi])
    return np.clip((a - p1) / (p2 - p1 + 1e-12), 0, 1)


def rgba_continuous(a, cmap_name, alpha):
    n = stretch(a)
    rgba = (matplotlib.colormaps[cmap_name](np.nan_to_num(n)) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(np.isfinite(a), int(alpha * 255), 0)
    return rgba


def rgba_rgb(r, g, b, alpha):
    out = np.stack([np.nan_to_num(stretch(x)) for x in (r, g, b)], axis=-1)
    rgba = np.zeros((*r.shape, 4), dtype=np.uint8)
    rgba[..., :3] = (out * 255).astype(np.uint8)
    rgba[..., 3] = np.where(np.isfinite(r) & np.isfinite(g) & np.isfinite(b), int(alpha * 255), 0)
    return rgba


def rgba_categorical(lab, alpha, highlight=None):
    rgba = np.zeros((*lab.shape, 4), dtype=np.uint8)
    for c in np.unique(lab[lab >= 0]):
        if highlight is not None and c not in highlight:
            continue
        rgba[lab == c, :3] = PALETTE[int(c) % len(PALETTE)]
        rgba[lab == c, 3] = int(alpha * 255)
    return rgba


def make_map(bounds, rgba=None, label="Layer", location=None, zoom=None, points=None, colors=None):
    west, south, east, north = bounds
    m = folium.Map(location=location or [(south + north) / 2, (west + east) / 2],
                   zoom_start=zoom or 12, tiles=None, control_scale=True)
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Satellite").add_to(m)
    folium.TileLayer("OpenStreetMap", name="Street map").add_to(m)
    folium.Rectangle([[south, west], [north, east]], color="#19c3e6", weight=2, fill=False).add_to(m)
    if rgba is not None:
        ImageOverlay(rgba, bounds=[[south, west], [north, east]], opacity=1,
                     name=label, interactive=False).add_to(m)
    for p in points or []:
        folium.CircleMarker([p["lat"], p["lon"]], radius=6, weight=2, color="white", fill=True,
                            fill_color=(colors or {}).get(p["label"], "#888"), fill_opacity=1,
                            tooltip=p["label"]).add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    if location is None:
        m.fit_bounds([[south, west], [north, east]])
    return m


def to_geotiff(arrays, bounds, nodata, dtype="float32"):
    arrays = np.asarray(arrays)
    n, h, w = arrays.shape
    with MemoryFile() as mem:
        with mem.open(driver="GTiff", height=h, width=w, count=n, dtype=dtype, crs="EPSG:4326",
                      transform=from_bounds(*bounds, w, h), nodata=nodata) as dst:
            dst.write(arrays.astype(dtype))
        return mem.read()


# =========================================================================== #
# Get data from Google Earth Engine -> data/ folder
# =========================================================================== #
def build_product(gp, product, region, s, e, scale):
    ee = gp.ee
    if product.startswith("HydroScan"):
        return gp.build_stack(region, s, e, scale=scale), ["VV", "VH", "NDVI"]

    if product.startswith("Sentinel-2"):
        col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(s, e)
               .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", gp.MAX_CLOUD_PCT)))
        if col.size().getInfo() == 0:
            raise RuntimeError("No Sentinel-2 scenes for this area/date range.")
        img = col.map(gp.mask_s2_clouds).select(["B2", "B3", "B4", "B8", "B11", "B12"]).median().divide(10000)
        out = img.addBands(img.normalizedDifference(["B8", "B4"]).rename("NDVI"))
        return out.clip(region).toFloat().unmask(gp.NODATA), \
            ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2", "NDVI"]

    if product.startswith("Landsat"):
        names = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]

        def prep(img):
            qa = img.select("QA_PIXEL")
            ok = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))  # no cloud / shadow
            sr = img.select(["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"], names)
            return sr.multiply(0.0000275).add(-0.2).updateMask(ok)

        col = (ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2"))
               .filterBounds(region).filterDate(s, e))
        if col.size().getInfo() == 0:
            raise RuntimeError("No Landsat 8/9 scenes for this area/date range.")
        return col.map(prep).median().clip(region).toFloat().unmask(gp.NODATA), names

    # NASA SMAP
    col = (ee.ImageCollection("NASA_USDA/HSL/SMAP10KM_soil_moisture").filterBounds(region)
           .filterDate(s, e).select("ssm"))
    if col.size().getInfo() == 0:
        raise RuntimeError("No SMAP data for this date range.")
    return col.mean().clip(region).toFloat().unmask(gp.NODATA), ["Soil moisture (mm)"]


def render_get_data(R_active):
    st.markdown("Download a satellite image of any area straight into the **data/** folder, "
                "then select it in the sidebar. Needs a free Google Earth Engine project "
                "(one-time login: run `python -c \"import ee; ee.Authenticate()\"` in the terminal).")
    products = ["Sentinel-2 optical (Blue, Green, Red, NIR, SWIR1, SWIR2 + NDVI)  - 10 m",
                "Landsat 8/9 surface reflectance (6 bands)  - 30 m",
                "HydroScan stack: Sentinel-1 VV, VH + Sentinel-2 NDVI  - 10 m",
                "NASA SMAP soil moisture  - 10 km"]
    c1, c2 = st.columns([2, 3])
    project = c1.text_input("Earth Engine project ID", key="gd_project")
    product = c2.selectbox("Satellite product", products, key="gd_product")
    b0 = R_active["bounds"] if R_active else DEFAULT_BOUNDS
    d1, d2, d3, d4 = st.columns(4)
    west = d1.number_input("West", value=float(b0[0]), format="%.5f", key="gd_w")
    south = d2.number_input("South", value=float(b0[1]), format="%.5f", key="gd_s")
    east = d3.number_input("East", value=float(b0[2]), format="%.5f", key="gd_e")
    north = d4.number_input("North", value=float(b0[3]), format="%.5f", key="gd_n")
    e1, e2, e3 = st.columns(3)
    start = e1.date_input("Start date", value=dt.date.today() - dt.timedelta(days=75), key="gd_start")
    days = e2.number_input("Window (days)", 5, 120, 30, key="gd_days")
    default_scale = 30 if "Landsat" in product else (10000 if "SMAP" in product else 10)
    scale = e3.number_input("Resolution (m)", 5, 20000, default_scale, key=f"gd_scale_{default_scale}")
    fname = st.text_input("Save as", f"{product.split()[0].lower()}_{start:%Y%m}.tif", key="gd_name")

    if st.button("🛰️ Download image", key="gd_go"):
        if not project.strip():
            st.error("Enter your Earth Engine project ID.")
            return
        try:
            import gee_pipeline as gp
            gp.ee.Initialize(project=project.strip())
        except Exception as exc:
            st.error(f"Could not start Earth Engine: {exc}. Log in once with: "
                     "python -c \"import ee; ee.Authenticate()\"")
            return
        bbox = [west, south, east, north]
        try:
            with st.spinner("Asking Google Earth Engine for the image (can take a minute)..."):
                region = gp.make_region(bbox)
                s, e = gp.date_range(start.isoformat(), int(days))
                image, names = build_product(gp, product, region, s, e, scale)
                os.makedirs(DATA_DIR, exist_ok=True)
                out = os.path.join(DATA_DIR, fname if fname.endswith((".tif", ".tiff")) else fname + ".tif")
                gp.download_geotiff(image, region, bbox, out, scale=scale, n_bands=len(names))
                gp.label_bands(out, names)
        except Exception as exc:
            st.error(f"Download failed: {exc}")
            return
        st.session_state["pending_add"] = os.path.relpath(out, HERE)
        st.success(f"Saved {os.path.relpath(out, HERE)} with bands: {', '.join(names)}")
        st.rerun()


# =========================================================================== #
# Sources (sidebar)
# =========================================================================== #
def local_tifs():
    out = {}
    for d in (HERE, DATA_DIR):
        for p in sorted(glob.glob(os.path.join(d, "*.tif")) + glob.glob(os.path.join(d, "*.tiff"))):
            out[os.path.relpath(p, HERE)] = p
    return out


with st.sidebar:
    st.header("📁 Data")
    uploads = st.file_uploader("Upload GeoTIFF file(s)", type=["tif", "tiff"], accept_multiple_files=True)
    local = local_tifs()
    st.session_state.setdefault("local_pick", ["farm_stack.tif"] if "farm_stack.tif" in local else [])
    pend = st.session_state.pop("pending_add", None)
    if pend:
        st.session_state["local_pick"] = list(dict.fromkeys(st.session_state["local_pick"] + [pend]))
    st.session_state["local_pick"] = [p for p in st.session_state["local_pick"] if p in local]
    chosen_local = st.multiselect("Or use files from this folder / data/", list(local), key="local_pick")
    max_dim = st.slider("Max display size (pixels, longest side)", 300, 2500, 900, 100,
                        help="Large rasters are downsampled for speed. Raise for more detail.")
    px_override = st.number_input("Native pixel size in metres (0 = auto)", min_value=0.0, value=0.0,
                                  help="Use only if the automatic area looks wrong.")
    bg_choice = st.selectbox("Background / nodata", ["Auto-detect", "None", "Use a value"],
                             help="Clipped images (e.g. a watershed) have an empty background. "
                                  "It must NOT be counted as land.")
    bg_value = st.number_input("Background value", value=0.0) if bg_choice == "Use a value" else 0.0
    bg_mode = {"Auto-detect": "auto", "None": "none", "Use a value": "value"}[bg_choice]

sources = {}
for f in uploads:
    sources[f"⬆ {f.name}"] = (f.getvalue(), f"{f.name}|{f.size}")
for name in chosen_local:
    p = local[name]
    sources[name] = (p, f"{p}|{os.path.getmtime(p)}|{os.path.getsize(p)}")

if not sources:
    st.info("👈 Upload .tif files in the sidebar, put them in the **data/** folder, "
            "or download a satellite image below.")
    render_get_data(None)
    st.stop()

rasters = {}
for name, (src, key) in sources.items():
    try:
        rasters[name] = load_raster(src, key, max_dim, bg_mode, float(bg_value))
    except Exception as exc:
        st.sidebar.error(f"{name}: could not read ({exc})")
if not rasters:
    st.stop()

with st.sidebar:
    st.divider()
    active = st.selectbox("🎯 Active raster", list(rasters))
R = rasters[active]
S = f"|{active}"  # keeps widget state separate per raster
arr = R["arr"]
nb, H, W = arr.shape

with st.sidebar:
    preset = st.selectbox("Band names preset", list(BAND_PRESETS), key="bp" + S,
                          help="Satellite files often have unnamed bands. Name them so you know which is which.")
    typed = st.text_input("...or type band names (comma separated)", key="bn" + S)

names = R["names"]
if typed.strip():
    parts = [x.strip() for x in typed.split(",") if x.strip()]
    if len(parts) == nb:
        names = parts
    else:
        st.sidebar.warning(f"This file has {nb} bands but you typed {len(parts)} names.")
elif BAND_PRESETS[preset] and len(BAND_PRESETS[preset]) == nb:
    names = BAND_PRESETS[preset]

st.session_state.setdefault("derived", {})
st.session_state.setdefault("results", {})
derived = st.session_state["derived"].setdefault(active, {})

layers = {f"{i + 1}: {n}": arr[i] for i, n in enumerate(names)}
layers.update(derived)
layer_names = list(layers)

px_area = R["pixel_area_m2"]
if px_override > 0:
    px_area = (px_override * R["native_wh"][0] / W) * (px_override * R["native_wh"][1] / H)
valid_px = int(np.isfinite(arr).all(axis=0).sum())
generic_names = all(n.startswith("Band ") for n in names)

if not R["georef"]:
    st.warning("This file has no georeferencing, so it is placed on a default area of the map.")
if R["suspect"]:
    st.warning(f"⚠️ {R['suspect']['share']:.0%} of this image has exactly the same value "
               f"({R['suspect']['value'][0]:g}) in every band. That looks like empty background that is being "
               "counted as land. Set **Background / nodata → Use a value** in the sidebar.")
if R["bg_info"]:
    st.success(f"Background removed: value {R['bg_info']['value'][0]:g} "
               f"({R['bg_info']['share']:.0%} of the file) is not counted as land.")

t_files, t_map, t_idx, t_train, t_an, t_cmp, t_get, t_exp = st.tabs(
    ["📂 Files", "🗺️ Map", "🧮 Indices", "🎓 Train", "🤖 Analysis", "🔁 Compare & trends",
     "🛰️ Get data", "⬇️ Export"])

# --------------------------------------------------------------------------- #
# Files
# --------------------------------------------------------------------------- #
with t_files:
    rows = []
    for nm, r in rasters.items():
        rows.append({"file": nm, "bands": r["meta"]["bands"], "native size": r["meta"]["native_size"],
                     "type": r["meta"]["dtype"], "CRS": r["meta"]["crs"], "pixel size": r["meta"]["native_res"],
                     "nodata": r["meta"]["nodata"]})
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.subheader(f"Band statistics: {active}")
    stats = pd.DataFrame({
        "layer": layer_names,
        "min": [np.nanmin(v) if np.isfinite(v).any() else np.nan for v in layers.values()],
        "mean": [np.nanmean(v) if np.isfinite(v).any() else np.nan for v in layers.values()],
        "max": [np.nanmax(v) if np.isfinite(v).any() else np.nan for v in layers.values()],
        "% valid": [100 * np.isfinite(v).mean() for v in layers.values()],
    })
    st.dataframe(stats, width="stretch", hide_index=True)
    c1, c2, c3 = st.columns(3)
    c1.metric("Display grid", f"{W} x {H} px")
    c2.metric("Land area (valid pixels)", f"{valid_px * px_area / ACRE_M2:,.1f} acres")
    c3.metric("Approx. pixel size", f"{np.sqrt(px_area):.1f} m")
    st.caption("Check: does 'Land area' match the real size of your study area? "
               "If it is much bigger, empty background is being counted.")

# --------------------------------------------------------------------------- #
# Map
# --------------------------------------------------------------------------- #
with t_map:
    modes = ["Single layer", "RGB composite"]
    if active in st.session_state["results"]:
        modes.append("Analysis result")
    a, b, c = st.columns([2, 2, 1])
    mode = a.radio("Display", modes, horizontal=True)
    alpha = c.slider("Opacity", 0.1, 1.0, 0.8)
    rgba, label = None, "Layer"
    if mode == "Single layer":
        layer = b.selectbox("Layer", layer_names, key="map_layer" + S)
        cmap = a.selectbox("Colour map", ["viridis", "RdYlGn", "gray", "Blues", "magma", "RdBu_r"], key="cmap" + S)
        rgba, label = rgba_continuous(layers[layer], cmap, alpha), layer
    elif mode == "RGB composite":
        d1, d2, d3 = st.columns(3)
        ri = d1.selectbox("Red", layer_names, index=0, key="rgb_r" + S)
        gi = d2.selectbox("Green", layer_names, index=min(1, len(layer_names) - 1), key="rgb_g" + S)
        bi = d3.selectbox("Blue", layer_names, index=min(2, len(layer_names) - 1), key="rgb_b" + S)
        rgba, label = rgba_rgb(layers[ri], layers[gi], layers[bi], alpha), "RGB composite"
        st.caption("Tip: for a natural-colour picture choose the Red, Green and Blue bands, in that order.")
    else:
        res = st.session_state["results"][active]
        rgba, label = rgba_categorical(res["labels"], alpha), res["title"]
        st.caption("Legend: " + "  ".join(
            f"<span style='color:rgb{PALETTE[i % 10]}'>■</span> {n}" for i, n in enumerate(res["names"])),
            unsafe_allow_html=True)
    st_folium(make_map(R["bounds"], rgba, label), height=560, use_container_width=True,
              returned_objects=[], key=f"map_{active}_{mode}")

# --------------------------------------------------------------------------- #
# Indices
# --------------------------------------------------------------------------- #
with t_idx:
    st.markdown("Create a new layer from your bands, then use it in the Map, Train and Analysis tabs.")
    presets = {
        "NDVI  (NIR - Red) / (NIR + Red)": ("NDVI", "NIR", "Red"),
        "NDWI  (Green - NIR) / (Green + NIR)": ("NDWI", "Green", "NIR"),
        "NDMI  (NIR - SWIR) / (NIR + SWIR)": ("NDMI", "NIR", "SWIR"),
        "Custom normalized difference (A - B) / (A + B)": ("ND", "A", "B"),
        "Ratio  A / B": ("RATIO", "A", "B"),
        "Difference  A - B": ("DIFF", "A", "B"),
    }
    p = st.selectbox("Formula", list(presets))
    nm, la, lb = presets[p]

    def find(word, default):
        for i, n in enumerate(layer_names):
            if word.lower() in n.lower():
                return i
        return default

    c1, c2, c3 = st.columns(3)
    A = c1.selectbox(f"{la} band", layer_names, index=find(la, 0), key="idx_a" + S + nm)
    B = c2.selectbox(f"{lb} band", layer_names, index=find(lb, min(1, len(layer_names) - 1)), key="idx_b" + S + nm)
    new_name = c3.text_input("New layer name", nm, key="idx_name" + S + nm)
    if st.button("➕ Create layer"):
        x, y = layers[A], layers[B]
        with np.errstate(divide="ignore", invalid="ignore"):
            out = x / y if nm == "RATIO" else (x - y if nm == "DIFF" else (x - y) / (x + y))
        derived[f"✨ {new_name}"] = np.where(np.isfinite(out), out, np.nan).astype("float32")
        st.rerun()
    if derived:
        st.write("Derived layers:", ", ".join(derived))
        if st.button("Remove derived layers"):
            derived.clear()
            st.rerun()
    if generic_names:
        st.info("Your bands have no names. Name them in the sidebar (Band names preset) so the right "
                "bands are pre-selected.")

# --------------------------------------------------------------------------- #
# Train (label examples on the map, train on ALL bands of this raster)
# --------------------------------------------------------------------------- #
with t_train:
    st.markdown("**Teach the app with your own examples.** Pick a class, click fields on the map, "
                "then press *Train*. The model learns from **all bands of this raster**, so it works "
                "with any satellite image.")
    st.session_state.setdefault("train_pts", {})
    st.session_state.setdefault("train_view", {})
    st.session_state.setdefault("train_click", {})
    st.session_state.setdefault("train_metrics", {})
    pts = st.session_state["train_pts"].setdefault(active, [])

    left, right = st.columns([1, 2.4])
    with left:
        cls_text = st.text_input("Class names (comma separated)", "irrigated, not_irrigated", key="tr_cls" + S)
        classes = [c.strip() for c in cls_text.split(",") if c.strip()]
        cur = st.radio("Label for the next click", classes, key="tr_cur" + S)
        target = st.multiselect("Target class(es) to measure in acres", classes, default=classes[:1],
                                key="tr_tgt" + S)
        bg_layer = st.selectbox("Background layer on the map", ["RGB composite (first 3 bands)"] + layer_names,
                                key="tr_bg" + S)
        counts = pd.Series([p["label"] for p in pts]).value_counts().to_dict() if pts else {}
        st.write("Points:", counts or "none yet")
        u1, u2 = st.columns(2)
        if u1.button("↩️ Undo", key="tr_undo" + S) and pts:
            pts.pop()
            st.rerun()
        if u2.button("🗑️ Clear", key="tr_clr" + S):
            pts.clear()
            st.rerun()
        csv_in = st.file_uploader("Load labels CSV (lon, lat, label)", type=["csv"], key="tr_csv" + S)
        if csv_in is not None and st.button("Add CSV points", key="tr_addcsv" + S):
            d = pd.read_csv(csv_in)
            if {"lon", "lat", "label"} <= set(d.columns):
                pts.extend(d[["lon", "lat", "label"]].astype({"label": str}).to_dict("records"))
                st.rerun()
            else:
                st.error("CSV needs the columns lon, lat, label.")
        if pts:
            st.download_button("💾 Save labels (CSV)", pd.DataFrame(pts).to_csv(index=False), "my_labels.csv")
        train_go = st.button("🎓 Train model", type="primary", key="tr_go" + S)

    with right:
        west, south, east, north = R["bounds"]
        if bg_layer.startswith("RGB"):
            i3 = [min(i, len(layer_names) - 1) for i in range(3)]
            bgrgba = rgba_rgb(*[layers[layer_names[i]] for i in i3], 0.9)
        else:
            bgrgba = rgba_continuous(layers[bg_layer], "viridis", 0.8)
        view = st.session_state["train_view"].get(active)
        colors = {c: "#%02x%02x%02x" % PALETTE[i % 10] for i, c in enumerate(classes)}
        tm = make_map(R["bounds"], bgrgba, "Background", location=view["center"] if view else None,
                      zoom=view["zoom"] if view else None, points=pts, colors=colors)
        st.caption("Click a field to add a point with the selected class. Zoom in first for accuracy, "
                   "and check the field in Street map / Satellite before labelling.")
        out = st_folium(tm, height=560, use_container_width=True,
                        returned_objects=["last_clicked", "center", "zoom"], key=f"trainmap_{active}")
        if out:
            if out.get("center") and out.get("zoom"):
                st.session_state["train_view"][active] = {
                    "center": [out["center"]["lat"], out["center"]["lng"]], "zoom": out["zoom"]}
            click = out.get("last_clicked")
            if click:
                ck = (round(click["lat"], 6), round(click["lng"], 6))
                if ck != st.session_state["train_click"].get(active):
                    st.session_state["train_click"][active] = ck
                    if west <= click["lng"] <= east and south <= click["lat"] <= north:
                        pts.append({"lon": click["lng"], "lat": click["lat"], "label": cur})
                        st.rerun()
                    else:
                        st.warning("That click is outside the image.")

    if train_go:
        feats = np.stack([layers[n] for n in layer_names])          # (F, H, W)
        r = ((north - np.array([p["lat"] for p in pts])) / (north - south) * H).astype(int) if pts else np.array([])
        c = ((np.array([p["lon"] for p in pts]) - west) / (east - west) * W).astype(int) if pts else np.array([])
        inside = (r >= 0) & (r < H) & (c >= 0) & (c < W) if pts else np.array([], bool)
        X = feats[:, r[inside], c[inside]].T if pts else np.zeros((0, len(layer_names)))
        y = np.array([p["label"] for p in pts], dtype=object)[inside] if pts else np.array([], dtype=object)
        ok = np.isfinite(X).all(axis=1)
        X, y = X[ok], y[ok]
        cls, cnt = np.unique(y, return_counts=True) if len(y) else (np.array([]), np.array([]))
        if len(cls) < 2 or cnt.min() < 5:
            st.error("Need at least 2 classes with 5+ valid points each (points on empty background don't count). "
                     f"Valid so far: {dict(zip(cls.tolist(), cnt.tolist()))}")
        else:
            with st.spinner("Training..."):
                Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
                rf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1).fit(Xtr, ytr)
                test_acc = float((rf.predict(Xte) == yte).mean())
                folds = int(min(5, cnt.min()))
                cv = cross_val_score(RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1),
                                     X, y, cv=StratifiedKFold(folds, shuffle=True, random_state=42))
                rf.fit(X, y)
                valid = np.isfinite(feats).all(axis=0).ravel()
                flat = feats.reshape(len(layer_names), -1).T
                lab = np.full(H * W, -1, np.int16)
                idx = np.where(valid)[0]
                cl = list(rf.classes_)
                for i in range(0, len(idx), 200_000):
                    part = idx[i:i + 200_000]
                    lab[part] = [cl.index(v) for v in rf.predict(flat[part])]
            st.session_state["results"][active] = {
                "labels": lab.reshape(H, W), "names": [str(x) for x in cl], "title": "Trained on your labels",
                "highlight": [cl.index(t) for t in target if t in cl], "method": "trained"}
            st.session_state["train_metrics"][active] = {
                "n": int(len(y)), "classes": dict(zip(cls.tolist(), cnt.tolist())), "test": test_acc,
                "cv": float(cv.mean()), "cv_std": float(cv.std()), "folds": folds,
                "importance": dict(zip(layer_names, rf.feature_importances_.tolist()))}
            st.success("Model trained. See the result below, or open the Analysis tab.")

    tm_ = st.session_state["train_metrics"].get(active)
    if tm_:
        st.divider()
        a1, a2, a3 = st.columns(3)
        a1.metric("Labelled points used", tm_["n"])
        a2.metric("Held-out test accuracy", f"{tm_['test']:.0%}")
        a3.metric(f"{tm_['folds']}-fold CV accuracy", f"{tm_['cv']:.0%}", f"± {tm_['cv_std']:.0%}", delta_color="off")
        st.caption("Accuracy is measured on points the model did not train on. Nearby points look alike, so "
                   "real accuracy on new fields may be lower: label points spread across the whole area.")
        st.subheader("Which bands mattered most")
        st.bar_chart(pd.Series(tm_["importance"]))

# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
EXPLAIN = {
    "threshold": "A simple rule: every pixel above (or below) your threshold is highlighted. It is a proxy, "
                 "not a trained prediction.",
    "kmeans": "The computer groups similar pixels. The groups are NOT named: look at the map and decide what "
              "each cluster means. Clusters are sorted by the first band's average (Cluster 1 = lowest).",
    "model": "The built-in model was trained on Sentinel-1 VV, VH and NDVI. It is only valid for those three inputs.",
    "trained": "A model trained on the examples YOU labelled, using all bands of this image.",
}

with t_an:
    method = st.radio("Method", ["Threshold rule (binary)", "K-means clustering (no labels needed)",
                                 "Trained on my labels (Train tab)", "Built-in Sentinel model (VV, VH, NDVI)"],
                      horizontal=True)
    result = None

    if method.startswith("Threshold"):
        c1, c2, c3 = st.columns([2, 1, 2])
        tl = c1.selectbox("Layer", layer_names, key="thr_layer" + S)
        op = c2.selectbox("Pixels where value is", [">", "<"], key="thr_op" + S)
        v = layers[tl]
        lo, hi = (float(np.nanmin(v)), float(np.nanmax(v))) if np.isfinite(v).any() else (0.0, 1.0)
        med = float(np.nanmedian(v)) if np.isfinite(v).any() else lo
        thr = c3.slider("Threshold", lo, hi, med, step=(hi - lo) / 200 or 0.01, key="thr_val" + S + tl)
        st.caption(f"The slider starts at the median ({med:.4g}), which always selects about 50% of the land. "
                   "Move it to a meaningful value.")
        if st.button("🚀 Run analysis", key="run_thr"):
            lab = np.full(v.shape, -1, np.int16)
            okp = np.isfinite(v)
            sel = (v > thr) if op == ">" else (v < thr)
            lab[okp] = sel[okp].astype(np.int16)
            result = {"labels": lab, "names": ["Other", f"{tl} {op} {thr:.3g}"], "title": "Threshold rule",
                      "highlight": [1], "method": "threshold"}

    elif method.startswith("K-means"):
        c1, c2 = st.columns([3, 1])
        use = c1.multiselect("Layers to cluster", layer_names, default=layer_names[:6], key="km_layers" + S)
        k = c2.slider("Clusters", 2, 8, 4, key="km_k" + S)
        if st.button("🚀 Run analysis", key="run_km"):
            if not use:
                st.warning("Select at least one layer.")
            else:
                with st.spinner("Clustering..."):
                    X = np.stack([layers[u] for u in use]).reshape(len(use), -1).T
                    okp = np.isfinite(X).all(axis=1)
                    if okp.sum() < k * 10:
                        st.error("Not enough valid pixels common to the selected layers.")
                    else:
                        Z = (X[okp] - X[okp].mean(0)) / (X[okp].std(0) + 1e-9)
                        idx = np.random.default_rng(0).choice(len(Z), min(len(Z), 50_000), replace=False)
                        km = KMeans(k, n_init=5, random_state=0).fit(Z[idx])
                        pred = km.predict(Z)
                        means = [X[okp][pred == i, 0].mean() if (pred == i).any() else -np.inf for i in range(k)]
                        remap = np.empty(k, int)
                        remap[np.argsort(means)] = np.arange(k)
                        lab = np.full(H * W, -1, np.int16)
                        lab[okp] = remap[pred]
                        result = {"labels": lab.reshape(H, W), "names": [f"Cluster {i + 1}" for i in range(k)],
                                  "title": f"K-means (k={k})", "highlight": [k - 1], "method": "kmeans"}

    elif method.startswith("Trained"):
        if active in st.session_state["results"] and st.session_state["results"][active].get("method") == "trained":
            st.success("Showing the model you trained in the Train tab (below). Re-train there to update it.")
        else:
            st.info("Go to the 🎓 Train tab, label some fields and press Train.")

    else:
        model_path = os.path.join(HERE, "model.joblib")
        if not os.path.exists(model_path):
            st.info("No model.joblib found. Use 'Trained on my labels' instead.")
        else:
            model = load_model(model_path, os.path.getmtime(model_path))
            st.caption("Map your bands to the model's three inputs:")
            c1, c2, c3 = st.columns(3)
            vv = c1.selectbox("VV", layer_names, index=find("VV", 0), key="m_vv" + S)
            vh = c2.selectbox("VH", layer_names, index=find("VH", min(1, len(layer_names) - 1)), key="m_vh" + S)
            nd = c3.selectbox("NDVI", layer_names, index=find("NDVI", min(2, len(layer_names) - 1)), key="m_nd" + S)
            default = [x for x in model.classes_ if "irrig" in str(x).lower() and "not" not in str(x).lower()]
            irr = st.multiselect("Classes that count as irrigated", list(model.classes_),
                                 default=default or list(model.classes_)[:1], key="m_irr" + S)
            if st.button("🚀 Run analysis", key="run_model"):
                stack = np.stack([layers[vv], layers[vh], layers[nd]])
                okp = np.isfinite(stack).all(axis=0).ravel()
                feats = make_features(stack)
                lab = np.full(H * W, -1, np.int16)
                if okp.any():
                    cl = list(model.classes_)
                    lab[okp] = [cl.index(x) for x in model.predict(feats[okp])]
                result = {"labels": lab.reshape(H, W), "names": [str(x) for x in model.classes_],
                          "title": "Built-in model", "highlight": [list(model.classes_).index(x) for x in irr],
                          "method": "model", "bands": (vv, vh, nd)}

    if result is not None:
        st.session_state["results"][active] = result
    res = st.session_state["results"].get(active)
    if res:
        st.divider()
        st.info(f"**What this result is:** {EXPLAIN[res['method']]}")
        rn = res["names"]
        pick = st.multiselect("Classes to highlight / measure", rn,
                              default=[rn[i] for i in res["highlight"] if i < len(rn)],
                              key="hl" + S + res["title"])
        hl = [rn.index(n) for n in pick]
        lab = res["labels"]
        valid = int((lab >= 0).sum())
        sel_px = int(np.isin(lab, hl).sum())
        share = 100 * sel_px / max(valid, 1)
        m1, m2, m3 = st.columns(3)
        m1.metric("💧 Selected area", f"{sel_px * px_area / ACRE_M2:,.1f} acres")
        m2.metric("🌍 Analysed land area", f"{valid * px_area / ACRE_M2:,.1f} acres")
        m3.metric("📊 Share of land", f"{share:.1f} %")

        with st.expander("✅ Are these numbers right? (sanity check)", expanded=True):
            msgs = []
            if R["bg_info"]:
                msgs.append(("success", f"Empty background ({R['bg_info']['share']:.0%} of the file) was removed, "
                                        "so only real land is counted."))
            elif R["suspect"]:
                msgs.append(("warning", f"{R['suspect']['share']:.0%} of the file looks like empty background "
                                        "that is counted as land. Fix it in the sidebar (Background / nodata)."))
            msgs.append(("info", f"Analysed land = {valid:,} pixels = {valid * px_area / 1e6:,.0f} km². "
                                 "Compare with the real size of your area (e.g. draw a polygon in Google Earth). "
                                 "If it is much larger, something that is not land is being counted."))
            msgs.append(("info", f"Pixel size used ≈ {np.sqrt(px_area):.0f} m on the display grid "
                                 f"(file's own pixel size: {R['meta']['native_res']})."))
            if res["method"] == "threshold" and abs(share - 50) < 3:
                msgs.append(("warning", "The share is about 50%: your threshold is at the median, which always "
                                        "gives ~50%. Move the threshold to a meaningful value."))
            if res["method"] == "kmeans":
                msgs.append(("warning", "K-means groups are not named. The highlighted cluster is simply the group "
                                        "with the highest first-band values; it is NOT automatically 'irrigated'."))
            if res["method"] == "model":
                good = all(w.lower() in b.lower() for w, b in zip(["vv", "vh", "ndvi"], res["bands"]))
                msgs.append(("success" if good else "warning",
                             "Bands match the model's inputs." if good else
                             "The chosen bands are not named VV / VH / NDVI. The built-in model only makes sense "
                             "for Sentinel-1 VV, VH and Sentinel-2 NDVI. Use 'Trained on my labels' for other data."))
            if res["method"] == "trained":
                m_ = st.session_state["train_metrics"].get(active)
                if m_:
                    msgs.append(("info", f"Trained on {m_['n']} points; cross-validated accuracy {m_['cv']:.0%}. "
                                         "More, well-spread points make this more reliable."))
            if generic_names:
                msgs.append(("info", "Bands have no names, so check which band is which (e.g. Landsat: Blue, Green, "
                                     "Red, NIR, SWIR1, SWIR2) using the Band names preset in the sidebar."))
            for level, text in msgs:
                getattr(st, level)(text)

        table = pd.DataFrame({
            "class": rn,
            "pixels": [int((lab == i).sum()) for i in range(len(rn))],
            "acres": [round((lab == i).sum() * px_area / ACRE_M2, 1) for i in range(len(rn))],
            "% of land": [round(100 * (lab == i).sum() / max(valid, 1), 1) for i in range(len(rn))],
        })
        a, b = st.columns([1, 1])
        a.dataframe(table, width="stretch", hide_index=True)
        b.bar_chart(table.set_index("class")["acres"])
        st_folium(make_map(R["bounds"], rgba_categorical(lab, 0.75, hl), res["title"]), height=480,
                  use_container_width=True, returned_objects=[], key=f"res_{active}_{res['title']}")

# --------------------------------------------------------------------------- #
# Compare & trends
# --------------------------------------------------------------------------- #
with t_cmp:
    if len(rasters) < 2:
        st.info("Load at least two rasters (e.g. two dates) to compare them and plot trends.")
    else:
        st.subheader("Change detection (B - A)")
        names_all = list(rasters)
        c1, c2 = st.columns(2)
        na = c1.selectbox("Raster A (earlier)", names_all, index=0, key="cmp_a")
        nb_ = c2.selectbox("Raster B (later)", names_all, index=1, key="cmp_b")
        ra, rb = rasters[na], rasters[nb_]
        la_names = [f"{i + 1}: {n}" for i, n in enumerate(ra["names"])]
        lb_names = [f"{i + 1}: {n}" for i, n in enumerate(rb["names"])]
        d1, d2 = st.columns(2)
        ba = d1.selectbox("Band in A", la_names, key="cmp_ba" + na + nb_)
        bb = d2.selectbox("Band in B", lb_names, key="cmp_bb" + na + nb_)
        A2 = ra["arr"][la_names.index(ba)]
        B2 = rb["arr"][lb_names.index(bb)]
        B_on_A = np.full(A2.shape, np.nan, dtype="float32")
        reproject(B2, B_on_A,
                  src_transform=from_bounds(*rb["bounds"], B2.shape[1], B2.shape[0]), src_crs="EPSG:4326",
                  dst_transform=from_bounds(*ra["bounds"], A2.shape[1], A2.shape[0]), dst_crs="EPSG:4326",
                  src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.bilinear)
        diff = B_on_A - A2
        if np.isfinite(diff).any():
            lim = float(np.nanpercentile(np.abs(diff), 98)) or 1.0
            n_ = np.clip((diff + lim) / (2 * lim), 0, 1)
            rgba = (matplotlib.colormaps["RdBu"](np.nan_to_num(n_, nan=0.5)) * 255).astype(np.uint8)
            rgba[..., 3] = np.where(np.isfinite(diff), 200, 0)
            m1, m2, m3 = st.columns(3)
            m1.metric("Mean change", f"{np.nanmean(diff):+.3f}")
            m2.metric("Pixels increased", f"{100 * np.nanmean(diff[np.isfinite(diff)] > 0):.1f} %")
            m3.metric("Pixels decreased", f"{100 * np.nanmean(diff[np.isfinite(diff)] < 0):.1f} %")
            st.caption("Blue = increase, red = decrease (colour scale: 2nd-98th percentile).")
            st_folium(make_map(ra["bounds"], rgba, "Change (B - A)"), height=460,
                      use_container_width=True, returned_objects=[], key=f"chg_{na}_{nb_}_{ba}_{bb}")
            st.session_state["last_diff"] = (diff, ra["bounds"])
        else:
            st.warning("The two rasters do not overlap, so no change map can be built.")

        st.subheader("Time series across all loaded files")
        n_common = min(r["meta"]["bands"] for r in rasters.values())
        bi = st.number_input("Band number to track", 1, int(n_common), 1, key="ts_band" + str(len(rasters)))
        ts = pd.Series({k: float(np.nanmean(r["arr"][int(bi) - 1])) for k, r in sorted(rasters.items())})
        st.line_chart(ts)
        st.dataframe(ts.rename("mean value").to_frame(), width="stretch")

# --------------------------------------------------------------------------- #
# Get data
# --------------------------------------------------------------------------- #
with t_get:
    render_get_data(R)

# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
with t_exp:
    st.markdown(f"Exports for **{active}** (display grid {W} x {H} px, lat/lon).")
    stack = np.stack(list(layers.values()))
    st.download_button("⬇️ All layers (GeoTIFF)", to_geotiff(stack, R["bounds"], np.nan),
                       f"{os.path.splitext(os.path.basename(active))[0]}_layers.tif")
    res = st.session_state["results"].get(active)
    if res:
        st.download_button("⬇️ Analysis result (GeoTIFF, class ids)",
                           to_geotiff(res["labels"][None], R["bounds"], -1, "int16"), "hydroscan_result.tif")
        lab = res["labels"]
        table = pd.DataFrame({
            "class": res["names"],
            "pixels": [int((lab == i).sum()) for i in range(len(res["names"]))],
            "acres": [round((lab == i).sum() * px_area / ACRE_M2, 2) for i in range(len(res["names"]))],
        })
        st.download_button("⬇️ Area table (CSV)", table.to_csv(index=False), "hydroscan_areas.csv")
    else:
        st.info("Run an analysis to enable result exports.")
    if "last_diff" in st.session_state:
        d, bds = st.session_state["last_diff"]
        st.download_button("⬇️ Change map B - A (GeoTIFF)", to_geotiff(d[None], bds, np.nan), "hydroscan_change.tif")
