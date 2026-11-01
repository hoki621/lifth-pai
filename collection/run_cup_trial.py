"""Run one simulated teacher trial and retain raw validation and physical evidence."""
import hashlib
import sys
import shutil
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

ROOT = Path(sys.argv[1]).resolve()
os.chdir('/pai')
CONFIG = ROOT / 'scene.json'
SCENE = json.loads(CONFIG.read_text())
FILES = [CONFIG, *sorted(Path('collection').glob('*.py'))]
HASHES = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in FILES}
RESULTS = {'started': time.time(), 'code_hashes': HASHES,
           'pai_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
           'foundation_commit': subprocess.check_output(['git', '-C', 'external/lifth_arm_gen2', 'rev-parse', 'HEAD'], text=True).strip(),
           'trials': []}
(ROOT / f'code-before-{sys.argv[2]}.diff').write_text(subprocess.check_output(['git', 'diff', '--', 'collection'], text=True))

def run(args, log, timeout=30):
    with log.open('w') as out:
        try:
            return subprocess.run(['bash', 'collection/ros.sh', *args], stdout=out,
                                  stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            return 124

def stop_process(process):
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=25)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()

def trace(process, path):
    with path.open('w') as out:
        for line in process.stdout:
            msg = json.loads(line)
            cup = next((p for p in msg.get('pose', []) if p.get('name') == 'pai_cup'), None)
            if cup is not None:
                out.write(json.dumps({'wall': time.time(), 'header': msg['header'], 'cup': cup}) + '\n')

def sim(row):
    s = row['header']['stamp']
    return int(s.get('sec', 0)) + s.get('nsec', 0)/1e9

def tilt(row):
    q = row['cup']['orientation']
    return math.degrees(math.acos(max(-1, min(1, 1-2*(q.get('x', 0)**2+q.get('y', 0)**2)))))

