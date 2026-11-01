# Issue #5: ランダム配置100成功エピソード

## 視認性の訂正（2026-11-01）

旧100件の形式・物理条件の検査と、VLAに必要な視認性の検査を混同していた。
旧動画は開始時にカップが映らず、置き先も見切れるため、VLA学習用として採用しない。
以下の100件の記録は履歴として保持し、新しい構図の収集結果とは区別する。
ユーザー指定により、旧構図のraw168件・派生dataset・動画と修正中の失敗raw13件は削除済み。
ログ・設定・結果と俯瞰の成功3件は保持し、`outputs/issue5/current/` に成功3件への入口を置く。
削除内容は `outputs/issue5/cleanup-result.json` に記録し、成功raw全ファイルの削除前後hash一致を確認した。

既定設定そのものを次の条件へ変更した。別モードは追加しない。

- D405をPAI生成モデルのbase_linkに固定。光学中心は概ね(0.52, 0, 0.75)m、真下向き。
  既存D405のRGB・calibration・optical TFを共通して使用する。
- 柱を廃止し、上面z=0.10mの連続した平面にカップを置く。
  移動先の胴体中心は(0.50, 0.16)m、緑の16cm四方の領域。
- 中央(0.52, -0.04)・右側(0.50, -0.32)・上側(0.62, 0.02)mの3配置。
  yawは0 / -0.15 / +0.15 rad。開始時からカップと置き先が映る構図とする。
  グリッパーが胴体上縁を通過できる幅ではないため、持ち手を上から挟む。
  カップyawに合わせて把持・設置のTCP位置と姿勢を回す。
  指は40mmの閉指指令、接触時は8mmの未到達を許容（開いたままなら拒否）。
  最終接近と解放時だけ指・カップの計画上の接触を許可し、把持後・退避後・終了時に復元する。
  腕・平面の衝突判定は維持し、物理拘束は追加しない。
  右側は中央の既知姿勢を経由してからCartesianで接近し、旋回軸が後ろ向きの解を選ぶのを避ける。
  把持後の移送は姿勢を保つCartesian経路とし、カップtraceで実際の保持と設置を判定する。
- 把持の高さ条件は「初期平面から5cm以上」にする。旧平面z=0.20mでは従来のz>=0.25mと同値。
  保持2秒・傾き・設置誤差・raw validatorの条件は維持する。

修正の実行記録は `outputs/issue5/view-correction-20261101/` に保存する。
失敗試行もscene/world/source snapshotとともに保持する。新たな100件の収集・学習は実行しない。

3配置ともGazeboで把持・移送・設置に成功し、raw complete・既存validator終了0を確認した。
中央は `revision-10/baseline/trial-01`、右は `revision-13/near/trial-01`、上は `revision-11/yaw_plus/trial-01`。
`pilot-results.json` にscene/world hash、現行3設定との一致、base固定カメラ・同一K・初期joint状態、物理結果を記録する。
カップvisualの外接箱を実Gazebo姿勢から記録Kへ投影し、全trace sampleで画面内に収まることを確認した。
緑の領域も画面内。これは幾何学的な見切れの検査であり、腕による遮蔽はRGB抽出画像で別途確認する。

| 配置 | RGB frame | 最終XY誤差 | 保持中の最大傾き |
| --- | --- | --- | --- |
| 中央 | 757 | 2.76 mm | 0.29度 |
| 右 | 975 | 2.11 mm | 5.42度 |
| 上 | 916 | 2.63 mm | 0.48度 |

確認用動画は `previews/01-baseline.mp4`、`02-near.mp4`、`03-yaw_plus.mp4`。
`three-starts.jpg` と各10フレームの確認シート、対応episode情報を `three-patterns.zip` にまとめる。
MP4はraw RGBのsim時刻を保持し、全フレームをdecodeして枚数と最終時刻を照合する。
成功3件のrawは維持する。旧構図データと失敗rawは上記の削除指示に従って整理済み。
3パターンの確認結果を100件の再収集完了とは扱わない。



## 新しい100件を集める前の残件

現在のランダム生成はbaseline周辺のX±2cm・Y±3cmであり、画面全体に分散する収集範囲へは未変更。
新しい100件は旧runを再開せず、分布と視認性の条件を決めて別の出力先へ収集する。

VLAの入力はRGB1視点と関節状態8軸、出力は絶対関節位置8軸であり、手元視点を必須としない。
俯瞰視点の採用はユーザー合意済み。ただしこの3件は教師の物理成功であり、VLA性能の実証ではない。
推論adapterは指の接触許容差を指定せず既定0.1mmを使う一方、教師の40mm閉指では8mmを許容する。
成功3件でも保持中に約0.7〜6.3mmの指令未到達があり、推論側で正常な接触を失敗扱いし得る。
この不整合は未修正で、推論側の接触処理を整合させる必要がある。100件での性能は保証しない。

