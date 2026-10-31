# Issue #3: policy 接続と停止検証

2026-11-01。実装、CPU試験、Gazeboの人工policy接続・停止試験、完成checkpointの
独立GPU再読込み・推論時間測定を実施した。その後ユーザーが「学習完了までで十分」と
範囲を縮小したため、追加実験を停止した。**学習済みpolicyのGazebo接続・指令適用は未実施。**
Issue #4の全工程完了、cupタスク成功、policy性能確認とは扱わない。

## 成果物と契約

- ROS adapter: `collection/policy_adapter.py --timing PATH [--contract PATH]`
- 接続launch: `collection/policy_bridge.launch.py timing:=PATH [contract:=PATH] [port:=9090]`
- ML入口: `learning/run_policy.py --mode hold|small-step|checkpoint`
  (`--contract`、`--port`、`--steps`、`--timeout`、checkpoint時の`--checkpoint`/`--device`を指定可能)。
- ROS依存はHumble側、ML依存は #2 の単一 `learning/.venv` に分離した。
  ML環境・lockの状態は [learning/README.md](../learning/README.md) を参照する。

外部state/actionは固定順序の8軸絶対位置、RGBは1視点の640×360 RGB8。
`learning.common.load_contract()` は固定基盤のschemaを再利用してfeature・単位・revisionを
検査する。両プロセスは凍結contractのcanonical SHA-256をstatus/startで照合する。
checkpointは #2 の `check_checkpoint.load_checkpoint()` で保存済みpolicy・pre/postprocessorを
厳密に再読込みする。入力はRGB float CHW、state vector、契約のtask文、出力は有限な8軸。
同期 `select_action()` を使い、出力のclampや独自の学習loopは追加していない。

**学習contractと実指令用timingは別ファイル。** `configs/policy_contract.json` の
`timing.validated=false` は維持した。adapterは別途 `--timing` が必須で、明示的な
`validated=true` と必要項目を確認する。候補設定を無条件に実指令へ使わない。

## 実装した検査・停止

- 最初の送信前に8軸全体のshape、有限値、URDF範囲・速度、session、観測token、
  source stamp、age/skewを検査する。腕→左指→右指の各受付後にも送信前鮮度を再検査する。
- 3controllerへの送信は原子的ではない。部分拒否・結果失敗時は後続を止め、
  受付済み・後着のgoalも取消す。固定controllerのcancel経路が現在位置holdへ入る。
  取消し応答とterminal resultを追跡し、配送が不明なら新sessionを拒否する。
- watchdogは明示的な `ClockType.STEADY_TIME`。初回観測・配送停止・推論/heartbeat途絶・
  clock停止/逆行/過大な前進・goal timeout・手動停止を扱う。
- DDSでJointStateが最新`/clock`より先に届く実測があった。未到達sampleをstagingし、
  clockが到達してから昇格する。最後のcausal sampleの元配送時刻を保持するため、
  heartbeatや未来sampleの反復で観測期限は延長されない。SafetyCoreの未来stamp拒否は維持した。
  最終レビューでpending上書きによるsample欠落を修正し、streamごとに最大128件を保持して
  到達済みの最新sampleを昇格し、未来sampleを残すようにした。この履歴修正は実験中止後の
  明示依頼に基づくCPU検証のみで、ROSで再実験していない。
- MLはstatusだけで開始せず、観測publisherのDDS subscription countが正になるまで
  **停止状態のまま**待つ。開始には新sessionと一致するcontract hashが必要。
- 観測はtokenごとに1回だけRELIABLEで送る。約923KBの同じ画像を50Hz watchdogから
  再送し続ける処理を除いた。新観測は全controller成功後、両source stampが完了時clockを
  超えたものを要求する。
- `reliable_topic_type()` の小さいsubclassは、固定roslibpy 2.0.1の `_connect_topic(message)`
  hookで**subscribeだけ**にRELIABLE / VOLATILE / KEEP_LAST depth10を付ける。
  元のadvertise/unsubscribe/close処理を使い、upstreamコードはコピー・変更していない。
  このprivate hookは固定版のsourceを確認済みで、実行時version検査と焦点を絞ったテストがある。
- teacherとadapterは共通 `collection/control_lock.py` を使う。adapterは起動確認から
  shutdown cancellationまでlockを保持する。同じUIDと同じ`/tmp`が必要であり、別UIDや
  private `/tmp`を持つ別containerへの排他保証はない。
- 再接続だけでは再開しない。強制kill、middleware/backend消失時は取消しを保証できないため、
  backend確認/reset後に明示的に開始する。実機接続は今回行っていない。

## 実行環境と証拠

今回のignored実行rootは `outputs/issue4/e2e-20261101-022215/`。
以下の証拠はその `issue3/` 以下に保持した。実画像・重み・ログ・実行環境はGitへ含めない。
集約は `transport_report.json`（partial）、`stop_report.json`（incomplete）。
学習済みtrialのユーザー延期とWebSocket harnessのexit1を含め、`pipeline_complete=false` とした。

