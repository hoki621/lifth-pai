"""CPU tests: no ROS imports, simulator, bridge or robot connection."""

import ast
import copy
import json
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace as NS

from policy_adapter import GROUPS, JOINTS, CausalInputs, SafetyCore, calibrated_timing, pack_rgb


class Goal:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.result = Future()
        self.cancel = Future()
        self.cancel_count = 0

    def get_result_async(self):
        return self.result

    def cancel_goal_async(self):
        self.cancel_count += 1
        return self.cancel

    def finish(self, status=4, error=0):
        self.result.set_result(NS(status=status, result=NS(error_code=error)))

    def cancelled(self):
        self.cancel.set_result(NS(return_code=0, goals_canceling=[1]))
        self.finish(status=5)


class AdapterTest(unittest.TestCase):
    def setUp(self):
        self.now = 1_000_000_000
        contract = json.loads((Path(__file__).resolve().parents[1]/'configs/policy_contract.json').read_text())
        self.timing = {**contract['timing'], 'validated': True, 'trajectory_duration_ns': 100_000_000,
                       'watchdog_timeout_ns': 150_000_000, 'clock_stall_timeout_ns': 150_000_000,
                       'clock_jump_tolerance_ns': 100_000_000, 'goal_timeout_ns': 300_000_000}
        self.properties = {name: {'lower': -1, 'upper': 1, 'velocity': 1} for name in JOINTS}
        self.calls = []

        def send(name, values, duration):
            future = Future()
            self.calls.append((name, values, duration, future))
            return future

        self.core = SafetyCore(self.properties, self.timing, send, contract_hash='frozen', steady=lambda: self.now)
        self.core.clock_update(self.now)
        self.core.start('one', 'frozen')
        self.obs = self.core.observe([0.0]*8, self.now, self.now, 'rgb')
        self.command = {k: self.obs[k] for k in ('session', 'id', 'state_stamp_ns', 'image_stamp_ns')}
        self.command['action'] = [0.01]*8

    def accept(self, index, accepted=True):
        handle = Goal(accepted)
        self.calls[index][3].set_result(handle)
        return handle

    def advance(self, ns, clock=True, heartbeat=True):
        self.now += ns
        if clock:
            self.core.clock_update(self.now)
        if heartbeat:
            self.core.heartbeat('one')

    def test_calibration_required(self):
        for bad in ({**self.timing, 'validated': False}, {**self.timing, 'goal_timeout_ns': 1},
                    {**self.timing, 'max_command_age_ns': True}):
            with self.assertRaises(ValueError):
                calibrated_timing(bad)

    def test_contract_mismatch_rejected_before_start_or_goal(self):
        self.core.stop('manual')
        with self.assertRaisesRegex(ValueError, 'contract hash'):
            self.core.start('two', 'different')
        self.assertTrue(self.core.stopped)
        self.assertFalse(self.calls)

    def test_entire_eight_vector_checked_before_first_send(self):
        cases = [[0]*7, [0]*7+[float('nan')], [0]*7+[float('inf')], [0]*7+[True],
                 [0]*7+[2], [0]*7+[0.11]]
        for action in cases:
            with self.subTest(action=action):
                self.setUp()
                with self.assertRaises(ValueError):
                    self.core.submit({**self.command, 'action': action})
                self.assertFalse(self.calls)
                self.assertTrue(self.core.stopped)

    def test_controller_mapping_and_new_observation_after_results(self):
        self.core.submit(self.command)
        goals = [self.accept(i) for i in range(3)]
        self.assertEqual([c[0] for c in self.calls], list(GROUPS))
        self.assertEqual([len(c[1]) for c in self.calls], [6, 1, 1])
        self.assertIsNone(self.core.observe([0]*8, self.now, self.now, 'rgb'))
        for goal in goals:
            goal.finish()
        self.assertIsNone(self.core.batch)
        self.assertIsNone(self.core.observe([0]*8, self.now, self.now, 'rgb'))
        self.advance(10_000_000)
        obs = self.core.observe([0.01]*8, self.now, self.now, 'new rgb')
        self.assertNotEqual(obs['id'], self.obs['id'])

    def test_source_stamps_skew_and_future_rejected(self):
        for stamps in ((self.now-101_000_000, self.now), (self.now, self.now+1),
                       (self.now, self.now-self.timing['max_observation_skew_ns']-1)):
            with self.subTest(stamps=stamps), self.assertRaises(ValueError):
                self.core.observe([0]*8, *stamps, 'rgb')
        with self.assertRaises(ValueError):
            self.core.submit({**self.command, 'image_stamp_ns': self.now-1})
        self.assertFalse(self.calls)

    def test_delayed_action_and_wrong_session_rejected(self):
        self.advance(self.timing['max_command_age_ns']+1)
        with self.assertRaises(ValueError):
            self.core.submit(self.command)
        self.assertFalse(self.calls)
        self.setUp()
        with self.assertRaises(ValueError):
            self.core.submit({**self.command, 'session': 'old'})
        self.assertFalse(self.calls)

    def test_partial_rejection_cancels_arm_and_never_sends_right(self):
        self.core.submit(self.command)
        arm = self.accept(0)
        self.accept(1, accepted=False)
        self.assertTrue(self.core.stopped)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(arm.cancel_count, 1)
        with self.assertRaises(ValueError):
            self.core.start('two', 'frozen')
        arm.cancelled()
        self.assertIsNone(self.core.batch)
        self.core.start('two', 'frozen')
        self.assertFalse(self.core.stopped)

    def test_cancel_waits_for_response_and_terminal(self):
        self.core.submit(self.command)
        arm = self.accept(0)
        self.core.stop('manual')
        finger = self.accept(1)  # acceptance after stop
        arm.finish(status=5)
        finger.finish(status=5)
        self.assertIsNotNone(self.core.batch)
        arm.cancel.set_result(NS(return_code=0, goals_canceling=[1]))
        self.assertIsNotNone(self.core.batch)
        finger.cancel.set_result(NS(return_code=0, goals_canceling=[1]))
        self.assertIsNone(self.core.batch)
        self.assertEqual(len(self.calls), 2)

    def test_acceptance_after_action_expiry_does_not_send_fingers(self):
        self.core.submit(self.command)
        self.advance(self.timing['max_command_age_ns']+1)
        arm = self.accept(0)
        self.assertTrue(self.core.stopped)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(arm.cancel_count, 1)
        arm.cancelled()
        self.assertIsNone(self.core.batch)

    def test_acceptance_after_goal_timeout_is_cancelled(self):
        self.core.submit(self.command)
        self.advance(self.timing['goal_timeout_ns']+1)
        self.core.tick()
        self.assertTrue(self.core.stopped)
        arm = self.accept(0)
        self.assertEqual(arm.cancel_count, 1)
        self.assertEqual(len(self.calls), 1)
        arm.cancelled()

    def test_result_failure_cancels_remaining_and_late_acceptance(self):
        self.core.submit(self.command)
        arm = self.accept(0)
        arm.finish(status=6, error=-4)
        finger = self.accept(1)
        self.assertTrue(self.core.stopped)
        self.assertEqual(finger.cancel_count, 1)
        self.assertEqual(len(self.calls), 2)
        finger.cancelled()

    def test_send_exception_preserves_unresolved_delivery(self):
        def fail(*args):
            raise RuntimeError('transport lost')
        self.core.send = fail
        self.core.submit(self.command)
        self.assertTrue(self.core.stopped)
        self.assertIsNotNone(self.core.batch)
        with self.assertRaises(ValueError):
            self.core.start('two', 'frozen')

    def test_missing_observations_deadline_independent_of_heartbeat(self):
        self.core.observation = None
        self.advance(self.timing['max_observation_age_ns']+1)
        self.core.check_observation_delivery()
        self.assertTrue(self.core.stopped)
        self.assertIn('observation', self.core.reason)

    def test_future_dds_sample_waits_for_clock_and_cannot_wait_forever(self):
        self.assertFalse(self.core.sources_ready(self.now+9_000_000, self.now))
        self.assertFalse(self.core.stopped)
        self.advance(10_000_000)
        self.assertTrue(self.core.sources_ready(self.now-1_000_000, self.now))
        self.assertFalse(self.core.sources_ready(self.now+1_000_000_000, self.now))
        self.advance(self.timing['max_observation_age_ns']+1)
        self.assertFalse(self.core.sources_ready(self.now+1_000_000_000, self.now))
        self.assertTrue(self.core.stopped)

    def test_streaming_future_states_preserve_last_causal_sample(self):
        inputs = CausalInputs()
        inputs.put('state', self.now, {'state_stamp': self.now, 'state_wall': self.now}, self.now)
        for _ in range(5):
            inputs.put('state', self.now+9_000_000,
                       {'state_stamp': self.now+9_000_000, 'state_wall': self.now}, self.now)
            self.assertEqual(inputs.latest['state_stamp'], self.now)
            self.advance(10_000_000)
            inputs.advance(self.now)
            self.assertEqual(inputs.latest['state_stamp'], self.now-1_000_000)
            inputs.put('state', self.now, {'state_stamp': self.now, 'state_wall': self.now}, self.now)
        # Pending future traffic cannot refresh the causal delivery timestamp.
        delivered = inputs.latest['state_wall']
        self.advance(self.timing['max_observation_age_ns']+1)
        inputs.put('state', self.now+1_000_000_000, {'state_wall': self.now}, self.now)
        self.core.check_observation_delivery(inputs.latest['state_wall'], self.now)
        self.assertEqual(inputs.latest['state_wall'], delivered)
        self.assertTrue(self.core.stopped)

    def test_multiple_arrivals_before_clock_promote_latest_causal_and_retain_future(self):
        inputs = CausalInputs()
        inputs.put('state', 100, {'state_stamp': 100, 'state_wall': 1}, 100)
        inputs.put('state', 109, {'state_stamp': 109, 'state_wall': 2}, 100)
        inputs.put('state', 119, {'state_stamp': 119, 'state_wall': 3}, 100)
        self.assertEqual(inputs.latest['state_stamp'], 100)
        inputs.advance(110)
        self.assertEqual(inputs.latest, {'state_stamp': 109, 'state_wall': 2})
        inputs.advance(120)
        self.assertEqual(inputs.latest, {'state_stamp': 119, 'state_wall': 3})
        self.assertFalse(inputs.pending)

    def test_pending_history_overflow_keeps_bound_and_never_promotes_future(self):
        inputs = CausalInputs()
        inputs.put('state', 100, {'state_stamp': 100}, 100)
        for stamp in range(101, 230):
            inputs.put('state', stamp, {'state_stamp': stamp}, 100)
        self.assertEqual(len(inputs.pending['state']), 128)
        inputs.advance(101)  # Oldest pending sample was evicted; latest causal stays valid.
        self.assertEqual(inputs.latest['state_stamp'], 100)
        inputs.advance(102)
        self.assertEqual(inputs.latest['state_stamp'], 102)
        inputs.advance(229)
        self.assertEqual(inputs.latest['state_stamp'], 229)
        self.assertFalse(inputs.pending)

    def test_stalled_state_or_rgb_delivery(self):
        self.advance(self.timing['max_observation_age_ns']+1)
        self.core.check_observation_delivery(self.now, self.now-101_000_000)
        self.assertTrue(self.core.stopped)

    def test_inference_stall(self):
        self.advance(self.timing['max_command_age_ns']+1)
        self.core.tick()
        self.assertTrue(self.core.stopped)
        self.assertEqual(self.core.reason, 'inference stalled')

    def test_clock_stall_disconnect_and_clock_anomalies_cancel(self):
        for trigger in ('clock', 'heartbeat', 'reversal', 'jump'):
            with self.subTest(trigger=trigger):
                self.setUp()
                self.core.submit(self.command)
                arm = self.accept(0)
                if trigger == 'clock':
                    self.advance(151_000_000, clock=False)
                elif trigger == 'heartbeat':
                    self.advance(151_000_000, heartbeat=False)
                elif trigger == 'reversal':
                    self.core.clock_update(self.now-1)
                else:
                    self.core.clock_update(self.now+self.timing['clock_jump_tolerance_ns']+1)
                self.core.tick()
                self.assertTrue(self.core.stopped)
                self.assertEqual(arm.cancel_count, 1)
                late = self.accept(1)
                arm.cancelled()
                late.cancelled()
                self.core.heartbeat('one')
                self.assertTrue(self.core.stopped)

    def test_velocity_from_previous_target(self):
        self.core.submit(self.command)
        goals = [self.accept(i) for i in range(3)]
        for goal in goals:
            goal.finish()
        self.advance(1_000_000)
        obs = self.core.observe([0.01]*8, self.now, self.now, 'rgb')
        command = {k: obs[k] for k in ('session', 'id', 'state_stamp_ns', 'image_stamp_ns')}
        command['action'] = [0.02]*8  # within measured->target budget, over target->target dt budget
        with self.assertRaisesRegex(ValueError, 'previous target'):
            self.core.submit(command)
        self.assertEqual(len(self.calls), 3)

    def test_rgb_padding_and_frame(self):
        import base64
        pixel = b'\x01\x02\x03'*640
        msg = NS(height=360, width=640, encoding='rgb8', step=1924,
                 data=(pixel+b'pad!')*360, header=NS(frame_id='camera_color_optical_frame'))
        self.assertEqual(base64.b64decode(pack_rgb(msg)), pixel*360)
        for field, value in (('encoding', 'bgr8'), ('step', 1923), ('height', 1)):
            invalid = copy.deepcopy(msg)
            setattr(invalid, field, value)
            with self.assertRaises(ValueError):
                pack_rgb(invalid)

    def test_bridge_parameter_strings_match_pinned_parser(self):
        # Source-level check, not a claim of ROS runtime compatibility. The exact pinned
        # parse_glob_string strips [] and single quotes and comma-splits each string.
        tree = ast.parse(Path(__file__).with_name('policy_bridge.launch.py').read_text())
        assignment = next(n for n in tree.body if isinstance(n, ast.Assign))
        params = ast.literal_eval(assignment.value)
        def parse(value):
            if value == '[]':
                return []
            return [s.strip().strip("'") for s in value[1:-1].split(',') if s.strip()]
        self.assertEqual(params['address'], '127.0.0.1')
        self.assertEqual(parse(params['topics_pub_glob']), ['/pai/policy/control', '/pai/policy/action'])
        self.assertEqual(parse(params['topics_sub_glob']), ['/pai/policy/observation', '/pai/policy/status'])
        for name in ('topics_glob', 'services_glob', 'actions_glob'):
            self.assertEqual(parse(params[name]), [])


if __name__ == '__main__':
    unittest.main()
