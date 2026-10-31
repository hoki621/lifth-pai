"""Validate explicitly accepted raw v2 episodes, causally align, write/reload official v3 datasets."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from alignment import COMMANDS, OBSERVATIONS, align
from common import REPO, load_contract, offline, upstream, verify_lerobot


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def hashes(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"raw symlink forbidden: {path}")
        if path.is_file():
            result[str(path.relative_to(root))] = digest(path)
    return result


def resolve(base, value):
    path = Path(value)
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def inspect_manifest(manifest_path, contract):
    load, parse_json, validate = upstream()
    manifest_path = Path(manifest_path).resolve()
    manifest = load(manifest_path)
    if manifest["version"] != 1 or not manifest["episodes"]:
        raise ValueError("nonempty acceptance manifest version 1 required")
    placements, poses, ids, paths, accepted, excluded = {}, {}, set(), set(), [], []
    for entry in manifest["episodes"]:
        scene_path = resolve(manifest_path.parent, entry["scene"])
        scene = load(scene_path)
        placement, split = entry["placement_id"], entry["split"]
        if (not placement or split not in ("train", "validation", "heldout")
                or scene["placement_id"] != placement or scene["split"] != split
                or digest(scene_path) != entry["scene_sha256"]
                or entry["cup_pose"] != scene["cup_pose"] or entry["place_pose"] != scene["place_pose"]):
            raise ValueError("scene snapshot/placement/split/hash mismatch")
        identity = (split, entry["scene_sha256"])
        if placement in placements and placements[placement] != identity:
            raise ValueError("placement leaks across splits or snapshots")
        placements[placement] = identity
        pose = tuple(scene["cup_pose"] + scene["place_pose"])
        if pose in poses and poses[pose] != split:
            raise ValueError("same physical placement leaks across splits")
        poses[pose] = split
        if type(entry["accepted"]) is not bool:
            raise ValueError("explicit accepted boolean required")
        if not entry["accepted"]:
            if not entry["exclusion_reason"].strip():
                raise ValueError("excluded episode needs a reason")
            excluded.append(entry)
            continue
        if (entry["task_success"] is not True or type(entry["sequence_exit_code"]) is not int
                or entry["sequence_exit_code"] != 0 or entry["exclusion_reason"]):
            raise ValueError("accepted episode needs explicit human success and sequence exit 0")
        if entry["foundation_revision"] != contract["foundation_revision"] or not entry["pai_revision"]:
            raise ValueError("trial execution revisions required")
        world = resolve(manifest_path.parent, entry["world"])
        if digest(world) != entry["world_sha256"]:
            raise ValueError("world snapshot hash mismatch")
        raw = resolve(manifest_path.parent, entry["raw_path"])
        metadata = load(raw / "episode.json")
        if (type(metadata["schema_version"]) is not int or metadata["schema_version"] != 2
                or metadata["status"] != "complete" or metadata["model"]["id"] != contract["model"]
                or metadata["clock"]["use_sim_time"] is not True
                or metadata["provenance"]["backend"] != "gazebo"):
            raise ValueError("complete Gazebo simulation raw schema v2 / matching model required")
        episode_id = entry["episode_id"]
        if episode_id != metadata["episode_id"] or episode_id in ids or raw in paths:
            raise ValueError("duplicate episode/raw path or episode ID mismatch")
        ids.add(episode_id)
        paths.add(raw)
        before = hashes(raw)
        validator_report = validate(raw)
        names = contract["joint_names"]
        if ([*metadata["command"]["joints"], *metadata["left_command"]["joints"],
             *metadata["right_command"]["joints"]] != names
                or any(n not in metadata["state"]["joints"] for n in names)):
            raise ValueError("raw model command order differs from external8 contract")
        streams = {n: [parse_json(line) for line in (raw / f"{n}.jsonl").read_text().splitlines()]
                   for n in (*OBSERVATIONS, *COMMANDS)}
        frames = align(streams, contract["timing"])
        for frame in frames:
            rows = {n: streams[n][i] for n, i in frame["indices"].items()}
            frame["state"] = [rows["state"]["positions"][metadata["state"]["joints"].index(n)] for n in names]
            frame["action"] = sum((rows[n]["positions"] for n in COMMANDS), [])
            frame["rgb_path"] = rows["rgb"]["path"]
            frame["rgb_sha256"] = before[frame["rgb_path"]]
        accepted.append({"entry": entry, "raw": raw, "raw_hashes": before, "raw_metadata": metadata,
                         "validator": validator_report, "frames": frames})
    if not accepted:
        raise ValueError("no accepted episodes")
    return accepted, excluded


def convert(manifest, output, contract=None, dataset_class=None):
    contract = load_contract(contract)
    accepted, excluded = inspect_manifest(manifest, contract)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output exists; implicit overwrite/append forbidden")
    selected = {s: [e for e in accepted if e["entry"]["split"] == s] for s in ("train", "validation")}
    if any(not rows for rows in selected.values()):
        raise ValueError("separate nonempty train and validation placements required")
    offline()
    if dataset_class is None:
        verify_lerobot()
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        dataset_class = LeRobotDataset
    import numpy as np
    from PIL import Image

    features = {
        contract["state_key"]: {"dtype": "float32", "shape": (8,), "names": contract["joint_names"]},
        contract["action_key"]: {"dtype": "float32", "shape": (8,), "names": contract["joint_names"]},
        contract["image_key"]: {"dtype": "image", "shape": tuple(contract["image_shape_hwc"]),
                                "names": ["height", "width", "channels"]},
    }
    output.mkdir(parents=True)
    report = {"version": 1, "status": "in_progress", "contract": contract,
              "manifest_sha256": digest(manifest), "excluded": excluded,
              "pai_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
              "storage": "lossless image (no video codec)", "splits": {},
              "heldout_reserved": [e["entry"] for e in accepted if e["entry"]["split"] == "heldout"]}
    report_path = output / "conversion_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    for split, episodes in selected.items():
        root, repo_id = output / split, f"lifth/cup-{split}"
        writer = dataset_class.create(repo_id=repo_id, root=root, fps=15, features=features,
                                      robot_type=contract["model"], use_videos=False, video_backend="pyav")
        try:
            for episode in episodes:
                for frame in episode["frames"]:
                    with Image.open(episode["raw"] / frame["rgb_path"]) as image:
                        rgb = np.array(image)
                    writer.add_frame({contract["state_key"]: np.array(frame["state"], dtype=np.float32),
                                      contract["action_key"]: np.array(frame["action"], dtype=np.float32),
                                      contract["image_key"]: rgb, "task": contract["task"]})
                writer.save_episode()
        finally:
            writer.finalize()
        # Reload via the same official reader, check every frame and its color/channel ordering.
        reader = dataset_class(repo_id=repo_id, root=root, video_backend="pyav")
        flat = [(episode, frame) for episode in episodes for frame in episode["frames"]]
        if len(reader) != len(flat):
            raise ValueError("reloaded frame count mismatch")
        for index, (episode, frame) in enumerate(flat):
            row = reader[index]
            for key, expected in ((contract["state_key"], frame["state"]), (contract["action_key"], frame["action"])):
                np.testing.assert_array_equal(row[key].numpy(), np.array(expected, dtype=np.float32))
            with Image.open(episode["raw"] / frame["rgb_path"]) as image:
                expected_rgb = np.array(image).transpose(2, 0, 1).astype(np.float32) / 255
                np.testing.assert_array_equal(row[contract["image_key"]].numpy(), expected_rgb)
            if row["task"] != contract["task"]:
                raise ValueError("reloaded task mismatch")
        split_report = {"root": str(root), "repo_id": repo_id, "frames": len(flat), "episodes": []}
        for episode in episodes:
            if hashes(episode["raw"]) != episode["raw_hashes"]:
                raise ValueError("raw changed during conversion")
            split_report["episodes"].append({"acceptance": episode["entry"], "raw_path": str(episode["raw"]),
                "raw_hashes": episode["raw_hashes"], "validator": episode["validator"],
                "raw_provenance": episode["raw_metadata"]["provenance"],
                "raw_model": episode["raw_metadata"]["model"],
                "first_observation_time_ns": episode["frames"][0]["observation_time_ns"],
                "last_observation_time_ns": episode["frames"][-1]["observation_time_ns"],
                "alignment": episode["frames"]})
        report["splits"][split] = split_report
        (root / "conversion_provenance.json").write_text(json.dumps({"split": split, "contract": contract,
            "manifest_sha256": report["manifest_sha256"], "stats_sha256": digest(root / "meta/stats.json")}, indent=2) + "\n")
    report["status"] = "complete"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--timing", type=Path, help="full timing object; otherwise retain shared candidate timing")
    parser.add_argument("--check-only", action="store_true", help="upstream raw validation and causal alignment; no ML import")
    args = parser.parse_args()
    contract = load_contract()
    if args.timing:
        contract["timing"] = upstream()[0](args.timing)
    contract = load_contract(contract)
    if args.check_only:
        accepted, excluded = inspect_manifest(args.manifest, contract)
        print(json.dumps({"accepted": len(accepted), "excluded": len(excluded), "timing": contract["timing"],
                          "frames": {e["entry"]["episode_id"]: len(e["frames"]) for e in accepted}}, indent=2))
    else:
        convert(args.manifest, args.output, contract)


if __name__ == "__main__":
    main()