## 旧100件の履歴

2026-11-01、hikariのGazeboで本収集・LeRobot v3変換・全フレーム再読込みまで完了。
168試行から成功100件を採用し、68件を理由付きで除外した。
アーム設置・初期状態とカメラ設定を固定し、カップのX/Y/yawだけをランダム化した。

| 出力 | 成功episode | frame |
| --- | --- | --- |
| `dataset/train/` | 90 | 95,480 |
| `dataset/validation/` | 10 | 10,697 |
| 合計 | 100 | 106,177 |

実行rootは `outputs/issue5/random-20261101/`、dataset本体は約3.0 GiB。
`final-check-command.json` と `convert-command.json` は終了0。
`dataset/conversion_report.json` と `completion-audit.json` はcomplete。
公式readerで全106,177 frameのRGB/state/action/task一致とraw hash不変を確認した。
独立の `collection-audit.json` で全100件の物理条件・固定条件・配置・素材を照合し、
`csv-audit.json` で `episodes.csv` 全168行と最終manifestの対応を確認した。
本変換の採用入力は `final-acceptance.json`。個別 `converter-selection.json` は試験時点の入力として保持する。

raw・dataset・ログ・実行source snapshotはGit外に保存する。今回の作業では学習・実機操作は行っていない。
以下は手順と各段階の実行記録。

ユーザー指定: アームの設置・初期姿勢とカメラ位置・姿勢・画角を固定し、
カップ位置・向きにランダムな多様性を持たせる。成功rawからLeRobot形式100件を作る。
train 90件、validation 10件とし、heldoutは別途配置だけ予約する。

## 実装と確認順

1. `prepare_cup_collection.random_scene` が既存baseline周辺のX±0.02 m、Y±0.03 m、
   yaw±30度を一様乱数で生成する。Z、roll/pitch、質量・摩擦・指令値・TCP姿勢は固定。
   胴体中心の変化を把持側の4 waypointへ加算し、置き先の胴体中心は既存値を保つ。
   カップyawは移送中に変更しない。支持台は既存world生成処理で配置する。
2. 既存 `prepare_cup_trial` でscene/world/hash/版を保存する。
3. `run_cup_trial.py` は既存の実験用runnerを整理した入口。
   launch再起動、既存start/teacher/stop/validator、実Gazebo cup traceを保存する。
   recorder/validatorやROS APIは再実装しない。
4. `collect_cups.py` は既存Docker imageとbuildを用い、domain/partitionを分けた2環境で収集する。
   まず各3件の少量確認。その画像とtraceを確認してから各50件へ進める。
   失敗は記録し、同じsplitの別乱数配置で補充する。各workerの10成功ごとに1件validation。
5. 物理条件合格だけではacceptedにしない。画像確認後に採否を確定し、
   `{version: 1, episodes: [...]}` の既存採否manifestを生成する。
6. `learning/convert_raw.py --check-only` と公式writer/readbackを使い、
   90/10件のLeRobot dataset、全frame照合、raw hash不変、split非混入を確認する。

## 起動

追加インストールをせず、準備済み `lifth-pai-collection:humble` と
`external/lifth_arm_gen2/install` を使う。PAI rootから:

```bash
python3 collection/collect_cups.py outputs/issue5/RUN --per-worker 3
# 少量確認後、同じrootで再開
python3 collection/collect_cups.py outputs/issue5/RUN --per-worker 50
```

収集先はhikari。ユーザーの継続実行指示により、このマシンで収集から変換まで行う。
Gitにはコードと手順だけを置く。raw・scene snapshot・結果・画像・datasetはoutputs内のGit外。
物理成功条件は従来どおり、保持2 sim秒以上・旧平面ではz>=0.25 m・傾き<=30度、
設置XY誤差<=20 mm・Z誤差<=10 mm・傾き<=10度、教師終了0。
raw complete・upstream validator合格も必須。

## 少量確認（2026-11-01 hikari）

`outputs/issue5/random-20261101/` で8試行、成功6件・失敗2件。
成功6件すべてraw complete、upstream validator終了0、RGB目視・実cup trace確認済み。
既存converterのcheck-onlyは6件すべて合格（6,965 frame）。
`pilot-acceptance.json` と `pilot-converter-check.json` に保存。
失敗は移送Cartesian経路不成立1件、教師終了0だが物理転倒・飛散1件。
失敗は採用せず、閾値・乱数範囲を変更しない。
この6件を引き継ぎ、同じrootで各worker50件へ再開する。
この少量確認時点ではLeRobot writer/readbackと100件の完了は未確認だった。最終結果は冒頭を参照。

