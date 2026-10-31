# Issue #1 検証結果

## hikari Docker 初回実行（2026-10-31）

- PAI: `6cdda3e566bc209e2cd2f174311a5923eb22bad6`（PR #8 merge）、基盤は上記手順の固定版 `de410efb3a90348e256015305e80e10ecdcfd972`。教師設定は変更なし。
- 提供モデルZIP・カップZIPのSHAは記録と一致。モデル展開27ファイル・mesh10個の検査に合格。必要素材は揃っている。
- Docker 29.7.1、CPU描画。イメージbuild、rosdep依存導入、全9packageビルド、モデル設定追加、world生成、起動に成功。ホストにROS・学習環境は導入していない。
- 固定設定1試行のシーケンスは終了0。Gazebo実カップposeで把持・移送・設置を確認し、退避まで完了。移送中8.727 sim秒の最低zは0.381369 m、最大傾き0.022334度。最終XY誤差0.073380 mm、Z誤差0.000065 mm、傾き0.000079度で上記の成功条件に合格。
- raw: `data/raw/episode_8f2ef2ded8e14c4ebe2aa8e29a77af93/`。**保存はincomplete、既存validatorは終了1。** 下降中にRGBの入力stamp間隔330 msが既存上限300 msを超え、自動停止した。明示stopは「no active episode」を返した。
- 保存RGBは640×360の304枚（画像を確認）、stateは2159件。全工程のRGBは保存されておらず、学習用completeデモの生成可否は未確認。描画・bridge・DDSのどの層で欠落したかは未特定。教師設定や欠落閾値は変更していない。
- 詳細: Git外の `outputs/issue1/hikari-result.json`、`hikari-cup-trace.jsonl`、`hikari-sequence.log`、`hikari-launch.log`、`hikari-setup.log`、`hikari-stop.log`、`hikari-validator.log`。導入版は `runtime-packages.txt`、Docker buildログは `/tmp/lifth-pai-hikari-docker-build.log`。

### hikari RGB欠落の原因調査（同日）

Gazeboネイティブ購読とROS購読の撮影stampを同時観測した。GazeboのRGB/CameraInfoは最大67 ms間隔で継続し、ROS診断購読ではGazeboに存在した画像6枚が欠落した。さらに既存recorderでもGazeboのstamp `129955000000`、`130021000000` の2枚がrawに届かず、間隔が198 msになった。`/proc/net/udp` のsocket inodeをPIDへ対応させ、recorderプロセスの受信socketで3件、診断ROS購読で23件のUDP破棄を確認。`/proc/net/snmp`でも`RcvbufErrors`を確認した。

この診断で確認した欠落箇所はROS/DDSのUDP受信経路。PNG書込みやGazebo描画の欠落ではない。bridgeのRGB publisherはRELIABLEだがrecorder購読はBEST_EFFORTであり、受信落ちを再送で回復しない。ホストの`net.core.rmem_max`・`rmem_default`は各212992 bytes、RGB payloadは691200 bytes。受信バッファ上限の小ささは候補だが、個々のDDS socketの実バッファ容量や溢れを起こすスケジューリング条件までは未測定。前回の330 ms欠落時の送信側・socket記録はなく、前回と同一原因であることは未確定。

診断rawは `data/raw/episode_aeab6f447e954c40aec9582a69c50462/`。約142 sim秒、RGB2156枚、complete・既存validator終了0（RGB最大source gap 198 ms）。これは収録経路の診断で、全工程の成功例ではない。教師動作は下降Cartesian経路fraction約0.161の既知条件で停止した。教師設定・欠落閾値・基盤コード・ホストsysctlは変更していない。

証拠はGit外の `outputs/issue1/hikari-diagnostic-*`（Gazebo/ROS stamp、集計JSON、UDP/SNMP、QoS、launch、start/stop、validator）。次の修正候補はRGB受信の信頼性・バッファ設定。上流のrecorder変更やホスト設定変更は今回行っていない。

### hikari RELIABLE RGB比較検証（同日・再起動なし）

固定基盤のrecorderを継承するGit外の診断wrapper `outputs/issue1/hikari-reliable-recorder.py` で、RGB購読だけをRELIABLE/depth100に変更した。元のrecorderプロセスは停止し、同じmodel/backend/output_dir/use_sim_timeでwrapperを起動。画像形式、教師設定、source gap/age閾値、他streamのQoS、ホストsysctl、固定基盤のソースは変更なし。manifestの`provenance.settings.qos.rgb`に診断overrideを記録した。ROS endpointでもRELIABLEを確認。

