"""Simulation-only adapter: ignore finger software position bounds."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'collection'))
import policy_adapter

def simulation_positions(value, properties):
    if not isinstance(value, (list, tuple)) or len(value) != 8:
        raise ValueError("expected eight absolute positions")
    for name, position in zip(policy_adapter.JOINTS, value):
        bounds = properties[name]
        if isinstance(position, bool) or not isinstance(position, (int, float)) or not math.isfinite(position):
            raise ValueError(f"invalid position: {name}")
        if name not in ("ee_f1", "ee_f2") and not bounds["lower"] <= position <= bounds["upper"]:
            raise ValueError(f"invalid position or URDF limit: {name}")
    return list(value)

policy_adapter.positions = simulation_positions
policy_adapter.main()
