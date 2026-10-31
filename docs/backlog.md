# Issue 候補（未投稿・未実装）

実際の Issue 作成は別途依頼後に行います。以下は優先順のたたき台です。

| 候補 | 着手条件 | 最小の完了条件 |
| --- | --- | --- |
| 環境・版の確定 | hikari の OS / GPU / driver、tg1 の既存環境を確認 | Python / LeRobot commit / Torch 等を記録し、最小 import・dataset writer 試験に合格 |
| cup / world の準備 | 共通基盤でモデルが選択可能、素材の許諾確認 | Fortress で物体・座標・衝突・初期姿勢を再現、起動手順を記録 |
| 教師デモと収集接続 | 共通基盤 #14 の必要機能、#15 / #16 の固定版仕様確認 | 正常・異常 episode と state / 実際の command / 画像 / 時刻を検証 |
| raw → LeRobot v3 外部変換 | schema と action の意味・同期方針、採用版を確定 | 公式 writer で短い正常データを生成・再読込み、不完全 raw を拒否 |
| pi05 最小学習・評価 | GPU 適合、利用許諾、変換データ確認 | 最小試行を再現し、設定・指標・重みの保存先を記録。期限で SmolVLA を再評価 |
| Remote / Async Inference 接続 | 採用版 API、ROS とのプロセス境界、モデル契約を確定 | mock / sim で観測と指令、時刻・単位、切断・古い出力時の停止を検証 |

## 共通基盤の状況（2026-10-31 API / ソース確認）

- [#14](https://github.com/LifthPJT/lifth_arm_gen2/issues/14): OPEN。モデル設定による URDF 切替、左右独立グリッパー位置指令、指先 TF は実装待ちとして扱う。
- [#15](https://github.com/LifthPJT/lifth_arm_gen2/issues/15): CLOSED。camera 基盤。PAI 対象環境での検証は未実施。
- [#16](https://github.com/LifthPJT/lifth_arm_gen2/issues/16): OPEN。ただし確認 commit に recorder / schema / validator と README が存在する。Issue の open/closed とコードの存在を区別する。実行検証の追認はしていない。

state / action とも8軸は将来案です。現状の state 8 / command 6 を変換側で勝手に揃えません。
公開提出前には LICENSE・外部素材・秘密情報・履歴の確認が必要です。今回は public 化しません。
