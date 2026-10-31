"""人工素材でworld生成と不正設定の拒否を確認する。"""

import tempfile
import unittest
from pathlib import Path

from prepare_cup_world import prepare


class CupWorldTests(unittest.TestCase):
    def test_world_and_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            base = path / "base.sdf"
            base.write_text('<sdf version="1.9"><world name="lifth"/></sdf>')
            (path / "meshes").mkdir()
            (path / "meshes/model.obj").write_text("v -0.05 -0.05 0\nv 0.05 0.05 0.1\n")
            (path / "model.sdf").write_text(
                '<sdf><model name="Threshold_Porcelain_Coffee_Mug_All_Over_Bead_White">'
                '<link name="link_0"><collision name="c"><geometry><mesh>'
                '<uri>meshes/model.obj</uri></mesh></geometry></collision></link></model></sdf>')
            config = {"cup_pose": [0.4, 0, 0, 0, 0, 0], "mass_kg": 0.3, "friction": 0.8}
            tree = prepare(base, path, config)
            world = tree.getroot().find("world")
            cup = world.find("model[@name='pai_cup']")
            self.assertEqual(cup.findtext("link/inertial/mass"), "0.3")
            self.assertAlmostEqual(float(cup.findtext("link/inertial/inertia/ixx")), 0.0005)
            self.assertEqual(cup.findtext("link/collision/surface/friction/ode/mu"), "0.8")
            self.assertTrue(cup.findtext("link/collision/geometry/mesh/uri").startswith("file:///"))
            self.assertIsNotNone(world.find("model[@name='pai_floor']"))
            for key, value in (("mass_kg", -1), ("friction", -1),
                               ("cup_pose", [0] * 5), ("cup_pose", [float("nan")] * 6)):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    prepare(base, path, {**config, key: value})
            (path / "meshes/model.obj").unlink()
            with self.assertRaisesRegex(ValueError, "asset URI"):
                prepare(base, path, config)


if __name__ == "__main__":
    unittest.main()
