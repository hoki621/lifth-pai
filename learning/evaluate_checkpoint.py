"""Small offline validation forward pass using saved train processors; never updates weights."""

import argparse
import json
import math
from pathlib import Path

from check_checkpoint import inspect_checkpoint, load_checkpoint
from common import load_contract, offline, upstream, verify_lerobot
from convert_raw import digest


def validation_provenance(root, contract, training_inputs):
    root = Path(root).resolve()
    record = upstream()[0](root / "conversion_provenance.json")
    report_path = root.parent / "conversion_report.json"
    report = upstream()[0](report_path)
    verification_level = report.get("verification_level", "full_frame_readback")
    if (record["split"] != "validation" or load_contract(record["contract"]) != contract
            or record["manifest_sha256"] != training_inputs["manifest_sha256"]
            or root == Path(training_inputs["train_root"]).resolve()
            or digest(root / "meta/stats.json") != record["stats_sha256"]
            or report["status"] not in ("complete", "coarse_verified")
            or report["contract"] != contract
            or report["manifest_sha256"] != training_inputs["manifest_sha256"]
            or Path(report["splits"]["validation"]["root"]).resolve() != root
            or training_inputs.get("conversion_report_sha256", digest(report_path)) != digest(report_path)
            or training_inputs.get("dataset_verification_level", verification_level) != verification_level
            or ("verification_level" in record and record["verification_level"] != verification_level)
            or (report["status"] == "coarse_verified" and verification_level != "episode_frame_counts_only")):
        raise ValueError("separate validation root from the same conversion manifest required")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("validation_root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--max-frames", type=int, default=8)
    parser.add_argument("--export-input", type=Path, help="write first validation RGB/state as NPZ for separate reload CLI")
    args = parser.parse_args()
    if args.max_frames < 1 or args.report.exists() or (args.export_input and args.export_input.exists()):
        raise ValueError("positive max-frames and new report/sample paths required")
    offline()
    config, inputs = inspect_checkpoint(args.checkpoint)
    contract = inputs["contract"]
    validation_provenance(args.validation_root, contract, inputs)
    verify_lerobot()
    import numpy as np
    import torch
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from torch.utils.data import DataLoader

    policy, pre, _ = load_checkpoint(args.checkpoint, contract, args.device)
    dataset = LeRobotDataset(repo_id="lifth/cup-validation", root=args.validation_root, video_backend="pyav",
        delta_timestamps={contract["action_key"]: [i / 15 for i in range(config["chunk_size"])]})
    if args.export_input:
        row = dataset[0]
        rgb = (row[contract["image_key"]].permute(1, 2, 0).numpy() * 255).round().astype(np.uint8)
        with args.export_input.open("xb") as stream:
            np.savez(stream, rgb=rgb, state=row[contract["state_key"]].numpy())
    torch.manual_seed(1000)
    losses = []
    with torch.inference_mode():
        for index, batch in enumerate(DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0)):
            if index >= args.max_frames:
                break
            loss, _ = policy.forward(pre(batch))
            value = float(loss.cpu())
            if not math.isfinite(value):
                raise ValueError("nonfinite validation loss")
            losses.append(value)
    if not losses:
        raise ValueError("empty validation dataset")
    result = {"version": 1, "checkpoint": str(args.checkpoint.resolve()), "validation_root": str(args.validation_root.resolve()),
              "contract": contract, "train_stats_sha256": inputs["train_stats_sha256"],
              "dataset_verification_level": inputs["dataset_verification_level"],
              "normalization": "saved training processors; validation statistics not used",
              "frames": len(losses), "mean_loss": sum(losses) / len(losses), "seed": 1000,
              "weights_sha256": digest(args.checkpoint / "model.safetensors")}
    with args.report.open("x") as stream:
        json.dump(result, stream, indent=2)


if __name__ == "__main__":
    main()
