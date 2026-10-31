"""固定版のexternal checkoutへ、提供モデル専用の設定だけを追加する。"""

import argparse
import copy
import json
import math
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from check_robot_model import PACKAGE, SHA256, check_model

BASE_SHA = "de410efb3a90348e256015305e80e10ecdcfd972"
XACRO = "http://www.ros.org/wiki/xacro"
ET.register_namespace("xacro", XACRO)


def tip_point(package, visual):
    """基盤と同じ最大+Z面の面積重心。実機の接触点ではない。"""
    origin = visual.find("origin")
    if any(float(v) != 0 for v in origin.get("rpy").split()):
        raise ValueError("tip extraction requires zero visual rotation")
    offset = list(map(float, origin.get("xyz").split()))
    mesh = visual.find("geometry/mesh")
    scale = list(map(float, mesh.get("scale").split()))
    data = (package / "meshes" / Path(mesh.get("filename")).name).read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * count:
        raise ValueError("expected binary STL")
    triangles = [[[v * scale[k] + offset[k] for k, v in enumerate(
        struct.unpack_from("<3f", data, 84 + i * 50 + 12 + j * 12))]
        for j in range(3)] for i in range(count)]
    top = max(v[2] for triangle in triangles for v in triangle)
    weighted, total = [0.0] * 3, 0.0
    for triangle in triangles:
        if any(top - v[2] > 1e-7 for v in triangle):
            continue
        a = [triangle[1][k] - triangle[0][k] for k in range(3)]
        b = [triangle[2][k] - triangle[0][k] for k in range(3)]
        area = math.sqrt(sum((a[i] * b[j] - a[j] * b[i]) ** 2
                             for i, j in ((1, 2), (2, 0), (0, 1)))) / 2
        total += area
        for k in range(3):
            weighted[k] += area * sum(v[k] for v in triangle) / 3
    if not total:
        raise ValueError("no distal face found")
    return [v / total for v in weighted]


def prepare(base, provided):
    external = Path(__file__).resolve().parent.parent / "external"
    if not base.resolve().is_relative_to(external.resolve()):
        raise ValueError("model settings may only be generated inside PAI external/")
    check_model(provided)
    if subprocess.check_output(["git", "-C", str(base), "rev-parse", "HEAD"], text=True).strip() != BASE_SHA:
        raise ValueError(f"expected base SHA {BASE_SHA}")
    destination = base / "src" / PACKAGE
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}; inspect before replacing")
    original = provided / PACKAGE
    root = ET.parse(original / "urdf/LIFTH_arm_v2_1_1.xacro").getroot()
    # 基盤wrapperではGazebo拡張を一元化する。提供物の単体表示設定はopt-inで保持。
    ET.SubElement(root, f"{{{XACRO}}}arg", name="include_gazebo", default="true")
    for include in list(root.findall(f"{{{XACRO}}}include")):
        if include.get("filename", "").endswith(".gazebo"):
            root.remove(include)
            enabled = ET.SubElement(root, f"{{{XACRO}}}if", value="$(arg include_gazebo)")
            enabled.append(include)
    tips = {}
    for side, link in (("left", "f1_1"), ("right", "f2_1")):
        point = tip_point(original, root.find(f"link[@name='{link}']/visual"))
        tips[side] = point
        name = f"{side}_finger_tip"
        ET.SubElement(root, "link", name=name)
        joint = ET.SubElement(root, "joint", name=f"{name}_fixed", type="fixed")
        ET.SubElement(joint, "parent", link=link)
        ET.SubElement(joint, "child", link=name)
        ET.SubElement(joint, "origin", xyz=" ".join(map(str, point)), rpy="0 0 0")
    for mesh in root.iter("mesh"):
        mesh.set("filename", mesh.get("filename").replace(f"file://$(find {PACKAGE})/", f"package://{PACKAGE}/"))
    # 既存D405 macroを参照する。光学原点は基盤と同じ暫定値で校正値ではない。
    ET.SubElement(root, f"{{{XACRO}}}include",
                  filename="$(find LIFTH_arm_v2_1_0_description)/urdf/d405.xacro")
    ET.SubElement(root, f"{{{XACRO}}}arg", name="enable_d405", default="false")
    condition = ET.SubElement(root, f"{{{XACRO}}}if", value="$(arg enable_d405)")
    ET.SubElement(condition, f"{{{XACRO}}}d405_frames")
    bringup = base / "src/lifth_bringup"
    model = yaml.safe_load((bringup / "config/models/v2_1_0.yaml").read_text())
    model.update(package=PACKAGE, xacro="urdf/LIFTH_arm_v2_1_1.xacro", version="2.1.1",
                 robot_name="LIFTH_arm_v2_1_1", initial_positions="config/models/v2_1_1_initial.yaml")
    model["moveit"] = copy.deepcopy(model["moveit"])
    model["moveit"]["directory"] = "config/v2_1_1"
    # limitsは提供URDFから基盤が取得する。端で姿勢変更すると指が停止する実測に対処。
    initial = bringup / "config/models/v2_1_0_initial.yaml"
    moveit = base / "src/lifth_moveit_config/config"
    if (moveit / "v2_1_1").exists():
        raise ValueError("model-specific MoveIt config already exists")
    shutil.copytree(original, destination)
    ET.ElementTree(root).write(destination / "urdf/LIFTH_arm_v2_1_1.xacro", encoding="utf-8", xml_declaration=True)
    (bringup / "config/models/v2_1_1.yaml").write_text(yaml.safe_dump(model, sort_keys=False))
    initial_data = yaml.safe_load(initial.read_text())
    initial_data["initial_positions"][model["gripper"]["left"]["joint"]] = 0.0002
    initial_data["initial_positions"][model["gripper"]["right"]["joint"]] = -0.0002
    (bringup / model["initial_positions"]).write_text(yaml.safe_dump(initial_data, sort_keys=False))
    (moveit / "v2_1_1").mkdir()
    for name in ("arm.srdf", "kinematics.yaml", "ompl_planning.yaml", "moveit_controllers.yaml", "joint_limits.yaml"):
        content = (moveit / name).read_text().replace("LIFTH_arm_v2_1_0", "LIFTH_arm_v2_1_1")
        (moveit / "v2_1_1" / name).write_text(content)
    manifest = {"base_sha": BASE_SHA, "source_zip_sha256": SHA256, "tips_m": tips,
                "finger_open_positions_m": [0.0002, -0.0002],
                "camera": "existing D405 macro; provisional optical origin, not calibrated"}
    (destination / "pai-model-source.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("provided", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.base, args.provided), indent=2))
