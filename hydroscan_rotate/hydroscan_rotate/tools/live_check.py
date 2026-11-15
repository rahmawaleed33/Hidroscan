"""LIVE DATA CHECK - run this on a computer with internet. It calls every real source for real Egyptian locations and writes
LIVE_CHECK_EVIDENCE.md + live_check_evidence.json (what was retrieved, when, how many records, first/last values).
Nothing is simulated. A source that fails is reported as FAIL with the exact reason.

    python -m tools.live_check                      # default test sites
    python -m tools.live_check --lat 31.117 --lon 30.950 --name "Sakha"
Optional (for Sentinel-2 / IMERG / SMAP / SoilGrids-on-GEE):  set HYDROSCAN_GEE_PROJECT=<your project id>  and run  earthengine authenticate  once.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

SITES = [
    {"name": "Sakha research-station area, Kafr El-Sheikh (old-land North Delta; coordinates as stated in the ARC papers)", "lat": 31.117, "lon": 30.950},
    {"name": "HydroScan demo field (north-west Delta desert fringe; the area covered by the supplied Sentinel stack)", "lat": config.DEMO_FIELD["lat"], "lon": config.DEMO_FIELD["lon"]},
]


def _t(fn):
    t0 = time.time()
    try:
        return fn(), None, round(time.time() - t0, 1)
    except Exception as exc:  # report, never hide
        return None, f"{type(exc).__name__}: {str(exc)[:300]}", round(time.time() - t0, 1)


def check_site(site):
    from data_sources.gpm import get_imerg_monthly
    from data_sources.nasa_power import get_power_data
    from data_sources.sentinel import get_ndvi_history
    from data_sources.smap import get_smap_monthly
    from data_sources.soilgrids import get_soil_data
    lat, lon = site["lat"], site["lon"]
    out = []

    def rec(name, call, summarize):
        res, err, secs = _t(call)
        if err is None and res["data"] is not None:
            p = res["provenance"]
            out.append({"source": name, "result": "PASS", "status": p["status"], "retrieved": p["retrieved"], "seconds": secs, "period": p["period"],
                        "resolution": p["spatial_resolution"], "evidence": summarize(res["data"]), "note": p.get("reason")})
        else:
            reason = err or res["provenance"]["reason"]
            out.append({"source": name, "result": "FAIL", "seconds": secs, "reason": reason})

    rec("NASA POWER daily", lambda: get_power_data(lat, lon),
        lambda d: {"daily_records": d["daily_records"], "months": len(d["monthly"]), "first": d["monthly"][0], "last": d["monthly"][-1]})
    rec("ISRIC SoilGrids (WCS -> GEE -> REST)", lambda: get_soil_data(lat, lon),
        lambda d: {k: v["depths"] for k, v in d.items()})
    gee = bool(config.GEE_PROJECT)
    for name, fn, summ in (("Sentinel-2 NDVI via GEE", lambda: get_ndvi_history(lat, lon),
                            lambda d: {"months": len(d), "valid_months": int(d["ndvi"].notna().sum()), "first": d.iloc[0].to_dict(), "last": d.iloc[-1].to_dict()}),
                           ("GPM IMERG via GEE", lambda: get_imerg_monthly(lat, lon), lambda d: {"months": len(d["monthly"]), "first": d["monthly"][0], "last": d["monthly"][-1]}),
                           ("SMAP via GEE", lambda: get_smap_monthly(lat, lon), lambda d: {"months": len(d["monthly"]), "first": d["monthly"][0], "last": d["monthly"][-1]})):
        if gee:
            rec(name, fn, summ)
        else:
            out.append({"source": name, "result": "SKIPPED", "reason": "HYDROSCAN_GEE_PROJECT is not set (see SETUP_GUIDE.md)"})
    return {"site": site, "checks": out}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--lat", type=float); ap.add_argument("--lon", type=float); ap.add_argument("--name", default="custom site")
    a = ap.parse_args()
    sites = [{"name": a.name, "lat": a.lat, "lon": a.lon}] if a.lat is not None else SITES
    report = {"run_at": dt.datetime.now().isoformat(timespec="seconds"), "gee_project_set": bool(config.GEE_PROJECT), "results": [check_site(s) for s in sites]}
    with open("live_check_evidence.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    md = [f"# Live data check\nRun at {report['run_at']}. GEE project configured: {report['gee_project_set']}.\n"]
    for r in report["results"]:
        md.append(f"## {r['site']['name']} ({r['site']['lat']}, {r['site']['lon']})\n\n| Source | Result | Retrieved | Period | Resolution | Evidence / reason |\n|---|---|---|---|---|---|")
        for c in r["checks"]:
            ev = json.dumps(c.get("evidence"), default=str, ensure_ascii=False)[:260] if c["result"] == "PASS" else c.get("reason", "")
            md.append(f"| {c['source']} | **{c['result']}** | {c.get('retrieved', '-')} | {c.get('period', '-')} | {c.get('resolution', '-')} | {ev} |")
        md.append("")
    open("LIVE_CHECK_EVIDENCE.md", "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md))
    fails = sum(1 for r in report["results"] for c in r["checks"] if c["result"] == "FAIL")
    print(f"\n{fails} FAILED source checks. Send LIVE_CHECK_EVIDENCE.md back so failures can be fixed." if fails else "\nAll attempted sources returned data.")


if __name__ == "__main__":
    main()
