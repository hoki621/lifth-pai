# Dockerによる収集環境

Ubuntu 22.04 / ROS 2 Humble / Gazebo FortressをDockerで実行します。ホストにはDocker、Git、Python 3とPyYAMLが必要です。

## 外部素材

次のロボットモデルとカップ素材は本リポジトリに含まれていません。利用条件を確認した上で別途用意してください。ロボットモデルはZIPと、その展開済みpackageの両方が必要です。

```text
external/robot_models/
  LIFTH_arm_v2_1_1_description.zip
  LIFTH_arm_v2_1_1_description/
external/assets/
  model.sdf
  model.config
  metadata.pbtxt
  meshes/model.obj
  meshes/model.mtl
  materials/textures/texture.png
```

## 基盤の取得とビルド

```bash
mkdir -p external
git clone --no-checkout https://github.com/LifthPJT/lifth_arm_gen2.git external/lifth_arm_gen2
git -C external/lifth_arm_gen2 checkout --detach de410efb3a90348e256015305e80e10ecdcfd972
docker build -f collection/Dockerfile -t lifth-pai-collection:humble .
docker run -d --name lifth-pai-collection --init --shm-size=1g \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/pai" \
  lifth-pai-collection:humble
docker exec lifth-pai-collection bash collection/setup.sh
```

`collection/setup.sh` は基盤のcommitと提供モデルのハッシュを検査し、生成モデル・基盤のbuild・worldを用意します。ローカルデータや成果物は `outputs/` に保存されます。収集は[collection/README.md](../collection/README.md)に従ってください。
