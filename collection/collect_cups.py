"""Collect randomized simulation candidates; physical checks do not replace visual review.

Uses the existing built collection Docker image, recorder, teacher and validator.
Run from the repository root. Resume counts only completed physical candidates.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess

from prepare_cup_collection import random_scene
from prepare_cup_trial import prepare_trial

REPO = Path(__file__).resolve().parents[1]


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def worker(root, index, target):
    folder = root / f'worker-{index}'
    folder.mkdir(exist_ok=True)
    container = f'pai-issue5-{root.name}-w{index}'
    inspect = subprocess.run(['docker', 'inspect', container], capture_output=True)
    if inspect.returncode:
        subprocess.run(['docker', 'run', '-d', '--name', container, '--init', '--shm-size=1g',
                        '--user', f'{os.getuid()}:{os.getgid()}', '--network', 'host',
                        '--mount', f'type=bind,src={REPO},dst=/pai',
                        '--mount', f'type=bind,src={REPO},dst={REPO}',
                        '-e', f'ROS_DOMAIN_ID={190 + index}', '-e', 'ROS_LOCALHOST_ONLY=1',
                        '-e', f'IGN_PARTITION={container}', '-e', f'ROS_LOG_DIR={folder}/ros',
                        'lifth-pai-collection:humble'], check=True)
    else:
        subprocess.run(['docker', 'start', container], check=True)
    baseline = json.loads((REPO / 'configs/cup_scene.json').read_text())
    candidates = []
    attempts = sorted(folder.glob('placement-*/trial-01/result.json'))
    for path in attempts:
        result = json.loads(path.read_text())
        trial = json.loads((path.parents[1] / 'trial.json').read_text())
        if (result['task_success'] and result['validator_exit'] == 0
                and result.get('raw_status') == 'complete' and not trial.get('conversion_error')):
            candidates.append(str(path))
    number = max([int(p.parent.parent.name.split('-')[-1]) for p in attempts], default=0)
    try:
        while len(candidates) < target:
            number += 1
            placement = f'w{index}-{number:04d}'
            validation_count = sum(
                json.loads((Path(path).parents[1] / 'trial.json').read_text())['split'] == 'validation'
                for path in candidates)
            if len(candidates) - validation_count >= target - target // 10:
                split = 'validation'
            elif validation_count >= target // 10:
                split = 'train'
            else:
                split = 'validation' if len(candidates) % 10 == 9 else 'train'
            scene = random_scene(baseline, 20261101 + index * 100000 + number, placement, split)
            scene_path = folder / f'scene-{number:04d}.json'
            scene_path.write_text(json.dumps(scene, indent=2) + '\n')
            trial_root = folder / f'placement-{number:04d}'
            prepare_trial(scene_path, trial_root,
                          REPO / 'external/lifth_arm_gen2/src/lifth_bringup/worlds/arm_camera.sdf',
                          REPO / 'external/assets')
            with (trial_root / 'runner.log').open('w') as log:
                process = subprocess.run(['docker', 'exec', container, 'python3', '-u',
                                          '/pai/collection/run_cup_trial.py', str(trial_root), '1'],
                                         stdout=log, stderr=subprocess.STDOUT)
            if process.returncode:
                raise RuntimeError(f'worker {index}: runner failed; inspect {trial_root}/runner.log')
            result_path = trial_root / 'trial-01/result.json'
            result = json.loads(result_path.read_text())
            eligible = result['task_success'] and result['validator_exit'] == 0 and result.get('raw_status') == 'complete'
            trial = json.loads((trial_root / 'trial.json').read_text())
            trial.update(episode_id=result['episode_id'], raw_path=result.get('raw_path'),
                         sequence_exit_code=result.get('sequence_exit'),
                         physical_task_success=result['task_success'],
                         task_success=None, accepted=False,
                         exclusion_reason='pending visual review' if eligible else 'physical or raw validation failed',
                         physical_evidence=str(result_path))
            write(trial_root / 'trial.json', trial)
            if eligible:
                candidates.append(str(result_path))
            write(folder / 'progress.json', {'physical_candidates': len(candidates), 'attempts': number,
                                            'target': target, 'results': candidates})
            print(f'worker={index} attempt={number} physical_candidates={len(candidates)}/{target} eligible={eligible}', flush=True)
    finally:
        subprocess.run(['docker', 'stop', '-t', '35', container], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='run directory, e.g. outputs/datasets/cup-100-RUN')
    parser.add_argument('--per-worker', type=int, default=50)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, root, i, args.per_worker) for i in (1, 2)]
        for future in futures:
            future.result()


if __name__ == '__main__':
    main()