for number in [int(sys.argv[2])]:
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in HASHES.items()), 'runtime/config changed'
    folder = ROOT / f'trial-{number:02d}'
    folder.mkdir()
    (folder / 'source').mkdir()
    for source_file in FILES:
        shutil.copy2(source_file, folder / 'source' / source_file.name)
    result = {'trial': number, 'started': time.time(), 'grasp_success': False,
              'task_success': False, 'validator_exit': None, 'episode_id': None, 'code_hashes': HASHES}
    launch = pose = sequence = worker = None
    phases = {}
    print(f'TRIAL {number} START', flush=True)
    with (folder / 'launch.log').open('w') as launch_log:
        try:
            launch = subprocess.Popen(['bash', 'collection/ros.sh', 'ros2', 'launch', 'collection/cup_demo.launch.py', f'world:={ROOT / "world.sdf"}', f'output_dir:={ROOT.parent / "raw"}'],
                                      stdout=launch_log, stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic()+100
            while True:
                text = (folder / 'launch.log').read_text()
                ready = all(s in text for s in ('POSE ready:', 'episode_recorder: ready', 'right_finger_controller'))
                ready = ready and 'Configured and activated' in text
                if ready:
                    break
                if launch.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('launch readiness failed; inspect launch.log')
                time.sleep(.5)
            time.sleep(1)
            pose = subprocess.Popen(['ign', 'topic', '-e', '-t', '/world/lifth/pose/info', '--json-output'],
                                    stdout=subprocess.PIPE, stderr=(folder / 'pose-stderr.log').open('w'),
                                    text=True, start_new_session=True)
            worker = threading.Thread(target=trace, args=(pose, folder / 'cup-trace.jsonl'))
            worker.start()
            start_exit = run(['python3', 'collection/start_episode.py'], folder / 'start.log')
            result['start_exit'] = start_exit
            if start_exit:
                raise RuntimeError('start failed; inspect start.log')
            start = next(json.loads(line) for line in (folder / 'start.log').read_text().splitlines() if line.startswith('{'))
            result['episode_id'] = start['episode_id']
            episode_path = Path(start['path'])
            sequence = subprocess.Popen(['bash', 'collection/ros.sh', 'python3', '-u', 'collection/cup_sequence.py', str(CONFIG), '--world', str(ROOT / 'world.sdf')],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
            timer = threading.Timer(240, stop_process, args=(sequence,))
            timer.start()
            try:
                with (folder / 'sequence.log').open('w') as log:
                    for line in sequence.stdout:
                        now = time.time()
                        log.write(f'{now:.6f} {line}')
                        log.flush()
                        if line.startswith('phase='):
                            phases[line.strip().split('=', 1)[1]] = now
                            print(f'TRIAL {number} {line.strip()}', flush=True)
                result['sequence_exit'] = sequence.wait()
            finally:
                timer.cancel()
            time.sleep(3)
        except Exception as exc:
            result['run_error'] = repr(exc)
        finally:
            stop_process(sequence)
            result['stop_exit'] = run(['ros2', 'service', 'call', '/lifth/episode/stop', 'std_srvs/srv/Trigger', '{}'], folder / 'stop.log', 15)
            stop_process(pose)
            if worker:
                worker.join(timeout=10)
            if result['episode_id']:
                result['raw_path'] = str(episode_path)
                result['validator_exit'] = run(['python3', '-m', 'lifth_dataset.validate', str(episode_path)], folder / 'validator.log', 90)
                manifest = json.loads((episode_path / 'episode.json').read_text())
                result.update(raw_status=manifest['status'], counts=manifest['counts'], errors=manifest['errors'], qos=manifest['provenance']['settings']['qos'])
            stop_process(launch)
    rows = [json.loads(line) for line in (folder / 'cup-trace.jsonl').read_text().splitlines()] if (folder / 'cup-trace.jsonl').exists() else []
    if rows:
        final = rows[-1]
        p = final['cup']['position']
        target = SCENE['place_pose']
        result.update(final_position_m=p, final_tilt_deg=tilt(final),
                      place_xy_error_m=math.hypot(p.get('x', 0)-target[0], p.get('y', 0)-target[1]),
                      place_z_error_m=abs(p.get('z', 0)-target[2]))
        held = [r for r in rows if phases.get('transfer', float('inf')) <= r['wall'] < phases.get('place', float('inf'))]
        if len(held) >= 2:
            result.update(held_sim_seconds=sim(held[-1])-sim(held[0]),
                          held_min_z_m=min(r['cup']['position']['z'] for r in held), held_max_tilt_deg=max(map(tilt, held)))
            result['grasp_success'] = result['held_sim_seconds'] >= 2 and result['held_min_z_m'] >= SCENE['cup_pose'][2] + .05 and result['held_max_tilt_deg'] <= 30
        result['task_success'] = result['grasp_success'] and result.get('sequence_exit') == 0 and result['place_xy_error_m'] <= .02 and result['place_z_error_m'] <= .01 and result['final_tilt_deg'] <= 10
    result['phases'] = phases
    result['finished'] = time.time()
    (folder / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    old_path = ROOT / 'results.json'
    if old_path.exists():
        RESULTS['trials'] = json.loads(old_path.read_text())['trials']
    RESULTS['trials'].append(result)
    (ROOT / 'results.json').write_text(json.dumps(RESULTS, indent=2)+'\n')
    print(f"TRIAL {number} END episode={result['episode_id']} task={result['task_success']} raw={result.get('raw_status')} validator={result['validator_exit']}", flush=True)
    time.sleep(2)
RESULTS['finished'] = time.time()
RESULTS['task_successes'] = sum(r['task_success'] for r in RESULTS['trials'])
RESULTS['raw_complete'] = sum(r.get('raw_status') == 'complete' for r in RESULTS['trials'])
RESULTS['validator_passes'] = sum(r['validator_exit'] == 0 for r in RESULTS['trials'])
(ROOT / 'results.json').write_text(json.dumps(RESULTS, indent=2)+'\n')
print('FINISHED', RESULTS['task_successes'], RESULTS['raw_complete'], RESULTS['validator_passes'], flush=True)
