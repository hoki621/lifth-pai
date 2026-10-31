"""Seal one manually supplied Issue #4 result with local artifact SHA-256 inventories.

This does not run a validator, converter, trainer, policy, or ROS process.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


STAGES = {
    "collection": {"raw_episode", "raw_validation_report", "selection", "scene"},
    "conversion": {"raw_episode", "raw_validation_report", "selection", "dataset", "dataset_report", "contract"},
    "training": {"dataset_report", "train_config", "checkpoint", "processors", "lock", "model_snapshot"},
    "reload": {"checkpoint", "processors", "reload_input", "reload_report", "contract"},
    "transport": {"transport_report", "contract"},
    "stops": {"stop_report", "contract"},
    "policy_trial": {"checkpoint", "processors", "trial_report", "scene", "contract"},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def digest(path):
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def inventory(path, allow_file_symlinks=False):
    require(not path.is_symlink(), f"symlink artifact: {path}")
    require(path.exists(), f"missing artifact: {path}")
    paths = sorted(path.rglob("*")) if path.is_dir() else [path]
    files = []
    for child in paths:
        target = None
        if child.is_symlink():
            require(allow_file_symlinks and child.is_file(), f"symlink artifact: {child}")
            target = str(child.resolve(strict=True))
        if child.is_dir():
            continue
        require(child.is_file(), f"not a regular file: {child}")
        before = child.stat()
        sha256 = digest(child)
        after = child.stat()
        require((before.st_size, before.st_mtime_ns, before.st_ino) ==
                (after.st_size, after.st_mtime_ns, after.st_ino), f"artifact changed: {child}")
        files.append({"path": child.relative_to(path).as_posix() if path.is_dir() else child.name,
                      "size_bytes": after.st_size, "sha256": sha256})
        if target is not None:
            require(str(child.resolve(strict=True)) == target, f"symlink changed: {child}")
            files[-1]["symlink_target"] = target
    require(files, f"empty artifact: {path}")
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"path": str(path), "files": files,
            "inventory_sha256": hashlib.sha256(canonical).hexdigest()}


def git_state(repository):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repository), *args])

    return {
        "commit": git("rev-parse", "HEAD").decode().strip(),
        "status": git("status", "--porcelain", "--untracked-files=all").decode(),
        "tracked_diff_sha256": hashlib.sha256(git("diff", "HEAD", "--binary")).hexdigest(),
    }


def record(spec, base, repository):
    require(spec.get("version") == 1, "record input version must be 1")
    require(isinstance(spec.get("run_id"), str) and
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", spec["run_id"]), "invalid run_id")
    require(type(spec.get("seed")) is int, "integer seed required")
    require(isinstance(spec.get("placements"), list), "placements list required")
    placement_ids = set()
    raw_placements = set()
    for placement in spec["placements"]:
        require(isinstance(placement, dict) and nonempty(placement.get("id")), "placement ID required")
        require(placement["id"] not in placement_ids, "duplicate placement ID (including across splits)")
        placement_ids.add(placement["id"])
        require(placement.get("split") in ("train", "validation", "heldout"), "invalid placement split")
        raw_ids = placement.get("raw_artifacts")
        require(isinstance(raw_ids, list) and all(nonempty(x) for x in raw_ids),
                "placement raw_artifacts list required")
        for raw_id in raw_ids:
            require(raw_id not in raw_placements, "raw episode assigned to multiple placements/splits")
            raw_placements.add(raw_id)
    require(isinstance(spec.get("runtime_blockers"), list) and
            all(nonempty(x) for x in spec["runtime_blockers"]), "runtime_blockers must be strings")
    artifacts = spec.get("artifacts")
    require(isinstance(artifacts, dict), "artifacts object required")
    captured = {}
    raw_paths = set()
    episode_ids = set()
    for name, artifact in artifacts.items():
        require(nonempty(name) and isinstance(artifact, dict), "invalid artifact")
        require(nonempty(artifact.get("role")) and nonempty(artifact.get("path")),
                f"artifact {name}: role and path required")
        path = base / artifact["path"]
        captured[name] = {"role": artifact["role"],
                          **inventory(path.absolute(), allow_file_symlinks=artifact["role"] == "model_snapshot")}
        if artifact["role"] == "raw_episode":
            # Metadata for provenance only; upstream validate() remains authoritative.
            manifest = json.loads((path / "episode.json").read_text())
            require(path.resolve() not in raw_paths, "raw episode path aliased by multiple artifacts")
            raw_paths.add(path.resolve())
            episode_id = manifest.get("episode_id")
            require(nonempty(episode_id), "raw manifest episode_id required")
            require(episode_id not in episode_ids, "raw manifest episode_id aliased by multiple artifacts")
            episode_ids.add(episode_id)
            captured[name]["manifest"] = {
                key: manifest.get(key) for key in ("episode_id", "schema_version", "status", "model", "provenance")
            }

    contracts = [name for name, artifact in captured.items() if artifact["role"] == "contract"]
    require(len(contracts) == 1, "exactly one contract artifact required")
    contract = json.loads((base / artifacts[contracts[0]]["path"]).read_text())
    foundation = git_state(repository / "external/lifth_arm_gen2")
    require(contract.get("foundation_revision") == foundation["commit"], "contract/foundation revision mismatch")
    require(nonempty(contract.get("model")), "contract model required")
    for placement in spec["placements"]:
        scene = captured.get(placement.get("scene_artifact"), {})
        require(scene.get("role") == "scene", "placement scene_artifact required")
        snapshot = json.loads(Path(scene["path"]).read_text())
        require(snapshot.get("placement_id") == placement["id"] and snapshot.get("split") == placement["split"],
                "placement ID/split differs from scene snapshot")
        for raw_id in placement["raw_artifacts"]:
            require(captured.get(raw_id, {}).get("role") == "raw_episode", "placement raw artifact missing")
    for name, artifact in captured.items():
        if artifact["role"] == "raw_episode":
            require(name in raw_placements, "raw episode must link to a placement/split")
            manifest = artifact["manifest"]
            require(manifest.get("schema_version") == 2, "raw schema v2 required")
            require(isinstance(manifest.get("model"), dict) and
                    manifest["model"].get("id") == contract["model"], "raw/contract model mismatch")

    stages = spec.get("stages")
    require(isinstance(stages, dict) and set(stages) == set(STAGES), "all seven stages required")
    for name, stage in stages.items():
        require(isinstance(stage, dict), f"{name}: stage object required")
        status = stage.get("status")
        require(status in ("passed", "failed", "not_run", "blocked"), f"{name}: invalid status")
        require(nonempty(stage.get("reason")), f"{name}: reason required")
        evidence = stage.get("evidence", [])
        require(isinstance(evidence, list) and all(isinstance(x, str) and x in captured for x in evidence),
                f"{name}: unknown evidence artifact")
        if status in ("passed", "failed"):
            require(isinstance(stage.get("command"), list) and stage["command"] and
                    all(nonempty(x) for x in stage["command"]), f"{name}: actual command argv required")
            require(type(stage.get("exit_code")) is int, f"{name}: exit_code required")
            require(status != "passed" or stage["exit_code"] == 0, f"{name}: passed with nonzero exit")
            for key in ("started_at", "finished_at"):
                require(nonempty(stage.get(key)), f"{name}: {key} required")
            start = datetime.fromisoformat(stage["started_at"])
            end = datetime.fromisoformat(stage["finished_at"])
            require(start.tzinfo is not None and end.tzinfo is not None and start <= end,
                    f"{name}: ordered timestamps with timezone required")
            roles = {captured[x]["role"] for x in evidence}
            require({"runtime_versions", "log", "source"} <= roles,
                    f"{name}: runtime_versions, log, source evidence required")
            if status == "passed":
                require(STAGES[name] <= roles, f"{name}: missing required artifact roles {STAGES[name] - roles}")
                if name in ("collection", "conversion", "policy_trial"):
                    require(placement_ids, f"{name}: placements required")
                    scenes = {p["scene_artifact"] for p in spec["placements"]}
                    for item in evidence:
                        if captured[item]["role"] == "scene":
                            require(item in scenes, f"{name}: scene must link to a placement")
                        if name != "policy_trial" and captured[item]["role"] == "raw_episode":
                            require(captured[item]["manifest"]["status"] == "complete",
                                    f"{name}: passed with incomplete raw")
        else:
            require(stage.get("exit_code") is None, f"{name}: unrun stage cannot have exit_code")

    task = spec.get("manual_task")
    require(isinstance(task, dict) and task.get("outcome") in
            ("success", "failure", "unknown", "not_run"), "manual_task outcome required")
    require(nonempty(task.get("reason")), "manual_task reason required")
    require(isinstance(task.get("evidence"), list) and
            all(isinstance(x, str) and x in captured for x in task["evidence"]), "manual_task evidence invalid")
    if task["outcome"] in ("success", "failure"):
        require(nonempty(task.get("observer")) and task["evidence"], "manual outcome needs observer and evidence")
        require(stages["policy_trial"]["status"] in ("passed", "failed"),
                "manual outcome requires an executed policy_trial")

    for earlier, later, roles in (
        ("collection", "conversion", {"raw_episode", "selection"}),
        ("conversion", "training", {"dataset_report"}),
        ("training", "reload", {"checkpoint", "processors"}),
        ("reload", "policy_trial", {"checkpoint", "processors"}),
    ):
        if stages[earlier]["status"] == stages[later]["status"] == "passed":
            for role in roles:
                previous = {x for x in stages[earlier]["evidence"] if captured[x]["role"] == role}
                current = {x for x in stages[later]["evidence"] if captured[x]["role"] == role}
                require(current <= previous, f"{earlier}/{later}: {role} lineage mismatch")

    return {**spec, "recorded_at": datetime.now(timezone.utc).isoformat(),
            "recorder_sha256": digest(Path(__file__)),
            "recording_repository": git_state(repository), "recording_foundation": foundation,
            "artifacts": captured,
            "pipeline_complete": all(stage["status"] == "passed" for stage in stages.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="result input JSON; artifact paths relative to this file")
    parser.add_argument("--output", type=Path, required=True, help="new immutable result JSON")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    result = record(spec, args.spec.absolute().parent, Path(__file__).resolve().parents[1])
    result["input_sha256"] = digest(args.spec)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(encoded)
    print(args.output)


if __name__ == "__main__":
    main()
