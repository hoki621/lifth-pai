"""Strict local reload of a completed official pi05 checkpoint and its saved processors."""

import argparse
import json
import math
import time
from pathlib import Path

from common import load_contract, offline, upstream, verify_lerobot
from convert_raw import digest
from prepare_training import policy_features


def verify_training_statistic(key, statistic, actual, expected):
    import torch

    actual = torch.as_tensor(actual).float().cpu()
    expected = torch.as_tensor(expected).float()
    # Pinned converters.from_tensor_to_numpy uses .item() for numel()==1 when
    # NormalizerProcessorStep reloads stats. Only count is semantically scalar;
    # retain exact feature dimensions for every normalization value.
    if statistic == "count" and actual.numel() == expected.numel() == 1:
        actual, expected = actual.reshape(()), expected.reshape(())
    torch.testing.assert_close(actual, expected, rtol=0, atol=0,
                               msg=lambda message: f"{key}.{statistic}: {message}")


def inspect_checkpoint(path, contract=None):
    load, _, _ = upstream()
    path = Path(path).resolve()
    for filename in ("config.json", "model.safetensors", "train_config.json",
                     "policy_preprocessor.json", "policy_postprocessor.json"):
        if not (path / filename).is_file():
            raise ValueError(f"completed local checkpoint missing {filename}")
    config, trainer = load(path / "config.json"), load(path / "train_config.json")
    source = Path(trainer["policy"]["pretrained_path"]).resolve().parent
    inputs = load(source / "training_inputs.json")
    recorded = load_contract(inputs["contract"])
    contract = recorded if contract is None else load_contract(contract)
    if contract != recorded:
        raise ValueError("checkpoint training contract/timing differs from requested inference contract")
    if (config["type"] != "pi05" or config["input_features"] != policy_features(contract)
            or config["output_features"] != {contract["action_key"]: {"type": "ACTION", "shape": [8]}}
            or config.get("use_relative_actions", False) or config.get("empty_cameras", 0) != 0):
        raise ValueError("checkpoint must have exactly one RGB, external8 absolute state/action")
    root = Path(trainer["dataset"]["root"]).resolve()
    if (str(root) != inputs["train_root"] or trainer["dataset"]["eval_split"] != 0.0
            or digest(root / "meta/stats.json") != inputs["train_stats_sha256"]):
        raise ValueError("checkpoint training stats/split provenance mismatch")
    for filename in ("policy_preprocessor.json", "policy_postprocessor.json"):
        processor = load(path / filename)
        normalization_found = False
        tokenizer_found = False
        for step in processor["steps"]:
            name = step["registry_name"]
            if name in ("normalizer_processor", "unnormalizer_processor"):
                normalization_found = True
                features = step["config"].get("features", {})
                required = {"action": {"type": "ACTION", "shape": [8]}}
                if name == "normalizer_processor":
                    required.update(policy_features(contract))
                if features != required:
                    raise ValueError("saved normalization features differ from checkpoint contract")
                state_file = step.get("state_file")
                if not state_file or not (path / state_file).resolve().is_relative_to(path) or not (path / state_file).is_file():
                    raise ValueError("checkpoint requires saved train normalization state")
            if name == "tokenizer_processor":
                tokenizer_found = True
                tokenizer = Path(step["config"]["tokenizer_name"])
                if not tokenizer.is_absolute() or not tokenizer.is_dir() or str(tokenizer) != inputs["tokenizer"]["path"]:
                    raise ValueError("checkpoint tokenizer must reference the recorded local snapshot")
                if digest(tokenizer / "tokenizer.json") != inputs["tokenizer"]["tokenizer_sha256"]:
                    raise ValueError("tokenizer content changed")
        if not normalization_found:
            raise ValueError("saved normalization processor missing")
        if filename == "policy_preprocessor.json" and not tokenizer_found:
            raise ValueError("saved local tokenizer processor missing")
    return config, inputs


