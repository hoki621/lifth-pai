"""Exercise the real pinned raw v2 validator with synthetic RGB and independent commands."""

import copy
import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from common import REPO, load_contract, upstream
from convert_raw import convert, digest, inspect_manifest

class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contract = load_contract()
        from lifth_dataset.schema import metadata_v2
        from lifth_dataset.storage import Episode

        load = upstream()[0]
        fixture = REPO / "external/lifth_arm_gen2/src/lifth_dataset/test/fixtures/complete"
        old = load(fixture / "episode.json")
        model = {"id": "v2_1_1", "robot_name": "fixture", "package": "test_description", "version": "fixture",
                 "arm_joints": self.contract["joint_names"][:6], "passive_joints": [], "base_frame": "base_link",
                 "tcp_frame": "EE_1", "gripper": {"left": {"joint": "ee_f1", "tip_frame": "left_tip"},
                                                  "right": {"joint": "ee_f2", "tip_frame": "right_tip"}}}
        xml = ET.parse(fixture / "model.urdf").getroot()
        xml.set("name", "fixture")
        xml.set("lifth_model_id", "v2_1_1")
        for frame in ("base_link", "EE_1", "left_tip", "right_tip"):
            if xml.find(f"link[@name='{frame}']") is None:
                ET.SubElement(xml, "link", name=frame)
        xml = ET.tostring(xml, encoding="unicode")
        metadata = metadata_v2("test cup", xml, old["camera"], "gazebo", True, old["provenance"], model)
        ep = Episode(self.root / "raw", metadata, xml, 1_000_000_000, 2_000_000_000)
        for stream, positions in (("state", [1., 2., 3., 4., 5., 6., .01, -.02]),
                                   ("command", [.1, .2, .3, .4, .5, .6]),
                                   ("left_command", [.001]), ("right_command", [-.002])):
            for i in range(21):
                delta = i * 20_000_000
                ep.add(stream, 1_000_000_000 + delta, 1_000_000_000 + delta,
                       2_000_000_000 + delta, positions)
        for i in range(7):
            delta = i * 1_000_000_000 // 15
            ep.add("rgb", 1_000_000_000 + delta, 1_000_000_000 + delta,
                   2_000_000_000 + delta, bytes([13, 29, 47]) * (640 * 360))
        result = ep.finish("complete", 1_500_000_000, 2_500_000_000)
        self.assertEqual(result["status"], "complete", result["errors"])
        scene = self.root / "scene.json"
        scene.write_bytes((REPO / "configs/cup_placements/baseline.json").read_bytes())
        config = load(scene)
        world = self.root / "world.sdf"
        world.write_text("<sdf/>")
        self.entry = {"placement_id": "baseline", "split": "train", "scene": str(scene),
                      "scene_sha256": digest(scene), "world": str(world), "world_sha256": digest(world),
                      "cup_pose": config["cup_pose"], "place_pose": config["place_pose"],
                      "pai_revision": "0" * 40, "foundation_revision": self.contract["foundation_revision"],
                      "raw_path": str(ep.path), "episode_id": result["episode_id"],
                      "accepted": True, "task_success": True, "sequence_exit_code": 0, "exclusion_reason": ""}
        self.manifest = self.root / "acceptance.json"

    def inspect(self, entries=None):
        self.manifest.write_text(json.dumps({"version": 1, "episodes": entries or [self.entry]}))
        return inspect_manifest(self.manifest, self.contract)

    def test_actual_validator_and_external8_commands_not_state(self):
        episodes, excluded = self.inspect()
        self.assertEqual(excluded, [])
        self.assertEqual(len(episodes[0]["frames"]), 7)
        frame = episodes[0]["frames"][2]
        self.assertEqual(frame["action"], [.1, .2, .3, .4, .5, .6, .001, -.002])
        self.assertNotEqual(frame["state"], frame["action"])
        self.assertEqual(episodes[0]["validator"]["episode_id"], self.entry["episode_id"])

    def test_failed_missing_label_duplicate_and_wrong_snapshot_rejected(self):
        for changes in ({"task_success": False}, {"task_success": None}, {"sequence_exit_code": 1},
                        {"scene_sha256": "wrong"}, {"split": "validation"}, {"world_sha256": "wrong"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.inspect([{**self.entry, **changes}])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.inspect([self.entry, copy.deepcopy(self.entry)])
        entry = copy.deepcopy(self.entry)
        del entry["task_success"]
        with self.assertRaises(KeyError):
            self.inspect([entry])

    def test_split_leak_and_exclusion_reason(self):
        other = copy.deepcopy(self.entry)
        scene = json.loads(Path(other["scene"]).read_text())
        scene["split"] = "validation"
        scene_path = self.root / "other_scene.json"
        scene_path.write_text(json.dumps(scene))
        other.update(scene=str(scene_path), scene_sha256=digest(scene_path), split="validation")
        with self.assertRaisesRegex(ValueError, "placement leaks"):
            self.inspect([self.entry, other])
        with self.assertRaisesRegex(ValueError, "reason"):
            self.inspect([{**self.entry, "accepted": False}])
        accepted, excluded = self.inspect([self.entry, {**self.entry, "accepted": False, "exclusion_reason": "slip"}])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(excluded[0]["exclusion_reason"], "slip")

    def test_schema_unknown_incomplete_missing_finger_and_corruption_rejected(self):
        raw = Path(self.entry["raw_path"])
        metadata_path = raw / "episode.json"
        original = metadata_path.read_text()
        for changes in ({"schema_version": 1}, {"schema_version": 3}, {"schema_version": True}, {"status": "incomplete"}):
            metadata = json.loads(original)
            metadata.update(changes)
            metadata_path.write_text(json.dumps(metadata))
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.inspect()
        metadata_path.write_text(original)
        finger = raw / "right_command.jsonl"
        finger.write_text("")
        with self.assertRaisesRegex(ValueError, "empty|count"):
            self.inspect()

    @unittest.skipUnless(importlib.util.find_spec("lerobot") and importlib.util.find_spec("numpy"),
                         "requires the pinned ML environment")
    def test_official_writer_finalize_reload_and_independent_split_stats(self):
        other = ConversionTests("test_actual_validator_and_external8_commands_not_state")
        other.setUp()
        self.addCleanup(other.doCleanups)
        entry = other.entry
        scene_path = Path(entry["scene"])
        scene = json.loads(scene_path.read_text())
        scene.update(placement_id="test-validation", split="validation")
        scene["cup_pose"][0] += .02
        scene_path.write_text(json.dumps(scene))
        entry.update(placement_id=scene["placement_id"], split="validation", cup_pose=scene["cup_pose"],
                     scene_sha256=digest(scene_path))
        self.manifest.write_text(json.dumps({"version": 1, "episodes": [self.entry, entry]}))
        output = self.root / "official-v3"
        report = convert(self.manifest, output, self.contract)
        self.assertEqual(report["status"], "complete")
        for split in ("train", "validation"):
            self.assertEqual(report["splits"][split]["frames"], 7)
            self.assertTrue((output / split / "meta/stats.json").is_file())
        self.assertFalse((output / "heldout").exists())
        with self.assertRaisesRegex(ValueError, "output exists"):
            convert(self.manifest, output, self.contract)


if __name__ == "__main__":
    unittest.main()
