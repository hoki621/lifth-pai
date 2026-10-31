"""External8 position adapter; ROS imports stay outside the CPU-testable safety core."""

import argparse
import base64
import json
import math
import signal
import sys
import threading
import time
import uuid
from collections import deque
from pathlib import Path

JOINTS = ('base_j2', 'j2_j3', 'j3_j4', 'j4_j5', 'j5_j6', 'j6_ee', 'ee_f1', 'ee_f2')
GROUPS = {'arm_controller': JOINTS[:6], 'left_finger_controller': JOINTS[6:7],
          'right_finger_controller': JOINTS[7:]}
TIMING_KEYS = ('max_observation_age_ns', 'max_observation_skew_ns', 'max_command_age_ns',
               'trajectory_duration_ns', 'watchdog_timeout_ns', 'clock_stall_timeout_ns',
               'clock_jump_tolerance_ns', 'goal_timeout_ns')


def calibrated_timing(value):
    if value.get('validated') is not True:
        raise ValueError('live commands require explicitly calibrated timing: validated=true')
    for key in TIMING_KEYS:
        if type(value.get(key)) is not int or value[key] <= 0:
            raise ValueError(f'{key} must be a positive integer in ns')
    if value['goal_timeout_ns'] <= value['trajectory_duration_ns']:
        raise ValueError('goal timeout must exceed trajectory duration')
    return dict(value)


def positions(value, properties):
    if not isinstance(value, (list, tuple)) or len(value) != 8:
        raise ValueError('expected eight absolute positions')
    for name, position in zip(JOINTS, value):
        bounds = properties[name]
        if (isinstance(position, bool) or not isinstance(position, (int, float))
                or not math.isfinite(position) or not bounds['lower'] <= position <= bounds['upper']):
            raise ValueError(f'invalid position or URDF limit: {name}')
    return list(value)


def stamp_ns(stamp):
    sec, nano = stamp.sec, stamp.nanosec
    if sec < 0 or not 0 <= nano < 1_000_000_000:
        raise ValueError('invalid source stamp')
    return sec * 1_000_000_000 + nano


def pack_rgb(msg):
    if (msg.height, msg.width, msg.encoding, msg.header.frame_id) != (
            360, 640, 'rgb8', 'camera_color_optical_frame'):
        raise ValueError('RGB shape/encoding/frame differs from pinned D405')
    if msg.step < 1920 or len(msg.data) != msg.height * msg.step:
        raise ValueError('invalid image step/data')
    data = bytes(msg.data)
    return base64.b64encode(b''.join(data[y*msg.step:y*msg.step+1920]
                                   for y in range(360))).decode('ascii')


class CausalInputs:
    """Keep bounded DDS history and promote the newest sample reached by /clock."""

    def __init__(self):
        self.latest = {}
        self.pending = {}

    def put(self, key, stamp, values, clock):
        self.pending.setdefault(key, deque(maxlen=128)).append((stamp, values))
        self.advance(clock)

    def advance(self, clock):
        if clock is None:
            return
        for key, pending in list(self.pending.items()):
            causal = max((item for item in reversed(pending) if item[0] <= clock),
                         key=lambda item: item[0], default=None)
            if causal is not None:
                self.latest.update(causal[1])
            future = deque((item for item in pending if item[0] > clock), maxlen=128)
            if future:
                self.pending[key] = future
            else:
                del self.pending[key]


