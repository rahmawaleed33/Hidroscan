#!/usr/bin/env python3
"""
model_training.py
=================
Train a Random Forest on the VV / VH / NDVI stack produced by gee_pipeline.py
and report HONEST accuracy numbers (held-out test split + 5-fold cross-validation).

You provide:
  * the stack GeoTIFF       (bands: VV, VH, NDVI)
  * a labels CSV with columns:  lon, lat, label
    (use REAL points: label_tool.py creates labels_real.csv by clicking the map)

Outputs:
  * model.joblib   - the trained model
  * metrics.json   - accuracy, class counts, feature importance (shown in the dashboard)

Usage:
    python model_training.py --stack farm_stack.tif --labels labels_real.csv --model model.joblib
"""

import argparse
import json
import os

import joblib
import numpy as np
import pandas as pd
import rasterio
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

NODATA = -9999.0
FEATURE_NAMES = ["VV", "VH", "NDVI", "VH_minus_VV"]


def make_features(stack):
    """stack: array (3, H, W) or (N, 3) -> feature matrix (N, 4). Shared with the dashboard."""
    if stack.ndim == 3:  # (bands, H, W) -> (H*W, bands)
        stack = stack.reshape(stack.shape[0], -1).T
    vv, vh, ndvi = stack[:, 0], stack[:, 1], stack[:, 2]
    return np.column_stack([vv, vh, ndvi, vh - vv])


def sample_stack(stack_path, labels_csv):
    """Read the raster value at each labelled lon/lat."""
    df = pd.read_csv(labels_csv)
    with rasterio.open(stack_path) as ds:
        vals = np.array(list(ds.sample(zip(df["lon"], df["lat"]))), dtype="float32")
    keep = ~(vals == NODATA).any(axis=1) & ~np.isnan(vals).any(axis=1)
    # Plain numpy string array (new pandas versions return Arrow-backed arrays
    # that scikit-learn cannot index).
    labels = df["label"].astype(str).to_numpy(dtype=object)
    return make_features(vals[keep]), labels[keep]


def train(stack_path, labels_csv, model_path):
    X, y = sample_stack(stack_path, labels_csv)
    classes, counts = np.unique(y, return_counts=True)
    print(f"Usable samples: {len(y)}")
    for c, n in zip(classes, counts):
        print(f"  {c}: {n}")

    if len(classes) < 2:
        raise SystemExit("Need at least 2 different classes in the labels.")
    if counts.min() < 5:
        raise SystemExit("Each class needs at least 5 points inside valid pixels.")

    # 1) Held-out test split
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
    model = RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1)
    model.fit(X_tr, y_tr)
    pred = model.predict(X_te)
    test_acc = accuracy_score(y_te, pred)
    print(classification_report(y_te, pred))

    # 2) Cross-validation (more reliable than a single split)
    n_splits = int(min(5, counts.min()))
    cv = cross_val_score(
        RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1),
        X, y, cv=StratifiedKFold(n_splits, shuffle=True, random_state=42),
    )
    print(f"Held-out test accuracy : {test_acc:.1%}")
    print(f"{n_splits}-fold CV accuracy      : {cv.mean():.1%} (+/- {cv.std():.1%})")

    # Final model uses all labelled points
    model.fit(X, y)
    joblib.dump(model, model_path)

    metrics = {
        "n_samples": int(len(y)),
        "classes": {str(c): int(n) for c, n in zip(classes, counts)},
        "test_accuracy": float(test_acc),
        "cv_folds": n_splits,
        "cv_accuracy_mean": float(cv.mean()),
        "cv_accuracy_std": float(cv.std()),
        "features": FEATURE_NAMES,
        "feature_importance": [float(v) for v in model.feature_importances_],
    }
    out = os.path.join(os.path.dirname(os.path.abspath(model_path)), "metrics.json")
    with open(out, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Model saved: {model_path}")
    print(f"Metrics saved: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--model", default="model.joblib")
    a = ap.parse_args()
    train(a.stack, a.labels, a.model)
