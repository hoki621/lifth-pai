# Issue #1 検証結果

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
