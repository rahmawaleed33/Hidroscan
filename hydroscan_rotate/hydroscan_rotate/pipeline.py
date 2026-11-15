"""One call from field coordinates to ranked rotations, risks and scenarios."""
import config
from analysis.field_profile import build_field_profile
from rotation.scenarios import PRESETS, run_scenario
from rotation.scoring import rank_rotations
from rotation.uncertainty import assess


def run_analysis(lat, lon, priority="water", water_availability="unknown", economic_inputs=None, stack_path=None, radius_m=300, use_gpm=None, _inject=None):
    profile = build_field_profile(lat, lon, stack_path=stack_path, radius_m=radius_m, use_gpm=use_gpm, _inject=_inject)
    ranked = rank_rotations(profile, priority, water_availability, economic_inputs)
    unc = assess(profile, ranked, water_availability, economic_inputs)
    scen = {k: run_scenario(profile, p, priority, water_availability, economic_inputs) for k, p in PRESETS.items() if k != "baseline"}
    return {"inputs": {"lat": lat, "lon": lon, "priority": priority, "water_availability": water_availability,
                       "economic_inputs": economic_inputs, "radius_m": radius_m},
            "profile": profile, "ranked": ranked, "uncertainty": unc, "scenarios": scen}
