"""mesh由来の指先代表点を人工STLで検査する。"""

import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from prepare_robot_model import prepare, tip_point


class TipPointTests(unittest.TestCase):
    def test_refuses_to_modify_original_checkout(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "inside PAI external"):
            prepare(Path(directory), Path(directory))

    def test_distal_face_with_scale_and_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            (package / "meshes").mkdir()
            # 上面と底面。上面の面積重心は(2/3, 2/3, 1)。
            triangles = [(0, 0, 1, 2, 0, 1, 0, 2, 1),
                         (0, 0, 0, 2, 0, 0, 0, 2, 0)]
            data = b"\0"*80 + struct.pack("<I", len(triangles))
            for triangle in triangles:
                data += struct.pack("<12fH", 0, 0, 1, *triangle, 0)
            (package / "meshes/finger.stl").write_bytes(data)
            visual = ET.fromstring('<visual><origin xyz="1 2 3" rpy="0 0 0"/>'
                                   '<geometry><mesh filename="finger.stl" scale="0.1 0.1 0.1"/>'
                                   '</geometry></visual>')
            result = tip_point(package, visual)
            for value, expected in zip(result, [1+0.2/3, 2+0.2/3, 3.1]):
                self.assertAlmostEqual(value, expected)
            visual.find("origin").set("rpy", "0 1 0")
            with self.assertRaises(ValueError):
                tip_point(package, visual)


if __name__ == "__main__":
    unittest.main()
