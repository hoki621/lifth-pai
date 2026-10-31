# hikari でカップ教師デモを生成する

Ubuntu 22.04 / ROS 2 Humble / Gazebo Fortress を Docker に隔離する。
ホストに ROS や LeRobot を導入する必要はない。既定は CPU 描画で、GPU 設定は不要。
[tg1 の固定設定検証](issue-1-validation.md)は 9/10 成功。hikariでもDocker build・起動・物理タスク成功を確認した。従来のBEST_EFFORT RGB購読で発生した通信欠落への対処として、通常launchもRGBだけをRELIABLE購読に変更した。固定基盤のソースは変更せず再利用する。詳細は同検証記録を参照。
hikariでの変更後の固定10試行は、物理タスク8/10成功、raw 10/10 complete・validator合格、RGB欠落推定0。失敗2件は下降経路の部分解による安全停止だった。

## clone と素材配置

PR #8 の merge 前は、このブランチを指定する。

```bash
git clone --branch feat/issue-1-cup-collection https://github.com/hoki621/lifth-pai.git
cd lifth-pai
mkdir -p external/robot_models external/assets
```

以下の提供物だけを tg1 から別途コピーする。既存の `build/`・`install/`・生成worldはコピーしない。

```text
external/robot_models/
  LIFTH_arm_v2_1_1_description.zip
  LIFTH_arm_v2_1_1_description/  # ZIPを展開したpackage（package.xml, urdf/, meshes/等）
external/assets/
  model.sdf
  model.config
  metadata.pbtxt
  meshes/model.obj
  meshes/model.mtl
  materials/textures/texture.png
```

URDF の ZIP と展開内容は準備時に SHA と全バイトを照合する。
カップの帰属・素材ハッシュ・物性仮定は[Issue #1の記録](issue-1-status.md)を参照。
素材・raw・外部checkoutはGitへ追加されず、Docker build contextにも入らない。

## イメージ作成と初回準備

PAIルートから実行する。インターネット接続と、private PAI repository を clone できる Git 認証が必要。
共通基盤もprivateのため、ホストで両リポジトリにアクセスできるGitHub認証を用意する。
依存基盤は `dependencies.repos` の commit に固定し、PAIの `external/` だけへ取得する。
Dockerへ認証情報を渡さず、ホストで取得した基盤のpackage.xmlだけをイメージ作成に利用する。
Dockerイメージ・aptの版は完全固定していないため、実際の導入版を `outputs/issue1/runtime-packages.txt` に保存する。

```bash
# 両repoへのGit認証を設定したホストで実行（既存checkoutがあればcloneは不要）。
git clone --no-checkout https://github.com/LifthPJT/lifth_arm_gen2.git external/lifth_arm_gen2
git -C external/lifth_arm_gen2 checkout --detach de410efb3a90348e256015305e80e10ecdcfd972
docker build -f collection/Dockerfile -t lifth-pai-collection:humble .
docker run -d --name lifth-pai-collection --init --shm-size=1g \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$PWD,dst=/pai" \
  lifth-pai-collection:humble
docker exec lifth-pai-collection bash collection/setup.sh
```

`setup.sh` は固定基盤のcommit確認、許可されたモデル固有設定の追加、基盤全packageのビルド、
カップworldの再生成を行う。元の `lifth_arm_gen2` checkoutやupstreamには書き込まない。
同じ素材・固定版で再実行できる。異なる既存commitや生成記録なら上書きせず停止する。
ビルド成果物はこのコンテナ内の `/pai` パスに対応するため、実行時も同じmount先を使う。
Docker経由の生成物もホストの実行ユーザー所有になる。

## 1エピソードの収録

ターミナルAで起動する。起動だけでは運動しない。終了時は Ctrl-C。

```bash
docker exec -it lifth-pai-collection bash collection/ros.sh \
  ros2 launch collection/cup_demo.launch.py
```

controller・MoveToPose・camera・recorderの起動後、ターミナルBで以下を順番に実行する。
`start_episode.py` が出す `episode_id` と保存先を控える。

```bash
docker exec lifth-pai-collection bash collection/ros.sh python3 collection/start_episode.py
docker exec -it lifth-pai-collection bash collection/ros.sh \
  python3 collection/cup_sequence.py configs/cup_scene.json
# シーケンスが失敗しても、rawを明示終了して検証する。
docker exec lifth-pai-collection bash collection/ros.sh \
  ros2 service call /lifth/episode/stop std_srvs/srv/Trigger '{}'
# episode_IDはstart時に表示された実際の保存先に置き換える。
docker exec lifth-pai-collection bash collection/ros.sh \
  python3 -m lifth_dataset.validate data/raw/episode_ID
```

rawはホスト側の `data/raw/` に保存される。画像と実際の把持を見て成功例を選ぶ。
validator合格・completeとタスク成功は別。タスク成功ラベルは自動確定しない。
RGB購読はRELIABLE/depth100、他streamの購読と欠落・鮮度の閾値は従来どおり。
実際のRGB設定は `episode.json` の `provenance.settings.qos.rgb` に記録される。

次の試行はターミナルAのlaunchをCtrl-Cで終了し、再起動して初期配置へ戻してから収録する。
同じworldのままシーケンスだけ繰り返すと、カップが置き先に残る。
途中取消はシーケンス側のCtrl-CでActionを取り消す。rawのstopは別途必ず呼ぶ。
全作業を終えたら `docker stop lifth-pai-collection`。
再開は `docker start lifth-pai-collection`。コンテナを削除してもbind先の素材・rawは残る。

## 確認範囲

移行スクリプトはtg1のUbuntu 22.04 / Humble環境で、元checkoutのinstallをsourceせずに確認済み。
新規checkoutで全9packageをビルドし、同じ準備処理の再実行、world再生成、Gazebo/MoveIt/camera/recorder起動、
短いraw収録と既存validator合格まで確認した。この収録は起動確認用で、上記9/10の成功率測定には含めない。
既存PRootのrosdepは未初期化でcheckできなかった。インストール済み依存でのビルド検証であり、
Docker内のrosdep依存導入は未実行。
Dockerイメージのbuildはhikariで成功。従来の購読ではRGBのUDP受信落ちが確認された。RGBだけをRELIABLEにするrecorderでは、把持・移送・設置・退避と全工程RGB収録に成功し、rawはcomplete・validator合格。この設定を通常launchにも適用した。固定基盤のソースは未変更。
GPU描画・高速シミュレーション・LeRobot変換・学習は今回の範囲外。

依存導入は[Gazebo Fortress公式手順](https://gazebosim.org/docs/fortress/install_ubuntu/)と
[Humble gz_ros2_control公式手順](https://control.ros.org/humble/doc/gz_ros2_control/doc/index.html)を参照した。
