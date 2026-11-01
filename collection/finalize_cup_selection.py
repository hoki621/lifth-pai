"""Seal 100 reviewed successful trials into the existing converter manifest format."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path


def finalize(root):
    entries = []
    for path in sorted(root.glob('worker-*/placement-*/trial.json')):
        entry = json.loads(path.read_text())
        if entry['accepted']:
            if entry.get('conversion_error'):
                raise ValueError(f'accepted trial has a converter rejection: {path}')
            result = json.loads(Path(entry['physical_evidence']).read_text())
            if not (entry['task_success'] is True and result['task_success'] is True
                    and result['validator_exit'] == 0 and result['raw_status'] == 'complete'
                    and result['sequence_exit'] == 0):
                raise ValueError(f'accepted trial lacks physical/raw success: {path}')
            review = json.loads(Path(entry['visual_review']).read_text())
            if review['outcome'] != 'success' or not review['observer'] or not review['reason']:
                raise ValueError(f'accepted trial lacks visual review: {path}')
            if set(review['images']) != {'start', 'held', 'final'}:
                raise ValueError(f'missing reviewed images: {path}')
            for image in review['images'].values():
                if hashlib.sha256(Path(image['path']).read_bytes()).hexdigest() != image['sha256']:
                    raise ValueError(f'reviewed image changed: {path}')
        elif not entry['exclusion_reason'].strip():
            raise ValueError(f'excluded trial needs a reason: {path}')
        entries.append(entry)
    accepted = [entry for entry in entries if entry['accepted']]
    counts = Counter(entry['split'] for entry in accepted)
    if counts != {'train': 90, 'validation': 10}:
        raise ValueError(f'need 90 train / 10 validation reviewed successes; found {dict(counts)}')
    for key in ('placement_id', 'episode_id', 'raw_path'):
        if len({entry[key] for entry in accepted}) != 100:
            raise ValueError(f'duplicate {key}')
    heldout = json.loads((root / 'heldout-reserved.json').read_text())
    reserved = {tuple(scene['cup_pose']) for scene in heldout}
    if any(tuple(entry['cup_pose']) in reserved for entry in accepted):
        raise ValueError('heldout placement leaked into collected selection')
    destination = root / 'final-acceptance.json'
    with destination.open('x') as stream:
        json.dump({'version': 1, 'episodes': entries}, stream, indent=2)
        stream.write('\n')
    fields = ('placement_id', 'episode_id', 'split', 'cup_x', 'cup_y', 'cup_yaw',
              'physical_task_success', 'task_success', 'accepted', 'exclusion_reason',
              'raw_path', 'scene', 'physical_evidence', 'visual_review')
    with (root / 'episodes.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for entry in entries:
            row = {key: entry.get(key) for key in fields}
            row.update(cup_x=entry['cup_pose'][0], cup_y=entry['cup_pose'][1],
                       cup_yaw=entry['cup_pose'][5])
            writer.writerow(row)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(finalize(parser.parse_args().root.resolve()))
