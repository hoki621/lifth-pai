"""確認済みActionを1段ずつ実行する教師シーケンス。Ctrl-Cで取消し、後続を送らない。"""

import argparse
import copy
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
        if set(step) not in ({"name", "pose"}, {"name", "cartesian"}, {"name", "gripper"}):
            raise ValueError("each step needs a name and exactly one pose/cartesian/gripper target")
        values = step.get("pose", step.get("cartesian", step.get("gripper")))
        expected = 2 if "gripper" in step else 7
        if len(values) != expected or not all(math.isfinite(v) for v in values):
            raise ValueError(f"invalid target: {step['name']}")
        if "gripper" not in step and abs(sum(v*v for v in values[3:]) - 1) > 1e-6:
            raise ValueError("pose quaternion must be normalized")


def run_steps(steps, execute, stopped):
    validate_steps(steps)
    for step in steps:
        if stopped():
            raise RuntimeError("sequence stopped; no further goals sent")
        execute(step)


def validate_scene_world(config, path):
    world = ET.parse(path).find("world")
    pose = world.findtext("model[@name='pai_cup']/pose") if world is not None else None
    expected = config["cup_pose"]
    observed = list(map(float, pose.split())) if pose is not None else []
    if (len(expected) != 6 or len(observed) != 6 or not all(math.isfinite(v) for v in observed + expected)
            or any(abs(a - b) > 1e-9 for a, b in zip(observed, expected))):
        raise ValueError("teacher scene and selected world cup pose differ")


def main():
    from control_lock import acquire_control

    with acquire_control():
        run_teacher()


