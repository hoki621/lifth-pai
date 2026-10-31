#!/usr/bin/env bash
# Run inside the collection container. Never installs packages on the host.
set -e
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$repo_dir"
source /opt/ros/humble/setup.bash
python3 - <<'PY'
import json
import subprocess
import sys
from pathlib import Path

import yaml
sys.path.insert(0, 'collection')
from prepare_robot_model import BASE_SHA, PACKAGE, SHA256, check_model, prepare

spec = yaml.safe_load(Path('dependencies.repos').read_text())['repositories']['lifth_arm_gen2']
if spec['version'] != BASE_SHA:
    raise SystemExit('dependency pin and model adapter disagree')
provided = Path('external/robot_models')
check_model(provided)
base = Path('external/lifth_arm_gen2')
if not base.exists():
    raise SystemExit('clone the pinned foundation on the host first; see docs/hikari-collection.md')
if not base.resolve().is_relative_to(Path('external').resolve()):
    raise SystemExit('foundation must be an independent checkout inside PAI external/')
actual = subprocess.check_output(['git', '-C', str(base), 'rev-parse', 'HEAD'], text=True).strip()
if actual != BASE_SHA:
    raise SystemExit('existing external checkout has the wrong commit; inspect it before proceeding')
if subprocess.run(['git', '-C', str(base), 'diff', '--quiet', 'HEAD', '--']).returncode:
    raise SystemExit('foundation has tracked modifications; inspect before building')
marker = base / 'src' / PACKAGE / 'pai-model-source.json'
if marker.exists():
    recorded = json.loads(marker.read_text())
    if recorded['base_sha'] != BASE_SHA or recorded['source_zip_sha256'] != SHA256:
        raise SystemExit('existing model settings have a different source; inspect before replacing')
else:
    prepare(base, provided)
PY
# Build all foundation packages, including its controller plugins, without a tg1 underlay.
bash external/lifth_arm_gen2/build.sh
python3 collection/prepare_cup_world.py \
    external/lifth_arm_gen2/src/lifth_bringup/worlds/arm_camera.sdf \
    external/assets configs/cup_scene.json outputs/issue1/cup_world.sdf
mkdir -p outputs/issue1
dpkg-query -W > outputs/issue1/runtime-packages.txt
