# 環境準備

収集・GazeboとMLでPython環境を分離します。共通基盤は [LIFTH arm gen2](https://github.com/LifthPJT/lifth_arm_gen2) の `dependencies.repos` に指定したcommitを使います。

## ROS / Gazebo

収集環境はUbuntu 22.04、ROS 2 Humble、Gazebo Fortressを使用します。Dockerでの準備と別途必要なモデル・カップ素材は[収集環境の手順](hikari-collection.md)を参照してください。ROS環境にはLeRobotの依存を混ぜません。

## ML

別のシェルでPython 3.12.16と `uv` を用意し、リポジトリ直下から実行します。

```bash
uv sync --project learning --frozen --python /absolute/path/to/python3.12.16 --no-python-downloads
source learning/.venv/bin/activate
```

`learning/pyproject.toml` と `learning/uv.lock` がLeRobot、PyTorch、roslibpyの版を固定します。モデルとtokenizerは別途ローカルに用意します。取得・利用にはそれぞれの公開条件と認証が必要な場合があります。データ変換・学習・推論の手順は[learning/README.md](../learning/README.md)を参照してください。