- episode: `f6397d7d78914d7bae7dbc47ef4d77f8`。rawは `data/raw/episode_f6397d7d78914d7bae7dbc47ef4d77f8/`。
- 同時観測した66.726 sim秒・Gazebo RGB1012枚のうち、並行BEST_EFFORT購読は2枚欠落（stamp `21055000000`、`21121000000`）。RELIABLE recorderは欠落0枚、最大source gap66 ms、最大source age71 ms。
- **全工程のrawはcomplete、既存validator終了0。** RGB1012枚、state6681件。移送・退避後の実画像も確認した。
- **物理タスクも成功。** シーケンス終了0、持上げ後8.729 sim秒の最低z 0.381490 m、最大傾き0.022360度。最終設置XY誤差0.072810 mm、Z誤差0.000127 mm、傾き0.000081度。
- ログ・比較結果・実カップtraceは `outputs/issue1/reliable-check/`（`comparison.json`、`hikari-result.json`、`validator.log`、`qos.txt`等）。コンテナは停止した。

再起動せずRGB購読QoSの変更で欠落のない全工程収録ができた。この診断時点では既定の起動手順はBEST_EFFORTのまま。後述のPAI接続で通常launchにも適用した。基盤checkoutの追跡ファイル・upstreamは変更していない。

### 通常launchへのRGB RELIABLE適用

`collection/reliable_rgb_recorder.py` が固定基盤のRecorderを継承し、RGB購読だけをRELIABLE/depth100へ変更する。基盤の`main()`を再利用して保存・終了・エラー処理を維持し、`cup_demo.launch.py`から通常起動する。manifestの`provenance.settings.qos`にはRGB設定と他streamのBEST_EFFORT設定を区別して記録する。欠落・鮮度閾値、教師設定、基盤commitは変更していない。

通常launchをhikariのDockerで起動し、RGB endpointのRELIABLE設定を確認した。episode `6f44bad5833e495a8a20676d55a53ee6` は全工程成功・raw complete・既存validator終了0。RGB1064枚、欠落推定0、最大source gap66 ms、最大source age119 ms。実カップの保持は8.760 sim秒、最低z0.381433 m、最大傾き0.022523度。最終設置XY誤差0.073288 mm。rawは `data/raw/episode_6f44bad5833e495a8a20676d55a53ee6/`、ログ・実カップtrace・判定はGit外の `outputs/issue1/reliable-patch/`。

既存unittest8件、変更したPythonのruff、collectionのcompileall、`git diff --check`に合格。manifestのRGB QoSと300 ms閾値も照合した。基盤の追跡ファイルは未変更。コンテナは停止した。続いて下記の固定10試行を実施した。

### hikari 通常launch・固定設定10試行（2026-10-31〜11-01 JST）

**把持・移送・設置・退避まで8/10成功。rawは10/10 complete・既存validator合格。RGB合計8999枚、全試行で欠落推定0。**

通常launchのRGB RELIABLEパッチを使用し、各試行でGazeboを終了・再起動した。基盤commit・教師設定はtg1と同じ。タスク設定SHA-256は `2bc66df9c6746e49d3bf849392949c303a8ad7084bf26c56c2cc21cf1fa05ba7`。試行間で設定・実行コードを変更していないことを全collection Pythonのハッシュで照合した。今回のパッチは未commitのため、PAI HEAD `6cdda3e566bc209e2cd2f174311a5923eb22bad6` に対する差分とファイルハッシュを実行記録に保存している。過去の診断episodeは分母に含めない。

