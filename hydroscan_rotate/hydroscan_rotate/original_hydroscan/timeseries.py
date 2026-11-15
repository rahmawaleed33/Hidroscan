#!/usr/bin/env python3
"""
timeseries.py
=============
Monthly time series for your farm area -> timeseries.csv (shown in the dashboard).

Columns:
  month, ndvi (Sentinel-2), vv, vh (Sentinel-1, dB),
  soil_moisture (NASA SMAP 10 km surface soil moisture, mm)

NASA data: NASA_USDA/HSL/SMAP10KM_soil_moisture (SMAP, band 'ssm').

Usage:
    python timeseries.py --project YOUR_PROJECT_ID --bbox 30.40 30.50 30.45 30.55 \
        --start 2026-01-01 --months 10 --out timeseries.csv
"""

import argparse
import datetime as dt

import ee
import pandas as pd

import gee_pipeline as gp


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, 1)


def mean_of(image, region, scale):
    """Mean of every band of `image` over `region` -> python dict."""
    return image.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=region, scale=scale,
        bestEffort=True, maxPixels=1e9,
    ).getInfo()


def month_row(region, s, e):
    row = {"month": s[:7], "ndvi": None, "vv": None, "vh": None, "soil_moisture": None}

    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(region).filterDate(s, e)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", gp.MAX_CLOUD_PCT)))
    if s2.size().getInfo() > 0:
        img = s2.map(gp.mask_s2_clouds).map(gp.add_ndvi).select("NDVI").median()
        row["ndvi"] = (mean_of(img, region, 20) or {}).get("NDVI")

    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filterBounds(region).filterDate(s, e)
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
          .select(["VV", "VH"]))
    if s1.size().getInfo() > 0:
        vals = mean_of(s1.median(), region, 20) or {}
        row["vv"], row["vh"] = vals.get("VV"), vals.get("VH")

    smap = (ee.ImageCollection("NASA_USDA/HSL/SMAP10KM_soil_moisture")
            .filterBounds(region).filterDate(s, e).select("ssm"))
    if smap.size().getInfo() > 0:
        row["soil_moisture"] = (mean_of(smap.mean(), region, 10000) or {}).get("ssm")
    return row


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", required=True)
    p.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    p.add_argument("--start", required=True, help="First month, YYYY-MM-DD (day is ignored)")
    p.add_argument("--months", type=int, default=8)
    p.add_argument("--out", default="timeseries.csv")
    a = p.parse_args()

    gp.init_earth_engine(a.project)
    region = gp.make_region(a.bbox)
    first = dt.date.fromisoformat(a.start).replace(day=1)

    rows = []
    for i in range(a.months):
        s, e = add_months(first, i), add_months(first, i + 1)
        print(f"Month {s:%Y-%m} ...")
        rows.append(month_row(region, s.isoformat(), e.isoformat()))

    pd.DataFrame(rows).to_csv(a.out, index=False)
    print(f"Saved {a.out}")


if __name__ == "__main__":
    main()