class SafetyCore:
    """Single outstanding observation and action batch. All callbacks serialize on lock.

    send(controller, positions, duration_ns) returns an rclpy-like acceptance future.
    Stopped batches retain unresolved futures/handles, preventing unsafe restart.
    """

    def __init__(self, properties, timing, send, contract_hash, steady=time.monotonic_ns):
        self.properties = properties
        self.timing = calibrated_timing(timing)
        self.send = send
        self.contract_hash = contract_hash
        self.steady = steady
        self.lock = threading.RLock()
        self.stopped = True
        self.reason = 'explicit start required'
        self.session = None
        self.observation = None
        self.batch = None
        self.clock = None
        self.clock_wall = self.steady()
        self.heartbeat_wall = self.steady()
        self.last_target = None
        self.last_target_clock = None

    def clock_update(self, now):
        with self.lock:
            wall = self.steady()
            if type(now) is not int or now < 0:
                self.stop('invalid clock')
                return
            if self.clock is not None:
                delta = now - self.clock
                if delta < 0 or delta > wall - self.clock_wall + self.timing['clock_jump_tolerance_ns']:
                    self.stop('clock jump or reversal')
                if delta == 0:
                    return
            self.clock, self.clock_wall = now, wall

    def start(self, session, contract_hash):
        with self.lock:
            if contract_hash != self.contract_hash:
                raise ValueError('frozen policy contract hash differs')
            if not self.stopped or self.batch is not None:
                raise ValueError('already running or cancellation unresolved; restart refused')
            if not isinstance(session, str) or not session or session == self.session:
                raise ValueError('restart requires a new session')
            if self.clock is None or self.steady() - self.clock_wall > self.timing['clock_stall_timeout_ns']:
                raise ValueError('fresh advancing clock required')
            self.session = session
            self.stopped, self.reason = False, ''
            self.observation = None
            self.minimum_stamps = None
            self.last_target = self.last_target_clock = None
            self.heartbeat_wall = self.steady()
            self.started_wall = self.steady()
            self.future_wall = None

    def sources_ready(self, state_stamp, image_stamp):
        """Wait for DDS /clock delivery to catch up, without using future observations."""
        with self.lock:
            if self.clock is None:
                return False
            if state_stamp > self.clock or image_stamp > self.clock:
                if self.future_wall is None:
                    self.future_wall = self.steady()
                if self.steady()-self.future_wall > self.timing['max_observation_age_ns']:
                    self.stop('source stamps did not become causal')
                return False
            self.future_wall = None
            return True

    def check_observation_delivery(self, state_wall=None, image_wall=None):
        with self.lock:
            if self.stopped:
                return
            now = self.steady()
            for delivered in (state_wall, image_wall):
                if now-(self.started_wall if delivered is None else delivered) > self.timing['max_observation_age_ns']:
                    self.stop('missing or stalled observation delivery')
                    return

    def heartbeat(self, session):
        with self.lock:
            if session == self.session and not self.stopped:
                self.heartbeat_wall = self.steady()

    def observe(self, state, state_stamp, image_stamp, rgb):
        with self.lock:
            if self.stopped or self.batch is not None:
                return None
            self._fresh(state_stamp, image_stamp)
            state = positions(state, self.properties)
            if self.observation is None:
                if self.minimum_stamps is not None and (
                        state_stamp <= self.minimum_stamps[0] or image_stamp <= self.minimum_stamps[1]):
                    return None
                self.observation = {'session': self.session, 'id': uuid.uuid4().hex,
                                    'state': state, 'state_stamp_ns': state_stamp,
                                    'image_stamp_ns': image_stamp, 'rgb': rgb}
                self.observation_wall = self.steady()
            return self.observation

    def _fresh(self, state_stamp, image_stamp):
        if self.clock is None:
            raise ValueError('missing clock')
        for stamp in (state_stamp, image_stamp):
            if (type(stamp) is not int or stamp < 0
                    or not 0 <= self.clock-stamp <= self.timing['max_observation_age_ns']):
                raise ValueError('future or stale observation')
        if abs(state_stamp-image_stamp) > self.timing['max_observation_skew_ns']:
            raise ValueError('observation skew')

    def submit(self, command):
        with self.lock:
            try:
                self.tick()
                obs = self.observation
                if self.stopped or self.batch is not None or obs is None:
                    raise ValueError('stopped, busy or missing observation')
                if (command['session'], command['id']) != (self.session, obs['id']):
                    raise ValueError('wrong session or observation token')
                self._fresh(obs['state_stamp_ns'], obs['image_stamp_ns'])
                if (command['state_stamp_ns'] != obs['state_stamp_ns']
                        or command['image_stamp_ns'] != obs['image_stamp_ns']):
                    raise ValueError('action source stamps differ')
                if self.steady()-self.observation_wall > self.timing['max_command_age_ns']:
                    raise ValueError('delayed inference action')
                values = positions(command['action'], self.properties)
                duration = self.timing['trajectory_duration_ns']
                for index, name in enumerate(JOINTS):
                    velocity = self.properties[name]['velocity']
                    if abs(values[index]-obs['state'][index]) > velocity*duration/1e9:
                        raise ValueError(f'URDF velocity exceeded from state: {name}')
                    if self.last_target is not None:
                        dt = min(duration, self.clock-self.last_target_clock)
                        if dt <= 0 or abs(values[index]-self.last_target[index]) > velocity*dt/1e9:
                            raise ValueError(f'URDF velocity exceeded from previous target: {name}')
                self.last_target, self.last_target_clock = values, self.clock
                self.minimum_stamps = (obs['state_stamp_ns'], obs['image_stamp_ns'])
                self.observation = None
                self.batch = {'entries': {}, 'values': values, 'next': 0,
                              'started': self.steady(), 'observation_wall': self.observation_wall,
                              'state_stamp': obs['state_stamp_ns'], 'image_stamp': obs['image_stamp_ns'],
                              'sending_done': False}
                self._send_next()
            except Exception as error:
                self.stop(str(error))
                raise

    def _send_next(self):
        batch = self.batch
        if self.stopped or batch is None:
            return
        names = list(GROUPS)
        if batch['next'] == len(names):
            batch['sending_done'] = True
            self._settle()
            return
        try:
            self.tick()
            self._fresh(batch['state_stamp'], batch['image_stamp'])
            if self.steady()-batch['observation_wall'] > self.timing['max_command_age_ns']:
                raise ValueError('action expired while waiting for controller acceptance')
            if self.stopped:
                return
        except ValueError as error:
            self.stop(str(error))
            return
        name = names[batch['next']]
        batch['next'] += 1
        entry = {'handle': None, 'terminal': False, 'cancel_sent': False, 'cancel_done': False}
        batch['entries'][name] = entry
        try:
            future = self.send(name, [batch['values'][JOINTS.index(j)] for j in GROUPS[name]],
                               self.timing['trajectory_duration_ns'])
            future.add_done_callback(lambda f: self._accepted(batch, entry, f))
        except Exception as error:
            # A send exception may mean delivery is unknown: keep entry unresolved.
            self.stop(f'goal send failed, delivery unresolved: {error}')

    def _accepted(self, batch, entry, future):
        with self.lock:
            try:
                handle = future.result()
                entry['handle'] = handle
                if not handle.accepted:
                    entry['terminal'] = True
                    self.stop('controller rejected goal')
                else:
                    handle.get_result_async().add_done_callback(
                        lambda f: self._result(batch, entry, f))
                    if self.stopped:
                        self._cancel(entry)
                    else:
                        self._send_next()
            except Exception as error:
                self.stop(f'acceptance unresolved: {error}')
            self._settle()

    def _result(self, batch, entry, future):
        with self.lock:
            try:
                result = future.result()
                entry['terminal'] = True
                if not self.stopped and (result.status != 4 or result.result.error_code != 0):
                    self.stop('controller result failure')
            except Exception as error:
                self.stop(f'result unresolved: {error}')
            self._settle()

    def _cancel(self, entry):
        if entry['handle'] is None or entry['terminal'] or entry['cancel_sent']:
            return
        entry['cancel_sent'] = True
        try:
            entry['handle'].cancel_goal_async().add_done_callback(lambda f: self._cancelled(entry, f))
        except Exception as error:
            self.reason = f'cancel send failed; reset backend before restart: {error}'

    def _cancelled(self, entry, future):
        with self.lock:
            try:
                response = future.result()
                entry['cancel_done'] = True
                if response.return_code != 0 or not response.goals_canceling:
                    self.reason = 'cancel not confirmed; wait for terminal result/reset backend'
            except Exception as error:
                self.reason = f'cancel unconfirmed: {error}'
            self._settle()

    def _settle(self):
        if self.batch and (self.stopped or self.batch['sending_done']):
            if all(e['terminal'] and (not e['cancel_sent'] or e['cancel_done'])
                   for e in self.batch['entries'].values()):
                if not self.stopped:
                    # Require both inputs to be sampled after the completed action batch.
                    self.minimum_stamps = (self.clock, self.clock)
                self.batch = None

    def stop(self, reason):
        with self.lock:
            self.stopped, self.reason = True, reason
            self.observation = None
            if self.batch:
                for entry in self.batch['entries'].values():
                    self._cancel(entry)
                self._settle()

    def tick(self):
        with self.lock:
            if self.stopped:
                return
            now = self.steady()
            if now-self.clock_wall > self.timing['clock_stall_timeout_ns']:
                self.stop('sim clock stalled')
            elif now-self.heartbeat_wall > self.timing['watchdog_timeout_ns']:
                self.stop('ML disconnected or heartbeat stalled')
            elif self.batch and now-self.batch['started'] > self.timing['goal_timeout_ns']:
                self.stop('goal acceptance/result timeout')
            elif self.observation and now-self.observation_wall > self.timing['max_command_age_ns']:
                self.stop('inference stalled')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--contract', type=Path, default=Path(__file__).resolve().parents[1]/'configs/policy_contract.json')
    parser.add_argument('--timing', type=Path, required=True, help='explicit calibrated timing JSON')
    args = parser.parse_args()
    # Shared boundary is stdlib-only and reuses the pinned upstream schema/validator.
    # This imports no ML package into the ROS environment.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from learning.common import contract_digest, load_contract

    contract = load_contract(json.loads(args.contract.read_text()))
    timing = calibrated_timing(json.loads(args.timing.read_text()))
    load_contract({**contract, 'timing': timing})

    import rclpy
    from control_msgs.action import FollowJointTrajectory
    from lifth_bringup.gripper import require_live_model
    from lifth_bringup.model import controller_joints, joint_properties, load_model, robot_description
    from rclpy.action import ActionClient
    from rclpy.clock import Clock, ClockType
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.signals import SignalHandlerOptions
    from rosgraph_msgs.msg import Clock as ClockMessage
    from sensor_msgs.msg import Image, JointState
    from std_msgs.msg import String
    from trajectory_msgs.msg import JointTrajectoryPoint

    from control_lock import acquire_control

    # Lock includes live-model checks, every goal, late acceptance and shutdown cancellation.
    with acquire_control(model='v2_1_1'):
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        node = Node('pai_policy_adapter')
        clients = {}
        core = None
        shutdown = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: shutdown.set())
        signal.signal(signal.SIGTERM, lambda *_: shutdown.set())
        try:
            model = load_model('v2_1_1')
            if {k: tuple(v) for k, v in controller_joints(model).items()} != GROUPS:
                raise ValueError('pinned controller joint mapping differs')
            properties = joint_properties(robot_description('gazebo', 'v2_1_1', True), JOINTS)
            require_live_model(node, 'v2_1_1')
            clients = {name: ActionClient(node, FollowJointTrajectory, f'/{name}/follow_joint_trajectory')
                       for name in GROUPS}
            if not all(client.wait_for_server(timeout_sec=5) for client in clients.values()):
                raise RuntimeError('all three controllers must be available')

            def send(name, values, duration):
                goal = FollowJointTrajectory.Goal()
                goal.trajectory.joint_names = list(GROUPS[name])
                point = JointTrajectoryPoint(positions=list(map(float, values)))
                point.time_from_start.sec, point.time_from_start.nanosec = divmod(duration, 1_000_000_000)
                goal.trajectory.points = [point]
                return clients[name].send_goal_async(goal)

            core = SafetyCore(properties, timing, send, contract_digest(contract))
            observation_pub = node.create_publisher(String, '/pai/policy/observation', 1)
            status_pub = node.create_publisher(String, '/pai/policy/status', 1)
            inputs = CausalInputs()
            latest = inputs.latest
            published_id = None

            def guarded(callback):
                def receive(msg):
                    try:
                        callback(msg)
                    except Exception as error:
                        core.stop(str(error))
                        node.get_logger().error(str(error))
                return receive

            def image(msg):
                stamp = stamp_ns(msg.header.stamp)
                inputs.put('image', stamp, {'rgb': pack_rgb(msg), 'image_stamp': stamp,
                                           'image_wall': time.monotonic_ns()}, core.clock)

            def state(msg):
                if len(msg.name) != len(set(msg.name)) or len(msg.position) != len(msg.name):
                    raise ValueError('invalid joint state names/positions')
                indexed = dict(zip(msg.name, msg.position))
                stamp = stamp_ns(msg.header.stamp)
                inputs.put('state', stamp, {'state': positions([indexed[name] for name in JOINTS], properties),
                                           'state_stamp': stamp, 'state_wall': time.monotonic_ns()}, core.clock)

            def clock(msg):
                core.clock_update(stamp_ns(msg.clock))
                inputs.advance(core.clock)

            def control(msg):
                value = json.loads(msg.data)
                operation = value['op']
                if operation == 'start':
                    core.start(value['session'], value['contract_sha256'])
                elif operation == 'heartbeat':
                    core.heartbeat(value['session'])
                elif operation == 'stop':
                    core.stop('manual stop')
                else:
                    raise ValueError('unknown control operation')

            node.create_subscription(Image, '/camera/camera/color/image_raw', guarded(image), qos_profile_sensor_data)
            node.create_subscription(JointState, '/joint_states', guarded(state), qos_profile_sensor_data)
            node.create_subscription(ClockMessage, '/clock', guarded(clock), 10)
            node.create_subscription(String, '/pai/policy/control', guarded(control), 10)
            node.create_subscription(String, '/pai/policy/action', guarded(lambda m: core.submit(json.loads(m.data))), 1)

            def watchdog():
                nonlocal published_id
                core.tick()
                if not core.stopped:
                    core.check_observation_delivery(latest.get('state_wall'), latest.get('image_wall'))
                    if ({'state', 'rgb'} <= latest.keys()
                            and core.sources_ready(latest['state_stamp'], latest['image_stamp'])):
                        try:
                            obs = core.observe(latest['state'], latest['state_stamp'], latest['image_stamp'], latest['rgb'])
                            # One reliable publication per token. Repeating the same ~923KB
                            # image at the 50Hz watchdog cadence floods the bridge queue.
                            if obs and obs['id'] != published_id:
                                observation_pub.publish(String(data=json.dumps(obs, allow_nan=False)))
                                published_id = obs['id']
                        except ValueError as error:
                            core.stop(str(error))
                status_pub.publish(String(data=json.dumps({'session': core.session, 'stopped': core.stopped,
                                                           'reason': core.reason, 'busy': core.batch is not None,
                                                           'contract_sha256': core.contract_hash,
                                                           'observation_subscribers': observation_pub.get_subscription_count()})))

            # Explicit steady clock: this timer still cancels goals while /clock is frozen.
            node.create_timer(0.02, watchdog, clock=Clock(clock_type=ClockType.STEADY_TIME))
            while rclpy.ok() and not shutdown.is_set():
                rclpy.spin_once(node, timeout_sec=0.02)
        finally:
            if core is not None:
                core.stop('adapter shutdown')
                warned = False
                deadline = time.monotonic_ns()+timing['goal_timeout_ns']
                # Keep lock and callbacks alive for late acceptance. Unknown delivery is a blocker,
                # never a reason to release ownership while an old command can still execute.
                while core.batch is not None and rclpy.ok():
                    rclpy.spin_once(node, timeout_sec=0.02)
                    if time.monotonic_ns() > deadline and not warned:
                        node.get_logger().error('Cancellation unresolved; retaining control lock. Reset backend before terminating.')
                        warned = True
            for client in clients.values():
                client.destroy()
            node.destroy_node()
            rclpy.shutdown()


if __name__ == '__main__':
    main()
