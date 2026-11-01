# collection (tg1 / hikari)

教師デモと raw 収録への PAI 固有接続を置く場所です。
Issue #1の素材検査・確認world生成は[手順と原因切分け](../docs/issue-1-status.md)を参照してください。
教師シーケンスと既存収録の起動接続があります。ROS環境と既存のPyYAMLを使います。
共通基盤の camera / recorder を利用し、重複実装しません。
`cup_demo.launch.py` は `reliable_rgb_recorder.py` を介し、固定基盤recorderのRGB購読だけをRELIABLEにします。
他streamは従来のBEST_EFFORTを維持し、実際のRGB QoSはrawの `provenance.settings.qos.rgb` に記録します。

環境は Ubuntu 22.04 / ROS 2 Humble / Gazebo Fortress。
[環境手順](../docs/environment.md)に従い、LeRobot をこの環境へ導入しません。
固定 recorder はschema v2でstate 8軸とarm6・左右各1軸の実commandを独立保存します。指のcommandをstateやゼロ値で合成しません。
raw の読込みは manifest の仕様・正常完了・画像・時刻・joint 順序と単位を確認してから行います。

hikariでのclone後のDocker準備と収録は[移行手順](../docs/hikari-collection.md)を参照してください。

ランダム配置で成功100件を収集しLeRobot v3へ渡す手順・実行結果は[Issue #5の記録](../docs/issue-5-collection.md)を参照してください。

現在の既定カメラは、PAI生成モデルの `base_link` に固定した俯瞰配置です。
`setup.sh` は既存の生成済みモデルにもこの配置を適用します（変更後は既存手順でbuild）。
RGBと光学TFは同じD405モデルから生成し、提供ZIPと固定基盤の追跡ファイルは変更しません。
`prepare_cup_world.py` は連続した平面と緑の16 cm四方の置き先を生成します。
`baseline` / `near` / `yaw_plus` はそれぞれ画面中央・右側・上側の3候補です。
旧100件は視認性不足のためVLA学習用として採用しません。

収集raw・変換dataset・確認動画は `outputs/datasets/<run>/` に保存します。
現在の成功3件は `outputs/datasets/cup-pilot-20261101/`、入口は `outputs/datasets/current/`。
新しい100件の収集先は `outputs/datasets/cup-100-RUN/` とし、runごとに分けます。
