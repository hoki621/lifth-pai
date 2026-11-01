# データ変換・学習・推論

[環境準備](../docs/environment.md)に従い、ROSをsourceしていないML環境を使用します。契約は `configs/policy_contract.json` にあります。モデル・tokenizerのsnapshot、データ、学習済み重みは別途用意してください。

## データ変換

[収集手順](../collection/README.md)で画像を確認し、採用manifestを作成します。

```bash
python learning/convert_raw.py outputs/datasets/cup-run/final-acceptance.json \
  outputs/datasets/cup-run/dataset --check-only
python learning/convert_raw.py outputs/datasets/cup-run/final-acceptance.json \
  outputs/datasets/cup-run/dataset
```

出力は `dataset/train/` と `dataset/validation/` に分かれます。`--timing /path/timing.json` を渡すとcontractのtimingを明示的に置換できます。rawの検証と画像・state・actionの対応付けに失敗した場合は変換を停止します。

## 学習設定

次のモデルの固定revisionとtokenizerを、各ディレクトリ名がrevisionとなるようにローカルへ用意します。Pi0.5のtokenizerには利用条件への同意や認証が必要な場合があります。

| モデル | base revision | tokenizer / VLM revision |
| --- | --- | --- |
| Pi0.5 | `lerobot/pi05_base@22c30e5b34f9e7ab738b1b34fc2fc5ecfe2d28f0` | `google/paligemma-3b-pt-224@35e4f46485b4d07967e7e9935bc3786aad50687c` |
| SmolVLA | `lerobot/smolvla_base@5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6` | `HuggingFaceTB/SmolVLM2-500M-Video-Instruct@7b375e1b73b11138ff12fe22c8f2822d8fe03467` |

```bash
python learning/prepare_training.py outputs/datasets/cup-run/dataset/train \
  /local/snapshots/22c30e5b34f9e7ab738b1b34fc2fc5ecfe2d28f0 \
  /local/snapshots/35e4f46485b4d07967e7e9935bc3786aad50687c \
  outputs/training-prepared --training-output outputs/training \
  --steps 10 --device cuda --dtype bfloat16 --train-expert-only --gradient-checkpointing

# prepare_training.pyは設定を作るだけ。下記で学習を開始する。
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  HF_DATASETS_OFFLINE=1 WANDB_MODE=disabled \
  lerobot-train --config_path=outputs/training-prepared/train_config.json
```

SmolVLAでは上表のbaseとVLM revisionを同じ位置引数に指定します。`--batch-size`、`--num-workers`、`--steps` などは `python learning/prepare_training.py --help` で確認できます。

## checkpoint確認

```bash
python learning/evaluate_checkpoint.py outputs/training/checkpoints/000010/pretrained_model \
  outputs/datasets/cup-run/dataset/validation --device cpu --max-frames 8 \
  --export-input outputs/validation-input.npz --report outputs/validation-forward.json
python learning/check_checkpoint.py outputs/training/checkpoints/000010/pretrained_model \
  --device cpu --input outputs/validation-input.npz --report outputs/checkpoint-reload.json
```

保存済みcheckpointとtrain統計を使用し、検証データの統計で正規化し直しません。出力先は新しいファイル名を指定してください。

## ROS / Gazeboとの1点推論

学習時の `training_inputs.json` の `contract` をJSONとして保存し、adapterとML側に同じものを渡します。別途、実行環境に合わせて校正したruntime timing JSONが必要です。`configs/policy_contract.json` のtimingは `validated=false` の候補であり、runtime timingの代わりには使えません。

ROS側で環境を起動した後、別端末でbridgeを起動します。

```bash
collection/ros.sh ros2 launch collection/policy_bridge.launch.py \
  timing:=/absolute/path/to/calibrated-timing.json \
  contract:=/absolute/path/to/contract.json port:=19090
```

ML環境からcheckpointを読み込んで推論します。

```bash
python learning/run_policy.py --mode checkpoint \
  --checkpoint /absolute/path/to/checkpoint/pretrained_model \
  --contract /absolute/path/to/contract.json --port 19090 --steps 1
```

10点連続軌道の試験用差分は[experiments/issue7](../experiments/issue7/README.md)にあります。
