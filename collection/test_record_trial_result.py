"""CPU-only tests of result provenance and honest execution states."""

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from record_trial_result import STAGES, inventory, record


REPOSITORY = Path(__file__).resolve().parents[1]


class TrialResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.spec = json.loads((REPOSITORY / "configs/issue4-result.json").read_text())
        contract = (REPOSITORY / "configs/policy_contract.json").read_text()
        (self.base / "contract").write_text(contract)
        self.spec["artifacts"]["contract"]["path"] = "contract"

    def artifact(self, name, role, content="evidence"):
        (self.base / name).write_text(content)
        self.spec["artifacts"][name] = {"role": role, "path": name}
        return name

    def raw(self):
        raw = self.base / "episode"
        raw.mkdir()
        manifest = {"episode_id": "example", "schema_version": 2, "status": "incomplete",
                    "model": {"id": "v2_1_1"}}
        (raw / "episode.json").write_text(json.dumps(manifest))
        (raw / "left_command.jsonl").write_text("{}\n")
        self.spec["artifacts"]["raw"] = {"role": "raw_episode", "path": "episode"}
        scene = self.artifact("scene", "scene", json.dumps({"placement_id": "baseline", "split": "train"}))
        self.spec["placements"] = [{"id": "baseline", "split": "train",
                                    "raw_artifacts": ["raw"], "scene_artifact": scene}]
        return raw

    def executed(self, stage, status="passed"):
        evidence = []
        for role in sorted(STAGES[stage] | {"runtime_versions", "log", "source"}):
            if role == "raw_episode":
                evidence.append("raw")
            elif role == "contract":
                evidence.append("contract")
            elif role in self.spec["artifacts"]:
                evidence.append(role)
            else:
                evidence.append(self.artifact(role, role))
        self.spec["stages"][stage] = {
            "status": status, "reason": "Observed test result", "evidence": evidence,
            "command": ["python3", "example.py"], "exit_code": 0,
            "started_at": "2026-11-01T01:00:00+00:00", "finished_at": "2026-11-01T01:01:00+00:00",
        }

    def test_preparation_does_not_claim_completion(self):
        result = record(self.spec, self.base, REPOSITORY)
        self.assertFalse(result["pipeline_complete"])
        self.assertEqual(result["manual_task"]["outcome"], "not_run")
        self.assertEqual(len(result["recording_foundation"]["commit"]), 40)

    def test_inventory_hashes_every_file_and_changes_with_content(self):
        directory = self.base / "checkpoint"
        directory.mkdir()
        (directory / "weights").write_bytes(b"weights")
        (directory / "processors").mkdir()
        (directory / "processors/config.json").write_text("{}")
        first = inventory(directory)
        self.assertEqual([x["path"] for x in first["files"]], ["processors/config.json", "weights"])
        self.assertEqual(first["files"][1]["sha256"], hashlib.sha256(b"weights").hexdigest())
        (directory / "weights").write_bytes(b"new")
        self.assertNotEqual(first["inventory_sha256"], inventory(directory)["inventory_sha256"])

    def test_missing_empty_and_symlink_artifacts_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing artifact"):
            inventory(self.base / "missing")
        empty = self.base / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "empty artifact"):
            inventory(empty)
        (empty / "file").write_text("x")
        (empty / "link").symlink_to(empty / "file")
        with self.assertRaisesRegex(ValueError, "symlink"):
            inventory(empty)

    def test_local_snapshot_file_symlink_records_target_and_content(self):
        snapshot = self.base / "snapshot"
        snapshot.mkdir()
        blob = self.base / "blob"
        blob.write_bytes(b"local weights")
        (snapshot / "model.safetensors").symlink_to(blob)
        result = inventory(snapshot, allow_file_symlinks=True)
        self.assertEqual(result["files"][0]["symlink_target"], str(blob))
        self.assertEqual(result["files"][0]["sha256"], hashlib.sha256(b"local weights").hexdigest())
        (snapshot / "directory").symlink_to(self.base, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            inventory(snapshot, allow_file_symlinks=True)

    def test_successful_reload_requires_real_linked_evidence(self):
        self.executed("reload")
        result = record(self.spec, self.base, REPOSITORY)
        self.assertEqual(result["stages"]["reload"]["status"], "passed")
        self.assertEqual(result["manual_task"]["outcome"], "not_run")
        self.spec["stages"]["reload"]["evidence"].remove("processors")
        with self.assertRaisesRegex(ValueError, "missing required artifact"):
            record(self.spec, self.base, REPOSITORY)

    def test_failed_stage_preserves_reason_without_checkpoint(self):
        self.executed("training", "failed")
        stage = self.spec["stages"]["training"]
        stage["exit_code"] = 1
        stage["reason"] = "Out of memory before checkpoint save"
        stage["evidence"].remove("checkpoint")
        result = record(self.spec, self.base, REPOSITORY)
        self.assertEqual(result["stages"]["training"]["exit_code"], 1)
        self.assertFalse(result["pipeline_complete"])

    def test_inconsistent_status_and_manual_outcomes_rejected(self):
        self.executed("reload")
        valid = copy.deepcopy(self.spec)
        for key, value in (("exit_code", 1), ("evidence", ["missing"]),
                           ("started_at", "2026-11-02T00:00:00+00:00"), ("command", [])):
            self.spec = copy.deepcopy(valid)
            self.spec["stages"]["reload"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                record(self.spec, self.base, REPOSITORY)
        self.spec = valid
        self.spec["manual_task"] = {
            "outcome": "success", "reason": "looked successful", "observer": "operator", "evidence": ["log"]}
        with self.assertRaisesRegex(ValueError, "executed policy_trial"):
            record(self.spec, self.base, REPOSITORY)

    def test_raw_manifest_link_does_not_assert_validator_success(self):
        self.raw()
        result = record(self.spec, self.base, REPOSITORY)
        self.assertEqual(result["artifacts"]["raw"]["manifest"]["status"], "incomplete")
        self.assertEqual(len(result["artifacts"]["raw"]["files"]), 2)
        self.assertEqual(result["stages"]["conversion"]["status"], "blocked")
        self.executed("conversion")
        with self.assertRaisesRegex(ValueError, "incomplete raw"):
            record(self.spec, self.base, REPOSITORY)

    def test_placement_split_and_episode_leakage_rejected(self):
        self.raw()
        valid = copy.deepcopy(self.spec)
        for change in ("duplicate", "split", "raw", "scene"):
            self.spec = copy.deepcopy(valid)
            placement = self.spec["placements"][0]
            if change in ("duplicate", "raw"):
                other = {**placement, "split": "validation"}
                if change == "raw":
                    other["id"] = "other"
                self.spec["placements"].append(other)
            elif change == "split":
                placement["split"] = "test"
            else:
                placement["scene_artifact"] = "missing"
            with self.subTest(change=change), self.assertRaises(ValueError):
                record(self.spec, self.base, REPOSITORY)

    def test_scene_snapshot_cannot_be_relabelled(self):
        self.raw()
        for key, value in (("split", "validation"), ("id", "different")):
            valid = copy.deepcopy(self.spec)
            self.spec["placements"][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "scene snapshot"):
                record(self.spec, self.base, REPOSITORY)
            self.spec = valid

    def test_exact_heldout_spelling_accepted(self):
        self.raw()
        self.spec["placements"][0]["split"] = "heldout"
        (self.base / "scene").write_text(json.dumps({"placement_id": "baseline", "split": "heldout"}))
        result = record(self.spec, self.base, REPOSITORY)
        self.assertEqual(result["placements"][0]["split"], "heldout")
        self.spec["placements"][0]["split"] = "held-out"
        with self.assertRaisesRegex(ValueError, "invalid placement split"):
            record(self.spec, self.base, REPOSITORY)

    def test_raw_path_and_episode_id_aliases_rejected_across_splits(self):
        self.raw()
        self.artifact("scene2", "scene", json.dumps({"placement_id": "second", "split": "validation"}))
        self.spec["placements"].append({"id": "second", "split": "validation",
                                        "scene_artifact": "scene2", "raw_artifacts": ["alias"]})
        self.spec["artifacts"]["alias"] = {"role": "raw_episode", "path": "episode/../episode"}
        with self.assertRaisesRegex(ValueError, "path aliased"):
            record(self.spec, self.base, REPOSITORY)
        shutil.copytree(self.base / "episode", self.base / "copied")
        self.spec["artifacts"]["alias"]["path"] = "copied"
        with self.assertRaisesRegex(ValueError, "episode_id aliased"):
            record(self.spec, self.base, REPOSITORY)

    def test_contract_foundation_and_raw_model_mismatch_rejected(self):
        self.raw()
        raw = self.base / "episode/episode.json"
        manifest = json.loads(raw.read_text())
        manifest["model"]["id"] = "v2_1_0"
        raw.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "model mismatch"):
            record(self.spec, self.base, REPOSITORY)
        contract = json.loads((self.base / "contract").read_text())
        contract["foundation_revision"] = "0" * 40
        (self.base / "contract").write_text(json.dumps(contract))
        with self.assertRaisesRegex(ValueError, "foundation revision mismatch"):
            record(self.spec, self.base, REPOSITORY)

    def test_cli_writes_exclusively_and_records_input_hash(self):
        spec = self.base / "input.json"
        spec.write_text(json.dumps(self.spec))
        output = self.base / "result.json"
        command = ["python3", str(REPOSITORY / "collection/record_trial_result.py"),
                   str(spec), "--output", str(output)]
        first = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        result = json.loads(output.read_text())
        self.assertEqual(result["input_sha256"], hashlib.sha256(spec.read_bytes()).hexdigest())
        before = output.read_bytes()
        second = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(output.read_bytes(), before)

    def test_checkpoint_lineage_cannot_change_between_training_and_reload(self):
        self.executed("training")
        self.executed("reload")
        record(self.spec, self.base, REPOSITORY)
        self.artifact("different_checkpoint", "checkpoint")
        evidence = self.spec["stages"]["reload"]["evidence"]
        evidence.remove("checkpoint")
        evidence.append("different_checkpoint")
        with self.assertRaisesRegex(ValueError, "lineage mismatch"):
            record(self.spec, self.base, REPOSITORY)

    def test_policy_trial_requires_recorded_scene_and_keeps_manual_failure_distinct(self):
        self.executed("policy_trial")
        with self.assertRaisesRegex(ValueError, "placements required"):
            record(self.spec, self.base, REPOSITORY)
        self.raw()
        self.spec["manual_task"] = {"outcome": "failure", "reason": "Cup fell despite successful action delivery",
                                     "observer": "operator", "evidence": ["trial_report"]}
        result = record(self.spec, self.base, REPOSITORY)
        self.assertEqual(result["stages"]["policy_trial"]["status"], "passed")
        self.assertEqual(result["manual_task"]["outcome"], "failure")


if __name__ == "__main__":
    unittest.main()
