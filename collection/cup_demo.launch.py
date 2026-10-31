"""既存のMoveToPose・D405・recorderを同じモデルで起動する。運動は開始しない。"""

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, SetEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from lifth_bringup.model import load_model, moveit_configuration, robot_description


def generate_launch_description():
    repo = Path(__file__).resolve().parent.parent
    world = repo / "outputs/issue1/cup_world.sdf"
    if not world.is_file():
        raise ValueError("generate outputs/issue1/cup_world.sdf before launching")
    bringup = Path(get_package_share_directory("lifth_bringup")) / "launch/arm_gazebo.launch.py"
    server_config = Path(get_package_share_directory("lifth_exec_pick")) / "config/move_to_pose.yaml"
    model = load_model("v2_1_1")
    description = robot_description("gazebo", "v2_1_1", True)
    robot, controllers, ompl = moveit_configuration(model, description)
    planning = {**robot, **controllers, "ompl": ompl, "use_sim_time": True,
                "planning_pipelines": ["ompl"], "default_planning_pipeline": "ompl",
                "publish_robot_description": False, "publish_robot_description_semantic": True,
                "publish_planning_scene": True, "publish_geometry_updates": True,
                "publish_state_updates": True, "publish_transforms_updates": True}
    execution = {**robot, "use_sim_time": True, "planning_group": model["moveit"]["group"],
                 "tcp_link": model["tcp_frame"], "reference_frame": model["base_frame"]}
    return LaunchDescription([
        SetEnvironmentVariable("IGN_GAZEBO_RESOURCE_PATH", os.pathsep.join(filter(None, [
            str(repo / "external/assets/materials/textures"), os.environ.get("IGN_GAZEBO_RESOURCE_PATH", "")]))),
        # robot_descriptionの配信元を既存RSPに限定し、cameraなし記述との競合を避ける。
        IncludeLaunchDescription(PythonLaunchDescriptionSource(str(bringup)), launch_arguments={
            "model": "v2_1_1", "camera_enabled": "true", "world": str(world)}.items()),
        Node(package="lifth_moveit_config", executable="lifth_move_group", parameters=[planning], output="screen"),
        Node(package="lifth_exec_pick", executable="move_to_pose_server",
             parameters=[str(server_config), execution], output="screen", sigterm_timeout="10.0"),
        Node(executable="python3", arguments=[str(repo / "collection/reliable_rgb_recorder.py")],
             parameters=[{"model": "v2_1_1", "backend": "gazebo", "use_sim_time": True,
                          "output_dir": str(repo / "data/raw")}], output="screen"),
    ])
