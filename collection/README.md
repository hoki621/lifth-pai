# collection (tg1 / hikari)

教師デモと raw 収録への PAI 固有接続を置く場所です。
Issue #1の素材検査・確認world生成は[手順と原因切分け](../docs/issue-1-status.md)を参照してください。
教師シーケンスと既存収録の起動接続があります。ROS環境と既存のPyYAMLを使います。
共通基盤の camera / recorder を利用し、重複実装しません。

環境は Ubuntu 22.04 / ROS 2 Humble / Gazebo Fortress。
[環境手順](../docs/environment.md)に従い、LeRobot をこの環境へ導入しません。
固定 recorder はschema v2でstate 8軸とarm6・左右各1軸の実commandを独立保存します。指のcommandをstateやゼロ値で合成しません。
raw の読込みは manifest の仕様・正常完了・画像・時刻・joint 順序と単位を確認してから行います。

hikariでのclone後のDocker準備と収録は[移行手順](../docs/hikari-collection.md)を参照してください。
