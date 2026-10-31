"""Local-only pinned rosbridge + adapter; launch the Gazebo scene separately."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


BRIDGE_PARAMETERS = {
    'address': '127.0.0.1', 'port': 9090, 'max_message_size': 10000000,
    # The pinned server expects bracketed string lists. Legacy topics merge into
    # BOTH allowlists, so leave that list empty rather than broadening access.
    'topics_glob': '[]',
    'topics_pub_glob': "['/pai/policy/control', '/pai/policy/action']",
    'topics_sub_glob': "['/pai/policy/observation', '/pai/policy/status']",
    'services_glob': '[]', 'actions_glob': '[]',
}


def generate_launch_description():
    repo = Path(__file__).resolve().parents[1]
    return LaunchDescription([
        DeclareLaunchArgument('timing', description='Path to calibrated timing JSON (validated=true)'),
        DeclareLaunchArgument('contract', default_value=str(repo/'configs/policy_contract.json')),
        DeclareLaunchArgument('port', default_value='9090'),
        Node(package='rosbridge_server', executable='rosbridge_websocket',
             parameters=[{**BRIDGE_PARAMETERS,
                          'port': ParameterValue(LaunchConfiguration('port'), value_type=int)}], output='screen'),
        # ExecuteProcess avoids appending --ros-args to this plain argparse entrypoint.
        ExecuteProcess(cmd=['python3', str(repo/'collection/policy_adapter.py'),
             '--timing', LaunchConfiguration('timing'), '--contract', LaunchConfiguration('contract')],
             output='screen', sigterm_timeout='30.0'),
    ])
