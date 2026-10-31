# Issue 2 3 4 の実装計画

2026-11-01。対象は [Issue #2](https://github.com/hoki621/lifth-pai/issues/2)、[Issue #3](https://github.com/hoki621/lifth-pai/issues/3)、[Issue #4](https://github.com/hoki621/lifth-pai/issues/4)。
本計画は `b7ccc03fd7e82bcb54a460cd998f6c19de5a32fc` を基準とする。

## 目的と担当範囲

Issue #2で複数配置の少量収録・raw変換・学習・保存を用意し、#3でGazeboへの推論接続を作る。
#4は両者を使う統合検証の手順と記録を準備し、利用可能になった工程から確認する。
準備・実装は並行し、学習済みcheckpointを使う統合実行には依存順を設ける。

| 担当 | 成果物 | 依存する成果物 |
| --- | --- | --- |
| #2 前半 | 複数配置の少量収録手順、検証済みLeRobot dataset、変換照合結果 | #1の固定基盤・素材・既存収録 |
| #2 後半 | 固定ML環境、公式trainer設定、保存・再読込み可能なcheckpointとprocessor | #2前半のtrain dataset |
| #3 | ROS側adapter、ML側同期推論、接続・停止試験 | 共通feature契約。実policy接続時は#2後半 |
| #4 | 少量の一周検証手順、使用データ・版・結果を結ぶ実行記録 | #2・#3の各工程を順次利用 |

ユーザーとの合意により、複数配置での少量収録・変換確認は#2へ含める。
#5の本収集は後回しとし、本収集用の一括実行・件数管理・転送自動化は今回実装しない。
将来の本収集開始は#2前半の検証で判断できるようにし、#4の学習・推論完了を必須条件にしない。
GitHub上のIssue本文はまだこの分担へ更新していない。

## 現在の基盤と実装の入口

- 共通基盤は `de410efb3a90348e256015305e80e10ecdcfd972` に固定済み。モデルは `v2_1_1`、rawはschema v2。旧Issue本文の8軸未対応という前提は引き継がない。
- [検証記録](issue-1-validation.md)では、hikariで通常launchの固定10試行中8件が物理成功、rawは10件ともcomplete・validator合格。複数配置は今回確認する。
- `collection/prepare_cup_world.py` は設定からcup・支持台を生成できる。`configs/cup_scene.json` の教師目標は固定座標であり、cup位置やyawだけの変更では対応済みと扱えない。
- `collection/setup.sh`、`cup_demo.launch.py`、`cup_sequence.py` は `outputs/issue1/cup_world.sdf` を使う。配置別worldを渡す入口を最小限追加し、現在の既定値・手順は維持する。
- `learning/` はREADMEのみ。ML依存・converter・推論コードはこれから作る。

## 共通契約を最初に固定する

並行実装前に、#2が `configs/policy_contract.json` と短い説明を用意し、#3・#4が同じ契約で実装する。
ファイル名は新規成果物の案であり、以下の新規コマンドも実装前は利用できない。
共通基盤のschema定義を複製せず、manifestとモデル定義が契約に適合することを検査する。

| 項目 | 方針 |
| --- | --- |
| state / action | 外部8軸の絶対位置。`base_j2, j2_j3, j3_j4, j4_j5, j5_j6, j6_ee, ee_f1, ee_f2`。腕6軸はrad、指2軸はm |
| actionの由来 | `command.jsonl`、`left_command.jsonl`、`right_command.jsonl` の実出力を時刻対応させる。stateやゼロ値で代用しない |
| RGB | rawは640×360のRGB8、1視点。dataset key案は `observation.images.d405`。datasetのHWCとpolicy tensorのCHWを区別し、resize等は公式processorへ合わせる |
| policy入力 | RGB、`observation.state`、共通のtask文。配置ID、cup真値、教師phase、成功ラベルは入力しない |
| 時刻 | rawの `source_stamp_ns` によるsim時刻。変換後のframe indexと元source stampの対応を照合記録へ残す |
| サンプリング | 初期候補15 FPS。観測はサンプル時刻以前の最新値。actionもlabel時刻以前の各系列の最新値を使う |
| label offset | `label_time = observation_time + offset_ns` と符号を明記。初期候補0 nsを既知の指令で検証し、採用値を設定へ保存する |
| 許容する時間差 | RGB/stateのskew、各入力の最大age、command系列間の時間差を設定に残す。既存rawの300 ms上限を学習・指令適用の適切な上限とはみなさず、小試験で確定する |
| split | 配置単位でtrain / validation / held-outを事前指定。同じ配置・episodeを複数splitへ入れない |
| 保存物 | datasetの元episode対応表、train由来統計、policy設定、pre/postprocessor、時刻設定、基盤・PAI・modelの版を結び付ける |

## Issue 2 の実装手順

### 前半は複数配置と変換を検証する

1. **配置と収録入力を用意する。** 基準配置に加え、位置変更とyaw変更を含む少数のscene設定を明示的に用意する。腕初期姿勢と置き先は固定する。train側の複数配置と別のvalidation配置、将来のheld-out配置を先に区別する。具体的な座標と範囲は到達性・接触を確認して確定し、未検証値を本収集設定として扱わない。
2. **worldと教師目標を整合させる。** cupのmesh原点・胴体中心・支持台・接近／把持／移送の目標を各sceneで確認する。yaw変更に対してTCP目標を単純回転すれば動くとは仮定しない。既存のworld生成・シーケンス・指Actionを再利用し、IKやrecorderを新設しない。
3. **1試行分の入口を作る。** 配置を選んでscene snapshotとworldを試行固有ディレクトリへ生成し、同じsnapshotを教師と起動に渡す。launchと教師にworld指定を追加する。resetは既存と同じlaunch再起動を使い、自律反復や大量収集runnerは作らない。
4. **採用episodeを明示する。** `outputs/issue2/<run>/` に配置ID、pose/yaw、split、episode ID・rawパス、task成功の人手判定、validator結果、採否・除外理由、設定hash・実行版を記録する。rawは変更しない。保存complete、シーケンス終了0、タスク成功を別項目にする。既存の成功rawは変換着手に使えるが、同じ固定配置のrawを別splitへ割らない。
5. **ROS外converterを作る。** 固定基盤の `lifth_dataset.validate.validate()` を呼び、成功判定と対応表も検査する。schema v1、未完了、未知schema、指command不足、配置・split不明を拒否する。validator自体は再実装しない。
6. **時系列を対応させる。** 全系列が利用可能な共通区間に整数nsの固定FPSグリッドを作る。先頭・末尾の使用区間を記録し、episode境界を跨がない。観測の未来参照、欠損のゼロ埋め、内部区間の削除による時間圧縮は禁止する。内部で許容age・skew等を満たせないepisodeは理由付きで拒否する。
7. **公式writerで出力する。** 固定版の `LeRobotDataset.create()` → `add_frame()` → `save_episode()` → `finalize()` を使う。trainとvalidationを別のdataset rootへ出し、trainだけで学習用統計を作る。held-outは学習・checkpoint選択に使わず予約する。出力済みdatasetへの暗黙の上書きや追加はしない。
8. **再読込みと照合を行う。** 各配置の先頭・動作中・末尾で、元RGB、state、腕・左右指command、source stamp、label offsetを照合する。動画を使う場合はcodecを含め、frame・色・shapeの対応を確認する。rawが変換前後で不変であることも確認する。

前半の完了条件は、複数の位置・yaw条件の成功rawを同じconverterで読み、各splitの公式v3 datasetを再読込みできること。
これを収録・変換経路の確認として記録し、学習済みpolicyの性能と分ける。

### 後半は公式学習と保存を検証する

1. **ML環境を分離・固定する。** Python 3.12.16、LeRobot `7e241bd630a3719a56157a497ce5d08f244784f1` と公式lockを起点にする。公式lockのSHA-256は `fcca9a7a87244fdfe82ae2760e49f6254267b5016d8564e4b24596a166250c6f`。選択extra、index、解決ツール版、解決済みlockを保存する。候補torch 2.11.0+cu128 / torchvision 0.26.0+cu128はdriver・GPU・codecとの対応を確認して採用する。
2. **モデル参照を固定する。** pi05を優先し、VRAM・実行時間・利用条件等で困難なら理由付きで固定SmolVLAへ切り替える。model、tokenizer、VLMのsnapshotをlocal pathから使い、processor内の参照も固定する。
3. **8軸・1画像へ整合させる。** 配布configの入力featureを明示的に見直し、dataset由来の8軸と画像keyを反映する。配布processorの6軸統計等は流用しない。不足cameraの公式処理と内部paddingを確認し、外部actionが8軸であることを検査する。
4. **公式trainerを使う。** 小さいbatch・短いstep数でforward/backwardとcheckpoint保存を確認する。最終uploadと途中checkpoint uploadの両方を無効にし、外部ログ送信も無効にする。Gazebo検証は#3・#4の手順で行う。
5. **splitを保つ。** 標準trainerにはtrain専用rootを渡し、episode順から自動分割する `eval_split` は使わない。validationは保存済みprocessorとtrain統計を使う小さな評価処理で確認する。独自の学習loopやcheckpoint探索は作らない。
6. **別プロセスで再読込みする。** 保存したpolicy・pre/postprocessorを新しいプロセスで読み、同じ画像入力契約から有限な8軸出力が得られることを確認する。base weightsからの初期化と完成checkpointの読込みを区別する。

| 参照 | 固定revision |
| --- | --- |
| pi05 base | `lerobot/pi05_base@22c30e5b34f9e7ab738b1b34fc2fc5ecfe2d28f0` |
| pi05 tokenizer | `google/paligemma-3b-pt-224@35e4f46485b4d07967e7e9935bc3786aad50687c` |
| SmolVLA base | `lerobot/smolvla_base@5e8d12a6e2975b0e5e5fce7c8caf47c371d257b6` |
| SmolVLA VLM / tokenizer | `HuggingFaceTB/SmolVLM2-500M-Video-Instruct@7b375e1b73b11138ff12fe22c8f2822d8fe03467` |

## Issue 3 の実装手順

1. **transportだけで小試験する。** rosbridge_suite 2.0.8 / `bf8b370b1c700159ab5630a9a8616c62db519e7c` とroslibpy 2.0.1 / `19f0fccf9edd95bbf8fbe7f41864ce8f90bc4943` を候補に、pub/sub、実サイズRGB、stamp、joint state、短い指令を確認する。ROS ActionはHumble側で扱う。候補が不合格なら原因と採用する代替版を記録し、transportを並列に増やさない。
2. **localhost接続を確立する。** ROSはDockerのUbuntu 22.04 / Humble system Python、推論は別のML Python。rosbridgeのbindを `127.0.0.1` とし、両プロセスから到達するnetwork namespace構成を先に確認する。Dockerのport公開だけでcontainer内loopbackへ到達するとは仮定しない。
3. **観測を共通契約へ合わせる。** D405の実RGBと8軸stateを取得し、色順・画像step・shape・frame・source stamp・skew・ageを検査する。#2と同じkey、順序、単位、taskを返す。RGBのQoS・遅延は実測し、画像が見えるだけで合格にしない。
4. **ROS側の指令adapterを作る。** 8軸全体のshape・有限値・URDF limits・速度・鮮度を送信前に検査し、既存のarm・左右指controllerへ適用する。必要なAction受付・取消・holdをROS側で扱い、policy actionごとのMoveIt再計画は行わない。3controllerへの送信を原子的とは扱わず、一部拒否・失敗時にも後続を止め、受理済み指令を取消／holdする。
5. **停止を先に通す。** 古い観測、遅延action、推論途絶、WebSocket切断、sim clock停止・逆行、手動停止で新規指令を止める。watchdogはROS側の単調時計でも監視し、MLが応答しなくても停止できるようにする。再接続だけでは再開せず、明示的に再起動する。教師との指令権限を排他にする。
6. **人工policyから接続する。** #2の学習完了を待たず、保持目標・小さい既知指令で「観測→適用→新観測」と停止を確認する。安全性・transportの検証であることを明記する。
7. **学習済みpolicyへ置き換える。** #2で再読込み済みのlocal checkpointと同じprocessorを使い、公式の同期action選択を接続する。試行ごとにpolicy状態と古いactionを破棄する。sim / wall時間、推論待ち、指令適用間隔を測り、同期実行で不足すると確認された場合に限り同じLeRobot版の公式手段を検討する。

完了条件は、#1と同じモデル・worldで実画像から8軸actionを生成・適用し、新観測を取得でき、停止・拒否条件の小試験に合格すること。
タスク成功率の測定は#3の完了条件にしない。

## Issue 4 の準備と実行

#4は実験Issueとして、#2・#3と並行して次を準備する。converter、trainer、ROS adapterは各実装Issueの成果物を呼ぶ。

1. **入力と実行記録を決める。** #2で採用した少量の成功episodeとsplitを固定し、raw→dataset→train config→checkpoint→processor→Gazebo試行をrun IDで結ぶ。配置、実装commit、基盤SHA、依存lock、asset版、seed、採否・結果を `outputs/issue4/<run>/` に保存する。
2. **段階別の確認手順を作る。** 変換・照合、短い公式学習、別プロセスでの再読込み、#3の停止試験、実policyによる1試行を個別に実行できる手順にする。起動/reset/開始終了は本人が行い、成功・失敗を記録する。
3. **利用可能な工程から検証する。** #2前半ができたら複数配置の変換結果を確認し、#3の人工policy接続ができたら通信・停止を確認する。checkpointとadapterが揃ったら実policyで一周する。
4. **不具合を実装担当へ戻す。** 変換・正規化・保存は#2、通信・指令・停止は#3へ戻す。教師の共通不具合は#1の既存経路を修正する。必要時のcommand replayも#3の同じ検査・停止経路を通す。
5. **結果を区別して残す。** RGB/state/actionの整合、推論待ち・sim指令周期、物理タスクの人手判定、失敗理由を記録する。短い学習で成功しなかった場合も、その事実と原因候補を残す。配線の動作確認とpolicy性能を混同しない。

完了条件は、固定した少量データでraw→dataset→学習→保存・再読込み→Gazebo試行を一周し、データ・版・設定と結果が追跡できること。
本収集・本学習・held-outでの成功率実験は行わない。

## 並行作業の編集範囲と検証順

以下は実装時のファイル配置案。細かな分割は既存の小さいPython scriptとunittestの形式に合わせる。

| 担当 | 主な変更先 | 他担当への受け渡し |
| --- | --- | --- |
| #2 | `collection/prepare_cup_trial.py`、既存launch・教師のworld指定、配置設定、`learning/convert_raw.py`、`learning/check_checkpoint.py`、学習設定・ML lock、`learning/test_*.py` | 共通契約、少量dataset、照合結果、checkpoint・processor |
| #3 | `collection/policy_adapter.py`、接続launch、`learning/run_policy.py`、接続設定、adapter・停止のテスト | 人工policyと実policyの起動・終了手順、停止検証結果 |
| #4 | `docs/issue-4-validation.md`、少量実験設定、必要最小限の結果記録処理 | 再現手順、各段階の結果、不具合と再確認結果 |

ML lockと共通契約の更新は#2へ集約する。#3はroslibpyの追加要件を渡し、別のML環境・lockを作らない。
README・環境文書の統合は担当間で調整し、同じファイルを同時に書き換えない。
Issueごとのbranchで変更をレビューし、共有checkoutで並行してbranchを切り替えない。

| 段階 | 並行して進める作業 | 次へ渡す条件 |
| --- | --- | --- |
| 共通準備 | feature・時刻・保存物の契約を合わせる | #2・#3・#4の検査項目が一致 |
| 実装開始 | #2の配置・converter、#3のtransport・停止、#4の手順・記録 | 各担当のCPU試験が通る |
| データ確認 | #2の複数配置収録・変換、#3の人工policy試験、#4の段階検証 | 再読込み済みdatasetと停止確認済みadapter |
| 学習確認 | #2の短い公式学習・保存・再読込み、#3の実policy接続準備 | 同じ契約のcheckpoint・processor |
| 統合確認 | #4が#2・#3の確定版を使って一周 | 実行記録と不具合の修正・再確認 |

Herdrでは#2・#3・#4をそれぞれ担当させる。実装開始時、ツールのshellにはHerdr変数が引き継がれていなかったが、
親Codexプロセスの`HERDR_ENV=1`とpane情報を確認できたため、その接続情報を継承して3担当を起動した。
共有checkoutでは編集範囲を分け、branchの同時切替は行わない。
実装の並行数とGazebo実行の並列数は別に扱う。初期確認は1環境とし、配置ごとにworld・ログ・rawの対応を保つ。

## 検証項目と実行上の条件

| 対象 | 最小の検証 |
| --- | --- |
| 配置 | 元設定の既定動作を維持。cup・支持台・教師目標・world snapshotが同じ配置を指す。位置・yaw変更を含む少量の実収録 |
| converter | 既知の非同期時系列で未来観測を使わないこと、offsetの符号、左右指commandの順序、境界・欠損・不正raw拒否、split混入拒否、公式writer再読込み |
| 学習・保存 | train統計へのvalidation混入なし。PAIの8軸・1画像でforward/backward、保存後の別プロセス読込み、upload無効 |
| adapter | shape不正・NaN・limits・速度超過・古い観測・遅延actionを拒否。切断・推論途絶・clock異常・手動停止・一部controller拒否で停止 |
| 統合 | 同一データ・契約・processorによる一周、更新後観測、遅延記録、タスク成功の人手判定と失敗理由 |

既存の `collection/test_*.py` を回帰確認し、新規の挙動には同じunittest形式の焦点を絞ったテストを追加する。
実装ごとに関連テスト、利用可能なlint、`git diff --check` を実行する。実データ・重み・ログはGit外へ置く。

インストール、学習・GPU起動、SSH、公開は[AGENTS.md](../AGENTS.md)の個別依頼条件に従う。
計画作成時点ではこれらを実行していない。学習依存の解決・driver/codec対応、gated tokenizerの利用条件・認証、bridgeの統合対応は実行時に確認する。
実装済み・CPU試験済み・hikari統合確認済みを区別し、未実行の確認を完了扱いにしない。

## 採用版の確認先

- [固定基盤のraw schemaとvalidator](https://github.com/LifthPJT/lifth_arm_gen2/blob/de410efb3a90348e256015305e80e10ecdcfd972/src/lifth_dataset/README.md)
- [固定LeRobotのdataset writer](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/datasets/lerobot_dataset.py)
- [policyとprocessorのfactory](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/policies/factory.py)
- [標準trainer](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/scripts/lerobot_train.py)と[標準のepisode分割](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/datasets/factory.py)
