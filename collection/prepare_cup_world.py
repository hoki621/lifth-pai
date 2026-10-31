"""既存camera worldとGit外の採用cupから、物性を加えた確認用worldを生成する。"""

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def element(parent, tag, value):
    ET.SubElement(parent, tag).text = str(value)


def prepare(base_world, assets, config):
    pose = config["cup_pose"]
    mass, friction = config["mass_kg"], config["friction"]
    if len(pose) != 6 or not all(math.isfinite(v) for v in [*pose, mass, friction]):
        raise ValueError("cup_pose must contain six finite values; mass/friction must be finite")
    if mass <= 0 or friction < 0:
        raise ValueError("mass must be positive; friction must be nonnegative")
    root = ET.parse(base_world).getroot()
    world = root.find("world")
    if world is None or world.get("name") != "lifth":
        raise ValueError("base world must be named lifth for the existing bringup")
    if world.find("model[@name='pai_cup']") is not None:
        raise ValueError("base world already contains pai_cup")
    cup = ET.parse(assets / "model.sdf").find("model")
    if cup is None or cup.get("name") != "Threshold_Porcelain_Coffee_Mug_All_Over_Bead_White":
        raise ValueError("unexpected cup model")
    for uri in cup.iter("uri"):
        path = (assets / uri.text).resolve()
        if not path.is_relative_to(assets.resolve()) or not path.is_file():
            raise ValueError(f"missing or unexpected asset URI: {uri.text}")
        uri.text = path.as_uri()
    cup.set("name", "pai_cup")
    element(cup, "pose", " ".join(map(str, pose)))
    link = cup.find("link")
    if link.find("inertial") is not None:
        raise ValueError("cup already has inertia; review before overriding")
    # 提供OBJの外接箱から一様箱近似。陶器の実測値ではない。
    vertices = [list(map(float, line.split()[1:4]))
                for line in (assets / "meshes/model.obj").read_text().splitlines()
                if line.startswith("v ")]
    bounds = [(min(v[i] for v in vertices), max(v[i] for v in vertices)) for i in range(3)]
    size = [high - low for low, high in bounds]
    inertial = ET.SubElement(link, "inertial")
    element(inertial, "pose", " ".join(str((low + high) / 2) for low, high in bounds) + " 0 0 0")
    element(inertial, "mass", mass)
    inertia = ET.SubElement(inertial, "inertia")
    for axis, a, b in (("ixx", 1, 2), ("iyy", 0, 2), ("izz", 0, 1)):
        element(inertia, axis, mass * (size[a] ** 2 + size[b] ** 2) / 12)
    for axis in ("ixy", "ixz", "iyz"):
        element(inertia, axis, 0)
    # 動的三角形meshを避ける。胴体は外形に沿う段付き円柱、持ち手は箱近似。
    # 穴への指挿入は対象外。寸法はOBJの高さ別外接幅から保守的に設定する。
    for collision in link.findall("collision"):
        link.remove(collision)
    for index, radius in enumerate((0.036, 0.043, 0.047, 0.0485, 0.0485, 0.0485)):
        collision = ET.SubElement(link, "collision", name=f"body_{index}")
        height = min(0.02, 0.114624 - index * 0.02)
        element(collision, "pose", f"0.0165 -0.0018 {index * 0.02 + height / 2} 0 0 0")
        cylinder = ET.SubElement(ET.SubElement(collision, "geometry"), "cylinder")
        element(cylinder, "radius", radius)
        element(cylinder, "length", height)
    handle = ET.SubElement(link, "collision", name="handle")
    element(handle, "pose", "-0.043 -0.0018 0.057 0 0 0")
    handle_box = ET.SubElement(ET.SubElement(handle, "geometry"), "box")
    element(handle_box, "size", "0.045 0.016 0.077")
    for collision in link.findall("collision"):
        if collision.find("surface") is not None:
            raise ValueError("cup already has surface properties; review before overriding")
        ode = ET.SubElement(ET.SubElement(ET.SubElement(collision, "surface"), "friction"), "ode")
        element(ode, "mu", friction)
        element(ode, "mu2", friction)
    world.append(cup)
    # 低い胴体を横から挟めるよう、手首の下を塞がない細い支持台を置く。
    floor = ET.SubElement(world, "model", name="pai_floor")
    element(floor, "static", "true")
    floor_link = ET.SubElement(floor, "link", name="floor")
    supports = [pose]
    if "place_pose" in config and config["place_pose"] != pose:
        supports.append(config["place_pose"])
    for index, support in enumerate(supports):
        x = support[0] + 0.0165*math.cos(support[5]) + 0.0018*math.sin(support[5])
        y = support[1] + 0.0165*math.sin(support[5]) - 0.0018*math.cos(support[5])
        height = max(0.05, support[2])
        for kind in ("collision", "visual"):
            item = ET.SubElement(floor_link, kind, name=f"{kind}_{index}")
            element(item, "pose", f"{x} {y} {support[2] - height/2} 0 0 0")
            cylinder = ET.SubElement(ET.SubElement(item, "geometry"), "cylinder")
            element(cylinder, "radius", 0.028)
            element(cylinder, "length", height)
    return ET.ElementTree(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_world", type=Path)
    parser.add_argument("assets", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        tree = prepare(args.base_world, args.assets, json.loads(args.config.read_text()))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        ET.indent(tree)
        tree.write(args.output, encoding="utf-8", xml_declaration=True)
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as error:
        print(f"prepare_cup_world: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
