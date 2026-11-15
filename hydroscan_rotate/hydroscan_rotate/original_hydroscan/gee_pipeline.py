#!/usr/bin/env python3
"""
farm_stack_gee.py
=================
Build a 3-band analysis-ready stack (VV, VH, NDVI) for a farm region using
Google Earth Engine, and download it locally as one GeoTIFF.

Pipeline
--------
1. Define the area of interest (bounding box) and a 30-day window.
2. Sentinel-1 GRD (IW mode)  -> VV and VH (dB), median composite.
3. Sentinel-2 SR Harmonized  -> cloud mask (SCL band) -> NDVI, median composite.
4. Stack  [VV, VH, NDVI]  on the Sentinel-2 10 m grid.
5. Download to a local .tif via getDownloadURL (no Google Drive needed).

Setup (one time)
----------------
    pip install earthengine-api requests
    pip install rasterio          # optional: writes band names into the GeoTIFF

    # 1. Create / pick a Google Cloud project and enable the Earth Engine API:
    #    https://console.cloud.google.com/apis/library/earthengine.googleapis.com
    # 2. Register the project for Earth Engine (noncommercial or commercial):
    #    https://code.earthengine.google.com/register
    # 3. Authenticate (opens a browser, stores a token on this machine):
    earthengine authenticate
    #    ...or run this script with --authenticate, or call ee.Authenticate()
    #    in Python. On a headless server use:
    earthengine authenticate --auth_mode=notebook

Usage
-----
    python farm_stack_gee.py --project my-gcp-project \
        --bbox 30.40 30.50 30.45 30.55 \
        --start 2026-09-01 --output farm_stack.tif

    --bbox order is: west south east north  (lon/lat, EPSG:4326)
"""

import argparse
import datetime as dt
import os
import sys

import ee
import requests

# --------------------------------------------------------------------------- #
# Defaults (edit these, or override from the command line)
# --------------------------------------------------------------------------- #
# PLACEHOLDER bounding box (west, south, east, north) -- replace with your farm.
DEFAULT_BBOX = [30.40, 30.50, 30.45, 30.55]
DEFAULT_START = "2026-09-01"
WINDOW_DAYS = 30
SCALE_M = 10  # Sentinel-2 10 m grid (B4/B8 native resolution)
NODATA = -9999.0
MAX_CLOUD_PCT = 60  # scene-level pre-filter on S2 cloud percentage

# Google's synchronous download limit is ~48 MB per request.
MAX_DOWNLOAD_BYTES = 48 * 1024 * 1024

# Sentinel-2 Scene Classification Layer (SCL) classes to REMOVE:
#   3 = cloud shadow, 8 = cloud (medium prob), 9 = cloud (high prob),
#   10 = thin cirrus, 11 = snow/ice
SCL_MASKED_CLASSES = [3, 8, 9, 10, 11]


# --------------------------------------------------------------------------- #
# 1. Authentication / initialisation
# --------------------------------------------------------------------------- #
def init_earth_engine(project: str, force_auth: bool = False) -> None:
    """Initialise Earth Engine, authenticating first if needed."""
    if force_auth:
        ee.Authenticate()
    try:
        ee.Initialize(project=project)
    except Exception:
        # No valid credentials found -> run the interactive auth flow once.
        print("No valid Earth Engine credentials found; starting authentication...")
        ee.Authenticate()
        ee.Initialize(project=project)
    print(f"Earth Engine initialised (project: {project}).")


# --------------------------------------------------------------------------- #
# 2. Inputs: region and dates
# --------------------------------------------------------------------------- #
def make_region(bbox):
    """bbox = [west, south, east, north] in lon/lat -> ee.Geometry.Rectangle."""
    west, south, east, north = bbox
    if not (west < east and south < north):
        raise ValueError("bbox must be [west, south, east, north] with west<east, south<north")
    return ee.Geometry.Rectangle([west, south, east, north], proj="EPSG:4326", geodesic=False)


def date_range(start: str, days: int = WINDOW_DAYS):
    """Return (start, end) ISO strings; end is exclusive in GEE's filterDate."""
    start_dt = dt.date.fromisoformat(start)
    end_dt = start_dt + dt.timedelta(days=days)
    return start_dt.isoformat(), end_dt.isoformat()


# --------------------------------------------------------------------------- #
# 3. Sentinel-1: VV and VH
# --------------------------------------------------------------------------- #
def get_sentinel1(region, start, end):
    """
    Median composite of Sentinel-1 GRD IW scenes with both VV and VH.
    COPERNICUS/S1_GRD is already calibrated and terrain-corrected, with
    backscatter in dB (10*log10), so no extra conversion is needed.
    """
    col = (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .select(["VV", "VH"])
    )
    n = col.size().getInfo()
    if n == 0:
        raise RuntimeError("No Sentinel-1 scenes found for this region/date range.")
    print(f"Sentinel-1 scenes used: {n}")
    # Median across time reduces speckle; a small focal median smooths what's left.
    return col.median().focalMedian(radius=1, kernelType="square", units="pixels")


# --------------------------------------------------------------------------- #
# 4. Sentinel-2: cloud mask + NDVI
# --------------------------------------------------------------------------- #
def mask_s2_clouds(img):
    """Mask clouds/shadow/cirrus/snow using the SCL band."""
    scl = img.select("SCL")
    bad = ee.Image(0)
    for c in SCL_MASKED_CLASSES:
        bad = bad.Or(scl.eq(c))
    return img.updateMask(bad.Not())


