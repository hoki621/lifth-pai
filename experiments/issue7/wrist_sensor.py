"""Add the Issue 7 observation-only wrist camera to an expanded Gazebo URDF."""

import copy
import xml.etree.ElementTree as ET


def add_wrist_sensor(description):
    """Return an expanded URDF with a second RGB-D sensor on EE_1.

    The fixed overhead camera and all existing links and joints remain unchanged.
    The wrist sensor uses the received v2.1.1 mounting transform and the existing
    provisional D405 optical pose. It needs a separate Gazebo-to-ROS image bridge.
    No wrist optical TF is created by this observation-only experiment.
    """
    robot = ET.fromstring(description)
    original = next(g for g in robot.findall('gazebo') if g.find("sensor[@name='d405']") is not None)
    wrist = copy.deepcopy(original)
    wrist.set('reference', 'EE_1')
    sensor = wrist.find("sensor[@name='d405']")
    sensor.set('name', 'inspection_wrist_d405')
    sensor.find('pose').text = '-0.073152 0.009001 0.079349763964 0 -1.0471975511965976 0'
    sensor.find('topic').text = '/lifth/inspection_wrist_d405'
    sensor.find('camera/optical_frame_id').text = 'inspection_wrist_optical_frame'
    robot.append(wrist)
    return ET.tostring(robot, encoding='unicode')
