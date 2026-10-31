import copy
import unittest

from alignment import COMMANDS, OBSERVATIONS, align
from common import load_contract


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.timing = load_contract()["timing"]
        self.streams = {n: [{"source_stamp_ns": i * 20_000_000 + offset} for i in range(21)]
                        for n, offset in zip((*OBSERVATIONS, *COMMANDS), [0, 1, 2, 3, 4])}

    def test_causal_real_command_indices_and_integer_grid(self):
        frames = align(self.streams, self.timing)
        self.assertEqual(frames[0]["observation_time_ns"], 4)
        for i, frame in enumerate(frames):
            self.assertEqual(frame["observation_time_ns"], 4 + i * 1_000_000_000 // 15)
            for name, stamp in frame["source_stamp_ns"].items():
                target = frame["label_time_ns"] if name in COMMANDS else frame["observation_time_ns"]
                self.assertLessEqual(stamp, target)
                index = frame["indices"][name]
                if index + 1 < len(self.streams[name]):
                    self.assertGreater(self.streams[name][index + 1]["source_stamp_ns"], target)

    def test_signed_label_offset(self):
        for offset in (30_000_000, -30_000_000):
            frames = align(self.streams, {**self.timing, "label_offset_ns": offset})
            for f in frames:
                self.assertEqual(f["label_time_ns"] - f["observation_time_ns"], offset)
                self.assertLessEqual(max(f["source_stamp_ns"][n] for n in COMMANDS), f["label_time_ns"])
                self.assertLessEqual(max(f["source_stamp_ns"][n] for n in OBSERVATIONS), f["observation_time_ns"])

    def test_internal_gap_skew_empty_and_nonmonotonic_fail_whole_episode(self):
        streams = copy.deepcopy(self.streams)
        streams["right_command"] = [streams["right_command"][0], streams["right_command"][-1]]
        with self.assertRaisesRegex(ValueError, "age|skew"):
            align(streams, self.timing)
        with self.assertRaisesRegex(ValueError, "skew"):
            align(self.streams, {**self.timing, "max_command_skew_ns": 1})
        for bad in ([], [{"source_stamp_ns": 1}, {"source_stamp_ns": 1}]):
            with self.assertRaises(ValueError):
                align({**self.streams, "left_command": bad}, self.timing)

    def test_contract_rejects_order_units_features_and_model(self):
        contract = load_contract()
        for key, value in (("joint_names", list(reversed(contract["joint_names"]))),
                           ("joint_names", ["base_j2"] * 8), ("joint_units", ["rad"] * 8),
                           ("model", "v2_1_0"), ("state_key", "state"), ("image_key", "image")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_contract({**contract, key: value})


if __name__ == "__main__":
    unittest.main()