| 試行 | episode ID | 把持・全工程 | raw検証 | RGB枚数 |
| --- | --- | --- | --- | --- |
| 1 | `d254603424d94be3a64ab74277725c49` | 成功 | 合格 | 935 |
| 2 | `4734ce99b9544ed4992c6f993c96d63b` | 成功 | 合格 | 934 |
| 3 | `31d7ce6aaaff4b41b0aae92346ed0477` | 成功 | 合格 | 1420 |
| 4 | `b7c65dad71764151b012831d99dc37c5` | 成功 | 合格 | 936 |
| 5 | `48b022a9b6454594a5a16e7b5bb10d36` | 失敗 | 合格 | 273 |
| 6 | `63c4b5f4169140c28cbb598240b377e6` | 成功 | 合格 | 1415 |
| 7 | `6058a327ca9342899e6ab1ee6ae145c3` | 失敗 | 合格 | 275 |
| 8 | `ac01e72c05014f53a49a77de6d3a86d4` | 成功 | 合格 | 938 |
| 9 | `3e299d2061084d87b539f9fb028ba427` | 成功 | 合格 | 937 |
| 10 | `5771ce706eb940cf92ff646eca052ed5` | 成功 | 合格 | 936 |

失敗5・7はともに下降Cartesian経路がfraction `0.16304347826086957` の部分解になり、実行せず把持前に停止した。tg1にもあった計画上の失敗条件と一致し、RGB通信による停止ではない。失敗も分母に含め、再試行・パラメータ変更なしで10件を完走した。

物理判定は前述のtg1と同じ保持時間・実カップ高さ・傾き・設置誤差の条件を使用。成功8件の最大設置XY誤差0.0750 mm、最大設置Z誤差0.000113 mm、最大最終傾き0.000087度。試行1・10の移送中と退避後のRGB実画像も確認した。RGBの最大source gapは66 ms、最大source ageは240 msで、既存の300 ms閾値は変更していない。

rawは `data/raw/episode_<ID>/`。Git外の実行記録は `outputs/issue1/hikari-reliable-10-20261031-235203/`。`results.json` に全件の判定・実行コードハッシュ・RGB検証統計、`trial-XX/` にlaunch/sequence/start/stop/validatorログと実カップtrace、`successful_episodes.txt` に今回の成功8件の入力一覧を保存した。固定基盤の追跡ファイルは未変更、コンテナは停止済み。10試行での結果であり長時間・並列収集の安定性は未検証。

以下はtg1での検証記録。

確認日: 2026-10-31。対象: tg1、1配置のGazebo教師デモ。

**固定設定10試行で把持・設置・退避まで 9/10 成功。rawは10/10がcomplete・既存validator合格。**

## 条件と判定

- PAI実行コード: `c355b20e60348bd9257e88ec6bad63799e86386c`。測定後は結果文書と移行用Docker・準備スクリプトを追加。教師コード・設定は変更していない。
- 共通基盤: `de410efb3a90348e256015305e80e10ecdcfd972`。元checkout/upstreamは未変更。
- タスク設定SHA-256: `2bc66df9c6746e49d3bf849392949c303a8ad7084bf26c56c2cc21cf1fa05ba7`。試行間で変更せず、自動再試行なし。
- v2.1.1、提供ZIPの指定SHA確認済み。cupは指定Fuel v1、初期pose `(0.6,0,0.2,0,0,pi)`、置き先 `(0.6,0.12,0.2)`。
- 既存PRoot / Ubuntu 22.04.5 / Humble / Fortress、CPU描画。試行ごとにGazeboを再起動して同じ初期状態へ戻した。
- 把持成功: lift終了後の2 sim秒以上、カップ実位置z>=0.25 m、傾き<=30度を維持。Action結果だけでは判定しない。
- 全工程成功: シーケンス終了0、実カップの置き先XY誤差<=20 mm、Z誤差<=10 mm、傾き<=10度。
- 計画用attachは物理拘束ではない。Gazeboの実カップposeで検証し、成功episodeのRGB実画像も確認した。

## 全試行

| 試行 | episode ID | 把持 | 全工程 | raw検証 | 停止理由 |
| --- | --- | --- | --- | --- | --- |
| 1 | `16658baea1b94d0383df9eddea171904` | 成功 | 成功 | 合格 | — |
| 2 | `37779f7e946845b08283520f526e664b` | 失敗 | 失敗 | 合格 | 下降の直進経路が部分解となり、実行せず停止 |
| 3 | `a13e688973554607ad79435a26d79820` | 成功 | 成功 | 合格 | — |
| 4 | `8f375a97d1db4f4683bb49b3f0914335` | 成功 | 成功 | 合格 | — |
| 5 | `e79a1ac49a724372827712ce492f8735` | 成功 | 成功 | 合格 | — |
| 6 | `2facd7d7cd804485adcde4b659218cf1` | 成功 | 成功 | 合格 | — |
| 7 | `6c6d26b828434524b2f7b05367bdc6b5` | 成功 | 成功 | 合格 | — |
| 8 | `93bb7d3a25dd46fbb5dee81c4f1cedbc` | 成功 | 成功 | 合格 | — |
| 9 | `2d44a058e3314cb6b8e834af8d1f91fb` | 成功 | 成功 | 合格 | — |
| 10 | `d26118fc3b1b433aabe6b88536f3791a` | 成功 | 成功 | 合格 | — |

