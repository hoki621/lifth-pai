"""失敗・停止時に後続目標を送らず、不正設定は開始前に拒否する。"""

import unittest

from cup_sequence import run_steps


class SequenceTests(unittest.TestCase):
    def test_success_and_failure(self):
        steps = [{"name": str(i), "gripper": [0, 0]} for i in range(3)]
        sent = []
        run_steps(steps, lambda step: sent.append(step["name"]), lambda: False)
        self.assertEqual(sent, ["0", "1", "2"])
        sent.clear()

        def fail(step):
            sent.append(step["name"])
            raise RuntimeError("Action failed")

        with self.assertRaises(RuntimeError):
            run_steps(steps, fail, lambda: False)
        self.assertEqual(sent, ["0"])
        with self.assertRaises(RuntimeError):
            run_steps(steps, self.fail, lambda: True)

    def test_bad_later_target_rejected_before_first_step(self):
        for kind in ("pose", "cartesian"):
            steps = [{"name": "open", "gripper": [0, 0]},
                     {"name": "bad", kind: [0, 0, 0, 0, 0, 0, 0]}]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                run_steps(steps, self.fail, lambda: False)


if __name__ == "__main__":
    unittest.main()
