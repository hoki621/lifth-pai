"""Small, dependency-free boundaries shared by conversion and local policy loading."""

import importlib.metadata
import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEROBOT_REVISION = "7e241bd630a3719a56157a497ce5d08f244784f1"
FOUNDATION_REVISION = "de410efb3a90348e256015305e80e10ecdcfd972"


def contract_digest(contract):
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def offline():
    # Set before importing HF/transformers; never silently fetch missing assets.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["WANDB_MODE"] = "disabled"


def upstream():
    root = REPO / "external/lifth_arm_gen2"
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if revision != FOUNDATION_REVISION:
        raise ValueError("foundation revision differs from approved pin")
    sys.path.insert(0, str(root / "src/lifth_dataset"))
    from lifth_dataset.validate import load, parse_json, validate
    return load, parse_json, validate


def load_contract(contract=None):
    load, _, _ = upstream()
    from lifth_dataset.schema import STATE
    result = load(REPO / "configs/policy_contract.json") if contract is None else contract
    if (result["foundation_revision"] != FOUNDATION_REVISION
            or result["lerobot_revision"] != LEROBOT_REVISION
            or result["joint_names"] != STATE
            or result["joint_units"] != ["rad"] * 6 + ["m"] * 2
            or result["model"] != "v2_1_1"
            or result["state_key"] != "observation.state"
            or result["action_key"] != "action"
            or result["image_key"] != "observation.images.d405"
            or result["action_semantics"] != "absolute_position"
            or result["image_shape_hwc"] != [360, 640, 3]):
        raise ValueError("unsupported policy contract")
    timing = result["timing"]
    if type(timing["validated"]) is not bool or timing["fps"] != 15 or type(timing["label_offset_ns"]) is not int:
        raise ValueError("expected fixed15Hz and integer signed label_offset_ns")
    for name in ("max_observation_age_ns", "max_observation_skew_ns",
                 "max_command_age_ns", "max_command_skew_ns"):
        if type(timing[name]) is not int or timing[name] <= 0:
            raise ValueError(f"invalid timing: {name}")
    return result


def verify_lerobot():
    """Require either a pinned source checkout or wheel VCS provenance, not a version guess."""
    spec = importlib.util.find_spec("lerobot")
    if spec is None:
        raise RuntimeError("pinned LeRobot environment is unavailable; no automatic installation")
    location = Path(spec.origin).resolve()
    for parent in location.parents:
        if (parent / ".git").exists():
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=parent, text=True).strip()
            if revision == LEROBOT_REVISION:
                return
            break
    try:
        provenance = json.loads(importlib.metadata.distribution("lerobot").read_text("direct_url.json"))
    except (importlib.metadata.PackageNotFoundError, TypeError, ValueError):
        provenance = {}
    if provenance.get("vcs_info", {}).get("commit_id") != LEROBOT_REVISION:
        raise ValueError("LeRobot installation lacks matching pinned source provenance")
