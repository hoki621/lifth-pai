"""Candidate geometry and immutable per-trial snapshots, without ROS or real assets."""

import json
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from cup_sequence import validate_scene_world
from prepare_cup_trial import REPO, prepare_trial, sha256


def body_center(pose):
    x, y, _, _, _, yaw = pose
    return x + .0165 * math.cos(yaw) + .0018 * math.sin(yaw), y + .0165 * math.sin(yaw) - .0018 * math.cos(yaw)


class TrialTests(unittest.TestCase):
    def test_all_explicit_scenes_keep_grasp_and_fixed_destination(self):
        baseline = json.loads((REPO / "configs/cup_scene.json").read_text())
        for path in sorted((REPO / "configs/cup_placements").glob("*.json")):
            scene = json.loads(path.read_text())
            with self.subTest(scene=scene["placement_id"]):
                self.assertEqual(scene["physical_validation"], "pending")
                self.assertEqual(scene["cup_pose"][5], scene["place_pose"][5])
                for actual, expected in zip(body_center(scene["place_pose"]), body_center(baseline["place_pose"])):
                    self.assertAlmostEqual(actual, expected)
                originals = {step["name"]: step for step in baseline["steps"]}
                for step in scene["steps"]:
                    if step["name"] == "preapproach":
                        self.assertEqual(step["pose"], originals["approach"]["pose"])
                        continue
                    original = originals[step["name"]]
                    if "gripper" in step:
                        self.assertEqual(step, original)
                        continue
                    target = step.get("pose", step.get("cartesian"))
                    reference = original.get("pose", original.get("cartesian"))
                    self.assertEqual(target[2], reference[2])
                    yaw = scene["cup_pose"][5]
                    qx, qy, qz, qw = target[3:]
                    self.assertAlmostEqual(qx*qx + qy*qy, 1)
                    self.assertEqual([qz, qw], [0, 0])
                    parallel = (qx*qx-qy*qy)*math.cos(yaw) + 2*qx*qy*math.sin(yaw)
                    self.assertAlmostEqual(abs(parallel), 1)
                    if step["name"] in ("approach", "lower", "grasp_pose", "lift"):
                        for i in (0, 1):
                            self.assertAlmostEqual(target[i] - body_center(scene["cup_pose"])[i],
                                                   -.070 * (math.cos(yaw) if i == 0 else math.sin(yaw)))
                    elif step["name"] in ("transfer", "place", "retreat"):
                        for i in (0, 1):
                            self.assertAlmostEqual(target[i] - body_center(scene["place_pose"])[i],
                                                   -.070 * (math.cos(yaw) if i == 0 else math.sin(yaw)))
                    else:
                        self.assertEqual(target[:3], reference[:3])
                if scene["placement_id"] == "baseline":
                    self.assertEqual(scene["steps"], baseline["steps"])
                    self.assertEqual(scene["cup_pose"], baseline["cup_pose"])

    def test_snapshot_world_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, assets = root / "base.sdf", root / "assets"
            assets.mkdir()
            (assets / "meshes").mkdir()
            (assets / "meshes/model.obj").write_text("v -.05 -.05 0\nv .05 .05 .1\n")
            (assets / "model.sdf").write_text('<sdf><model name="Threshold_Porcelain_Coffee_Mug_All_Over_Bead_White"><link name="cup"/></model></sdf>')
            base.write_text('<sdf version="1.9"><world name="lifth"/></sdf>')
            scene = REPO / "configs/cup_placements/yaw_plus.json"
            trial = prepare_trial(scene, root / "trial", base, assets)
            config = json.loads(Path(trial["scene"]).read_text())
            self.assertEqual(sha256(scene), trial["scene_sha256"])
            self.assertEqual(sha256(trial["world"]), trial["world_sha256"])
            self.assertIsNone(trial["task_success"])
            self.assertFalse(trial["accepted"])
            validate_scene_world(config, trial["world"])
            world = ET.parse(trial["world"])
            floor = world.find("world/model[@name='pai_floor']/link")
            self.assertEqual(len(floor.findall('collision')), 1)
            self.assertEqual(floor.findtext('collision/geometry/box/size'), '0.96 0.90 0.03')
            self.assertIsNone(floor.find('collision/geometry/cylinder'))
            marker = floor.find("visual[@name='target_region']")
            self.assertEqual(marker.findtext('geometry/box/size'), '0.16 0.16 0.0002')
            xy = list(map(float, marker.findtext('pose').split()))[:2]
            for actual, expected in zip(xy, body_center(config['place_pose'])):
                self.assertAlmostEqual(actual, expected)
            with self.assertRaises(FileExistsError):
                prepare_trial(scene, root / "trial", base, assets)
            config["cup_pose"][0] += .01
            with self.assertRaisesRegex(ValueError, "differ"):
                validate_scene_world(config, trial["world"])


if __name__ == "__main__":
    unittest.main()
