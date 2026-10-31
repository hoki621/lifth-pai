# Issue #1: 素材検査と確認world

この変更は [I1 #1](https://github.com/hoki621/lifth-pai/issues/1) の収集接続。
教師シーケンスと診断rawを実装・検証し、固定設定の成功率と途中取消を確認している。
基盤は既存 `lifth_arm_gen2` を参照し、変更・転載しない。

## 素材検査

PAIルートで、ROS不要のsystem Pythonから実行する。

```bash
python3 collection/check_robot_model.py external/robot_models
```

Issue指定のZIP SHA-256と、展開ファイルの全バイト、package名、mesh参照を確認する。
tg1に配置された提供物で27ファイル・mesh10個が一致した。
追加ファイルの有無やxacro展開・制御適合・実開口の検査は含まない。
提供packageのlicenseはTODOであり、ZIP・meshはGitへ追加しない。

## カップの確認world

カップは本人が `external/assets/` に配置済み。追加ダウンロードしない。
採用元は [GoogleResearch / Threshold_Porcelain_Coffee_Mug_All_Over_Bead_White](https://app.gazebosim.org/GoogleResearch/fuel/models/Threshold_Porcelain_Coffee_Mug_All_Over_Bead_White)、Fuel version 1。
Copyright 2020 Google LLC、CC BY 4.0。素材自体は転載しない。
提供ZIP SHA-256: `dc34f175364540e239ae74f71e5b951a48aa99ccb48aaaf8c8c11771c5c56aa1`。
OBJ外接箱は約130.740 × 96.522 × 114.624 mm。これは把持高さの胴体径ではない。

```bash
python3 collection/prepare_cup_world.py \
  /nfs/hdd/lifth/lifth_arm_gen2/src/lifth_bringup/worlds/arm_camera.sdf \
  external/assets configs/cup_scene.json outputs/issue1/cup_world.sdf
```

既存camera worldを読み、ローカル生成物にcupと床を加える。基盤のファイルは変更しない。
生成worldは既存bringupの `world:=` 差替え口用で、単独ではロボットを起動しない。
URIは生成機上の絶対パスなのでhikariでは素材を置いて再生成する。
設定のposeはworld基準のm・radで、最後のyawを変更して持ち手方向を調整する。
初期値は確認用配置であり、腕からの到達・把持姿勢・置き先は未検証。

物性は実測ではなく仮定: 質量0.3 kg、摩擦係数0.8、OBJ外接箱の中心と一様箱慣性。
visualは提供meshを維持し、scaleは変更しない。collisionは高さ別外形幅に基づく6段の円柱と持ち手の箱で近似する。
低い胴体を横から把持できるよう、初期位置と置き先には半径28 mmの細い支持台を配置する。
これらの衝突形状と物性はPAI固有の仮定であり、実物の内部形状や持ち手の穴は再現しない。
Fortress/DART上の接触・摩擦・安定性、把持時のcollision適合は別途実行検証が必要。
摩擦や質量の調整で開口不適合を隠さない。

## モデル登録と実行環境

基盤候補SHAは `de410efb3a90348e256015305e80e10ecdcfd972`（PR #20）。
左右指制御・tip TF・raw schema v2が実装済み。v2.1.1の登録だけをPAIのexternal checkoutに追加する許可を受領した。
元の `/nfs/hdd/lifth/lifth_arm_gen2` とupstreamは変更しない。

```bash
# dependencies.reposで固定した版の独立checkoutをexternal/lifth_arm_gen2に用意してから実行。
python3 collection/prepare_robot_model.py external/lifth_arm_gen2 external/robot_models
```

モデル固有のdescription、tip frame、YAML、MoveIt設定だけを生成する。
生成先がPAIのexternal外、基盤SHA違い、提供ZIP不一致、既存生成先ありの場合は拒否する。
提供物の原本は変更しない。新たなモデル用tipは提供STLの最大+Z面の面積重心。
D405は基盤のmacroを参照する。光学原点は暫定値で実機校正済みとは扱わない。
提供物のGazebo拡張には基盤と同じinclude_gazebo切替を加え、wrapperとの二重設定を避ける。
初期・開放指位置は開側端から0.2 mm退避する（後述の対照試験）。
生成記録はexternalのdescription内 `pai-model-source.json` に残る。

ROS実行環境は既存PRoot / Ubuntu 22.04.5 / Python 3.10.12、Humble / Fortress 6.18.0。
ホストはUbuntu 24.04.4。CPU描画には既存の空/dev/dri bindとMesaを使用する。
既存基盤のinstallをunderlayにして、モデル・bringup・MoveItの3packageをPAI外部checkout内でビルドした。
通常の独立workspaceなら基盤のbuild.shを使う。いずれもROS環境でビルドし、そのinstallをsourceする。

```bash
# ROS環境で実行（PAIルート）。起動のみで運動は始めない。
ros2 launch collection/cup_demo.launch.py
# 別シェルで同じROS setup、domain、Gazebo partitionを使用する。
python3 collection/start_episode.py
python3 collection/cup_sequence.py configs/cup_scene.json
# シーケンスの成否によらず明示終了。completeとタスク成功は区別する。
ros2 service call /lifth/episode/stop std_srvs/srv/Trigger '{}'
python3 -m lifth_dataset.validate data/raw/episode_ID
```

起動接続は既存モデル検査、Gazebo bringup、MoveIt、MoveToPose、D405、recorderを使用する。
全ノードに同じカメラ付きモデル記述を使用し、robot_descriptionの配信元はRSPに限定する。
MoveItがカメラなし記述を同じtopicへ配信し、spawnがそれを取得する競合を避ける。
教師設定はworld基準の絶対値なので、cup位置・yawを変えるときはstepsとplace_poseも照合する。
TFとcup真値、教師phaseは教師生成・検証用であり、policy入力へは渡さない。

## 指停止の原因切分け

目標許容値は基盤の0.1 mmを維持して比較した。

| 条件 | 同じ指位置指令の結果 |
| --- | --- |
| 初期直立、右 -5 mm | 成功、実測 -5 mm |
| 把持姿勢、右 -1.8 mm | 実測ほぼ0 mmでtimeout |
| 把持姿勢のままcupを除去、左 +1.8 mm | 同じ停止 |
| さらに支持台を除去、左 +1.8 mm | 同じ停止 |
| アームを直立へ戻す、左 +1.8 mm | 成功 |
| 物体なし、手首のみ90度・60度へ回転、開側端0 mmから右を動かす | 停止 |
| 回転前に両指を開側端から1 mm離し、90度で両指を3 mmへ | 成功 |
| 両指を開側端から0.2 mm離し、直立→90度後に両指を1.5 mmへ | 成功 |

cupとの接触を原因とした当初の推測は、この対照試験で否定された。
再現条件は、開側の可動域端0 mmでアーム姿勢を変えた後の指操作。
内部の物理エンジン実装上の原因までは断定していない。
対処はモデル固有の初期位置とopen/releaseを `[0.0002, -0.0002]` mにし、端を避けること。
0.2 mmは既存の到達許容値0.1 mmの2倍。許容値、joint limits、摩擦、質量は緩めていない。
閉じ目標1.5 mmは、meshからの開口約88.9 mmと把持高さのcollision径86 mmから算出した値。

対照試験のログはGit外の `outputs/issue1/` にある。
`right-freeair-diagnosis.log`、`left-without-cup.log`、`left-without-support.log`、
`left-upright-after.log`、`fingers-wrist-90.log`、`fingers-wrist-60.log`、
`backoff-after.log`、`backoff-02-after.log` を対応させて確認できる。
一時的な接触センサーによる診断変更は取り除いており、基盤本体への変更はない。

## 検証中の事項

- 提供モデルのxacro・mesh・controller・MoveIt整合検査、起動、実測tip TF取得は成功。
- RGB約15 Hz、state約100 Hzの同時受信を確認。接近姿勢のAction成功と実測到達も確認。
- 初期の広い床は固定基部と重なり、物理計算とstate受信を遅延させた。支持台に変更。
- 遠い下降目標はMoveItの後処理後の衝突検査で拒否された。失敗後の把持指令は送られていない。
- 一時停止せずに開始したrawは、開始処理中の滞留入力が300 msを超えてincompleteになった。
  Gazeboを一時停止してstartを呼び、応答後に再開した診断rawはcompleteとなりvalidatorに合格した。
- 端から0.2 mm退避した設定で把持・約18 cmの持上げ・移送・設置を確認した。
  カップ実位置は置き先から約2 mm以内で直立。固定設定10試行と途中取消は引き続き検証する。

保存completeはタスク成功とは別であり、診断rawの合格だけでI1完了としない。

## 検査

```bash
python3 -m unittest discover -s collection -p 'test_*.py' -v
git diff --check
```

人工素材だけをテストに用い、提供素材やrawはcommitしない。

今回の実行結果: 上記unittestは4件成功。配置済み素材によるworld生成成功。
既存PRoot / Ubuntu 22.04環境の `ign sdf -k` は `Valid.`、終了コード0。
これはSDF構文検査であり、Gazeboの物理起動・安定性・把持成功を確認した結果ではない。
