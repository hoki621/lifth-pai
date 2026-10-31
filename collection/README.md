# collection (tg1)

教師デモと raw 収録への PAI 固有接続を置く場所です。
Issue #1の素材検査・確認world生成は[手順と未完了事項](../docs/issue-1-status.md)を参照してください。
教師シーケンスは未実装で、追加 Python 依存はありません。
共通基盤の camera / recorder を利用し、重複実装しません。

環境は Ubuntu 22.04 / ROS 2 Humble / Gazebo Fortress。
[環境手順](../docs/environment.md)に従い、LeRobot をこの環境へ導入しません。
現行 recorder は state 8 / command 6。指の command を state やゼロ値で合成しません。
raw の読込みは manifest の仕様・正常完了・画像・時刻・joint 順序と単位を確認してから行います。
