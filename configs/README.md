# configs

PAI 固有設定の置き場です。`cup_scene.json` はIssue #1の確認world生成用です。
物性の仮定と未検証事項は[Issue #1の手順](../docs/issue-1-status.md)を参照してください。
`policy_contract.json` はIssue #2・#3共通の入力・出力契約です。固定基盤のschema v2に合わせ、
stateとactionは腕6軸(rad)・左右指各1軸(m)の絶対位置、RGBは640×360の1視点とします。
actionは独立した3系列の実commandから作り、stateでは代用しません。

`timing` の15 FPS・offset 0 ns・age 100 ms・観測skew 70 ms・command skew 50 msは小試験用の候補です。
`validated: false` のまま保存し、変換の照合・指令遅延の実測を経て対象マシンの
`*.local.json` に採用値と`validated: true`を保存します。値の変更だけを実測済みの根拠にはしません。
この候補契約で実行可能なCPU検査と、実際に指令を送れる状態を区別します。
既存の成功rawをCPUで照合した際、15 FPSの因果的な対応では観測skewが最大65 msとなり、
初期候補50 msではframe 66で拒否されたため、観測側だけを70 msへ見直しました。
これは1 episodeの変換時系列の診断であり、通信を経た観測鮮度・指令遅延の校正ではありません。
サンプル時刻以前の最新観測を使い、actionのlabel時刻は観測時刻に`label_offset_ns`を加えます。
配置・成功ラベルは採否とsplitのために記録し、policy入力には含めません。
学習時の契約はcheckpointの記録と同じ内容を保持します。adapterには別の校正済み
timing JSONを渡し、watchdog等の実行時設定を追加します。学習済み契約の`validated`を
後から変更して、校正済みの実行時設定の代わりにしません。

マシン固有値は `*.local.*` に分離し、認証情報は置きません。