def run_teacher():
    import rclpy
    from action_msgs.msg import GoalStatus
    from control_msgs.action import FollowJointTrajectory
    from control_msgs.msg import JointTolerance
    from geometry_msgs.msg import Pose
    from lifth_bringup.gripper import require_live_model, targets
    from lifth_bringup.model import joint_properties, load_model, robot_description
    from lifth_custom_msgs.action import MoveToPose
    from moveit_msgs.action import ExecuteTrajectory
    from moveit_msgs.msg import (
        AllowedCollisionEntry,
        AttachedCollisionObject,
        CollisionObject,
        PlanningSceneComponents,
    )
    from moveit_msgs.srv import ApplyPlanningScene, GetCartesianPath, GetPlanningScene
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions
    from shape_msgs.msg import SolidPrimitive
    from trajectory_msgs.msg import JointTrajectoryPoint

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--world", type=Path,
                        default=Path(__file__).resolve().parent.parent / "outputs/issue1/cup_world.sdf")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    validate_scene_world(config, args.world)
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
    original_contact_matrix = [None]

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
        world = ET.parse(args.world).find("world")
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
                # 解放直後の指とcupの接触は正常。腕・支持台の衝突除外は変えない。
                getter = node.create_client(GetPlanningScene, "/get_planning_scene")
                try:
                    if not getter.wait_for_service(timeout_sec=5):
                        raise RuntimeError("planning scene collision matrix unavailable")
                    query = GetPlanningScene.Request()
                    query.components.components = PlanningSceneComponents.ALLOWED_COLLISION_MATRIX
                    matrix = wait(getter.call_async(query), 5).scene.allowed_collision_matrix
                finally:
                    node.destroy_client(getter)
                original_contact_matrix[0] = copy.deepcopy(matrix)
                for name in ("pai_cup", "f1_1", "f2_1"):
                    if name not in matrix.entry_names:
                        matrix.entry_names.append(name)
                        for row in matrix.entry_values:
                            row.enabled.append(False)
                        matrix.entry_values.append(AllowedCollisionEntry(enabled=[False]*len(matrix.entry_names)))
                cup_index = matrix.entry_names.index("pai_cup")
                for link in ("f1_1", "f2_1"):
                    finger_index = matrix.entry_names.index(link)
                    matrix.entry_values[cup_index].enabled[finger_index] = True
                    matrix.entry_values[finger_index].enabled[cup_index] = True
                request.scene.allowed_collision_matrix = matrix
                item = AttachedCollisionObject()
                item.link_name = model["tcp_frame"]
                item.object.id, item.object.operation = "pai_cup", CollisionObject.REMOVE
                request.scene.robot_state.attached_collision_objects.append(item)
            if not wait(client.call_async(request), 5).success:
                raise RuntimeError("planning scene update rejected")
        finally:
            node.destroy_client(client)

    def restore_contacts():
        if original_contact_matrix[0] is None:
            return
        request = ApplyPlanningScene.Request()
        request.scene.is_diff = True
        request.scene.robot_state.is_diff = True
        request.scene.allowed_collision_matrix = original_contact_matrix[0]
        original_contact_matrix[0] = None
        client = node.create_client(ApplyPlanningScene, "/apply_planning_scene")
        try:
            if not client.wait_for_service(timeout_sec=5) or not wait(client.call_async(request), 5).success:
                raise RuntimeError("could not restore planning collision matrix; reset before next trial")
        finally:
            node.destroy_client(client)

    def execute(step):
        print(f"phase={step['name']}", flush=True)
        if "pose" in step or "cartesian" in step:
            goal = MoveToPose.Goal()
            goal.target.header.frame_id = model["base_frame"]
            values = step.get("pose", step.get("cartesian"))
            xyz, quat = list(map(float, values[:3])), list(map(float, values[3:]))
            goal.target.pose.position.x, goal.target.pose.position.y, goal.target.pose.position.z = xyz
            q = goal.target.pose.orientation
            q.x, q.y, q.z, q.w = quat
            if "cartesian" in step:
                client = node.create_client(GetCartesianPath, "/compute_cartesian_path")
                try:
                    if not client.wait_for_service(timeout_sec=5):
                        raise RuntimeError("existing Cartesian path service unavailable")
                    request = GetCartesianPath.Request()
                    request.header.frame_id = model["base_frame"]
                    request.start_state.is_diff = True
                    request.group_name = model["moveit"]["group"]
                    request.link_name = model["tcp_frame"]
                    request.waypoints = [goal.target.pose]
                    request.max_step = 0.002
                    request.revolute_jump_threshold = 0.1
                    request.avoid_collisions = True
                    request.max_velocity_scaling_factor = 0.5
                    request.max_acceleration_scaling_factor = 0.5
                    result = wait(client.call_async(request), 10)
                    if result.error_code.val != 1 or not 1.0 - 1e-9 <= result.fraction <= 1.0:
                        raise RuntimeError(f"Cartesian path incomplete: fraction={result.fraction}, error={result.error_code.val}")
                    print(f"cartesian fraction={result.fraction} points={len(result.solution.joint_trajectory.points)}", flush=True)
                    execution = ExecuteTrajectory.Goal()
                    execution.trajectory = result.solution
                finally:
                    node.destroy_client(client)
                action(ExecuteTrajectory, "/execute_trajectory", execution, lambda result: result.error_code.val == 1)
            else:
                goal.mode = MoveToPose.Goal.POSE
                action(MoveToPose, "/lifth/move_to_pose", goal, lambda result: result.success)
            if step["name"] == "retreat":
                restore_contacts()
        else:
            requested = targets(model, properties, *step["gripper"])
            for side, (joint, position) in requested.items():
                goal = FollowJointTrajectory.Goal()
                goal.trajectory.joint_names = [joint]
                point = JointTrajectoryPoint(positions=[position])
                point.time_from_start.sec = 2
                goal.trajectory.points = [point]
                if step["name"] == "close":
                    # 接触時の約0.1 mmの未到達で正常把持を打ち切らない。
                    # 0.2→1.5 mmの指令に対し、停止したままなら1.3 mm差で依然拒否する。
                    goal.goal_tolerance = [JointTolerance(name=joint, position=0.0003)]
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
        try:
            restore_contacts()
        finally:
            node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
