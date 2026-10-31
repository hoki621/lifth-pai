# 確認資料

確認日: 2026-10-31。以下は文書・ソースの読取り確認であり、対象環境での動作保証ではありません。

- 共通基盤固定 commit: [619bfd2508c869b30ac5954719a82dc5ff6632f7](https://github.com/LifthPJT/lifth_arm_gen2/tree/619bfd2508c869b30ac5954719a82dc5ff6632f7)。`dependencies.repos` と一致。
- [基盤 README](https://github.com/LifthPJT/lifth_arm_gen2/blob/619bfd2508c869b30ac5954719a82dc5ff6632f7/README.md): build.sh / check.sh、system-site-packages を使う venv。
- [raw recorder README](https://github.com/LifthPJT/lifth_arm_gen2/blob/619bfd2508c869b30ac5954719a82dc5ff6632f7/src/lifth_dataset/README.md): schema 1、state 8 / command 6、JSONL / PNG、depth 未収録、独立時系列と正常完了の検査。
- [ROS 2 Humble Ubuntu 手順](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html): Ubuntu 22.04 対象。今回はインストールしない。
- [LeRobot pyproject](https://github.com/huggingface/lerobot/blob/3f797de5952432284a7c77ad2760218cb74e2f26/pyproject.toml): 確認時 main commit `3f797de5952432284a7c77ad2760218cb74e2f26` は Python >=3.12、optional dependencies `pi` / `smolvla`。採用版を確定したものではない。
- [LeRobot installation](https://huggingface.co/docs/lerobot/installation): 採用版に合わせて将来確認するインストール手順。
- [pi05](https://huggingface.co/docs/lerobot/pi05): native policy と `pi` extra。GPU 適合と gated model の条件は別途確認。
- [SmolVLA](https://huggingface.co/docs/lerobot/smolvla): fallback 候補。
- [Dataset v3](https://huggingface.co/docs/lerobot/lerobot-dataset-v3): 公式 writer と finalize。PAI raw 用変換器は未実装。
- [Remote / Async Inference](https://huggingface.co/docs/lerobot/async): policy server / robot client。LIFTH 接続と Python のプロセス境界は未設計。

公式サイトの main 文書は更新されます。導入時は採用 commit のソース・手順と再照合してください。