def load_checkpoint(path, contract=None, device="cpu"):
    """Return (policy, preprocessor, postprocessor); never download or fall back to base weights."""
    offline()
    if device not in ("cpu", "cuda"):
        raise ValueError("explicit cpu/cuda device required")
    inspect_checkpoint(path, contract)
    verify_lerobot()
    from lerobot.configs import PreTrainedConfig
    from lerobot.policies.factory import get_policy_class, make_pre_post_processors
    from lerobot.processor.normalize_processor import NormalizerProcessorStep, UnnormalizerProcessorStep
    from safetensors.torch import load_model

    path = Path(path).resolve()
    cfg = PreTrainedConfig.from_pretrained(str(path), local_files_only=True, cli_overrides=[f"--device={device}"])
    policy = get_policy_class(cfg.type)(cfg)
    # pi05.from_pretrained catches load errors and can return random weights. Strict canonical
    # checkpoint loading uses the same safetensors loader as PreTrainedPolicy, and propagates errors.
    load_model(policy, str(path / "model.safetensors"), strict=True, device="cpu")
    policy.to(device)
    policy.eval()
    pre, post = make_pre_post_processors(cfg, pretrained_path=str(path),
        preprocessor_overrides={"device_processor": {"device": device}},
        postprocessor_overrides={"device_processor": {"device": "cpu"}})
    trainer = upstream()[0](path / "train_config.json")
    stats = upstream()[0](Path(trainer["dataset"]["root"]) / "meta/stats.json")
    for pipeline in (pre, post):
        for step in pipeline.steps:
            if isinstance(step, (NormalizerProcessorStep, UnnormalizerProcessorStep)):
                for key in ("observation.state", "action"):
                    if key not in step.features:
                        continue
                    if key not in step.stats:
                        raise ValueError(f"checkpoint normalization missing train stats for {key}")
                    for statistic, expected in stats[key].items():
                        if statistic not in step.stats[key]:
                            raise ValueError(f"checkpoint normalization missing {key}.{statistic}")
                        verify_training_statistic(key, statistic, step.stats[key][statistic], expected)
    policy.reset()
    return policy, pre, post


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path, help="official checkpoints/<step>/pretrained_model directory")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--input", type=Path, required=True, help="NPZ containing rgb uint8 HWC and state float32[8]")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    import numpy as np
    import torch
    from PIL import Image

    _, inputs = inspect_checkpoint(args.checkpoint)
    contract = inputs["contract"]
    sample = np.load(args.input, allow_pickle=False)
    rgb, state = sample["rgb"], sample["state"]
    if (rgb.dtype != np.uint8 or list(rgb.shape) != contract["image_shape_hwc"] or state.shape != (8,)
            or not np.isfinite(state).all()):
        raise ValueError("input requires uint8 RGB HWC360x640x3 and finite state[8]")
    Image.fromarray(rgb)  # Check array is a supported RGB image before model initialization.
    policy, pre, post = load_checkpoint(args.checkpoint, device=args.device)
    batch = {contract["image_key"]: torch.from_numpy(rgb.copy()).permute(2, 0, 1).float() / 255,
             contract["state_key"]: torch.from_numpy(state.astype(np.float32)), "task": contract["task"]}
    latencies, actions = [], []
    with torch.inference_mode():
        # First call includes model execution warm-up; later calls measure the same
        # synchronous pre/select/post path with the completed checkpoint resident.
        for _ in range(4):
            if args.device == "cuda":
                torch.cuda.synchronize()
            started = time.perf_counter_ns()
            action = post(policy.select_action(pre(batch))).cpu().reshape(-1).tolist()
            if args.device == "cuda":
                torch.cuda.synchronize()
            latencies.append(time.perf_counter_ns() - started)
            if len(action) != 8 or not all(math.isfinite(v) for v in action):
                raise ValueError("checkpoint output must be finite external8")
            actions.append(action)
    report = {"version": 1, "checkpoint": str(args.checkpoint.resolve()), "input_sha256": digest(args.input),
              "weights_sha256": digest(args.checkpoint / "model.safetensors"), "contract": contract,
              "training_inputs": inputs, "action": action, "separate_process_reload": True,
              "first_inference_wall_ns": latencies[0], "warmed_inference_wall_ns": latencies[1:],
              "measured_actions": actions, "latency_scope": "preprocessor + select_action + postprocessor + CPU output; excludes model loading"}
    with args.report.open("x") as stream:
        json.dump(report, stream, indent=2)


if __name__ == "__main__":
    main()
