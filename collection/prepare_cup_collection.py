"""Generate reproducible random upright cup scenes using the existing teacher geometry."""

import copy
import math
import random


def body_center(pose):
    x, y, _, _, _, yaw = pose
    return (x + .0165 * math.cos(yaw) + .0018 * math.sin(yaw),
            y + .0165 * math.sin(yaw) - .0018 * math.cos(yaw))


def random_scene(baseline, seed, placement_id, split):
    rng = random.Random(seed)
    scene = copy.deepcopy(baseline)
    scene['cup_pose'][0] += rng.uniform(-.02, .10)
    scene['cup_pose'][1] += rng.uniform(-.28, .02)
    scene['cup_pose'][5] += rng.uniform(-.15, .15)
    old_center = body_center(baseline['cup_pose'])
    new_center = body_center(scene['cup_pose'])
    destination = body_center(baseline['place_pose'])
    scene['place_pose'][5] = scene['cup_pose'][5]
    offset_center = body_center(scene['place_pose'])
    for axis in (0, 1):
        scene['place_pose'][axis] += destination[axis] - offset_center[axis]
    delta = scene['cup_pose'][5] - baseline['cup_pose'][5]
    c, s = math.cos(delta), math.sin(delta)
    qz, qw = math.sin(delta / 2), math.cos(delta / 2)
    for step in scene['steps']:
        target = step.get('pose', step.get('cartesian'))
        if target is None:
            continue
        # 持ち手と把持姿勢をcup yawに追従させる。緑の置き先の胴体中心は固定。
        if step['name'] in ('approach', 'lower', 'grasp_pose', 'lift'):
            before, after = old_center, new_center
        elif step['name'] in ('transfer', 'place', 'retreat'):
            before = after = destination
        else:
            before = after = None
        if before is not None:
            x, y = target[0] - before[0], target[1] - before[1]
            target[:2] = [after[0] + c*x - s*y, after[1] + s*x + c*y]
        x, y, z, w = target[3:]
        target[3:] = [qw*x - qz*y, qz*x + qw*y, qw*z + qz*w, qw*w - qz*z]
    # Start from the known forward-facing posture before moving to each cup.
    approach = next(step for step in scene['steps'] if step['name'] == 'approach')
    reference = next(step for step in baseline['steps'] if step['name'] == 'approach')
    preapproach = copy.deepcopy(reference)
    preapproach['name'] = 'preapproach'
    approach['cartesian'] = approach.pop('pose')
    scene['steps'].insert(1, preapproach)
    scene.update(placement_id=placement_id, split=split, seed=seed,
                 candidate=True, physical_validation='pending')
    return scene
