# learning (hikari)

raw 変換・学習・推論接続を将来置く場所です。実装・確定した依存・lockfile はまだありません。
LeRobot 用の Python 環境を collection と分け、ROS を source していないシェルで使います。

- 優先候補: native pi05。期限に応じた候補: SmolVLA。
- 変換は公式 LeRobotDataset v3 writer を使う計画。raw の同期・補間・action の意味は未確定です。
- Remote / Async Inference は公式 server/client を調査する計画。LIFTH との adapter や ROS 境界は未実装です。
- 採用版は GPU・OS と最小動作試験を確認してから固定します。現行 main の Python 要件は >=3.12 です。

[環境手順](../docs/environment.md)と[未投稿の候補](../docs/backlog.md)を参照してください。
