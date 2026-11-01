"""Gazeboを一時停止して既存recorderを開始し、開始処理中の入力滞留を避ける。"""

import json
import subprocess

import rclpy
from lifth_custom_msgs.srv import StartEpisode


def control(paused):
    response = subprocess.run([
        "ign", "service", "-s", "/world/lifth/control", "--reqtype", "ignition.msgs.WorldControl",
        "--reptype", "ignition.msgs.Boolean", "--timeout", "2000", "--req", f"pause: {str(paused).lower()}",
    ], capture_output=True, text=True, check=True, timeout=5)
    if "data: true" not in response.stdout:
        raise RuntimeError(f"Gazebo pause={paused} failed: {response.stdout} {response.stderr}")


def main():
    rclpy.init()
    node = rclpy.create_node("pai_episode_start")
    client = node.create_client(StartEpisode, "/lifth/episode/start")
    try:
        if not client.wait_for_service(timeout_sec=5):
            raise RuntimeError("existing recorder start service unavailable")
        control(True)
        try:
            request = StartEpisode.Request(task="I1 cup transfer to the green square")
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=4)
            if not future.done():
                raise RuntimeError("start response timeout; inspect recorder before starting again")
            result = future.result()
            if not result.success:
                raise RuntimeError(result.message)
            print(json.dumps({"episode_id": result.episode_id, "path": result.path, "task_success": None}))
        finally:
            control(False)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
