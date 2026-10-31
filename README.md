# lifth-pai

LIFTH を使う PAI 課題のリポジトリ。Issue #1の素材検査・確認world生成を実装しています。
**把持・教師収録は未実装、PAIとしてのtg1 / hikari統合動作は未検証です。**
現状と手順は[Issue #1の記録](docs/issue-1-status.md)を参照してください。

## 構成

| 場所 | 用途 |
| --- | --- |
| `collection/` | tg1 側の収集・教師デモ接続の作業場所 |
| `learning/` | hikari 側の外部変換・学習・推論接続の作業場所 |
| `configs/` | 実測・検証後に確定する PAI 固有設定 |
| `dependencies.repos` | 共通基盤の取得先と確認済み commit |
| `docs/environment.md` | マシン別の環境分離と将来の準備手順 |
| `docs/backlog.md` | 未投稿の Issue 候補と着手条件 |
| `docs/sources.md` | 公式資料と確認時点の記録 |

## 設計の前提

- 共通機能は [LifthPJT/lifth_arm_gen2](https://github.com/LifthPJT/lifth_arm_gen2) を依存参照します。コードや mesh を転載せず、派生コピーは作りません。
- tg1 は GPU なしの Ubuntu 22.04 / ROS 2 Humble / Gazebo Fortress 実行機。hikari は学習・推論用 GPU 機ですが、GPU 型番・OS・接続は未確認です。
- 同じ PAI リポジトリを両機で使い、Python 環境を分けます。tg1 の raw JSONL + PNG を ROS 外の LeRobot 環境で変換する境界を維持します。
- 現行基盤は state 8軸、command 6軸。state/action とも arm6 + finger2 の8軸は #14 に依存する計画案です。架空の topic・API・joint 設定は用意しません。
- LeRobot native pi05 を優先候補、締切上の fallback を SmolVLA とします。dataset v3 公式 writer と公式 Remote / Async Inference は将来の利用候補で、採用版・接続方式は未確定です。

## 開発

[環境手順](docs/environment.md)と[開発手順](CONTRIBUTING.md)を参照してください。
機能開発はIssueを起点に進めます。収録、変換、学習、推論はまだ実行していません。

## データと公開

リポジトリは private で開始します。データ、重み、認証情報、個人情報を commit しません。
課題提出時の public GitHub 要件は別途対応します。LICENSE は未決定です。
共通基盤の root LICENSE 未整備を含むコード・mesh の許諾を確認するまで、転載・再配布や公開の判断を進めません。
