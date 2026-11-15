"""Tiny cached JSON GET. Live -> cache (status 'ok'); network failure -> cached copy (status 'cached') -> None."""
import hashlib
import json
import os
import time

import config


def cache_path(key):
    return os.path.join(config.CACHE, hashlib.md5(key.encode()).hexdigest()[:16] + ".json")


def get_json(url, params=None, key=None, getter=None):
    """Returns (data, status, reason). `getter` lets tests inject a fake transport (never used in the app)."""
    data, status, reason, _ = get_json_meta(url, params, key, getter)
    return data, status, reason


def get_json_meta(url, params=None, key=None, getter=None):
    """Like get_json but also returns the retrieval date: today if live, the cache save date if cached."""
    key = key or (url + json.dumps(params or {}, sort_keys=True))
    path = cache_path(key)
    reason = None
    if config.ONLINE:
        try:
            if getter is not None:
                data = getter(url, params)
            else:
                import requests
                r = requests.get(url, params=params, timeout=config.HTTP_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            os.makedirs(config.CACHE, exist_ok=True)
            with open(path, "w") as f:
                json.dump({"saved": time.strftime("%Y-%m-%d"), "data": data}, f)
            return data, "ok", None, time.strftime("%Y-%m-%d")
        except Exception as exc:  # network down, HTTP error, bad JSON
            reason = f"{type(exc).__name__}: {str(exc)[:160]}"
    else:
        reason = "offline mode (HYDROSCAN_OFFLINE=1)"
    if os.path.exists(path):
        with open(path) as f:
            c = json.load(f)
        return c["data"], "cached", f"{reason}; using copy saved {c['saved']}", c["saved"]
    return None, "unavailable", reason, None


def cached_call(key, fn):
    """Run fn() (any JSON-serialisable result, e.g. a Google Earth Engine query). Same contract as get_json_meta:
    live -> (data, 'ok', None, today); failure -> cached copy (data, 'cached', reason, save date) -> (None, 'unavailable', reason, None)."""
    path = cache_path(key)
    reason = None
    if config.ONLINE:
        try:
            data = fn()
            os.makedirs(config.CACHE, exist_ok=True)
            with open(path, "w") as f:
                json.dump({"saved": time.strftime("%Y-%m-%d"), "data": data}, f)
            return data, "ok", None, time.strftime("%Y-%m-%d")
        except Exception as exc:
            reason = f"{type(exc).__name__}: {str(exc)[:200]}"
    else:
        reason = "offline mode (HYDROSCAN_OFFLINE=1)"
    if os.path.exists(path):
        with open(path) as f:
            c = json.load(f)
        return c["data"], "cached", f"{reason}; using copy saved {c['saved']}", c["saved"]
    return None, "unavailable", reason, None
