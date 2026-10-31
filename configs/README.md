# configs

PAI 固有設定の置き場です。`cup_scene.json` はIssue #1の確認world生成用です。
物性の仮定と未検証事項は[Issue #1の手順](../docs/issue-1-status.md)を参照してください。
モデル・joint 順序・単位・camera 契約・時刻・action の意味を基盤と照合してから追加します。
8軸 action や未確認の topic を仮設定で固定しません。
マシン固有値は `*.local.*` に分離し、認証情報は置きません。