def add_ndvi(img):
    """NDVI = (NIR - Red) / (NIR + Red) = (B8 - B4) / (B8 + B4)."""
    return img.addBands(img.normalizedDifference(["B8", "B4"]).rename("NDVI"))


def get_ndvi(region, start, end):
    """Cloud-masked median NDVI composite from Sentinel-2 L2A (surface reflectance)."""
    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_PCT))
    )
    n = col.size().getInfo()
    if n == 0:
        raise RuntimeError(
            "No Sentinel-2 scenes found (try a different window or raise MAX_CLOUD_PCT)."
        )
    print(f"Sentinel-2 scenes used: {n}")
    ndvi_col = col.map(mask_s2_clouds).map(add_ndvi).select("NDVI")
    # The median ignores masked pixels, so cloudy dates simply drop out.
    return ndvi_col.median()


# --------------------------------------------------------------------------- #
# 5. Stack
# --------------------------------------------------------------------------- #
def build_stack(region, start, end, scale=SCALE_M):
    """Return a Float32 image with bands [VV, VH, NDVI] clipped to the region."""
    s1 = get_sentinel1(region, start, end)
    ndvi = get_ndvi(region, start, end)

    # Use the Sentinel-2 projection as the common grid, then force the
    # S1 bands onto it (nearest/bilinear resampling is handled by reproject).
    proj = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).first().select("B4").projection()

    stack = (
        s1.select(["VV", "VH"])
        .addBands(ndvi)
        .reproject(crs=proj, scale=scale)
        .clip(region)
        .toFloat()
        .unmask(NODATA)  # fill masked pixels so the GeoTIFF has no gaps
    )
    return stack.select(["VV", "VH", "NDVI"])


# --------------------------------------------------------------------------- #
# 6. Local export
# --------------------------------------------------------------------------- #
def estimate_size_bytes(bbox, scale, n_bands=3):
    """Rough raw size of the download (Float32) from the bbox and scale."""
    west, south, east, north = bbox
    mid_lat = (south + north) / 2.0
    import math
    width_m = (east - west) * 111_320 * math.cos(math.radians(mid_lat))
    height_m = (north - south) * 110_540
    return int((width_m / scale) * (height_m / scale) * n_bands * 4)


def download_geotiff(image, region, bbox, output, scale=SCALE_M, n_bands=3):
    """Download the image as one GeoTIFF straight to disk."""
    est = estimate_size_bytes(bbox, scale, n_bands)
    print(f"Estimated download size: {est / 1e6:.1f} MB")
    if est > MAX_DOWNLOAD_BYTES:
        raise RuntimeError(
            "Region too large for a direct download (~48 MB limit). Use a smaller "
            "bbox, a coarser --scale, split the area into tiles, or use "
            "ee.batch.Export.image.toDrive for big areas."
        )

    url = image.getDownloadURL(
        {
            "region": region,
            "scale": scale,
            "crs": "EPSG:4326",
            "format": "GEO_TIFF",  # single multi-band GeoTIFF
            "filePerBand": False,
        }
    )
    print("Downloading...")
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()
    with open(output, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    print(f"Saved: {os.path.abspath(output)}")


def label_bands(path, names=("VV", "VH", "NDVI")):
    """Write band names into the GeoTIFF + set nodata (needs rasterio; optional)."""
    try:
        import rasterio
    except ImportError:
        print("(rasterio not installed - skipping band labels; order is VV, VH, NDVI)")
        return
    with rasterio.open(path, "r+") as ds:
        for i, name in enumerate(names, start=1):
            ds.set_band_description(i, name)
        ds.nodata = NODATA
    print("Band names written:", ", ".join(names))


# --------------------------------------------------------------------------- #
# One-call entry point (used by app.py)
# --------------------------------------------------------------------------- #
def export_stack(project, bbox, start, output, days=WINDOW_DAYS, scale=SCALE_M):
    """Initialise GEE, build the VV/VH/NDVI stack and save it to `output`."""
    init_earth_engine(project)
    region = make_region(bbox)
    s, e = date_range(start, days)
    stack = build_stack(region, s, e, scale=scale)
    download_geotiff(stack, region, bbox, output, scale=scale)
    label_bands(output)
    return output


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args():
    p = argparse.ArgumentParser(description="Export a VV/VH/NDVI GeoTIFF stack from GEE.")
    p.add_argument("--project", required=True, help="Your Google Cloud project ID registered for Earth Engine")
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), default=DEFAULT_BBOX)
    p.add_argument("--start", default=DEFAULT_START, help="Start date YYYY-MM-DD (window is 30 days)")
    p.add_argument("--days", type=int, default=WINDOW_DAYS, help="Window length in days (default 30)")
    p.add_argument("--scale", type=float, default=SCALE_M, help="Output resolution in metres (default 10)")
    p.add_argument("--output", default="farm_stack.tif")
    p.add_argument("--authenticate", action="store_true", help="Force a fresh Earth Engine login")
    return p.parse_args()


def main():
    args = parse_args()
    init_earth_engine(args.project, force_auth=args.authenticate)

    region = make_region(args.bbox)
    start, end = date_range(args.start, args.days)
    print(f"Date range: {start} -> {end}  |  bbox: {args.bbox}")

    stack = build_stack(region, start, end, scale=args.scale)
    download_geotiff(stack, region, args.bbox, args.output, scale=args.scale)
    label_bands(args.output)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # keep CLI errors readable
        sys.exit(f"Error: {exc}")
