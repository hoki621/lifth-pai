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
SMOLVLA_BASE_REVISION = "5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6"
SMOLVLA_VLM_REVISION = "7b375e1b73b11138ff12fe22c8f2822d8fe03467"


def policy_features(contract):
    height, width, channels = contract["image_shape_hwc"]
    return {contract["state_key"]: {"type": "STATE", "shape": [8]},
            contract["image_key"]: {"type": "VISUAL", "shape": [channels, height, width]}}


def prepare_training(train_root, base, tokenizer, output, training_output, steps=10, device="cpu", *,
                     train_expert_only=False, gradient_checkpointing=False, dtype="float32",
                     batch_size=1, num_workers=0):
    load, _, _ = upstream()
    train_root, base, tokenizer = (Path(p).resolve() for p in (train_root, base, tokenizer))
    output, training_output = Path(output).resolve(), Path(training_output).resolve()
    if output.exists() or training_output.exists() or output == training_output:
        raise ValueError("new, distinct preparation and training output paths required")
    provenance = load(train_root / "conversion_provenance.json")
    contract = load_contract(provenance["contract"])
    report = load(train_root.parent / "conversion_report.json")
    verification_level = report.get("verification_level", "full_frame_readback")
    if (provenance["split"] != "train" or report["status"] not in ("complete", "coarse_verified")
            or report["contract"] != contract or Path(report["splits"]["train"]["root"]).resolve() != train_root
            or provenance["stats_sha256"] != digest(train_root / "meta/stats.json")):
        raise ValueError("verified train-only dataset and unchanged training stats required")
    if (report["status"] == "coarse_verified" and verification_level != "episode_frame_counts_only"
            or provenance.get("verification_level", verification_level) != verification_level):
        raise ValueError("dataset verification level must match its conversion provenance")
    config = load(base / "config.json")
    model_type = config["type"]
    if model_type == "pi05":
        expected_base, expected_tokenizer = BASE_REVISION, TOKENIZER_REVISION
        base_repo, tokenizer_repo = "lerobot/pi05_base", "google/paligemma-3b-pt-224"
    elif model_type == "smolvla":
        expected_base, expected_tokenizer = SMOLVLA_BASE_REVISION, SMOLVLA_VLM_REVISION
        base_repo = "lerobot/smolvla_base"
        tokenizer_repo = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
    else:
        raise ValueError("only pinned pi05 and SmolVLA preparation is implemented")
    if base.name != expected_base or tokenizer.name != expected_tokenizer:
        raise ValueError("local model/tokenizer snapshots must use the approved exact revision directory names")
    required_assets = [base / "model.safetensors", tokenizer / "tokenizer_config.json", tokenizer / "tokenizer.json"]
    if model_type == "smolvla":
        required_assets += [tokenizer / "config.json", tokenizer / "model.safetensors",
                            tokenizer / "processor_config.json", tokenizer / "preprocessor_config.json"]
    for path in required_assets:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing local snapshot asset: {path}")
    weights_hash = digest(base / "model.safetensors")
    if model_type == "pi05" and weights_hash != BASE_WEIGHTS_SHA256:
        raise ValueError("base weights differ from pinned Hugging Face LFS SHA256")
    if (type(steps) is not int or steps < 1 or type(batch_size) is not int or batch_size < 1
            or type(num_workers) is not int or num_workers < 0
            or device not in ("cpu", "cuda") or dtype not in ("float32", "bfloat16")):
        raise ValueError("positive steps/batch size, nonnegative workers, and explicit cpu/cuda device required")
    config.update(input_features=policy_features(contract),
                  output_features={contract["action_key"]: {"type": "ACTION", "shape": [8]}},
                  device=device, push_to_hub=False, pretrained_path=None, pretrained_revision=None,
                  empty_cameras=0, n_action_steps=1, compile_model=False)
    if model_type == "pi05":
        config.update(use_relative_actions=False, train_expert_only=train_expert_only,
                      gradient_checkpointing=gradient_checkpointing, dtype=dtype)
    else:
        if gradient_checkpointing:
            raise ValueError("gradient checkpointing is not supported by the pinned SmolVLA config")
        config.update(adapt_to_pi_aloha=False, use_delta_joint_actions_aloha=False,
                      train_expert_only=train_expert_only, load_vlm_weights=True,
                      vlm_model_name=str(tokenizer), use_amp=(dtype == "bfloat16"))
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
               "steps": steps, "batch_size": batch_size, "num_workers": num_workers,
               "persistent_workers": num_workers > 0,
               "save_checkpoint": True, "save_freq": steps, "save_checkpoint_to_hub": False,
               "env_eval_freq": 0, "eval_steps": 0, "log_freq": 1,
               "wandb": {"enable": False, "mode": "disabled", "disable_artifact": True}, "seed": 1000}
    (output / "train_config.json").write_text(json.dumps(trainer, indent=2) + "\n")
    inputs = {"version": 1, "kind": "base_initialization_not_trained_checkpoint", "contract": contract,
              "model_type": model_type,
              "lerobot_revision": LEROBOT_REVISION, "train_root": str(train_root),
              "train_stats_sha256": provenance["stats_sha256"],
              "conversion_report_sha256": digest(train_root.parent / "conversion_report.json"),
              "dataset_verification_level": verification_level,
              "manifest_sha256": provenance["manifest_sha256"],
              "base": {"repo_id": base_repo, "revision": expected_base, "path": str(base),
                       "weights_sha256": weights_hash},
              "tokenizer": {"repo_id": tokenizer_repo, "revision": expected_tokenizer,
                            "path": str(tokenizer), "tokenizer_sha256": digest(tokenizer / "tokenizer.json")},
              "trainer_config_sha256": digest(output / "train_config.json"),
              "runtime_verified": False}
    if model_type == "smolvla":
        inputs["vlm"] = {"repo_id": tokenizer_repo, "revision": SMOLVLA_VLM_REVISION,
                         "path": str(tokenizer), "weights_sha256": digest(tokenizer / "model.safetensors"),
                         "config_sha256": digest(tokenizer / "config.json")}
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
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--num-workers", type=int, default=0)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--train-expert-only", action="store_true")
    parser.add_argument("--gradient-checkpointing", action="store_true")
    parser.add_argument("--dtype", choices=("float32", "bfloat16"), default="float32")
    args = parser.parse_args()
    prepare_training(args.train_root, args.base, args.tokenizer, args.output,
                     args.training_output, args.steps, args.device, train_expert_only=args.train_expert_only,
                     gradient_checkpointing=args.gradient_checkpointing, dtype=args.dtype,
                     batch_size=args.batch_size, num_workers=args.num_workers)
    print("Prepared only. Official trainer (requires separate runtime authorization):")
    print("HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 WANDB_MODE=disabled "
          f"lerobot-train --config_path={args.output / 'train_config.json'}")


if __name__ == "__main__":
    main()