## 採用manifestとLeRobot出力

画像確認は `learning/.venv/bin/python collection/preview_cup_trials.py outputs/issue5/RUN`
で作るstart/held/final画像と元PNGを使い、確認者・理由・画像hashを
各trialの `trial-01/visual-review.json` へ記録する。画像を確認した試行だけ
`trial.json` の `task_success=true, accepted=true, exclusion_reason=""` にする。

全件確認後、次を実行する。finalizeは90/10件、物理/raw合格、画像のhash・確認記録、
episodeと配置の重複、heldoutとの混入を検査し、未達ならmanifestを作らない。
converterがscene/world/rawの整合・既存validator・時刻対応を再検査する。

```bash
python3 collection/finalize_cup_selection.py outputs/issue5/RUN
learning/.venv/bin/python learning/convert_raw.py \
  outputs/issue5/RUN/final-acceptance.json outputs/issue5/RUN/dataset --check-only
learning/.venv/bin/python learning/convert_raw.py \
  outputs/issue5/RUN/final-acceptance.json outputs/issue5/RUN/dataset
```

最終出力は `dataset/train/` と `dataset/validation/`。
`dataset/conversion_report.json` の `status=complete` と件数、公式readerの全frame照合、
画像/state/action/task一致・raw hash不変を完了の根拠にする。

画像を実際に確認した後の採用記録は、既存記録の上書きを拒否する次の入口でも行える。
物理失敗・raw不正・画像hash不一致は受け付けない。画像を見る作業自体は自動化しない。

```bash
python3 collection/record_cup_review.py outputs/issue5/RUN/worker-N/placement-NNNN/trial.json \
  --observer NAME --reason '実際に画像で確認した内容'
```

## ランダム配置での公式writer確認

本収集中、採用済みtrain 1件（worker-1/placement-0002）とvalidation 1件
（worker-1/placement-0016）で既存converterを実行し、終了0を確認した。
`writer-smoke-dataset/conversion_report.json` はcomplete、train 943 frame、
validation 959 frame。全1,902 frameの公式readerによる画像/state/action/task一致、
raw hash不変を確認した。`writer-smoke-receipt.json` にcommandと終了結果を保存。
これは2件の確認用出力であり、最終100件の完成とは扱わない。

## converter拒否と補充

本収集中、worker-1/placement-0040は物理成功・raw complete・upstream validator合格だが、
既存converterがframe 378のarm/左右指command stamp skewで拒否した。
閾値は変更せず、`trial.json`に`conversion_error`と除外理由を残し、採用から外した。
収集中の初回collectorは停止せず、その終了後に同じrootで再開して補充する。
再開時はconverter拒否を成功数から除き、既存splitの実件数に合わせて45/5件を満たす。
初回collectorのソースはrun rootの`collector-first-pass.py`に保持する。

## 本収集の採用確定と独立監査

初回166試行と補充2試行、計168試行から、train 90件・validation 10件の100件を採用。
67件のタスク等の失敗と、上記command skew拒否1件を除外した。
補充はworker-1/placement-0080が失敗、0081が成功。補充後の実split件数を確認した。
`final-acceptance.json` と全168行の `episodes.csv` を確定した。

`collection-audit.json` は全100件のimmutable scene/world、乱数seedからの配置再生成、
固定のbase world・camera calibration、置き先胴体中心、core実行コード、
model/asset版・URDF構造、実Gazebo cup traceから再計算した保持・傾き・設置条件、
画像確認記録と元PNG hash、heldout非混入を検査してcompleteとなった。
保持時間の最小は5.237 sim秒、最終XY誤差の最大は約0.0786 mm。
これはGazebo教師デモの実測であり、実機や学習済みpolicyの性能ではない。

初回の監査はURDFのバイト一致を要求して失敗した。差分を調べ、全100件の差が
backendの生成controller YAMLパス `/tmp/lifth_controllers_*/controllers.yaml` のみと判明した。
固定基盤の `model_signature` も生成YAMLパスと形状/frameを区別する。
監査ではこの1要素だけを正規化し、その他のURDF全構造の一致と、各rawの実URDF SHAを確認した。
raw・manifestのhashは変更していない。初回失敗は `audit-initial.log` に保持する。
配置seedはPython配置乱数用であり、Gazeboの物理乱数seed指定とは扱わない。

全件の既存converter検査と公式writer/readbackは、run rootの `convert_all.py` から実行する。
実command、thread数・offline設定、開始終了時刻、終了コードを `*-command.json` に記録する。
最終100件のLeRobot出力の完了は `dataset/conversion_report.json` と実終了結果で判断する。
