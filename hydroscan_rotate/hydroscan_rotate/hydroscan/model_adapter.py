"""
Adapter that exposes the ORIGINAL HydroScan model (data/model.joblib) as one callable.

Reuses make_features() from the original model_training.py when importable (it needs rasterio at import
time); otherwise an identical local copy is used and tests assert both give the same output.
Original files are never modified.
"""
import os
import sys

import numpy as np

import config
from schemas import HydroScanError, InvalidCoordinates, OutsideCoverage, prov

sys.path.insert(0, os.path.join(config.ROOT, "original_hydroscan"))
try:  # preferred: the project's own implementation
    from model_training import FEATURE_NAMES, make_features  # type: ignore
    FEATURES_FROM = "original model_training.make_features"
except ImportError:  # rasterio not installed
    FEATURE_NAMES = ["VV", "VH", "NDVI", "VH_minus_VV"]
    FEATURES_FROM = "local copy of model_training.make_features (rasterio unavailable)"

    def make_features(stack):
        if stack.ndim == 3:
            stack = stack.reshape(stack.shape[0], -1).T
        vv, vh, ndvi = stack[:, 0], stack[:, 1], stack[:, 2]
        return np.column_stack([vv, vh, ndvi, vh - vv])

_MODEL_CACHE = {}


def read_stack(path):
    """-> (arr (3,H,W) float32, dict(west,north,px_x,px_y), source note). Band order VV, VH, NDVI."""
    if not os.path.exists(path):
        raise HydroScanError(f"Raster not found: {path}")
    try:
        import rasterio
        with rasterio.open(path) as ds:
            arr = ds.read().astype("float32")
            t = ds.transform
            geo = dict(west=t.c, north=t.f, px_x=t.a, px_y=-t.e)
    except ImportError:
        import tifffile
        with tifffile.TiffFile(path) as tf:
            pg = tf.pages[0]
            arr = tf.asarray().astype("float32")
            if "ModelTransformationTag" in pg.tags:
                m = pg.tags["ModelTransformationTag"].value
                geo = dict(west=m[3], north=m[7], px_x=m[0], px_y=-m[5])
            else:
                sc, tp = pg.tags["ModelPixelScaleTag"].value, pg.tags["ModelTiepointTag"].value
                geo = dict(west=tp[3], north=tp[4], px_x=sc[0], px_y=sc[1])
        if arr.ndim == 3 and arr.shape[-1] <= 4 < arr.shape[0]:
            arr = np.moveaxis(arr, -1, 0)
    if arr.ndim != 3 or arr.shape[0] != 3:
        raise HydroScanError(f"Expected a 3-band stack (VV, VH, NDVI); got shape {arr.shape}")
    return arr, geo


def bounds_of(arr, geo):
    h, w = arr.shape[1:]
    return (geo["west"], geo["north"] - geo["px_y"] * h, geo["west"] + geo["px_x"] * w, geo["north"])  # W,S,E,N


def load_model(path=None):
    path = path or config.MODEL_PATH
    if path not in _MODEL_CACHE:
        import joblib
        if not os.path.exists(path):
            raise HydroScanError(f"Model not found: {path}")
        _MODEL_CACHE[path] = joblib.load(path)
    return _MODEL_CACHE[path]


