# learning (Issue 2)

ROS を source していない専用 ML 環境で使う。2026-11-01 の明示許可に基づき、exact Python/ML 環境、固定snapshot取得、実raw変換、公式pi05の10 step学習まで実行した。実行証跡は `outputs/issue4/e2e-20261101-022215/ML/`。
共有契約は `configs/policy_contract.json`。時刻候補は15 FPS、offset 0 ns、観測age100 ms / skew70 ms、指令age100 ms / skew50 ms。`validated=false` を保持し、live 校正済みとは扱わない。

## 1試行と採否

`configs/cup_placements/{baseline,near,yaw_plus,yaw_minus}.json` は事前に train / train / validation / heldout を割り当てた候補。TCP quaternion は固定し、回転した mesh 胴体中心から pick 位置・置き先原点を整合させる。初期姿勢と置き先支持台の中心は固定。定義ファイルの候補flagは保持する。今回のbaseline/near/yaw_plusは各1試行の実収録で成功・RGB・cup trace・raw validatorを確認した。heldoutは未実行で、広い配置範囲の到達性や成功率は未評価。

```bash
python3 collection/prepare_cup_trial.py configs/cup_placements/near.json outputs/issue2/run1 --assets /absolute/path/to/cup
# ROS環境。1試行ごとにlaunchを再起動する。
ros2 launch collection/cup_demo.launch.py world:=/absolute/path/to/outputs/issue2/run1/world.sdf output_dir:=/absolute/path/to/raw
python3 collection/cup_sequence.py outputs/issue2/run1/scene.json --world outputs/issue2/run1/world.sdf
```

`prepare_cup_trial.py` は既存ディレクトリを拒否し、`scene.json`, `world.sdf`, `trial.json` を作る。教師は同じ world / scene を受け取り、生存期間全体で共有 control lock を保持する。教師終了0は物理成功を意味しない。

採否 manifest は `{"version":1,"episodes":[<trial.json の内容>, ...]}`。`trial.json` の `episode_id`, `raw_path`, `sequence_exit_code`, `task_success`, `accepted`, `exclusion_reason` を人手で記録する。採用には complete v2、上流validator合格、終了0、人手成功 true、除外理由空文字が必要。除外には理由が必要。scene/world hash・配置・split・実行revisionも検査する。パスは絶対パス、またはmanifestからの相対パス。raw を編集しない。同じ配置・物理pose・episode・rawを別splitへ入れない。

## raw変換

```bash
# Pillowだけで上流validator・manifest・causal alignmentを検査。output引数は未使用。
python3 learning/convert_raw.py outputs/issue2/acceptance.json outputs/issue2/datasets --check-only
# 固定LeRobot環境でのみ実行。trainとvalidationを別rootに作り、全frameを再読込み照合。
python3 learning/convert_raw.py outputs/issue2/acceptance.json outputs/issue2/datasets
```

`--timing /path/timing.json` は共有contractと同形式の timing object 全体を明示的に置換する。候補状態をレポートへ保存する。
観測時刻は全系列の共通区間の先頭を起点とする整数nsの固定15 Hzグリッド。RGB/stateは観測時刻以前、腕・左右指commandは `label_time = observation_time + label_offset_ns` 以前の最新実出力を使う。各系列のageと系列間skewを全frameで検査し、内部欠損を削除したりstate/ゼロで指令を代用しない。

公式 `LeRobotDataset.create/add_frame/save_episode/finalize` でlossless画像を保存し、HWC uint8 RGBと読込みCHW、float32 state/action、taskを全frame照合する。動画codecを使わない。`train/`, `validation/` は独立統計。heldoutは予約し出力・学習・選択に使わない。`conversion_report.json` に完全なframe対応、元source stamp、raw hash、validator、採否、契約、版を記録し、raw不変を照合する。途中失敗のoutputは再利用せず、別outputでやり直す。

## 学習設定と完成checkpoint

依存入力は [pyproject.toml](pyproject.toml)、解決記録は [dependency-provenance.json](dependency-provenance.json)。Python 3.12.16、LeRobot `[pi,training]` の固定commit、roslibpy 2.0.1、候補torch2.11.0+cu128 / torchvision0.26.0+cu128と専用indexを指定する。公式uv.lockのSHA256と区別して、プロジェクトの解決済み [uv.lock](uv.lock) を保存した。`pi` extraだけではdataset/trainer依存を含まないため、同じ固定ソースの `training` extraも使う。exact CPython3.12.16はastral/python-build-standaloneの20261026配布物を公開SHA256と照合し、ignored `learning/.python/` に導入した。uv0.9.26で127 packageを解決し、現platformには123 packageを導入した。`uv sync --project learning --frozen --python learning/.python/python/bin/python3.12 --no-python-downloads` で既存exact interpreterとlockを使う。

```bash
# ローカルsnapshotのディレクトリ名は固定revisionそのもの。モデル/ tokenizerを取得しない。
python3 learning/prepare_training.py outputs/issue2/datasets/train /local/snapshots/22c30e5b34f9e7ab738b1b34fc2fc5ecfe2d28f0 /local/snapshots/35e4f46485b4d07967e7e9935bc3786aad50687c outputs/issue2/prepared --training-output outputs/issue2/training --steps 10 --device cuda --dtype bfloat16 --train-expert-only --gradient-checkpointing
# 下記は準備後、別途学習実行を許可されたときだけ。現在は未実行。
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 WANDB_MODE=disabled lerobot-train --config_path=outputs/issue2/prepared/train_config.json
```