失敗した試行2は、初期接近で正の肘角の解が選ばれ、下降経路がfraction約0.163で打ち切られた。
成功試行は負の肘角の解から下降できていることをrawの実測関節位置で照合した。
部分経路は実行せず、把持へ進んでいない。失敗も分母に含め、条件を変更せず最後まで測定した。

成功9件の最大設置XY誤差は 0.075 mm、最大設置傾きは 0.0001 度。

## データ選択と再現

- raw: `data/raw/episode_<ID>/`。素材・raw・ログはGit外。
- 成功例の入力一覧: `outputs/issue1/successful_episodes.txt`。過去の校正・失敗episodeを混ぜず、上表の成功9件を選ぶ。
- 判定・正確な最終pose・件数・実行版: `outputs/issue1/cartesian-acceptance-10/results.json`。
- 各試行のlaunch、シーケンス、start/stop、validatorログ、cup実位置traceは同ディレクトリの`trial-XX-*`。
- 保存completeとタスク成功は別。全rawが読めることをもって成功扱いにはしない。
- 起動と収録の手順、素材帰属・物性仮定・原因切分けは[実行手順](issue-1-status.md)を参照。

## その他の確認

- 提供ZIP SHA一致、展開27ファイル、mesh10個を確認。原本は変更していない。
- モデル・bringup・MoveItの3packageをビルド。xacro、mesh、controller、MoveIt、実測tip TFを確認。
- 単体テスト8件、ruff、compileall、git diff --checkに合格。
- Cartesian軌道がcontrollerに受理された後にSIGINTを送り、取消完了と後続phase未送信を確認。
- 初期位置は指の端から0.2 mm退避。closeだけ到達許容0.3 mmとし、腕・指のURDF limitsは維持。

## 実行環境と生成速度

| パッケージ | 実測版 |
| --- | --- |
| libignition-gazebo6 | `6.18.0-1~jammy` |
| ros-humble-controller-manager | `2.54.3-1jammy.20261005.213325` |
| ros-humble-gz-ros2-control | `0.7.21-1jammy.20261005.230213` |
| ros-humble-moveit-ros-move-group | `2.5.10-1jammy.20261006.010000` |
| ros-humble-rclcpp | `16.0.21-1jammy.20260907.213403` |
| ros-humble-rclpy | `3.3.22-1jammy.20260907.213431` |
| ros-humble-ros-gz-bridge | `0.244.26-1jammy.20260915.210000` |

成功試行の収録中のsim時間/実時間は平均 0.873。約64 sim秒の収録に約74実秒。
worldの目標real_time_factorは1.0。hikariで描画等を高速化して上限へ届けば短縮の余地はあるが、
実時間より速い大量収集には上限変更を含む別の検証が必要。hikari移行・GPU・学習・実機は今回実行していない。

## hikari移行用の独立ビルド確認

同じtg1のPRootを使い、新規の基盤checkoutで元のinstallをsourceせず全9packageをビルドした。
`collection/setup.sh` の再実行も終了0。生成worldと `collection/ros.sh` で
Gazebo/MoveIt/camera/recorderを起動し、短いrawが既存validatorに合格した。
起動確認episodeは `3942dda34ad749ac828ff7fee66acd20`（全工程の成功率測定には含めない）。

ログ: `outputs/issue1/hikari-portability-build.log`、`hikari-portability-rerun.log`、
`hikari-portability-smoke.log`。初回は実行中の検証用スクリプトを更新したためビルド後に中断し、
更新後のスクリプトで再実行して完了した。起動・収録ログとrawはGit外の
`external/hikari-portability-check/` 内。元checkoutは未変更。
Dockerイメージbuildとhikari上の実行は未検証。[移行手順](hikari-collection.md)を参照。
