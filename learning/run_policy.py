"""Synchronous local policy -> localhost rosbridge -> ROS safety adapter (CPU default).

Hold and small-step modes exercise exactly the same transport/adapter as a checkpoint.
Nothing connects until this CLI is explicitly executed.
"""

import argparse
import base64
import importlib.metadata
import json
import math
import queue
import signal
import threading
import time
import uuid
from pathlib import Path


DEFAULT_CONTRACT = Path(__file__).resolve().parents[1]/'configs/policy_contract.json'
SUBSCRIPTION_QOS = {'reliability': 'reliable', 'durability': 'volatile',
                    'history': 'keep_last', 'depth': 10}


def reliable_topic_type(base):
    """Pinned roslibpy 2.0.1 lacks a public qos argument; preserve its topic lifecycle.

    The pinned rosbridge default is BEST_EFFORT even for our reliable publisher.
    Large fragmented RGB strings need an explicitly reliable ROS subscription.
    """
    class ReliableTopic(base):
        def _connect_topic(self, message):
            if message.get('op') == 'subscribe':
                message['qos'] = dict(SUBSCRIPTION_QOS)
            return super()._connect_topic(message)
    return ReliableTopic


def artificial_action(observation, mode, joint, delta, initial):
    state = observation['state']
    if len(state) != 8 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in state):
        raise ValueError('invalid eight-axis observation')
    result = list(state)
    if mode == 'small-step':
        # One fixed offset from the first observation, never a cumulative per-frame step.
        result[joint] = initial[joint]+delta
    return result


