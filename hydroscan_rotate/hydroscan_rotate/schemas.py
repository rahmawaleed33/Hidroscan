"""Provenance helpers: every dataset carries what it is, where it came from, and whether it is usable."""
import datetime as dt

# ILLUSTRATIVE / fallback data are deliberately NOT allowed: a missing source is "unavailable", never replaced by sample data.
# kind -> how the farmer/judge should read it. MEASURED = ground measurement (none yet); SATELLITE = satellite-derived observation;
# MODELLED = reanalysis/ML/model output; FARMER = provided by the farmer; REFERENCE = literature; ASSUMPTION = analyst rule.
KINDS = {"OBSERVATION", "SATELLITE", "MODELLED", "MODEL_PREDICTION", "DERIVED", "EXTERNAL_REFERENCE", "FARMER", "ASSUMPTION", "SCENARIO"}
STATUSES = {"ok", "cached", "unavailable"}


def prov(source, kind, status="ok", period=None, retrieved=None, spatial_resolution=None, temporal_resolution=None,
         units=None, method=None, note=None, reason=None):
    assert kind in KINDS and status in STATUSES, (kind, status)
    return {"source": source, "kind": kind, "status": status, "retrieved": retrieved or dt.date.today().isoformat(),
            "period": period, "spatial_resolution": spatial_resolution, "temporal_resolution": temporal_resolution,
            "units": units, "method": method, "note": note, "reason": reason}


def unavailable(source, reason, kind="OBSERVATION"):
    return {"data": None, "provenance": prov(source, kind, "unavailable", reason=reason)}


class HydroScanError(Exception):
    """Base class for explicit, user-presentable errors."""


class InvalidCoordinates(HydroScanError):
    pass


class OutsideCoverage(HydroScanError):
    pass
