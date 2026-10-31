"""Prepare local pi05 initialization and an official trainer config, without starting training."""

import argparse
import copy
import json
from pathlib import Path

from common import LEROBOT_REVISION, load_contract, upstream
from convert_raw import digest

BASE_REVISION = "22c30e5b34f9e7ab738b1b34fc2fc5ecfe2d28f0"
TOKENIZER_REVISION = "35e4f46485b4d07967e7e9935bc3786aad50687c"
BASE_WEIGHTS_SHA256 = "0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f"


def policy_features(contract):
    height, width, channels = contract["image_shape_hwc"]
    return {contract["state_key"]: {"type": "STATE", "shape": [8]},
            contract["image_key"]: {"type": "VISUAL", "shape": [channels, height, width]}}


def prepare_training(train_root, base, tokenizer, output, training_output, steps=10, device="cpu", *,
                     train_expert_only=False, gradient_checkpointing=False, dtype="float32"):
    load, _, _ = upstream()
    train_root, base, tokenizer = (Path(p).resolve() for p in (train_root, base, tokenizer))
    output, training_output = Path(output).resolve(), Path(training_output).resolve()
    if output.exists() or training_output.exists() or output == training_output:
        raise ValueError("new, distinct preparation and training output paths required")
    provenance = load(train_root / "conversion_provenance.json")
    contract = load_contract(provenance["contract"])
    report = load(train_root.parent / "conversion_report.json")
    if (provenance["split"] != "train" or report["status"] != "complete"
            or report["contract"] != contract or Path(report["splits"]["train"]["root"]).resolve() != train_root
            or provenance["stats_sha256"] != digest(train_root / "meta/stats.json")):
        raise ValueError("complete train-only conversion and unchanged training stats required")
    if base.name != BASE_REVISION or tokenizer.name != TOKENIZER_REVISION:
        raise ValueError("local snapshots must use the approved exact revision directory names")
    for path in (base / "model.safetensors", tokenizer / "tokenizer_config.json", tokenizer / "tokenizer.json"):
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing local snapshot asset: {path}")
    weights_hash = digest(base / "model.safetensors")
    if weights_hash != BASE_WEIGHTS_SHA256:
        raise ValueError("base weights differ from pinned Hugging Face LFS SHA256")
    if type(steps) is not int or steps < 1 or device not in ("cpu", "cuda") or dtype not in ("float32", "bfloat16"):
        raise ValueError("positive steps and explicit cpu/cuda device required")
    config = load(base / "config.json")
    if config["type"] != "pi05":
        raise ValueError("only source-verified pi05 preparation is implemented")
    config.update(input_features=policy_features(contract),
                  output_features={contract["action_key"]: {"type": "ACTION", "shape": [8]}},
                  device=device, push_to_hub=False, pretrained_path=None, pretrained_revision=None,
                  empty_cameras=0, n_action_steps=1, use_relative_actions=False, compile_model=False,
                  train_expert_only=train_expert_only, gradient_checkpointing=gradient_checkpointing, dtype=dtype)
    processors = {}
    for name in ("policy_preprocessor", "policy_postprocessor"):
        processor = copy.deepcopy(load(base / f"{name}.json"))
        for step in processor["steps"]:
            # Do not reuse base robot statistics. Official trainer supplies train-root stats.
            if step["registry_name"] in ("normalizer_processor", "unnormalizer_processor"):
                step.pop("state_file", None)
                step["config"]["features"] = {}
            if step["registry_name"] == "tokenizer_processor":
                step["config"]["tokenizer_name"] = str(tokenizer)
            if step["registry_name"] == "device_processor":
                step["config"]["device"] = device if name == "policy_preprocessor" else "cpu"
            if step["registry_name"] in ("relative_actions_processor", "absolute_actions_processor"):
                step["config"]["enabled"] = False
        processors[name] = processor
    output.mkdir(parents=True)
    initialization = output / "initialization"
    initialization.mkdir()
    (initialization / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    (initialization / "model.safetensors").symlink_to(base / "model.safetensors")
    for name, processor in processors.items():
        (initialization / f"{name}.json").write_text(json.dumps(processor, indent=2) + "\n")
    config["pretrained_path"] = str(initialization)
    trainer = {"dataset": {"repo_id": report["splits"]["train"]["repo_id"], "root": str(train_root),
                            "eval_split": 0.0, "use_imagenet_stats": False, "video_backend": "pyav"},
               "policy": config, "output_dir": str(training_output), "job_name": "lifth-cup-smoke",
               "steps": steps, "batch_size": 1, "num_workers": 0, "persistent_workers": False,
               "save_checkpoint": True, "save_freq": steps, "save_checkpoint_to_hub": False,
               "env_eval_freq": 0, "eval_steps": 0, "log_freq": 1,
               "wandb": {"enable": False, "mode": "disabled", "disable_artifact": True}, "seed": 1000}
    (output / "train_config.json").write_text(json.dumps(trainer, indent=2) + "\n")
    inputs = {"version": 1, "kind": "base_initialization_not_trained_checkpoint", "contract": contract,
              "lerobot_revision": LEROBOT_REVISION, "train_root": str(train_root),
              "train_stats_sha256": provenance["stats_sha256"],
              "conversion_report_sha256": digest(train_root.parent / "conversion_report.json"),
              "manifest_sha256": provenance["manifest_sha256"],
              "base": {"repo_id": "lerobot/pi05_base", "revision": BASE_REVISION, "path": str(base),
                       "weights_sha256": weights_hash},
              "tokenizer": {"repo_id": "google/paligemma-3b-pt-224", "revision": TOKENIZER_REVISION,
                            "path": str(tokenizer), "tokenizer_sha256": digest(tokenizer / "tokenizer.json")},
              "trainer_config_sha256": digest(output / "train_config.json"),
              "runtime_verified": False}
    (output / "training_inputs.json").write_text(json.dumps(inputs, indent=2) + "\n")
    return trainer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("train_root", type=Path)
    parser.add_argument("base", type=Path)
    parser.add_argument("tokenizer", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--training-output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--train-expert-only", action="store_true")
    parser.add_argument("--gradient-checkpointing", action="store_true")
    parser.add_argument("--dtype", choices=("float32", "bfloat16"), default="float32")
    args = parser.parse_args()
    prepare_training(args.train_root, args.base, args.tokenizer, args.output,
                     args.training_output, args.steps, args.device, train_expert_only=args.train_expert_only,
                     gradient_checkpointing=args.gradient_checkpointing, dtype=args.dtype)
    print("Prepared only. Official trainer (requires separate runtime authorization):")
    print("HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 WANDB_MODE=disabled "
          f"lerobot-train --config_path={args.output / 'train_config.json'}")


if __name__ == "__main__":
    main()
