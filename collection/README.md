# 教師デモ収集

[環境準備](../docs/environment.md)に従って基盤、ロボットモデル、カップ素材、Dockerイメージを用意します。`collection/ros.sh` はROS 2と基盤の環境を読み込んでからコマンドを実行します。

## 1エピソード

コンテナ内のターミナルでlaunchを起動します。起動だけではアームは動きません。

```bash
docker exec -it lifth-pai-collection bash collection/ros.sh \
  ros2 launch collection/cup_demo.launch.py
```

別ターミナルでrecorderを開始し、教師シーケンスを実行して終了します。

```bash
docker exec lifth-pai-collection bash collection/ros.sh python3 collection/start_episode.py
docker exec -it lifth-pai-collection bash collection/ros.sh \
  python3 collection/cup_sequence.py configs/cup_scene.json
docker exec lifth-pai-collection bash collection/ros.sh \
  ros2 service call /lifth/episode/stop std_srvs/srv/Trigger '{}'
docker exec lifth-pai-collection bash collection/ros.sh \
  python3 -m lifth_dataset.validate data/raw/episode_ID
```

`episode_ID` は開始時に表示された保存先に置き換えます。raw検証の合格と物理タスクの成功は別に確認します。次の試行前にはlaunchを終了・再起動して配置を戻します。

## ランダム配置の収集と確認

準備済みの `lifth-pai-collection:humble` と基盤buildを使い、リポジトリ直下から実行します。`collect_cups.py` は2 workerを使用します。

```bash
python3 collection/collect_cups.py outputs/datasets/cup-run --per-worker 3
# 必要に応じて同じ出力先から再開
python3 collection/collect_cups.py outputs/datasets/cup-run --per-worker 50
learning/.venv/bin/python collection/preview_cup_trials.py outputs/datasets/cup-run
```

各画像を確認してから、成功と判定したtrialを記録します。確認後、対象数の成功データが揃っていれば採用manifestを生成できます。

```bash
python3 collection/record_cup_review.py outputs/datasets/cup-run/worker-N/placement-NNNN/trial.json \
  --observer NAME --reason '画像で確認した内容'
python3 collection/finalize_cup_selection.py outputs/datasets/cup-run
```

manifestからの変換は[learning/README.md](../learning/README.md)を参照してください。
