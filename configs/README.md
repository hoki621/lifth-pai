# 設定

- `cup_scene.json`: カップworldと教師シーケンスの設定。
- `cup_placements/`: 位置と向きを変えたscene候補。
- `policy_contract.json`: 画像、関節状態、行動、taskとtimingの契約。

stateとactionは腕6軸（rad）と左右指各1軸（m）の絶対位置です。画像は640×360のRGB 1視点です。actionは実際に記録した腕・左右指の指令から作ります。

契約中のtimingは候補値で `validated=false` です。推論adapterには別途校正済みruntime timing JSONを渡し、checkpointに保存された学習時のcontractは変更しません。手順は[learning/README.md](../learning/README.md)を参照してください。
