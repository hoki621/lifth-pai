#!/usr/bin/env bash
set -e
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$repo_dir"
source /opt/ros/humble/setup.bash
source external/lifth_arm_gen2/install/local_setup.bash
export CYCLONEDDS_URI='<CycloneDDS><Domain><Discovery><MaxAutoParticipantIndex>100</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>'
exec "$@"