- rosbridge_suite **2.0.8** / `bf8b370b1c700159ab5630a9a8616c62db519e7c` を
  ignored `external/bridge` overlayへsource buildした。
- ROSは既存image `lifth-pai-collection:humble` の専用container
  `pai-issue4-e2e-scene`、UID1000、host network、ROS_DOMAIN_ID187、
  IGN_PARTITION=`pai_issue4_e2e_20261101`。#2/#4のyaw_plus worldを使い、教師終了後に実施した。
- MLはCPython3.12.16、roslibpy2.0.1。別のbuild/smoke専用containerは
  `pai-issue3-bridge-build`、domain188でsceneを起動していない。
- bridgeはlocalhost bind。既存Prometheusが9090番を使用していたため、既定値を維持して
  port指定を追加し、実験では **127.0.0.1:19090** を使った。無関係なcontainerは変更していない。
- `runtime-versions.json`、`bridge-revision.txt`、`bridge-build.log`、依存install logs、
  `commands.jsonl` / `fault-commands.jsonl` に版・argv・時刻・終了コードを保持した。
  初期hold/small-stepの正確なcommand開始時刻は未記録で、stdoutの実測値を証拠とする。

### 実際に確認した範囲

| 対象 | 実測結果 | `issue3/` 内の証拠 |
| --- | --- | --- |
| host ML→固定ROS bridge pub/sub | 成功 | `roslibpy-smoke.json` |
| 実Humbleのsteady timer、sim clock=0 | 0.3秒にsteady15回、sim timer0回 | `steady-timer-runtime.json` |
| 人工hold→3controller成功→新観測 | `applied=1`、初回wall約1.233秒 | `run-policy-hold-01.log` |
| base軸の既知0.001rad offset→新観測 | `applied=1`、wall約1.187秒 | `run-policy-small-step-01.log` |
| 暖機後holdの再試行 | `applied=1`、wall約1.494秒 | `run-policy-hold-05.log`、`hold-evidence-05/` |
| 各controllerの現在位置hold/cancel | 3件hold成功、3件cancel terminal status5。受付最大12.732ms、cancel応答最大2.372ms | `calibration-steady-holds.json` |
| 部分controller拒否 | 左指をdeactivateして拒否。armは2→3→5、右指へgoalなし | `partial-reliable.json`、`controller-events-fresh-09.jsonl` |
| sim pause | 進行中holdでsteady watchdog停止、取消し確認。unpauseしても自動再開なし | `clock-pause-reliable.json`、`controller-events-fresh-10.jsonl` |
| clock逆行 | `clock jump or reversal`、停止/idle | `clock-reversal-reliable.json` |
| 古いstate stamp注入 | `future or stale observation`、停止/idle | `stale-reliable.json` |
| 手動stop | 進行中hold停止、取消し確認 | `manual-stop-reliable.json` |
| WebSocket切断/heartbeat途絶 | 停止条件は確認。ただしharness cleanup失敗、exit1で試験全体は未合格 | `websocket-drop-reliable.json`、同名`.log`、`commands.jsonl` |
| 推論停止/遅延action | 実際のcommand budgetを超えて待機。`inference stalled`、停止/idle | `delayed-action-reliable.json` |
| 完成checkpointの独立再読込み・実RGB推論 | GPU2で4回とも有限8軸、未clamp。cold728.320ms、warm325.682/371.401/410.364ms | `checkpoint-latency-gpu2.json` |

hold/small-stepの成功は最終QoS修正前の実行である。修正後はRELIABLE endpointと実RGB配送、
上記の停止ケースを確認したが、最終実装での正常goal完了→新観測の再試行や学習済みpolicy適用は
ユーザーの中止指示後に追加実行していない。clock逆行・古いstampの注入試験はidle時の新規指令停止を
確認したものであり、そのケース単独で進行中goalの取消しまで確認したとは扱わない。

### 校正timing

共有の候補は観測skew70ms、command系列skew50ms、age100msのまま。
別の実験用timingはRGB/state/clock、現在位置hold、並行load下の配送、完成NN推論から算出した。
`timing-calibration-record.json` と `policy-timing-calibration-record.json` に入力hash・測定window・
marginを記録した。最終停止試験は次の**policy用profile**で実施した。

| 項目 | 最終実験値・根拠 |
| --- | --- |
| command age | 1.49秒。実測NN最大728.320msの2倍＋実測受付最大の2倍を10ms単位で切上げ |
| observation age | 1.94秒。測定したsensor envelope450ms＋command budget |
| observation skew | 450ms。暖機後skew最大223msの2倍を切上げ |
| trajectory duration / goal timeout | 1秒 / 2.12秒。現在位置hold実測から設定 |
| heartbeat timeout | 410ms。測定したRGB配送間隔から設定 |
| clock stall | 80ms。並行load下の最大clock gap35.223msの2倍を切上げ |
| clock jump tolerance | 10ms。測定したsim増分/steady増分の差から設定 |

これらは単一CPU描画Gazebo環境での実験値であり、実機や別load条件の保証ではない。
`calibrated-hold-timing.json` に初期profile、`calibrated-policy-timing.json` に最終profileを保存した。
学習contractの内容は変更していない。

