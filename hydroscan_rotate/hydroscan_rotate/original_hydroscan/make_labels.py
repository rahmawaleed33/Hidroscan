#!/usr/bin/env python3
"""
make_labels.py
==============
Create a STARTER labels.csv from farm_stack.tif so the full pipeline can run
before you have real field data.

Points are sampled at random and labelled from NDVI:
    bare_soil  : NDVI < 0.20
    sparse_veg : 0.20 <= NDVI < 0.45
    dense_veg  : NDVI >= 0.45

NOTE: these are pseudo-labels derived from the satellite itself, so the model
will look very accurate (it is partly learning the NDVI rule). Use it to test the
pipeline. For real results, replace labels.csv with ground-truth points from your
farm (crop type, healthy/stressed...) using the same columns: lon,lat,label.

Usage:
    python make_labels.py --stack farm_stack.tif --n 300 --out labels.csv
"""

import argparse

import numpy as np
import pandas as pd
import rasterio

NODATA = -9999.0


def label_from_ndvi(ndvi):
    if ndvi < 0.20:
        return "bare_soil"
    if ndvi < 0.45:
        return "sparse_veg"
    return "dense_veg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", required=True)
    ap.add_argument("--n", type=int, default=300, help="number of points")
    ap.add_argument("--out", default="labels.csv")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    with rasterio.open(a.stack) as ds:
        arr = ds.read().astype("float32")  # (3, H, W)
        valid = ~(arr == NODATA).any(axis=0) & ~np.isnan(arr).any(axis=0)
        rows, cols = np.where(valid)
        if len(rows) == 0:
            raise SystemExit("No valid pixels in the stack.")
        rng = np.random.default_rng(a.seed)
        pick = rng.choice(len(rows), size=min(a.n, len(rows)), replace=False)
        r, c = rows[pick], cols[pick]
        xs, ys = rasterio.transform.xy(ds.transform, r, c)
        ndvi = arr[2, r, c]

    df = pd.DataFrame({"lon": xs, "lat": ys, "label": [label_from_ndvi(v) for v in ndvi]})
    df.to_csv(a.out, index=False)
    print(f"Wrote {len(df)} points to {a.out}")
    print(df["label"].value_counts().to_string())


if __name__ == "__main__":
    main()
