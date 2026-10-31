# 環境準備

2026-11-01 時点。tg1とhikariの教師収録は[Issue #1の検証記録](issue-1-validation.md)を参照してください。
以下は再配置時の手順も含みます。ML側の候補依存は[pyproject.toml](../learning/pyproject.toml)に指定し、
[解決の記録](../learning/dependency-provenance.json)と[専用環境のlock](../learning/uv.lock)を保存しています。
Issue #4の依頼に基づき専用環境を導入し、公式writer往復、GPUでの10 step学習・保存、
別プロセス再読込みとvalidation forwardを確認しました。
今回は学習完了までで区切り、実policyのGazebo適用は後回しです。最新の実験結果は[検証記録](issue-4-validation.md)を参照してください。

## 配置と分離

| 環境 | 担当 | Python / 依存 |
| --- | --- | --- |
| Mac | 文書・Git・設定準備 | ROS / CUDA / LeRobot は不要 |
| tg1 | Fortress / camera / raw 収録 | 既存 Humble の Ubuntu Python（22.04 標準は3.10）。ROS の apt 依存を利用 |
| hikari | Docker内で収録、別環境で外部変換 / 学習 / 推論 | ROSはsystem Python 3.10、MLは専用Python 3.12.16。RTX A6000 48 GiB×3、driver 580.178.04 |

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
`external/` は Git 対象外。LeRobotの候補版はML側の `learning/pyproject.toml` で別に指定します。

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

この venv に LeRobot / CUDA / 学習依存を入れません。教師収録は既存基盤の依存を使います。
推論接続ではrosbridge_suiteの候補版が別途必要です。指定版・未検証事項は[実装計画](issue-234-plan.md)を参照してください。
基盤の dev 依存・build 出力は基盤ディレクトリ内で管理します。
録画手順や topic は固定 commit の `src/lifth_dataset/README.md` を正本とし、PAI で推測の起動コマンドを作りません。

## hikari の収録

Docker利用可能との確認を受領済み。clone・素材配置・ビルド・収録は[hikari手順](hikari-collection.md)にまとめる。
ROSのコンテナと、以下の学習用venvを分離する。

## hikari の学習

ROS を source していない新しいシェルを使い、OS・GPU 型番・VRAM・driver・Python を記録します。
今回はユーザーの実験依頼と環境導入許可に基づいて実行しました。SSHは使用していません。
候補はPython 3.12.16と固定LeRobot commit、PyTorch/CUDAをML側に指定しています。
初回の既存Python 3.12.3による解決失敗後、SHA-256を照合した指定PythonをGit外へ導入しました。
`learning/.venv`で`lerobot[pi,training]`と固定torch/torchvision、roslibpyを解決・導入しています。
ROS環境にはこれらを導入していません。
指定のPython 3.12.16が別途用意済みの場合、空の環境を作る例は:

```bash
# PAI repo 直下、hikari の別シェルで実行
/absolute/path/to/python3.12.16 -m venv learning/.venv
source learning/.venv/bin/activate
python --version
```

今回のpi05学習では公式extraの `pi,training` を使っています。SmolVLAは計画上の代替候補です。
依存の再導入は専用lockと[learning手順](../learning/README.md)に従います。
gated tokenizerの利用条件への同意とHub認証はユーザー本人が行い、固定revisionへのアクセスを確認しました。

## raw → dataset 境界

固定基盤の recorder は schema_version 2 の JSON/JSONL + PNG と URDF を保存します。
stateはarm6(rad) + finger2(m)、実commandはarm6(rad)と左右各1軸(m)の独立時系列です。depthは収録しません。
基盤の検証器に合格した `complete` episode のみを変換対象とし、欠損・時計の逆行・未完了を隠しません。
command は controller の position command interface の値であり、モーター送信確認ではありません。
左右指令のsource stampを維持し、8軸の同時刻commandを保存側で合成しません。
収録にはdata/raw/を使用し、completeとタスク成功は別々に扱います。

[共通契約](../configs/README.md)に沿う因果的15 Hz対応と8軸actionのconverterをROS外に実装しています。
固定版の公式 `create` / `add_frame` / `save_episode` / `finalize` と再読込み照合を使います。
利用方法は[learning手順](../learning/README.md)を参照してください。
公式writer往復、pi05の短い学習・保存・別プロセス再読込みを確認済みです。
ROS推論接続は検証記録で工程別に扱い、学習済みpolicyのGazebo試行は未実行です。
