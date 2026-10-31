"""提供素材を転載せず、人工ZIPで欠損・改変の拒否を検査する。"""

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import check_robot_model as model


class ModelSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.files = {
            "package.xml": f"<package><name>{model.PACKAGE}</name></package>",
            "urdf/LIFTH_arm_v2_1_1.xacro": (
                f'<robot><mesh filename="file://$(find {model.PACKAGE})/meshes/test.stl"/></robot>'
            ),
            "meshes/test.stl": "artificial mesh fixture",
        }
        archive = self.directory / f"{model.PACKAGE}.zip"
        with zipfile.ZipFile(archive, "w") as target:
            for name, content in self.files.items():
                relative = Path(model.PACKAGE) / name
                target.writestr(str(relative), content)
                extracted = self.directory / relative
                extracted.parent.mkdir(parents=True, exist_ok=True)
                extracted.write_text(content)
        self.expected = hashlib.sha256(archive.read_bytes()).hexdigest()

    def test_matching_source(self):
        with patch.object(model, "SHA256", self.expected):
            result = model.check_model(self.directory)
        self.assertEqual(result["matched_files"], 3)
        self.assertEqual(result["meshes"], ["meshes/test.stl"])

    def test_wrong_archive(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            model.check_model(self.directory)

    def test_changed_and_missing_mesh(self):
        mesh = self.directory / model.PACKAGE / "meshes/test.stl"
        for changed in (True, False):
            with self.subTest(changed=changed), patch.object(model, "SHA256", self.expected):
                if changed:
                    mesh.write_text("changed")
                else:
                    mesh.unlink()
                with self.assertRaisesRegex(ValueError, "missing or changed"):
                    model.check_model(self.directory)


if __name__ == "__main__":
    unittest.main()