## 失敗・未実施・残る制約

- 初期DDS ordering、初回観測DDS route未確立、BEST_EFFORTによる大きいRGB配送、同じ画像の
  反復送信で観測待ち/期限切れが発生した。`attempt-01/`、`attempt-02/`、
  `run-policy-hold-02.log`〜`04.log`、`*-fresh.json`、`partial_rejection-final.json` 等に保持した。
  固定bridgeの既定QoSを確認して修正し、`observation-qos-after.log` でbridge購読側の
  RELIABLE / KEEP_LAST depth10を実際に確認した。修正後は同じscene/bridgeで
  clock逆行→古いstamp→manual stop→WebSocket drop→遅延actionの各新sessionで停止statusを観測した。
  長時間運転や多数sessionの一般的な再利用保証は未検証。
- WebSocket dropのJSONは`completed=true`で期待する停止/idleを記録したが、command receiptはexit1。
  新しいread-only接続で停止を確認した後の`ros.terminate()`で
  `TwistedEventLoopManager._thread`の`AttributeError`が発生した。
  安全条件の観測とharness正常終了を分け、この試験全体をclean passとはしない。
  ユーザーの中止指示後には修正・再試験していない。
- runtime velocity faultの初期設計は失敗した。実URDFは全8軸velocity=100で、1秒profileでは
  各jointの可動span/durationがvelocity以下になるため、範囲内の初回targetで速度超過を作れない。
  +1radの試験入力は許可され、simのbaseが動いた。その後sceneを新規起動した。
  `velocity-runtime-proof.json` に全jointの限界値と証明を保存した。人工的に短い校正profileを
  作ってruntime拒否成功とはしていない。合成propertiesによるCPU負例は別に存在する。
- 独立したML process強制終了ケースは未実施。WebSocket切断/heartbeat途絶の実試験と区別する。
- 完成checkpointのGazebo適用、新観測取得、cup pose/RGBによる物理タスク判定は未実施。
  `learned-evidence-01/start.gate` は作成されず、接続前準備中のML PID41925はSIGTERMで終了し、
  `commands.jsonl` にexit=-15を記録した。学習済みpolicyはROSへ接続もstartもしていない。
- source snapshot `source-runtime/` は途中時点のもので、全試行が同じ実装だったとは扱わない。
  最終コードは `source-final/` に別途保存した。ignored証拠はPRへ入れず、今回の記録との対応を保つ。

## 終了と検証記録

ユーザーの範囲縮小後に新しいROS/GPU実験・モデル実行は行っていない。
adapterの `stopped=true / busy=false` を確認後、bridge/adapter group9520、observer9531、
scene/Gazebo group9076の終了を確認した。専用containerは両方停止済み
(`pai-issue4-e2e-scene` exit143、`pai-issue3-bridge-build` exit137)。
後者はDocker stopの20秒timeout後に終了した。GPU compute processはなく、データ・checkpoint・環境は保持した。
証拠は `safe-stop-confirmation.json`、`process-shutdown.json`、`shutdown-report.json`。

実施済みCPU検証はadapter23件、ML入口8件、対象5 Pythonファイルのruff、両CLIの`--help`、
`git diff --check`。範囲縮小後の履歴修正については、明示依頼のfocused CPU試験とruffだけを
再実行して成功した。複数sampleがclock前に到着する場合と128件overflowを回帰試験で確認した。
PRの最終回帰確認は主担当が行う。

## 確認したsource

- 固定基盤 [model helpers](../external/lifth_arm_gen2/src/lifth_bringup/lifth_bringup/model.py)、
  [gripper](../external/lifth_arm_gen2/src/lifth_bringup/lifth_bringup/gripper.py)、
  [controller cancellation](../external/lifth_arm_gen2/src/joint_trajectory_controller/src/joint_trajectory_controller.cpp)。
- [rosbridge server](https://github.com/RobotWebTools/rosbridge_suite/blob/bf8b370b1c700159ab5630a9a8616c62db519e7c/rosbridge_server/scripts/rosbridge_websocket.py)、
  [subscription QoS](https://github.com/RobotWebTools/rosbridge_suite/blob/bf8b370b1c700159ab5630a9a8616c62db519e7c/rosbridge_library/src/rosbridge_library/internal/subscribers.py)、
  [QoS extraction](https://github.com/RobotWebTools/rosbridge_suite/blob/bf8b370b1c700159ab5630a9a8616c62db519e7c/rosbridge_library/src/rosbridge_library/internal/qos_extraction.py)。
- [roslibpy2.0.1 Topic/private hook](https://github.com/gramaziokohler/roslibpy/blob/19f0fccf9edd95bbf8fbe7f41864ce8f90bc4943/src/roslibpy/core.py)、
  [Ros lifecycle](https://github.com/gramaziokohler/roslibpy/blob/19f0fccf9edd95bbf8fbe7f41864ce8f90bc4943/src/roslibpy/ros.py)。
- 固定LeRobot [factory](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/policies/factory.py)、
  [batch processor](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/src/lerobot/processor/batch_processor.py)。
