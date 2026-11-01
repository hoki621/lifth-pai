"""The generated model keeps RGB geometry and optical TF on one fixed mount."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from prepare_robot_model import BASE_SHA, PACKAGE, SHA256, configure_overview_camera


class CameraTests(unittest.TestCase):
    def test_fixed_mount_removes_only_old_adjacent_exclusion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'src' / PACKAGE
            (package / 'urdf').mkdir(parents=True)
            marker = package / 'pai-model-source.json'
            marker.write_text(json.dumps({'base_sha': BASE_SHA, 'source_zip_sha256': SHA256}))
            model = package / 'urdf/LIFTH_arm_v2_1_1.xacro'
            model.write_text('<robot><joint name="ee_camera_link" type="fixed">'
                             '<parent link="EE_1"/><child link="camera_link_1"/>'
                             '<origin xyz="0 0 0" rpy="0 0 0"/></joint></robot>')
            semantic = root / 'src/lifth_moveit_config/config/v2_1_1/arm.srdf'
            semantic.parent.mkdir(parents=True)
            semantic.write_text('<robot><disable_collisions link1="EE_1" link2="camera_link_1"/>'
                                '<disable_collisions link1="EE_1" link2="f1_1"/></robot>')
            configure_overview_camera(root)
            first = model.read_bytes(), semantic.read_bytes(), marker.read_bytes()
            configure_overview_camera(root)
            self.assertEqual(first, (model.read_bytes(), semantic.read_bytes(), marker.read_bytes()))
            joint = ET.parse(model).find('joint')
            self.assertEqual(joint.find('parent').get('link'), 'base_link')
            self.assertEqual(joint.find('child').get('link'), 'camera_link_1')
            self.assertEqual(joint.find('origin').get('xyz'), '0.52 0.001 0.7722')
            exclusions = ET.parse(semantic).findall('disable_collisions')
            self.assertEqual(len(exclusions), 1)
            self.assertEqual(exclusions[0].get('link2'), 'f1_1')
