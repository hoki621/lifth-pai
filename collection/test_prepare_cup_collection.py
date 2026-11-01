import json
import math
from pathlib import Path
import unittest

from prepare_cup_collection import body_center, random_scene


class RandomSceneTests(unittest.TestCase):
    def test_reproducible_geometry_and_fixed_destination(self):
        base = json.loads((Path(__file__).resolve().parents[1] / 'configs/cup_scene.json').read_text())
        original_base = json.dumps(base, sort_keys=True)
        for seed in range(100):
            scene = random_scene(base, seed, str(seed), 'train')
            self.assertEqual(scene, random_scene(base, seed, str(seed), 'train'))
            self.assertTrue(-.02 <= scene['cup_pose'][0] - base['cup_pose'][0] <= .10)
            self.assertTrue(-.28 <= scene['cup_pose'][1] - base['cup_pose'][1] <= .02)
            self.assertLessEqual(abs(scene['cup_pose'][5] - base['cup_pose'][5]), .15)
            for a, b in zip(body_center(scene['place_pose']), body_center(base['place_pose'])):
                self.assertAlmostEqual(a, b)
            for step, original in zip((s for s in scene['steps'] if s['name'] != 'preapproach'), base['steps']):
                if 'gripper' in step:
                    self.assertEqual(step, original)
                    continue
                target = step.get('pose', step.get('cartesian'))
                before = original.get('pose', original.get('cartesian'))
                self.assertEqual(target[2], before[2])
                yaw = scene['cup_pose'][5]
                for actual, expected in zip(target[3:], [-math.sin(yaw/2), math.cos(yaw/2), 0, 0]):
                    self.assertAlmostEqual(actual, expected)
                if step['name'] in ('approach', 'lower', 'lift', 'transfer', 'place', 'retreat'):
                    pose = scene['cup_pose'] if step['name'] in ('approach', 'lower', 'lift') else scene['place_pose']
                    for axis in (0, 1):
                        self.assertAlmostEqual(target[axis] - body_center(pose)[axis],
                                               -.070 * (math.cos(yaw) if axis == 0 else math.sin(yaw)))
                else:
                    self.assertEqual(target[:3], before[:3])
        self.assertEqual(json.dumps(base, sort_keys=True), original_base)


if __name__ == '__main__':
    unittest.main()
