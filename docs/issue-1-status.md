# Issue #1: 素材検査と確認world

この変更は [I1 #1](https://github.com/hoki621/lifth-pai/issues/1) の先行部分。
把持・教師シーケンス・正常rawの受入れは未完了。
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
collisionは提供meshを維持し、mesh scaleは変更しない。
Fortress/DART上の接触・摩擦・安定性、把持時のcollision適合は別途実行検証が必要。
摩擦や質量の調整で開口不適合を隠さない。

## 残る依存と作業

参照pin `619bfd2508c869b30ac5954719a82dc5ff6632f7` はモデル選択の基礎のみ。
ローカル基盤 `56441b0cc119ad84f5dad0b5b9b2173d67b94b90` も指はpassive、commandは6軸。
基盤の検証記録 `artifacts/issue-14-validation.md` は追加モデル・独立指・tip・schema更新を未実装と明記している。
提供URDFの配置は完了したが、これだけで必要な制御機能は揃わない。
基盤を変更しないという今回の指示に従い、PAI内へ不足機能を移植しない。

1. #14の必要機能を持つ版を受け入れ、完全SHAとschemaを固定する。
2. 提供モデルの起動・実開口・RGB取得、cupの胴体把持適合を確認する。
3. 固定した置き先と腕初期姿勢、MoveItの障害物・把持物設定を確認する。
4. 実APIを使う短い教師シーケンスと停止・失敗時の確認を実装する。
5. 既存recorderを `data/raw/` 出力で使用し、既存validatorで1正常episodeを検証する。
6. episode IDと配置、人手のタスク成功判定を別に記録する。

仮の指APIや8軸commandを用意して、これらを完了扱いにしない。

## 検査

```bash
python3 -m unittest discover -s collection -p 'test_*.py' -v
git diff --check
```

人工素材だけをテストに用い、提供素材やrawはcommitしない。

今回の実行結果: 上記unittestは4件成功。配置済み素材によるworld生成成功。
既存PRoot / Ubuntu 22.04環境の `ign sdf -k` は `Valid.`、終了コード0。
これはSDF構文検査であり、Gazeboの物理起動・安定性・把持成功を確認した結果ではない。
