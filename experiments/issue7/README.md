# Issue 7 のGazebo試験で使用した処理

このディレクトリは、課題実験のうち通常の1点推論から変更した部分を残すためのものです。共通adapterのコピーは置かず、差分と観察用センサーの追加処理を記録しています。**単独で完全な試験環境を構築・実行するパッケージではありません。** 元のデータ、生成world、モデル重み、起動用の一時スクリプト、試験結果はGitに含まれていません。

- `continuous_adapter.patch`: `collection/policy_adapter.py` の1点のFollowJointTrajectoryを、10点の連続軌道に変更した実験差分。速度は現在位置→最初の点と各点間を検査します。既定の1点adapterを変更する差分であり、自動適用されません。
- `continuous_policy.py`: 保存済み重みと学習統計を読み、50点の予測の先頭10点を1回の観測から送った実験スクリプト。引数に実験caseディレクトリを取り、`case.json` の `model`、`stage`、`checkpoint`、`base_weights`、`port` を参照します。actionの記録先は同ディレクトリです。
- `sim_finger_adapter.py`: ソフトウェア上の指の位置範囲検査のみを外すGazebo試験用wrapper。腕の位置・速度検査とGazeboの物理的な指の範囲は残します。指controllerの位置範囲検査を別途無効化し、到達許容差を2 mmにした上で試しました。このwrapperだけではcontrollerの設定は変わりません。
- `wrist_sensor.py`: 既存の俯瞰D405を残し、EE_1に観察専用D405 sensorを追加するURDF変換。別途 `/lifth/inspection_wrist_d405/image` のROS bridgeと画像保存が必要です。固有の光学TFは生成せず、VLAへの入力には使っていません。

点間隔は `trajectory_duration_ns=66666667`、10点ごとに観測・推論して50軌道を実行しました。学習前はbase weightsをstrict loadし、学習後と同じtrain統計を用いました。試験の起動は、ローカルのignored `outputs/` に生成したlaunch・観測・動画保存スクリプトを用いました。これらは環境固有のためここに含めておらず、以下の検証だけでGazebo試験が再現できることは意味しません。

実験差分が現在の共通adapterに適用可能か、および手元センサーのXML変換は次で確認できます。

```bash
git apply --check experiments/issue7/continuous_adapter.patch
(cd experiments/issue7 && python3 -m unittest test_wrist_sensor.py)
```

`git apply --check` はソースを変更しません。学習や実機の制御も開始しません。
