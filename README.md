# lifth-pai

LIFTH を使う PAI 課題のリポジトリ。Issue #1の素材準備・教師シーケンス・既存収録への接続に加え、
[Issue #2・#3・#4の計画](docs/issue-234-plan.md)に従って変換・学習準備・推論接続・統合検証手順を実装中です。
**tg1とhikariでカップの把持・移送・設置と教師rawの保存・検証を確認しています。**
**hikariでのclone・素材配置・Docker準備・収録は[移行手順](docs/hikari-collection.md)を参照してください。**
固定設定はtg1で9/10、hikariの通常launchで8/10成功。hikariのrawは10/10 complete・既存validator合格です。
[検証結果](docs/issue-1-validation.md)と[原因切分け](docs/issue-1-status.md)を記録しています。

Issue #5ではカップ位置・yawをランダム化した成功100件をhikariで収集し、LeRobot v3へ変換しました。
train 90件・validation 10件、全106,177 frameの公式reader照合を確認済みです。
ただし旧動画は開始時のカップ・置き先の視認性を満たさず、VLA学習用として採用しません。
現在の既定設定は固定俯瞰カメラ・連続した平面・緑の正方形の置き先へ修正しています。
旧構図データと失敗rawは削除済みで、現在有効な教師デモ3件の入口はhikariの `outputs/datasets/current/` です。
収集raw・変換dataset・確認動画の保存先は `outputs/datasets/<run>/` に統一します。
[収集・変換の手順と結果](docs/issue-5-collection.md)を参照してください。

## 構成

| 場所 | 用途 |
| --- | --- |
| `collection/` | tg1 / hikari の収集・教師デモ接続 |
| `learning/` | hikari 側の外部変換・学習・推論接続の作業場所 |
| `configs/` | PAI契約と検証待ちの候補設定 |
| `dependencies.repos` | 共通基盤の取得先と確認済み commit |
| `docs/environment.md` | マシン別の環境分離と将来の準備手順 |
| `docs/backlog.md` | 未投稿の Issue 候補と着手条件 |
| `docs/sources.md` | 公式資料と確認時点の記録 |

## 設計の前提

- 共通機能は [LifthPJT/lifth_arm_gen2](https://github.com/LifthPJT/lifth_arm_gen2) を依存参照します。コードや mesh を転載せず、派生コピーは作りません。
- tg1 は Ubuntu 24.04ホスト上の既存PRoot / Ubuntu 22.04 / ROS 2 Humble / Gazebo Fortress環境を使用します。hikari は Docker の ROS 環境とML環境を分離します。Issue #4の実験でRTX A6000 48 GiB×3、driver 580.178.04と専用ML環境でのCUDA動作を確認しました。
- 同じ PAI リポジトリを両機で使い、Python 環境を分けます。tg1 の raw JSONL + PNG を ROS 外の LeRobot 環境で変換する境界を維持します。
- 固定基盤は state 8軸、実commandはarm6 + 左指1 + 右指1の独立時系列をschema v2で収録します。同期・action変換はlearning側の範囲です。
- LeRobot native pi05 を優先候補、fallback を SmolVLA とします。Issue #2・#3では固定LeRobotのv3公式writer・trainer・同期推論を使う計画です。候補版と実行前の確認事項は[実装計画](docs/issue-234-plan.md)を参照してください。

## 開発

[環境手順](docs/environment.md)と[開発手順](CONTRIBUTING.md)を参照してください。
機能開発はIssueを起点に進めます。[配置・変換・学習準備](learning/README.md)と
[一周検証の手順](docs/issue-4-validation.md)を用意しています。
Issue #4の実験で3配置の教師収録、公式writer往復、GPUでの10 step学習・保存、
checkpointの別プロセス再読込みとvalidation forwardを確認しました。
ユーザーの指定により今回は学習完了までで区切り、実policyによるGazebo適用は後回しとしています。

## データと公開

リポジトリは private で開始します。データ、重み、認証情報、個人情報を commit しません。
課題提出時の public GitHub 要件は別途対応します。LICENSE は未決定です。
共通基盤の root LICENSE 未整備を含むコード・mesh の許諾を確認するまで、転載・再配布や公開の判断を進めません。
