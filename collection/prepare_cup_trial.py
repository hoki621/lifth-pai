"""Prepare exactly one immutable scene/world snapshot; never launch or move a robot."""

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from cup_sequence import validate_steps
from prepare_cup_world import prepare

REPO = Path(__file__).resolve().parent.parent


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_trial(scene, output, base_world, assets):
    scene, output = Path(scene).resolve(), Path(output).resolve()
    config = json.loads(scene.read_text())
    if config["split"] not in ("train", "validation", "heldout") or not config["placement_id"]:
        raise ValueError("placement_id and preassigned split required")
    validate_steps(config["steps"])
    tree = prepare(Path(base_world), Path(assets), config)
    output.mkdir(parents=True, exist_ok=False)
    (output / "scene.json").write_bytes(scene.read_bytes())
    ET.indent(tree)
    tree.write(output / "world.sdf", encoding="utf-8", xml_declaration=True)
    trial = {
        "version": 1, "placement_id": config["placement_id"], "split": config["split"],
        "cup_pose": config["cup_pose"], "place_pose": config["place_pose"],
        "scene": str(output / "scene.json"), "scene_sha256": sha256(output / "scene.json"),
        "world": str(output / "world.sdf"), "world_sha256": sha256(output / "world.sdf"),
        "candidate": True, "pai_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "pai_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True)),
        "collection_sources_sha256": {name: sha256(REPO / "collection" / name) for name in (
            "prepare_cup_trial.py", "prepare_cup_world.py", "cup_sequence.py", "cup_demo.launch.py", "control_lock.py")},
        "foundation_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO / "external/lifth_arm_gen2", text=True).strip(),
        "episode_id": None, "raw_path": None, "sequence_exit_code": None,
        "task_success": None, "accepted": False, "exclusion_reason": "not reviewed",
    }
    (output / "trial.json").write_text(json.dumps(trial, indent=2) + "\n")
    return trial


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scene", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-world", type=Path, default=REPO / "external/lifth_arm_gen2/src/lifth_bringup/worlds/arm_camera.sdf")
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_trial(args.scene, args.output, args.base_world, args.assets), indent=2))


if __name__ == "__main__":
    main()
