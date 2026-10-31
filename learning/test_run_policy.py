"""CPU-only artificial policy and transport lifecycle checks; no external connections."""

import copy
import json
import queue
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from run_policy import SUBSCRIPTION_QOS, artificial_action, main, reliable_topic_type, wait_adapter_ready, wait_for_stop
from common import contract_digest, load_contract


class ArtificialPolicyTest(unittest.TestCase):
    def test_reliable_subscription_preserves_other_lifecycle_messages(self):
        class Topic:
            def _connect_topic(self, message):
                return message
        topic = reliable_topic_type(Topic)()
        self.assertEqual(topic._connect_topic({'op': 'subscribe', 'topic': '/obs'})['qos'], SUBSCRIPTION_QOS)
        self.assertEqual(topic._connect_topic({'op': 'advertise', 'topic': '/action'}),
                         {'op': 'advertise', 'topic': '/action'})

    def test_hold_and_non_cumulative_small_step(self):
        first = {'state': [0.0]*8}
        later = {'state': [0.02]*8}
        self.assertEqual(artificial_action(later, 'hold', 0, 0.001, first['state']), later['state'])
        values = artificial_action(later, 'small-step', 6, 0.001, first['state'])
        self.assertEqual(values[6], 0.001)
        self.assertEqual(values[:6], later['state'][:6])
        with self.assertRaises(ValueError):
            artificial_action({'state': [0]*7}, 'hold', 0, 0, first['state'])

    def test_stop_confirmation_requires_matching_session_and_idle(self):
        statuses = queue.Queue()
        for status in ({'session': 'old', 'stopped': True, 'busy': False},
                       {'session': 'one', 'stopped': True, 'busy': True},
                       {'session': 'one', 'stopped': True, 'busy': False}):
            statuses.put(status)
        wait_for_stop(statuses, 'one', 0.1)
        with self.assertRaisesRegex(RuntimeError, 'Stop unconfirmed'):
            wait_for_stop(queue.Queue(), 'one', 0.001)

    def test_startup_waits_unarmed_for_observation_dds_match(self):
        statuses = queue.Queue()
        idle = {'stopped': True, 'busy': False, 'contract_sha256': 'frozen',
                'observation_subscribers': 0}
        statuses.put(idle)
        statuses.put({**idle, 'observation_subscribers': 1})
        wait_adapter_ready(statuses, 'frozen', 0.1)
        self.assertTrue(statuses.empty())
        statuses.put(idle)
        with self.assertRaisesRegex(RuntimeError, 'DDS subscriber'):
            wait_adapter_ready(statuses, 'frozen', 0.001)


class TransportLifecycleTest(unittest.TestCase):
    """Minimal fake pub/sub boundary exercises the real CLI loop and its cleanup."""

    def run_fake(self, failure=None):
        topics = {}
        terminated = []
        actions = []
        control_ops = []
        active_session = [None]
        ros = NS(is_connected=True, on=lambda *args: None, run=lambda **kwargs: None,
                 terminate=lambda: terminated.append(True))

        def emit(name, value):
            topics[name].callback({'data': json.dumps(value)})

        def observation(token, stamp):
            return {'session': active_session[0], 'id': token, 'state': [0.0]*8,
                    'state_stamp_ns': stamp, 'image_stamp_ns': stamp, 'rgb': ''}

        class Topic:
            def __init__(self, ros, name, message_type, **kwargs):
                self.name = name
                topics[name] = self

            def advertise(self):
                pass

            def subscribe(self, callback):
                self.callback = callback
                if self.name.endswith('/status'):
                    emit(self.name, {'session': None, 'stopped': True, 'busy': False,
                                     'observation_subscribers': 1,
                                     'contract_sha256': 'wrong' if failure == 'contract' else contract_digest(load_contract())})

            def publish(self, msg):
                value = copy.deepcopy(msg['data'])
                value = json.loads(value)
                if self.name.endswith('/control'):
                    control_ops.append(value['op'])
                    if value['op'] == 'start':
                        active_session[0] = value['session']
                        emit('/pai/policy/observation', observation('first', 1))
                    elif value['op'] == 'stop':
                        if failure == 'stop':
                            raise RuntimeError('stop publish failed')
                        emit('/pai/policy/status', {'session': active_session[0], 'stopped': True, 'busy': False})
                elif self.name.endswith('/action'):
                    actions.append(value)
                    emit('/pai/policy/observation', observation('second', 2))

            def unsubscribe(self):
                if failure == 'unsubscribe':
                    raise RuntimeError('unsubscribe failed')

            def unadvertise(self):
                pass

        fake = NS(Ros=lambda **kwargs: ros, Topic=Topic, Message=lambda value: value)
        with patch.dict(sys.modules, {'roslibpy': fake}), \
                patch('importlib.metadata.version', return_value='2.0.1'), \
                patch('signal.signal'), patch.object(sys, 'argv', ['run_policy.py', '--mode', 'hold', '--steps', '1']):
            if failure == 'contract':
                with self.assertRaisesRegex(RuntimeError, 'contract hash'):
                    main()
            elif failure:
                with self.assertRaisesRegex(RuntimeError, f'{failure}.*failed'):
                    main()
            else:
                main()
        self.assertEqual(terminated, [True])
        if failure == 'contract':
            self.assertFalse(actions)
            self.assertFalse(control_ops)
            return
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['action'], [0]*8)
        self.assertEqual(control_ops[0], 'start')
        self.assertEqual(control_ops[-1], 'stop')

    def test_hold_roundtrip_and_confirmed_stop(self):
        self.run_fake()

    def test_terminate_even_if_stop_publish_throws(self):
        self.run_fake('stop')

    def test_terminate_even_if_unsubscribe_throws(self):
        self.run_fake('unsubscribe')

    def test_contract_handshake_mismatch_never_sends_start(self):
        self.run_fake('contract')


if __name__ == '__main__':
    unittest.main()
