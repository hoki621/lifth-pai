"""Produce labeled start/held/final RGB sheets and source hashes for visual review."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw


def preview(root):
    for result_path in sorted(root.glob('worker-*/placement-*/trial-01/result.json')):
        result = json.loads(result_path.read_text())
        if not (result['task_success'] and result['validator_exit'] == 0):
            continue
        destination = result_path.parent / 'visual-inputs.json'
        raw = Path(result['raw_path'])
        frames = [json.loads(x) for x in (raw / 'rgb.jsonl').read_text().splitlines()]
        traces = [json.loads(x) for x in (result_path.parent / 'cup-trace.jsonl').read_text().splitlines()]
        phase = result['phases']
        held = [x for x in traces if phase['transfer'] <= x['wall'] < phase['place']]
        middle = held[len(held) // 2]['header']['stamp']
        stamp = int(middle.get('sec', 0)) * 10**9 + int(middle.get('nsec', 0))
        chosen = [frames[0], min(frames, key=lambda x: abs(x['source_stamp_ns'] - stamp)), frames[-1]]
        sheet = Image.new('RGB', (640 * 3, 390), 'white')
        draw = ImageDraw.Draw(sheet)
        evidence = {}
        for i, (label, frame) in enumerate(zip(('start', 'held', 'final'), chosen)):
            path = raw / frame['path']
            with Image.open(path) as image:
                sheet.paste(image, (640 * i, 30))
            draw.text((640 * i + 5, 5), f'{result_path.parents[1].name} {label}', fill='black')
            evidence[label] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        sheet.save(result_path.parent / 'visual-sheet.jpg', quality=95)
        destination.write_text(json.dumps(evidence, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    preview(parser.parse_args().root)
