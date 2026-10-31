"""Issue #1 の提供ZIPと展開済みモデルを、変更せずに照合する。"""

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


PACKAGE = "LIFTH_arm_v2_1_1_description"
SHA256 = "09174927e76a2808d5877404206e2e2b5c48739696223365a6dd1d17937f6120"


def check_model(directory):
    """提供物との一致を検査する。制御・把持への適合確認は含まない。"""
    archive = directory / f"{PACKAGE}.zip"
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != SHA256:
        raise ValueError(f"ZIP SHA-256 mismatch: expected={SHA256}, actual={digest}")
    package = directory / PACKAGE
    count = 0
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            path = Path(entry.filename)
            if path.parts[0] != PACKAGE or entry.is_dir():
                continue  # macOS metadata is not part of the ROS package.
            if ".." in path.parts or path.is_absolute():
                raise ValueError(f"invalid archive path: {entry.filename}")
            target = directory / path
            if not target.is_file() or target.read_bytes() != source.read(entry):
                raise ValueError(f"extracted file missing or changed: {entry.filename}")
            count += 1
    if ET.parse(package / "package.xml").findtext("name") != PACKAGE:
        raise ValueError("ROS package name mismatch")
    root = ET.parse(package / "urdf/LIFTH_arm_v2_1_1.xacro").getroot()
    prefix = f"file://$(find {PACKAGE})/"
    meshes = set()
    for mesh in root.iter("mesh"):
        filename = mesh.attrib["filename"]
        if not filename.startswith(prefix):
            raise ValueError(f"unexpected mesh reference: {filename}")
        relative = Path(filename[len(prefix):])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"invalid mesh path: {filename}")
        if not (package / relative).is_file():
            raise ValueError(f"mesh missing: {relative}")
        meshes.add(str(relative))
    return {
        "package": PACKAGE,
        "archive_sha256": digest,
        "matched_files": count,
        "meshes": sorted(meshes),
        "scope": "source integrity only; not a runtime acceptance",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="ZIPと展開済みpackageを置いたディレクトリ")
    args = parser.parse_args()
    try:
        result = check_model(args.directory)
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as error:
        print(f"check_robot_model: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
