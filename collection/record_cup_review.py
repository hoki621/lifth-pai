"""Record an explicitly supplied visual review after inspecting a trial's RGB images."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def record(trial_path, observer, reason):
    entry = json.loads(trial_path.read_text())
    folder = trial_path.parent / 'trial-01'
    result = json.loads((folder / 'result.json').read_text())
    if not (result['task_success'] is True and result['validator_exit'] == 0
            and result['raw_status'] == 'complete' and result['sequence_exit'] == 0):
        raise ValueError('visual success cannot accept a physically failed or invalid raw trial')
    if (entry.get('episode_id') != result['episode_id']
            or entry.get('raw_path') != result['raw_path']):
        raise ValueError('collection bookkeeping is not finished; wait before reviewing')
    images = json.loads((folder / 'visual-inputs.json').read_text())
    if set(images) != {'start', 'held', 'final'}:
        raise ValueError('all three reviewed images required')
    for image in images.values():
        if hashlib.sha256(Path(image['path']).read_bytes()).hexdigest() != image['sha256']:
            raise ValueError('review image changed')
    review = folder / 'visual-review.json'
    with review.open('x') as stream:
        json.dump({'observer': observer, 'reason': reason, 'outcome': 'success',
                   'reviewed_at': datetime.now(timezone.utc).isoformat(), 'images': images}, stream, indent=2)
        stream.write('\n')
    entry.update(task_success=True, accepted=True, exclusion_reason='', visual_review=str(review.resolve()))
    trial_path.write_text(json.dumps(entry, indent=2) + '\n')
    (trial_path.parent / 'converter-selection.json').write_text(
        json.dumps({'version': 1, 'episodes': [entry]}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial', type=Path)
    parser.add_argument('--observer', required=True)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    if not args.observer.strip() or not args.reason.strip():
        parser.error('observer and reason must be nonempty')
    record(args.trial.resolve(), args.observer, args.reason)
