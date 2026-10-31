# lifth-pai

LIFTH を使う PAI 課題のリポジトリ。Issue #1の素材準備・教師シーケンス・既存収録への接続を実装しています。
**tg1でカップの把持・移送・設置と教師rawの保存・検証を確認しています。hikariでの統合動作は未検証です。**
**hikariでのclone・素材配置・Docker準備・収録は[移行手順](docs/hikari-collection.md)を参照してください。**
固定設定はtg1で9/10成功。[検証結果](docs/issue-1-validation.md)と[原因切分け](docs/issue-1-status.md)を記録しています。

## 構成

| 場所 | 用途 |
| --- | --- |
| `collection/` | tg1 / hikari の収集・教師デモ接続 |
| `learning/` | hikari 側の外部変換・学習・推論接続の作業場所 |
| `configs/` | 実測・検証後に確定する PAI 固有設定 |
| `dependencies.repos` | 共通基盤の取得先と確認済み commit |
| `docs/environment.md` | マシン別の環境分離と将来の準備手順 |
| `docs/backlog.md` | 未投稿の Issue 候補と着手条件 |
| `docs/sources.md` | 公式資料と確認時点の記録 |

## 設計の前提

- 共通機能は [LifthPJT/lifth_arm_gen2](https://github.com/LifthPJT/lifth_arm_gen2) を依存参照します。コードや mesh を転載せず、派生コピーは作りません。
- tg1 は Ubuntu 24.04ホスト上の既存PRoot / Ubuntu 22.04 / ROS 2 Humble / Gazebo Fortress環境を使用します。hikari は Docker の ROS 環境で収集も行い、学習環境と分離します。GPU 型番・OS・接続は未確認です。
- 同じ PAI リポジトリを両機で使い、Python 環境を分けます。tg1 の raw JSONL + PNG を ROS 外の LeRobot 環境で変換する境界を維持します。
- 固定基盤は state 8軸、実commandはarm6 + 左指1 + 右指1の独立時系列をschema v2で収録します。同期・action変換はlearning側の範囲です。
- LeRobot native pi05 を優先候補、締切上の fallback を SmolVLA とします。dataset v3 公式 writer と公式 Remote / Async Inference は将来の利用候補で、採用版・接続方式は未確定です。

## 開発

[環境手順](docs/environment.md)と[開発手順](CONTRIBUTING.md)を参照してください。
機能開発はIssueを起点に進めます。変換、学習、推論はまだ実行していません。

## データと公開

リポジトリは private で開始します。データ、重み、認証情報、個人情報を commit しません。
課題提出時の public GitHub 要件は別途対応します。LICENSE は未決定です。
共通基盤の root LICENSE 未整備を含むコード・mesh の許諾を確認するまで、転載・再配布や公開の判断を進めません。
