"""Metadata preparation/reload rejection tests. Synthetic files are not runnable weights."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check_checkpoint import inspect_checkpoint, load_checkpoint, verify_training_statistic
from common import load_contract
from convert_raw import digest
from evaluate_checkpoint import validation_provenance
from prepare_training import BASE_REVISION, TOKENIZER_REVISION, policy_features, prepare_training


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class TrainingTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("torch"), "requires pinned ML environment")
    def test_saved_count_scalar_roundtrip_keeps_feature_stats_strict(self):
        import torch
        from lerobot.processor.converters import from_tensor_to_numpy

        actual = from_tensor_to_numpy(torch.tensor([1908.]))
        self.assertIsInstance(actual, float)
        verify_training_statistic("action", "count", actual, [1908])
        for statistic, observed, expected in (
                ("count", actual, [1909]), ("count", [1908, 1908], [1908]),
                ("mean", actual, [1908]), ("mean", [[0.] * 8], [0.] * 8),
                ("q99", [0.] * 7 + [1.], [0.] * 8)):
            with self.subTest(statistic=statistic), self.assertRaises(AssertionError):
                verify_training_statistic("action", statistic, observed, expected)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contract = load_contract()
        self.train = self.root / "dataset/train"
        write(self.train / "meta/stats.json", {"action": {"mean": [0] * 8}})
        self.provenance = {"split": "train", "contract": self.contract, "manifest_sha256": "a" * 64,
                           "stats_sha256": digest(self.train / "meta/stats.json")}
        write(self.train / "conversion_provenance.json", self.provenance)
        write(self.train.parent / "conversion_report.json", {"status": "complete", "contract": self.contract,
              "splits": {"train": {"root": str(self.train), "repo_id": "lifth/cup-train"}}})
        self.base, self.tokenizer = self.root / BASE_REVISION, self.root / TOKENIZER_REVISION
        self.base.mkdir()
        self.tokenizer.mkdir()
        write(self.base / "config.json", {"type": "pi05", "chunk_size": 50,
               "input_features": {"observation.state": {"type": "STATE", "shape": [32]}},
               "output_features": {"action": {"type": "ACTION", "shape": [32]}}})
        (self.base / "model.safetensors").write_bytes(b"synthetic fixture, not model weights")
        write(self.tokenizer / "tokenizer.json", {})
        write(self.tokenizer / "tokenizer_config.json", {})
        write(self.base / "policy_preprocessor.json", {"steps": [
            {"registry_name": "normalizer_processor", "config": {"features": {"old": {}}, "norm_map": {}}, "state_file": "old.safetensors"},
            {"registry_name": "tokenizer_processor", "config": {"tokenizer_name": "remote/model"}}]})
        write(self.base / "policy_postprocessor.json", {"steps": [
            {"registry_name": "unnormalizer_processor", "config": {"features": {}}, "state_file": "old.safetensors"}]})
        self.preparation, self.training_output = self.root / "prepared", self.root / "trained"

    def prepare(self):
        # Only metadata preparation is tested; bypass real snapshot digest for the explicit synthetic fixture.
        with patch("prepare_training.BASE_WEIGHTS_SHA256", digest(self.base / "model.safetensors")):
            return prepare_training(self.train, self.base, self.tokenizer, self.preparation, self.training_output)

    def checkpoint(self):
        trainer = self.prepare()
        checkpoint = self.root / "checkpoint/pretrained_model"
        checkpoint.mkdir(parents=True)
        config = copy.deepcopy(trainer["policy"])
        write(checkpoint / "config.json", config)
        write(checkpoint / "train_config.json", trainer)
        (checkpoint / "model.safetensors").write_bytes(b"not runnable")
        for name, registry in (("policy_preprocessor", "normalizer_processor"), ("policy_postprocessor", "unnormalizer_processor")):
            features = {"action": {"type": "ACTION", "shape": [8]}}
            if name == "policy_preprocessor":
                features.update(policy_features(self.contract))
            steps = [{"registry_name": registry, "config": {"features": features}, "state_file": f"{name}.safetensors"}]
            if name == "policy_preprocessor":
                steps.append({"registry_name": "tokenizer_processor", "config": {"tokenizer_name": str(self.tokenizer)}})
            write(checkpoint / f"{name}.json", {"steps": steps})
            (checkpoint / f"{name}.safetensors").write_bytes(b"not runnable")
        return checkpoint

    def test_train_only_local_preparation_disables_uploads_and_base_stats(self):
        trainer = self.prepare()
        self.assertEqual(trainer["dataset"]["eval_split"], 0)
        self.assertFalse(trainer["dataset"]["use_imagenet_stats"])
        self.assertFalse(trainer["save_checkpoint_to_hub"])
        self.assertFalse(trainer["policy"]["push_to_hub"])
        self.assertFalse(trainer["wandb"]["enable"])
        self.assertEqual(trainer["policy"]["input_features"], policy_features(self.contract))
        self.assertEqual(trainer["policy"]["output_features"]["action"]["shape"], [8])
        self.assertEqual(trainer["policy"]["n_action_steps"], 1)
        processor = json.loads((self.preparation / "initialization/policy_preprocessor.json").read_text())
        self.assertNotIn("state_file", processor["steps"][0])
        self.assertEqual(processor["steps"][1]["config"]["tokenizer_name"], str(self.tokenizer))
        inputs = json.loads((self.preparation / "training_inputs.json").read_text())
        self.assertFalse(inputs["contract"]["timing"]["validated"])
        self.assertFalse(inputs["runtime_verified"])
        self.assertTrue((self.preparation / "initialization/model.safetensors").is_symlink())
        with self.assertRaisesRegex(ValueError, "new, distinct"):
            self.prepare()

    def test_validation_stats_and_wrong_weights_refused(self):
        with self.assertRaisesRegex(ValueError, "weights differ"):
            prepare_training(self.train, self.base, self.tokenizer, self.preparation, self.training_output)
        write(self.train / "conversion_provenance.json", {**self.provenance, "split": "validation"})
        with self.assertRaisesRegex(ValueError, "train-only"):
            self.prepare()

    def test_checkpoint_metadata_provenance_and_candidate_timing(self):
        checkpoint = self.checkpoint()
        _, inputs = inspect_checkpoint(checkpoint, self.contract)
        self.assertFalse(inputs["contract"]["timing"]["validated"])
        calibrated = copy.deepcopy(self.contract)
        calibrated["timing"]["validated"] = True
        with self.assertRaisesRegex(ValueError, "timing differs"):
            inspect_checkpoint(checkpoint, calibrated)
        (self.train / "meta/stats.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "stats/split"):
            inspect_checkpoint(checkpoint)

    def test_base_not_checkpoint_missing_saved_processors_and_remote_tokenizer_refused(self):
        with self.assertRaisesRegex(ValueError, "train_config.json"):
            load_checkpoint(self.base)
        checkpoint = self.checkpoint()
        write(checkpoint / "policy_preprocessor.json", {"steps": [{"registry_name": "normalizer_processor",
              "config": {"features": {**policy_features(self.contract), "action": {"type": "ACTION", "shape": [8]}}}}]})
        with self.assertRaisesRegex(ValueError, "saved train normalization"):
            inspect_checkpoint(checkpoint)

    def test_validation_must_use_separate_matching_root(self):
        inputs = {"train_root": str(self.train), "manifest_sha256": "a" * 64}
        with self.assertRaisesRegex(ValueError, "separate validation"):
            validation_provenance(self.train, self.contract, inputs)
        validation = self.train.parent / "validation"
        write(validation / "meta/stats.json", {})
        write(validation / "conversion_provenance.json", {**self.provenance, "split": "validation",
              "stats_sha256": digest(validation / "meta/stats.json")})
        validation_provenance(validation, self.contract, inputs)


if __name__ == "__main__":
    unittest.main()
