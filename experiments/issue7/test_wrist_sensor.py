import unittest
import xml.etree.ElementTree as ET

from wrist_sensor import add_wrist_sensor


class WristSensorTest(unittest.TestCase):
    def test_adds_sensor_without_changing_links_joints_or_original(self):
        source = '''<robot name="arm"><link name="EE_1"/><joint name="arm_joint" type="fixed"/>
          <gazebo reference="camera_link_1"><sensor name="d405" type="rgbd_camera">
            <pose>0 0 0 0 0 0</pose><topic>/lifth/d405</topic>
            <camera><optical_frame_id>camera_color_optical_frame</optical_frame_id></camera>
          </sensor></gazebo></robot>'''
        result = ET.fromstring(add_wrist_sensor(source))
        self.assertEqual([x.get('name') for x in result.findall('link')], ['EE_1'])
        self.assertEqual([x.get('name') for x in result.findall('joint')], ['arm_joint'])
        sensors = result.findall('gazebo')
        self.assertEqual(len(sensors), 2)
        self.assertEqual(sensors[0].findtext('sensor/topic'), '/lifth/d405')
        self.assertEqual(sensors[1].get('reference'), 'EE_1')
        self.assertEqual(sensors[1].findtext('sensor/topic'), '/lifth/inspection_wrist_d405')
        self.assertEqual(sensors[1].findtext('sensor/camera/optical_frame_id'), 'inspection_wrist_optical_frame')


if __name__ == '__main__':
    unittest.main()
