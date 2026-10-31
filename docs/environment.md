# 環境準備

2026-10-31 時点。tg1でI1のモデル・教師収録接続を検証しています。
実行手順と確認済み範囲は[Issue #1の記録](issue-1-status.md)を参照してください。
以下は再配置時の手順も含み、hikariではまだ実行していません。
版を確定していない LeRobot の install コマンドはまだ用意しません。

## 配置と分離

| 環境 | 担当 | Python / 依存 |
| --- | --- | --- |
| Mac | 文書・Git・設定準備 | ROS / CUDA / LeRobot は不要 |
| tg1 | Fortress / camera / raw 収録 | 既存 Humble の Ubuntu Python（22.04 標準は3.10）。ROS の apt 依存を利用 |
| hikari | 外部変換 / 学習 / 推論 | OS・GPU・driver を確認後、LeRobot 専用 venv。確認した main は Python >=3.12 |

両機で `git clone https://github.com/hoki621/lifth-pai.git` を使う想定です。
private repo の認証は各機の認証機構で設定し、token を URL やファイルに埋め込みません。
収録データは Git の外で管理します。転送先・手段はまだ決めません。

## 共通基盤の取得

`dependencies.repos` は vcstool 形式です。vcstool が導入済みなら PAI repo 直下で:

```bash
mkdir -p external
vcs import external < dependencies.repos
git -C external/lifth_arm_gen2 rev-parse HEAD
```

期待 commit は `de410efb3a90348e256015305e80e10ecdcfd972` です。
上記は依存取得だけを行い、ROS のビルドや起動は行いません。
`external/` は Git 対象外。LeRobot は版選定前なので manifest に含めません。

## tg1

tg1はUbuntu 24.04ホスト上の既存PRoot / Ubuntu 22.04.5 / Humble / Fortress環境を使用します。
元のlifth_arm_gen2を変更せず、PAIのexternal checkoutへモデル固有設定を追加します。
既存の ROS / Fortress 環境を再インストールしません。
まず Ubuntu 版、`python3 --version`、ROS distro と既存 workspace の overlay を確認します。
共通基盤の固定 commit の README・package README にある build / rosdep 手順を確認して使います。
Python 開発用 venv が必要になったときだけ、同 README の方式で ROS の system packages を利用します:

```bash
# PAI repo 直下、tg1 の別シェルで実行
source /opt/ros/humble/setup.bash
python3 -m venv --system-site-packages collection/.venv
source collection/.venv/bin/activate
python --version
```

この venv に LeRobot / CUDA / 学習依存を入れません。collection の追加依存は現時点でありません。
基盤の dev 依存・build 出力は基盤ディレクトリ内で管理します。
録画手順や topic は固定 commit の `src/lifth_dataset/README.md` を正本とし、PAI で推測の起動コマンドを作りません。

## hikari（将来実施）

ROS を source していない新しいシェルを使い、OS・GPU 型番・VRAM・driver・Python を記録します。
GPU は今は起動せず、確認のための SSH も行いません。
採用 LeRobot commit と対応 Python / PyTorch / CUDA を選び、最小動作試験後に依存を固定します。
例えば Python 3.12 を採用し、既にインストール済みの場合の空の環境作成は:

```bash
# PAI repo 直下、hikari の別シェルで実行
python3.12 -m venv learning/.venv
source learning/.venv/bin/activate
python --version
```

pi05 の公式 optional dependency は `pi`、SmolVLA は `smolvla`。
具体的な install は採用版の公式資料に従って別作業で実施します。今回は重い依存を取得しません。
Hub 認証や gated model のライセンス同意は必要になった段階で本人が行います。

## raw → dataset 境界

固定基盤の recorder は schema_version 2 の JSON/JSONL + PNG と URDF を保存します。
stateはarm6(rad) + finger2(m)、実commandはarm6(rad)と左右各1軸(m)の独立時系列です。depthは収録しません。
基盤の検証器に合格した `complete` episode のみを変換対象とし、欠損・時計の逆行・未完了を隠しません。
command は controller の position command interface の値であり、モーター送信確認ではありません。
左右指令のsource stampを維持し、8軸の同時刻commandを保存側で合成しません。
収録にはdata/raw/を使用し、completeとタスク成功は別々に扱います。

同期・サンプリング・action 定義を決めた後、ROS 外の learning 環境で v3 公式 writer を使う計画です。
公式資料の `create` / `add_frame` / `save_episode` / `finalize` を採用版で確認し、変換後の再読込みも検証します。
raw schema の互換性や pi05・SmolVLA・Remote Inference との統合は未検証です。