def validate_coords(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise InvalidCoordinates("Latitude/longitude must be numbers.")
    if not (np.isfinite(lat) and np.isfinite(lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InvalidCoordinates(f"Coordinates out of range: lat={lat}, lon={lon} (order is lat, lon).")
    return lat, lon


def analyze_field(lat, lon, stack_path=None, radius_m=300, model_path=None):
    """Analyse the pixels within radius_m of (lat, lon). Returns the structured dict described in the audit."""
    lat, lon = validate_coords(lat, lon)
    stack_path = stack_path or config.DEMO_STACK
    arr, geo = read_stack(stack_path)
    w, s, e, n = bounds_of(arr, geo)
    if not (w <= lon <= e and s <= lat <= n):
        raise OutsideCoverage(f"Point ({lat:.5f}, {lon:.5f}) is outside the raster coverage "
                              f"(lon {w:.4f}..{e:.4f}, lat {s:.4f}..{n:.4f}).")
    H, W = arr.shape[1:]
    m_per_deg_lat = 110_540.0
    m_per_deg_lon = 111_320.0 * np.cos(np.radians(lat))
    cx, cy = (lon - w) / geo["px_x"], (n - lat) / geo["px_y"]
    rx, ry = radius_m / (geo["px_x"] * m_per_deg_lon), radius_m / (geo["px_y"] * m_per_deg_lat)
    yy, xx = np.mgrid[0:H, 0:W]
    inside = ((xx + 0.5 - cx) / max(rx, 0.5)) ** 2 + ((yy + 0.5 - cy) / max(ry, 0.5)) ** 2 <= 1
    valid = ~(arr == config.NODATA).any(axis=0) & ~np.isnan(arr).any(axis=0)
    sel = inside & valid
    warnings, missing, available = [], [], []
    if sel.sum() == 0:
        raise OutsideCoverage("No valid (non-nodata) pixels around this point.")
    if sel.sum() < 9:
        warnings.append(f"Only {int(sel.sum())} pixels in the window; statistics are unstable.")
    window = arr[:, sel]                                    # (3, N)
    model = load_model(model_path)
    pred = model.predict(make_features(window.T.copy()))
    classes, counts = np.unique(pred, return_counts=True)
    frac = {str(c): round(float(k) / len(pred), 4) for c, k in zip(classes, counts)}
    dominant = max(frac, key=frac.get)
    ndvi = window[2]
    pixel_m = geo["px_x"] * m_per_deg_lon
    available += ["sentinel1_vv_vh_composite", "sentinel2_ndvi_composite", "hydroscan_vegetation_class"]
    missing += ["irrigation_classification (no trained/validated irrigation model)",
                "crop_classification (no crop model or crop labels)"]
    warnings.append("HydroScan's model separates bare_soil / sparse_veg / dense_veg. It was trained on NDVI-threshold "
                    "pseudo-labels (audit: 99% agreement with the plain NDVI rule), so it carries no independent "
                    "information beyond vegetation density and has no validated accuracy.")
    return {
        "field": {"latitude": lat, "longitude": lon, "radius_m": radius_m, "pixels_used": int(sel.sum()),
                  "pixel_size_m": round(float(pixel_m), 2), "stack": os.path.basename(stack_path)},
        "irrigation": {"classification": None, "confidence": None,
                       "source": "not available: HydroScan has no trained or validated irrigation model",
                       "hint": ("high_greenness_in_this_composite" if float(np.mean(ndvi)) >= 0.40 else
                                "low_or_moderate_greenness_in_this_composite"),
                       "hint_note": "Greenness hint only. Green vegetation is not proof of irrigation."},
        "crop": {"classification": None, "confidence": None, "source": "not available: no crop model or labels"},
        "vegetation": {"class_fractions": frac, "dominant_class": dominant,
                       "ndvi_mean": round(float(np.mean(ndvi)), 4), "ndvi_std": round(float(np.std(ndvi)), 4),
                       "vv_mean_db": round(float(np.mean(window[0])), 3), "vh_mean_db": round(float(np.mean(window[1])), 3),
                       "ndvi_series": [], "observation_dates": []},
        "model": {"name": "HydroScan RandomForest (original model.joblib, unmodified)",
                  "classes": [str(c) for c in model.classes_], "features": list(FEATURE_NAMES),
                  "features_from": FEATURES_FROM, "validated_accuracy": None,
                  "explanation": f"Dominant class '{dominant}' = {frac[dominant]:.0%} of pixels in the {radius_m} m window; "
                                 f"mean NDVI {np.mean(ndvi):.2f}. The class describes vegetation density only."},
        "data_quality": {"available": available, "missing": missing, "warnings": warnings},
        "provenance": prov("Sentinel-1/2 composite via Google Earth Engine (supplied GeoTIFF) + HydroScan RF",
                           "MODEL_PREDICTION", spatial_resolution=f"{pixel_m:.0f} m", temporal_resolution="single composite",
                           units="VV/VH dB, NDVI unitless", method="RandomForest on [VV, VH, NDVI, VH-VV]"),
    }