prepareは重みを読み込んでモデルを起動せず、固定baseへのsymlinkを持つ `initialization/`、公式 `train_config.json`、`training_inputs.json` を生成する。bfloat16 / expert-only / gradient-checkpointingは明示オプションで保存する。base重みのSHA256 `0eb11ca9587678c1d2ef8cf32807c29f8ce53a2bfdfc1aa4a4c96f16fca59b0f` は [固定snapshotのHF API LFS metadata](https://huggingface.co/api/models/lerobot/pi05_base/tree/22c30e5b34f9e7ab738b1b34fc2fc5ecfe2d28f0) の `model.safetensors.lfs.oid` から確認。実行時に重みを取得し、このSHA256と一致することも確認した。gated tokenizerはユーザー本人の利用条件承認・対話認証後に固定revisionを取得し、ローカルファイルとhashを記録した。認証情報はログへ出さない。

配布configの32軸・3画像を外部8軸・1画像に置換し、モデル内部padding/resizeは公式pi05を使う。外部は絶対位置、`use_relative_actions=false`, `n_action_steps=1`, `empty_cameras=0`。base processorの統計は除き、公式trainerにtrain専用root統計を渡す。`eval_split=0`、ImageNet統計置換なし、final/途中upload・W&Bとも無効。検証rootは学習設定へ渡さない。

```bash
# 以下も完成checkpointとML環境が揃い、別途実行を許可された後。
# validationからのforwardのみ。保存済みtrain processor/統計を使い、先頭画像・stateをNPZへ出す。
python3 learning/evaluate_checkpoint.py outputs/issue2/training/checkpoints/000010/pretrained_model outputs/issue2/datasets/validation --device cpu --max-frames 8 --export-input outputs/issue2/validation_input.npz --report outputs/issue2/validation_forward.json
# 別プロセスで同じ入力契約から有限8軸を確認。base初期化を完成checkpointと混同しない。
python3 learning/check_checkpoint.py outputs/issue2/training/checkpoints/000010/pretrained_model --device cpu --input outputs/issue2/validation_input.npz --report outputs/issue2/checkpoint_reload.json
```

NPZは `rgb` uint8 HWC[360,640,3] と `state` finite[8]。公式のlossless画像readerはfloat32 CHW[0,1]を返すため、export時にHWCへ転置し255倍・丸めでuint8へ戻す。checkpoint内の `train_config.json`、saved normalization state、local tokenizer、元 `prepared/training_inputs.json` とtrain統計rootを保持する。loaderは保存統計がtrain由来と一致することを確認し、同期推論へ `load_checkpoint(path, contract=dict, device="cpu") -> (policy, preprocessor, postprocessor)` を渡す。`preprocessor`にはfloat CHW画像、state vector、taskを渡す。pi05の `from_pretrained` は読込み例外を捕捉するため、完成checkpointは公式標準と同じsafetensors strict loaderで読み、失敗を伝播させる。

初回reload/validationは保存statの `count` がJSON `[1908]` / processor読込み後scalarとなる表現差を厳密照合で検出して停止した。固定版 `from_tensor_to_numpy` の `.item()` 挙動を確認し、countだけを両者要素数1の場合にscalar比較する。mean/std/quantile等のshape・値は変更せず厳密に検査する。失敗試行のcommand/log/sourceも実行rootへ保持し、修正後の実reload/validationはattempt2として終了0を確認した。

checkpointの凍結contract/timingと要求contractの一致を検査する。adapterのlive校正値は別入力であり、checkpointの `validated=false` を上書きしない。

## 確認済みと未実行

専用ML環境でlearningテスト15件が通過（公式writer/finalize/readbackの実往復を含む）。実rawもtrain1908 frame / validation904 frameの全RGB/state/actionを再読込み照合し、raw不変と凍結contract一致を確認した。公式trainerの10 step forward/backward、完成checkpointとprocessor保存まで終了0。総4,143,404,816 parameter、学習対象693,422,112、batch1、bfloat16、expert-only、gradient-checkpointing。学習時Torch peak12.85 GiB / nvidia-smi最大13,671 MiB。最終step loss0.037は短い配線試験の結果であり、タスク成功率ではない。

torchcodec0.11.1はhostのFFmpeg共有libraryをloadできない。lossless画像保存と実readerは明示的なPyAV15.1.0で通過しており、この実験ではvideo codecを使わない。完成checkpointのstrict別プロセス再読込みとvalidation8 frame forwardも終了0。validation mean loss0.4745426653、同一重みSHA256 `d379388cfbf53d3185ca602004bdbc1ca8a1348de36950a16212f641465340d5` を両方で確認した。同期pre/select/postの実時間は初回670.603 ms、warm後319.176 / 300.756 / 306.739 ms（モデルloadを除く）。4出力とも有限8軸、clampなし。これらはvalidation入力での測定であり、Gazeboのlive freshness/適用/停止試験は別に確認する。

実行rootの `ml-result.json`, `*command*.json`, `training-summary.json`, `checkpoint-reload.json`, `validation-forward.json`, stage別source snapshot、失敗attempt1のlogを関連付けて保持する。

参照した固定版ソース: [writer](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/datasets/lerobot_dataset.py)、[画像reader変換](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/datasets/io_utils.py)、[trainer](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/scripts/lerobot_train.py)、[processor factory](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/policies/factory.py)、[pi05 loader](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/policies/pi05/modeling_pi05.py)。
