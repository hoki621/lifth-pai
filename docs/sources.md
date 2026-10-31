# 確認資料

確認日: 2026-10-31。以下は文書・ソースの読取り確認であり、対象環境での動作保証ではありません。I1の実行結果は[検証記録](issue-1-status.md)を参照してください。

- 共通基盤固定 commit: [de410efb3a90348e256015305e80e10ecdcfd972](https://github.com/LifthPJT/lifth_arm_gen2/tree/de410efb3a90348e256015305e80e10ecdcfd972)。`dependencies.repos` と一致。
- [基盤 README](https://github.com/LifthPJT/lifth_arm_gen2/blob/de410efb3a90348e256015305e80e10ecdcfd972/README.md): build.sh / check.sh、system-site-packages を使う venv。
- [raw recorder README](https://github.com/LifthPJT/lifth_arm_gen2/blob/de410efb3a90348e256015305e80e10ecdcfd972/src/lifth_dataset/README.md): schema v2、state 8 / arm command 6・左右command各1、JSONL / PNG、depth 未収録、独立時系列と正常完了の検査。
- [ROS 2 Humble Ubuntu 手順](https://docs.ros.org/en/humble/Installation/Ubuntu-Install-Debs.html): Ubuntu 22.04 対象。今回はインストールしない。
- [LeRobot pyproject](https://github.com/huggingface/lerobot/blob/3f797de5952432284a7c77ad2760218cb74e2f26/pyproject.toml): 確認時 main commit `3f797de5952432284a7c77ad2760218cb74e2f26` は Python >=3.12、optional dependencies `pi` / `smolvla`。採用版を確定したものではない。
- [LeRobot installation](https://huggingface.co/docs/lerobot/installation): 採用版に合わせて将来確認するインストール手順。
- [pi05](https://huggingface.co/docs/lerobot/pi05): native policy と `pi` extra。GPU 適合と gated model の条件は別途確認。
- [SmolVLA](https://huggingface.co/docs/lerobot/smolvla): fallback 候補。
- [Dataset v3](https://huggingface.co/docs/lerobot/lerobot-dataset-v3): 公式 writer と finalize。PAI raw 用変換器は未実装。
- [Remote / Async Inference](https://huggingface.co/docs/lerobot/async): policy server / robot client。LIFTH 接続と Python のプロセス境界は未設計。

公式サイトの main 文書は更新されます。導入時は採用 commit のソース・手順と再照合してください。
