# Issue #4: 一周検証の手順と実行記録

2026-11-01。対象は承認済み [#2/#3/#4 計画](issue-234-plan.md)。
当初は記録処理・CPU 試験・手順を用意した。その後、本人が専用環境への導入・少量収録・短い学習・GPU 推論・Gazebo 実験を明示承認し、以下の実験を開始した。一周検証の完了は段階ごとの実結果で判断する。#5 の一括収録・本学習・heldout 成功率測定は含めない。

本人の最終指示「ひとまずひととおり学習まで完了すればいい」により、学習・保存・再読込み・validation までで終了した。学習済み policy の Gazebo 適用は **NOT RUN（本人が延期）**。#4 の一周完了や policy の物理成功は主張しない。final record の `pipeline_complete` は `false`。

## 承認後の実験（学習までで終了）

run は Git 外の `outputs/issue4/e2e-20261101-022215/`。`/tmp/lifth-pai-active-run` はその絶対パスを保持するファイルである。`collection/acceptance.json` に host 絶対 raw/scene/world パス、split、設定・実行ソースhash、採否を保存した。scene/world は各配置1組を準備し、同じ world を launch と教師の両方へ明示指定した。

| 配置 / split | episode ID | 教師 / raw / validator | 保持sim秒 / 最低z m | 最終XY誤差 mm |
| --- | --- | --- | --- | --- |
| baseline / train | `2b2d830602b3439d837c15865803ffc5` | 終了0 / complete / 終了0 | 8.776 / 0.381370 | 0.072393 |
| near / train | `33bede876cd94c31b9ebca278e56dccb` | 終了0 / complete / 終了0 | 10.445 / 0.381311 | 0.072669 |
| yaw_plus / validation | `5b38cc217b7146f698862a280790b339` | 終了0 / complete / 終了0 | 7.384 / 0.381408 | 0.076328 |

3件とも最初の試行で既存の保持・傾き・設置条件に合格し、移送中と退避後の実 RGB を `view_image` で個別に確認した。確認者は Codex（RGB 目視と Gazebo cup trace の照合）。採否は Action 終了0だけでは決めていない。画像パスと SHA-256、物理指標、確認理由は各 `collection/<placement>/trial-01/visual-review.json`。閾値・目標・設定変更や再試行はない。これは教師の成功3件であり、学習済み policy の性能ではない。

コンテナは `pai-issue4-e2e-scene`、既存 image `lifth-pai-collection:humble`、UID/GID 1000、host network、domain 187、partition `pai_issue4_e2e_20261101`。CPU 描画を維持し、各試行で launch を終了・再起動した。実行版・依存・image情報・ソース・ログ・cup trace・validator 結果を `collection/` に保存した。収録終了後、同じコンテナを #3 へ引き渡した。Gazebo の seed は明示設定しておらず、学習 seed 1000 と混同しない。

実 raw/scene/source/runtime を結ぶ `collection-result.json` を、このコンテナの Python 3.10 で記録スクリプトから生成した。これは collection 段階の合格記録で、他工程の完了は表さない。最終的な学習完了範囲の記録は run 直下の `training-complete-result.json`、その固定入力は `training-complete-result-input.json`。raw→dataset report→train config→checkpoint/processor→実行版・hash を結び、延期した工程は合格にしていない。

公式変換も終了0で完了した。train は baseline 950 + near 958 = 1,908 frame、validation は yaw_plus 904 frame。全 RGB/state/action/task の公式 reader 照合と raw hash 不変確認を通過し、`ML/datasets/conversion_report.json` と実 command/start/end/exit を保存した。`through-conversion-result.json` が collection と conversion の合格を結ぶ。

接続実験では既存 Prometheus が9090を使用していたため、bridge の `port:=19090` と ML CLI の `--port 19090` を明示した。各入口の既定9090は変更していない。同じ scene で hold と small-step は各1指令の適用・更新後観測を確認済み。これは学習済み policy の結果には数えない。

公式 pi05 trainer は GPU 0 で10 step を完了し、終了0。実行設定は `ML/prepared/train_config.json`、command/env/start/end/exit は `ML/train-command.json`、step ごとの有限 loss/gradient は `ML/train.log`。`ML/training/checkpoints/000010/pretrained_model/` に weights と保存済み processor/state/train config がある。seed 1000、batch 1、train root のみ、upload/外部ログ無効、offline 指定で実行した。`ML/training-summary.json` に10 step の loss と測定メモリを保存した。短い保存確認であり、タスク性能を確認したとは扱わない。

初回の別プロセス再読込み・validation は、保存 normalization 統計の scalar と `[1]` の表現差を厳密比較して終了1。失敗した command/log/source を `recorded-failures/reload-initial/` に保存した。重み・元データの変更で回避せず、固定 processor の serializer が count を scalar として再構築する実装に合わせた比較修正後に再試験した。失敗を成功結果で上書きしていない。

修正版の実再試験は終了0。`ML/checkpoint-reload.json` に別プロセスでの厳密再読込みと有限8軸 action 4回を記録した。初回推論670.603 ms、warm 319.176 / 300.756 / 306.739 ms（preprocessor/select_action/postprocessor/CPU出力まで、モデル初期化は含まない）。`ML/validation-forward.json` は別 validation root の8 frame、保存済み train processor/統計で mean loss 0.4745426653。checkpoint weights の SHA-256 は両 report で `d379388cfbf53d3185ca602004bdbc1ca8a1348de36950a16212f641465340d5` と一致した。実行 receipt と修正版 source は `ML/reload-command-attempt2.json`、`ML/validation-command-attempt2.json` と各 `*-source-attempt2/`。初回失敗は `ML/reload-attempt1/`、`ML/validation-attempt1/` にも保存している。これらは offline 確認であり、live 指令の成功とは分ける。

追加で行った人工 policy の transport、部分 controller 拒否、clock pause/逆行、古い観測、手動停止、WebSocket 切断、遅延 action の結果と失敗 attempt は `issue3/` に残した。WebSocket 切断時は停止・`busy=false` を観測した一方、test process は `ros.terminate()` の cleanup 例外で終了1。安全条件の観測と harness の正常終了を分け、停止 suite 全体の無条件合格とは扱わない。実 scene 画像による GPU 2 の offline benchmark も実施したが、学習済み policy で controller を動かした証拠ではない。

安全終了は `issue3/shutdown-report.json`。learned child PID 41925 は gate を開けず終了 -15、接続・start は未実行。adapter の `stopped=true / busy=false` を確認した後、container 内 bridge PGID 9520、observer PGID 9531、scene PGID 9076 を終了した。`pai-issue4-e2e-scene` は exited 143、`pai-issue3-bridge-build` は exited 137、GPU compute process は空、localhost:19090 listener も消失した。データ・checkpoint・専用環境・停止済み container は保持した。

## 準備時点の証拠と制約

共有 [契約](../configs/policy_contract.json) は外部8軸の絶対位置、RGB 1視点。時刻候補は15 FPS、offset 0 ns、観測・command age 各100 ms、観測 skew 70 ms、command skew 50 ms。`timing.validated=false` を維持する。

Coordinator が保存した Git 外の `outputs/issue2/cpu-alignment-review.json` を確認した。既存の成功 raw `episode_d254603424d94be3a64ab74277725c49` の925 frame に対する CPU 因果対応付けで、観測最大 age 65,666,666 ns／skew 65,000,000 ns、command 最大 age 26,666,666 ns／skew 20,000,000 ns。元 stamp、先頭・末尾、raw stream・実装・契約の SHA-256 がある。同じ raw の upstream validator 合格は coordinator による別確認。ここでは再実行していない。

以前の観測 skew 50 ms 候補では frame 66 を拒否した。15 Hz の1画像周期約66.7 msを許す70 ms候補への明示変更後は上記925 frame が通った。内部 frame の除去や未来参照で回避した結果ではない。この1 episode の診断は公式 writer/readback、複数配置の適合、live timing 校正の証明にはならない。

準備時点で残っていた runtime blocker（承認後の進行は上記の実験記録を参照）:

- 候補配置の到達性・接触・yaw を含む少量の成功 raw と、配置単位の train/validation 分離の実確認。
- 固定 LeRobot の公式 writer/readback と train 由来統計の実確認。
- Python 3.12.16 の ML 環境、選択 extra/index/解決ツールを含む解決済み lock、GPU/driver/codec の適合確認。未解決を lock 済みと記録しない。
- 利用条件を満たす固定 revision の local model/tokenizer/VLM snapshot、短い学習・保存・別プロセス再読込み。
- ROS bridge の実サイズ RGB、controller 受理・取消・hold・停止、localhost の到達性、live timing の実測校正。候補 JSON の `validated` だけを書き換えて起動しない。

## 1試行の固定入力

全コマンドは PAI ルートを基準とする。`outputs/issue4/<run>/` に1試行の資料を保存する。raw・dataset・重み・ログは Git 外のまま扱う。起動、reset、開始、終了、採否は本人が1試行ずつ行う。

配置ID、pose/yaw、scene/world snapshot、split、seed、採用episodeを先に固定する。`train / validation / heldout` の3表記を使い、同じ配置・episodeを複数 split に入れない。heldout は予約し、学習・checkpoint 選択へ使わない。配置案は `configs/cup_placements/` にあり、値が存在することを実行成功と扱わない。

ROS 環境と ML 環境は別シェルにする。以下は再現用の入口であり、実行済みの範囲は上記の結果を参照する。今回の実行は本人の学習までという指示で終了しており、追加の実験は行っていない。

## #2: 収録から変換まで

配置 snapshot の準備入口は次。既存素材だけを参照し、出力先が既存なら上書きしない。

```bash
python3 collection/prepare_cup_trial.py configs/cup_placements/baseline.json \
  outputs/issue4/RUN/trial --assets external/assets
```

`scene.json`、`world.sdf`、`trial.json` が生成される。既定 base world を変えるときだけ実在する `--base-world PATH` を使う。生成時の候補フラグは到達性・接触の合格を意味しない。

ROS シェル（同じ domain/partition）で、別端末に起動を保持する。

```bash
collection/ros.sh ros2 launch collection/cup_demo.launch.py \
  world:="$PWD/outputs/issue4/RUN/trial/world.sdf"
collection/ros.sh python3 collection/start_episode.py
collection/ros.sh python3 collection/cup_sequence.py \
  outputs/issue4/RUN/trial/scene.json --world outputs/issue4/RUN/trial/world.sdf
collection/ros.sh ros2 service call /lifth/episode/stop std_srvs/srv/Trigger '{}'
```

最後の stop はシーケンスの成否と別に行う。reset は既存の launch 終了・再起動を使う。教師と adapter の制御権限を同時に取得しない。raw の upstream 検証入口は `python3 -m lifth_dataset.validate data/raw/episode_ID`（ROS シェルなら `collection/ros.sh` 経由）。ROS 外では既存 Pillow 環境と `PYTHONPATH=external/lifth_arm_gen2/src/lifth_dataset` で同じ validator を使える。ここで環境導入はしない。

人手で `trial.json` の `episode_id`、`raw_path`、`sequence_exit_code`、`task_success`、`accepted`、`exclusion_reason` を実測結果に更新する。scene/world の hash と実行版は保持する。`complete`、validator 合格、終了0、物理成功を別々に記録する。

`{ "version": 1, "episodes": [trial オブジェクト, ...] }` の採否 manifest を作る。相対パスはこの manifest のディレクトリ基準。train/validation は異なる配置にし、失敗・除外も理由を残す。

ROS を source していない ML シェルで、まず検査だけ、その後に公式 writer を使う。

```bash
python learning/convert_raw.py outputs/issue4/RUN/accepted.json \
  outputs/issue4/RUN/dataset --check-only
python learning/convert_raw.py outputs/issue4/RUN/accepted.json \
  outputs/issue4/RUN/dataset
```

`--check-only` は upstream 検証と因果対応付けだけで、dataset 作成合格にはしない。時刻を明示指定するときの実在オプションは `--timing PATH`（timing 全体の JSON）。採用した契約・timing の内容と hash を記録し、黙って閾値を変更しない。

出力は `conversion_report.json`、別 root の `train/` と `validation/`、各 root の `conversion_provenance.json`。report の `status=complete`、raw hash 不変、元 episode/frame/stamp・offset、RGB色/shape、state/左右 command 照合と公式再読込みを確認する。heldout は report に予約され、学習用 dataset にはしない。変換エラー時は未完了 report とログを残し、時刻圧縮・ゼロ埋めで合格させない。

## #2: 学習・保存・再読込み

学習用 root は train のみ。実際の #2 学習設定、解決済み lock、選択 extra/index と解決ツール版、local snapshot の固定 revision、train 統計、seed を保存する。upload と外部ログ送信が無効であることを確認する。依存未解決や snapshot 未用意なら `blocked`、学習自体を試していなければ `not_run` と理由を残す。

実在する準備入口と公式 trainer は次。`--steps 10` は短い保存確認用、`--device cpu` は明示指定の例であり、実行速度・完走を確認した結果ではない。

```bash
python learning/prepare_training.py outputs/issue4/RUN/dataset/train \
  /abs/snapshots/22c30e5b34f9e7ab738b1b34fc2fc5ecfe2d28f0 \
  /abs/snapshots/35e4f46485b4d07967e7e9935bc3786aad50687c \
  outputs/issue4/RUN/preparation --training-output outputs/issue4/RUN/training \
  --steps 10 --device cpu
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 WANDB_MODE=disabled \
  lerobot-train --config_path=outputs/issue4/RUN/preparation/train_config.json
```

準備だけでは学習を開始しない。`train_config.json` と `training_inputs.json` が生成される。現在の設定 seed は1000なので result の seed も実設定へ合わせる。pi05 と tokenizer は上記 revision 名の既存 local directory を渡す。準備の `initialization/` は base 初期化用であり、完成 checkpoint ではない。独自 trainer は作らない。

完成 checkpoint の `pretrained_model` と保存済み pre/postprocessor を組にする。base weights からの初期化を再読込み成功として扱わない。別プロセスで同じ8軸・画像・task契約から有限な8軸出力を確認し、入力、出力、processor/config、runtime 版を report に残す。

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_DATASETS_OFFLINE=1 python - <<'PY'
import json
from pathlib import Path
import numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset

run = Path("outputs/issue4/RUN")
report = json.loads((run / "dataset/conversion_report.json").read_text())
split = report["splits"]["validation"]
contract = report["contract"]
dataset = LeRobotDataset(repo_id=split["repo_id"], root=Path(split["root"]), return_uint8=True)
row = dataset[0]  # report.splits.validation.episodes[0].alignment[0] と対応
image = row[contract["image_key"]].numpy()
state = row[contract["state_key"]].numpy()
if (image.dtype != np.float32 or image.shape != (3, 360, 640)
        or not np.isfinite(image).all() or image.min() < 0 or image.max() > 1):
    raise ValueError("Expected finite float32 CHW RGB in [0, 1]")
if state.dtype != np.float32 or state.shape != (8,) or not np.isfinite(state).all():
    raise ValueError("Expected finite float32 state[8]")
np.savez(run / "reload-validation.npz",
         rgb=np.rint(image * 255).astype(np.uint8).transpose(1, 2, 0), state=state)
PY
python learning/check_checkpoint.py /abs/checkpoints/STEP/pretrained_model \
  --device cpu --input outputs/issue4/RUN/reload-validation.npz \
  --report outputs/issue4/RUN/reload-report.json
```

固定 LeRobot の `return_uint8=True` は video に対する指定で、今回の lossless image feature は float32 CHW [0,1] で返る。上記では shape・有限性・range を確認して255倍・丸めで uint8 へ戻し、NPZ は HWC へ転置する。#2 の `evaluate_checkpoint.py --export-input PATH` も同じ画像変換で NPZ を保存するが、その CLI は validation forward も実行するので単純な抽出コマンドとしては扱わない。

この抽出は独立 validation root の先頭 frame だけを読む。report の元 episode/frame/source stamp 対応と NPZ 自体を `reload_input` artifact として記録する。`rgb` は uint8 HWC 360×640×3、`state` は有限な8軸。checkpoint CLI は保存済み train processor/統計を使い、validation 統計で再 fit しない。これは1 frame の validation forward・有限出力の確認で、validation loss やタスク性能の測定ではない。`eval_split` による暗黙分割は使わない。この CLI は local tokenizer の照合、有限な8軸 action を report へ保存する。checkpoint だけを移して元の training inputs や train 統計への参照を壊さない。

## #3: 接続・停止・実 policy 1試行

scene は上記 #2 の launch で起動する。live timing は `collection/policy_adapter.py` の `TIMING_KEYS` を満たし、実測根拠を付けた JSON が別途必要。今回の測定・導出・採用値は `issue3/*timing*.json` に保存した。学習済み policy の live 適用確認は延期している。

学習済み policy に渡す `/abs/contract.json` は、保存した `preparation/training_inputs.json["contract"]` をそのまま JSON に書き出した固定契約とする。候補の `timing.validated=false` も含め、内容を変更しない。adapter と ML の両方へ同じ固定契約を渡し、canonical JSON の digest handshake で一致を確認する。artifact のファイル byte hash と canonical digest は別物。

校正済み live timing は別の `--timing` JSON（launch では `timing:=`）へ保存する。こちらには `validated=true` と adapter の runtime deadlines を含める。校正後も学習時契約は書き換えない。人工 hold/small-step の接続試験では、両側へ同じ共有 `configs/policy_contract.json` を渡してよいが、校正済み runtime timing は同様に別ファイルが必要。

ROS シェルで別端末に bridge を保持する。

```bash
collection/ros.sh ros2 launch collection/policy_bridge.launch.py \
  timing:=/abs/calibrated-timing.json contract:=/abs/contract.json port:=19090
```

ML シェルで、人工 policy の保持目標から小さい既知指令へ個別に進める。

```bash
python learning/run_policy.py --mode hold --steps 1 --contract /abs/contract.json --port 19090
python learning/run_policy.py --mode small-step --joint 0 --delta 0.001 --steps 1 \
  --contract /abs/contract.json --port 19090
```

この実験の localhost:19090 の transport、実 RGB/state と source stamp、skew/age、適用後の新観測を記録する。人工 policy は接続検査であり、学習性能の結果に含めない。

古い観測、遅延 action、ML 応答途絶、WebSocket 切断、sim clock 停止・逆行、手動停止、一部 controller 拒否を個別に検査する。各ケースで後続未送信・受理済み goal の取消／hold を確認し、ケース別の合否と理由を `stop_report` に残す。CPU safety core テストだけを runtime 停止合格としない。再接続後の自動再開を合格にしない。

transport と停止の runtime 検査後、保存・再読込み済みの同じ checkpoint を1試行だけ適用する。

```bash
python learning/run_policy.py --mode checkpoint \
  --checkpoint /abs/checkpoint/pretrained_model --steps 1 --contract /abs/contract.json --port 19090
```

上記 ML 入口は既定で CPU 同期推論、`--timeout` の既定値は10秒。1 step の接続成功をカップ移送成功と扱わない。必要な試行長は本人が明示し、各試行で policy 状態・残存 action を破棄する。sim/wall 時間、推論待ち、command 適用間隔、更新後観測、失敗理由を trial report に残す。物理タスクは実カップ trace と RGB を人手で判定し、Action 終了0とは別に記録する。判定基準は [既存の成功条件](issue-1-validation.md) に合わせ、保持時間・高さ・傾き・設置誤差を残す。

## 結果 JSON の保存

`collection/record_trial_result.py` は標準ライブラリと git のみで動く。validator/converter/trainer/adapter は起動しない。Python 3.10 で利用できる streaming SHA-256 を使い、file と directory 全ファイルの相対名・サイズ・hash、inventory 自体の hash を保存する。空 directory、欠損、hash 中のファイル変更は拒否する。symlink は `model_snapshot` 内の実在 file だけを認め、解決先の絶対パスと内容 hash を保存する。raw・その他の symlink や directory link は拒否する。作業中の出力ではなく終了後の固定 artifact を渡す。

現在の未実行状態を記録する最小コマンド:

```bash
python3 collection/record_trial_result.py configs/issue4-result.json \
  --output outputs/issue4/preparation-not-run/result.json
```

出力は新規作成だけで、既存 result は上書きしない。状態更新は新しいファイルへ保存する。別 run では [入力例](../configs/issue4-result.json) を Git 外へコピーし、`run_id`、seed、配置・artifact・各工程を実際の結果に直す。artifact の相対パスは入力 JSON の場所が基準なので、コピー時に直すか絶対パスを使う。

`placements` の各要素は以下の形式。`scene_artifact` は directory ではなく、実際の `scene.json` を指定する。snapshot の `placement_id` と `split` を照合する。raw は配置へ一意に結び付け、同じ raw パスや manifest episode ID の別名登録も拒否する。

```json
{
  "id": "baseline",
  "split": "train",
  "scene_artifact": "scene_baseline",
  "raw_artifacts": ["raw_episode_1"]
}
```

artifact は `{ "role": "checkpoint", "path": "/abs/checkpoint/pretrained_model" }` のように ID ごとに登録する。同じ契約は `contract` role で1つだけ登録する。raw の schema v2 と model ID、契約と実 checkout の基盤 commit を照合する。raw の `provenance.commit` は recorder の実行 cwd 由来なので、基盤 commit と決め付けず元の値を保存する。raw の内容検証自体は固定基盤の validator と #2 に任せる。

| stage | `passed` に必要な artifact role（共通3種に加える） |
| --- | --- |
| collection | raw_episode, raw_validation_report, selection, scene |
| conversion | raw_episode, raw_validation_report, selection, dataset, dataset_report, contract |
| training | dataset_report, train_config, checkpoint, processors, lock, model_snapshot |
| reload | checkpoint, processors, reload_input, reload_report, contract |
| transport | transport_report, contract |
| stops | stop_report, contract |
| policy_trial | checkpoint, processors, trial_report, scene, contract |

実行した stage（`passed / failed`）では共通して `source / runtime_versions / log` role の証拠、実 command の argv 配列、整数 `exit_code`、timezone 付き `started_at / finished_at`、具体的な `reason` が必要。`passed` は終了0と必要 role を要求する。`failed` は checkpoint が未生成でも、実ログと環境・source を残せる。隣接する合格工程で raw/selection、dataset report、checkpoint/processors が別 artifact へ入れ替わることを拒否する。

`source` は実行時の実装ファイル一式・commit・未commit差分を保存した固定 directory を指定する。`runtime_versions` はその工程を走らせた環境の Python、OS、package/ROS/Gazebo、bridge、LeRobot の版と revision、必要なら GPU/driver の実測情報。記録スクリプトを走らせた Python の版で代用しない。`lock` は実際の解決済みファイル、`model_snapshot` は固定 local model/tokenizer/VLM と revision 資料、素材・モデルの版は raw 内 URDF/provenance と scene/world、追加 artifact で結ぶ。hash は全ファイルを読むので、大きい重みでは時間がかかる。

未実行は `not_run`、先行条件待ちは `blocked`。いずれも理由を必須とし、終了コードを付けない。`manual_task.outcome` は `success / failure / unknown / not_run` の独立した人手判定で、成功・失敗には observer と証拠が必要。`pipeline_complete` は全7工程の `passed` だけから求め、タスク成功率を意味しない。`runtime_blockers` は残る条件を具体的に残す。

`recording_repository / recording_foundation` は記録時 checkout の commit/status/差分hash。過去に実行した工程の版の証明は各 stage の source/runtime 証拠で行う。記録には input と recorder 自体の SHA-256 も付く。入力・ログの自己申告内容が真実かを hash だけで証明する仕組みではない。

## CPU 検証

```bash
python3 -m unittest discover -s collection -p test_record_trial_result.py
ruff check collection/record_trial_result.py collection/test_record_trial_result.py
git diff --check
```

準備時に Python 3.12.3 による focused テスト16件、ruff、diff check が合格。CLI の未実行記録作成と上書き拒否も確認した。準備記録は Git 外の `outputs/issue4/preparation-not-run/result.json`（初回）と `result-v2.json`。承認後は Humble コンテナの Python 3.10 で実 raw・scene・ソース・runtime・公式変換成果物を渡し、上記の collection/through-conversion record を生成して終了0を確認した。実験の異常は変換・保存なら #2、通信・停止なら #3、教師なら #1 の既存経路へ戻す。