def policy_action(observation, contract, loaded):
    import torch

    policy, preprocessor, postprocessor = loaded
    height, width, channels = contract['image_shape_hwc']
    raw = base64.b64decode(observation['rgb'], validate=True)
    if len(raw) != height*width*channels:
        raise ValueError('RGB payload length differs from contract')
    image = torch.frombuffer(bytearray(raw), dtype=torch.uint8).reshape(height, width, channels)
    batch = {contract['image_key']: image.permute(2, 0, 1).float()/255,
             contract['state_key']: torch.tensor(observation['state'], dtype=torch.float32),
             'task': contract['task']}
    with torch.inference_mode():
        result = postprocessor(policy.select_action(preprocessor(batch)))
    if tuple(result.shape) != (1, 8) or not torch.isfinite(result).all():
        raise ValueError('expected finite postprocessed action with shape (1, 8)')
    return result[0].cpu().tolist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument('--mode', choices=('hold', 'small-step', 'checkpoint'), required=True)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--port', type=int, default=9090, help='localhost bridge port')
    parser.add_argument('--joint', type=int, choices=range(8), default=0)
    parser.add_argument('--delta', type=float, default=0.001, help='single fixed offset, rad for arm / m for fingers')
    parser.add_argument('--steps', type=int, default=1, help='number of applied actions; 0 runs until stopped')
    parser.add_argument('--timeout', type=float, default=10, help='steady seconds without adapter progress')
    args = parser.parse_args()
    if (not math.isfinite(args.delta) or not math.isfinite(args.timeout) or args.timeout <= 0
            or not 1 <= args.port <= 65535 or args.steps < 0
            or (args.mode == 'checkpoint') != (args.checkpoint is not None)):
        parser.error('invalid delta/timeout/steps or checkpoint mode/path combination')
    from common import contract_digest, load_contract

    contract = load_contract(json.loads(args.contract.read_text()))
    contract_hash = contract_digest(contract)
    loaded = None
    if args.mode == 'checkpoint':
        from check_checkpoint import load_checkpoint

        loaded = load_checkpoint(args.checkpoint, contract=contract, device=args.device)
        for component in loaded:
            component.reset()

    import roslibpy

    if importlib.metadata.version('roslibpy') != '2.0.1':
        raise RuntimeError('requires pinned roslibpy==2.0.1')
    topic_type = reliable_topic_type(roslibpy.Topic)
    ros = roslibpy.Ros(host='127.0.0.1', port=args.port)
    stop = threading.Event()
    observations = queue.Queue(maxsize=1)
    statuses = queue.Queue(maxsize=1)
    session = uuid.uuid4().hex
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    ros.on('close', lambda *_: stop.set())  # Reconnect never starts a new session.
    control = topic_type(ros, '/pai/policy/control', 'std_msgs/msg/String', reconnect_on_close=False)
    action = topic_type(ros, '/pai/policy/action', 'std_msgs/msg/String', reconnect_on_close=False)
    observation_topic = topic_type(ros, '/pai/policy/observation', 'std_msgs/msg/String',
                                     queue_length=1, reconnect_on_close=False)
    status_topic = topic_type(ros, '/pai/policy/status', 'std_msgs/msg/String',
                                queue_length=1, reconnect_on_close=False)

    def latest(target, msg):
        try:
            value = json.loads(msg['data'])
            if target is observations and value.get('session') != session:
                return
            if target.full():
                target.get_nowait()
            target.put_nowait(value)
        except (ValueError, KeyError, queue.Empty, queue.Full):
            stop.set()

    def publish(topic, payload):
        if not ros.is_connected:
            raise RuntimeError('bridge disconnected; explicit process restart required')
        topic.publish(roslibpy.Message({'data': json.dumps(payload, allow_nan=False)}))

    def heartbeat():
        while not stop.wait(0.02):
            try:
                publish(control, {'op': 'heartbeat', 'session': session})
            except Exception:
                stop.set()

    worker = None
    start_sent = False
    try:
        ros.run(timeout=args.timeout)
        control.advertise()
        action.advertise()
        observation_topic.subscribe(lambda m: latest(observations, m))
        status_topic.subscribe(lambda m: latest(statuses, m))
        # Wait for the subscriptions and an idle adapter before a single explicit start.
        wait_adapter_ready(statuses, contract_hash, args.timeout)
        start_sent = True
        publish(control, {'op': 'start', 'session': session, 'contract_sha256': contract_hash})
        worker = threading.Thread(target=heartbeat, daemon=True)
        worker.start()
        initial = None
        seen = set()
        pending = None
        count = 0
        deadline = time.monotonic()+args.timeout
        while not stop.is_set():
            if time.monotonic() > deadline:
                raise RuntimeError('adapter observation/result timeout')
            try:
                status = statuses.get_nowait()
                if status.get('session') == session and status['stopped']:
                    raise RuntimeError(f"adapter stopped: {status['reason']}")
            except queue.Empty:
                pass
            try:
                obs = observations.get(timeout=0.02)
            except queue.Empty:
                if time.monotonic() > deadline:
                    raise RuntimeError('adapter observation/result timeout')
                continue
            if obs['id'] in seen:
                continue
            # A new observation means all three previous action results succeeded.
            if pending is not None:
                count += 1
                print(json.dumps({'applied': count, 'observation_id': obs['id'],
                                  'state_stamp_ns': obs['state_stamp_ns'],
                                  'image_stamp_ns': obs['image_stamp_ns'],
                                  'inference_wall_ns': pending['inference_wall_ns'],
                                  'apply_wall_ns': time.monotonic_ns()-pending['sent_wall_ns'],
                                  'apply_sim_ns': obs['state_stamp_ns']-pending['state_stamp_ns']}), flush=True)
                if args.steps and count >= args.steps:
                    break
            seen.add(obs['id'])
            if initial is None:
                initial = list(obs['state'])
            started = time.monotonic_ns()
            values = (policy_action(obs, contract, loaded) if loaded else
                      artificial_action(obs, args.mode, args.joint, args.delta, initial))
            if stop.is_set():
                break
            pending = {'inference_wall_ns': time.monotonic_ns()-started,
                       'sent_wall_ns': time.monotonic_ns(), 'state_stamp_ns': obs['state_stamp_ns']}
            publish(action, {key: obs[key] for key in ('session', 'id', 'state_stamp_ns', 'image_stamp_ns')}
                    | {'action': values})
            deadline = time.monotonic()+args.timeout
    finally:
        stop.set()
        if worker:
            worker.join(timeout=1)
        try:
            if ros.is_connected and start_sent:
                publish(control, {'op': 'stop', 'session': session})
                wait_for_stop(statuses, session, args.timeout)
        finally:
            try:
                observation_topic.unsubscribe()
                status_topic.unsubscribe()
                action.unadvertise()
                control.unadvertise()
            finally:
                ros.terminate()


def wait_adapter_ready(statuses, contract_hash, timeout):
    """Wait unarmed for the large observation DDS route, not just the status route."""
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            status = statuses.get(timeout=max(0, deadline-time.monotonic()))
        except queue.Empty:
            break
        if not status['stopped'] or status['busy']:
            raise RuntimeError('adapter already running or cancellation unresolved')
        if status.get('contract_sha256') != contract_hash:
            raise RuntimeError('frozen policy contract hash differs from adapter')
        if status.get('observation_subscribers', 0) > 0:
            return
    raise RuntimeError('observation DDS subscriber did not match before startup timeout')


def wait_for_stop(statuses, session, timeout):
    # Wait for adapter acknowledgement and terminal results before closing transport.
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            status = statuses.get(timeout=0.05)
        except queue.Empty:
            continue
        if status.get('session') == session and status['stopped'] and not status['busy']:
            return
    raise RuntimeError('Stop unconfirmed: adapter retains control; verify/reset backend before restart.')


if __name__ == '__main__':
    main()
