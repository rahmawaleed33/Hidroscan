"""Google Earth Engine access. Needs (1) a free Google account registered for Earth Engine, (2) a Google Cloud project id,
(3) one-time `earthengine authenticate`. See SETUP_GUIDE.md. Without them every GEE source reports 'unavailable' with the reason."""
import config

_STATE = {"ee": None, "err": None, "project": None}


def get_ee(project=None):
    project = project or config.GEE_PROJECT
    if not project:
        return None, "no Google Earth Engine project configured (set HYDROSCAN_GEE_PROJECT)"
    if _STATE["ee"] is not None and _STATE["project"] == project:
        return _STATE["ee"], None
    try:
        import ee
        ee.Initialize(project=project)
        _STATE.update(ee=ee, err=None, project=project)
        return ee, None
    except Exception as exc:
        return None, f"Earth Engine init failed: {type(exc).__name__}: {str(exc)[:160]}"


def point_buffer(ee, lat, lon, radius_m):
    return ee.Geometry.Point([lon, lat]).buffer(radius_m)
