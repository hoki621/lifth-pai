"""確認済みActionを1段ずつ実行する教師シーケンス。Ctrl-Cで取消し、後続を送らない。"""

import argparse
import json
import math
import signal
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def validate_steps(steps):
    if not steps:
        raise ValueError("empty sequence")
    for step in steps:
        if set(step) not in ({"name", "pose"}, {"name", "gripper"}):
            raise ValueError("each step needs a name and exactly one pose/gripper target")
        values = step.get("pose", step.get("gripper"))
        expected = 7 if "pose" in step else 2
        if len(values) != expected or not all(math.isfinite(v) for v in values):
            raise ValueError(f"invalid target: {step['name']}")
        if "pose" in step and abs(sum(v*v for v in values[3:]) - 1) > 1e-6:
            raise ValueError("pose quaternion must be normalized")


def run_steps(steps, execute, stopped):
    validate_steps(steps)
    for step in steps:
        if stopped():
            raise RuntimeError("sequence stopped; no further goals sent")
        execute(step)


def main():
    import rclpy
    from action_msgs.msg import GoalStatus
    from control_msgs.action import FollowJointTrajectory
    from lifth_bringup.gripper import require_live_model, targets
    from lifth_bringup.model import joint_properties, load_model, robot_description
    from lifth_custom_msgs.action import MoveToPose
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions
    from trajectory_msgs.msg import JointTrajectoryPoint
    from moveit_msgs.msg import CollisionObject, AttachedCollisionObject
    from moveit_msgs.srv import ApplyPlanningScene
    from geometry_msgs.msg import Pose
    from shape_msgs.msg import SolidPrimitive

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    steps = config["steps"]
    validate_steps(steps)
    model = load_model("v2_1_1")
    properties = joint_properties(robot_description("gazebo", "v2_1_1"),
                                  [v["joint"] for v in model["gripper"].values()])
    # 全指令を動かす前に検査する。後半の不正値で途中まで動かさない。
    for step in steps:
        if "gripper" in step:
            targets(model, properties, *step["gripper"])
    stop = [False]
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__(0, True))
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__(0, True))
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = Node("pai_cup_teacher", parameter_overrides=[rclpy.parameter.Parameter("use_sim_time", value=True)])

    def wait(future, timeout):
        deadline = time.monotonic() + timeout
        while not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
        if not future.done():
            raise RuntimeError("Action response timeout; verify backend stop before restarting")
        return future.result()

    def action(action_type, name, goal, successful):
        client = ActionClient(node, action_type, name)
        handle = None
        try:
            if stop[0] or not client.wait_for_server(timeout_sec=5):
                raise RuntimeError(f"stopped or unavailable Action: {name}")
            acceptance = client.send_goal_async(goal)
            # 受付が遅れた場合も、後着したgoalを取消す。
            acceptance.add_done_callback(lambda f: f.result().cancel_goal_async()
                                         if stop[0] and f.result().accepted else None)
            handle = wait(acceptance, 5)
            if not handle.accepted:
                raise RuntimeError(f"Action rejected: {name}")
            future = handle.get_result_async()
            deadline = time.monotonic() + 90
            while not future.done() and not stop[0] and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.05)
            if not future.done() or stop[0]:
                stop[0] = True
                wait(handle.cancel_goal_async(), 10)
                wait(future, 10)
                raise RuntimeError(f"Action interrupted: {name}; sequence stopped")
            response = future.result()
            if response.status != GoalStatus.STATUS_SUCCEEDED or not successful(response.result):
                raise RuntimeError(f"Action failed: {name}: {response}")
        except Exception:
            stop[0] = True
            if handle is not None and handle.accepted:
                wait(handle.cancel_goal_async(), 10)
            raise
        finally:
            client.destroy()

    def scene(attached=False, placed=False):
        # Gazeboへの拘束は作らない。ここでのattachはMoveItの計画用のみ。
        world_path = Path(__file__).resolve().parent.parent / "outputs/issue1/cup_world.sdf"
        world = ET.parse(world_path).find("world")
        client = node.create_client(ApplyPlanningScene, "/apply_planning_scene")
        try:
            if not client.wait_for_service(timeout_sec=5):
                raise RuntimeError("planning scene unavailable")
            request = ApplyPlanningScene.Request()
            request.scene.is_diff = True
            request.scene.robot_state.is_diff = True
            for name, pose in (("pai_floor", [0.0]*6), ("pai_cup", config["place_pose" if placed else "cup_pose"])):
                if any(pose[i] != 0 for i in (3, 4)):
                    raise ValueError("teacher scene requires an upright cup")
                obj = CollisionObject()
                obj.id = name
                obj.header.frame_id = "world"
                obj.operation = CollisionObject.ADD
                for collision in world.findall(f"model[@name='{name}']/link/collision"):
                    primitive = SolidPrimitive()
                    geometry = collision.find("geometry")
                    if geometry.find("box") is not None:
                        primitive.type = SolidPrimitive.BOX
                        primitive.dimensions = list(map(float, geometry.findtext("box/size").split()))
                    else:
                        primitive.type = SolidPrimitive.CYLINDER
                        primitive.dimensions = [float(geometry.findtext("cylinder/length")),
                                                float(geometry.findtext("cylinder/radius"))]
                    local = list(map(float, collision.findtext("pose", "0 0 0 0 0 0").split()))
                    position = Pose()
                    c, s = math.cos(pose[5]), math.sin(pose[5])
                    position.position.x = pose[0] + c*local[0] - s*local[1]
                    position.position.y = pose[1] + s*local[0] + c*local[1]
                    position.position.z = pose[2] + local[2]
                    position.orientation.z, position.orientation.w = math.sin(pose[5]/2), math.cos(pose[5]/2)
                    obj.primitives.append(primitive)
                    obj.primitive_poses.append(position)
                if name == "pai_cup" and attached:
                    item = AttachedCollisionObject()
                    item.link_name = model["tcp_frame"]
                    item.object = obj
                    item.touch_links = ["f1_1", "f2_1"]
                    request.scene.robot_state.attached_collision_objects.append(item)
                else:
                    request.scene.world.collision_objects.append(obj)
            if placed:
                item = AttachedCollisionObject()
                item.link_name = model["tcp_frame"]
                item.object.id, item.object.operation = "pai_cup", CollisionObject.REMOVE
                request.scene.robot_state.attached_collision_objects.append(item)
            if not wait(client.call_async(request), 5).success:
                raise RuntimeError("planning scene update rejected")
        finally:
            node.destroy_client(client)

    def execute(step):
        print(f"phase={step['name']}", flush=True)
        if "pose" in step:
            goal = MoveToPose.Goal()
            goal.target.header.frame_id = model["base_frame"]
            xyz, quat = list(map(float, step["pose"][:3])), list(map(float, step["pose"][3:]))
            goal.target.pose.position.x, goal.target.pose.position.y, goal.target.pose.position.z = xyz
            q = goal.target.pose.orientation
            q.x, q.y, q.z, q.w = quat
            goal.mode = MoveToPose.Goal.POSE
            action(MoveToPose, "/lifth/move_to_pose", goal, lambda result: result.success)
        else:
            requested = targets(model, properties, *step["gripper"])
            for side, (joint, position) in requested.items():
                goal = FollowJointTrajectory.Goal()
                goal.trajectory.joint_names = [joint]
                point = JointTrajectoryPoint(positions=[position])
                point.time_from_start.sec = 2
                goal.trajectory.points = [point]
                action(FollowJointTrajectory, f"/{side}_finger_controller/follow_joint_trajectory",
                       goal, lambda result: result.error_code == 0)
            if step["name"] == "close":
                scene(attached=True)
            elif step["name"] == "release":
                scene(placed=True)

    try:
        require_live_model(node, "v2_1_1")
        scene()
        run_steps(steps, execute, lambda: stop[0])
        print("sequence complete; task success requires human judgement", flush=True)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
