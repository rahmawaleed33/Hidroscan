"""Central configuration. Nothing secret is stored here: use environment variables (.env.example)."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")

DEMO_STACK = os.path.join(DATA, "farm_stack.tif")              # primary demo field
COMPARISON_STACK = os.path.join(DATA, "sentinel-2_202608.tif")  # kept for comparison / tests
MODEL_PATH = os.path.join(DATA, "model.joblib")                 # original HydroScan model, never modified
TIMESERIES_CSV = os.path.join(DATA, "timeseries.csv")           # real monthly GEE output supplied with the project

# Google Earth Engine project: configurable, optional. Without it, GEE-dependent sources report "unavailable".
GEE_PROJECT = os.environ.get("HYDROSCAN_GEE_PROJECT", "").strip()

ONLINE = os.environ.get("HYDROSCAN_OFFLINE", "0") != "1"        # set HYDROSCAN_OFFLINE=1 to never call the network
HTTP_TIMEOUT = 25

NODATA = -9999.0
DEMO_FIELD = {"name": "Demo field (HydroScan farm stack)", "lat": 30.525, "lon": 30.425}

# Bare-soil calendar defaults (configurable; NOT universally valid, see analysis/bare_soil.py)
BARE_NDVI_THRESHOLD = 0.25
MIN_OBS_FOR_MONTH = 1

# ---- Real-data settings (all configurable) ----
CLIMATE_YEARS = 10          # NASA POWER daily history length (years ending last full year)
NDVI_START_YEAR, NDVI_END_YEAR = 2021, 2025   # Sentinel-2 SR HARMONIZED multi-year NDVI (5 seasons)
IMERG_START_YEAR, IMERG_END_YEAR = 2021, 2025
SMAP_START_YEAR, SMAP_END_YEAR = 2021, 2025
FIELD_BUFFER_M = 150        # radius around the point used for Sentinel-2 (a small field, not a 5 km box)
HEAT_DAY_TMAX_C = 35.0      # analyst-chosen threshold for "hot day" counts (NOT an agronomic standard)
FROST_DAY_TMIN_C = 0.0
# GEE dataset ids: dataset versions change, so they live here and can be edited without touching code.
GEE_IDS = {"s2": "COPERNICUS/S2_SR_HARMONIZED", "s2_cloud": "COPERNICUS/S2_CLOUD_PROBABILITY",
           "imerg": "NASA/GPM_L3/IMERG_V07", "smap": "NASA/SMAP/SPL3SMP_E/006",
           "soilgrids_prefix": "projects/soilgrids-isric/", "imerg_band": "precipitation", "smap_band": "soil_moisture_am"}
