# Working agreements

- 今回の基準状態は開発準備のみ。機能実装は合意した Issue の範囲で進める。
- 変更前に対象コード・呼び出し元・依存先を読む。最小の変更にし、必要な確認を実行する。
- 共通基盤をコピーしない。依存更新は commit と互換性の根拠を記録する。
- collection の ROS 環境と learning の LeRobot 環境を混ぜない。未確認の API・8軸 command・GPU 能力を仮定しない。
- 実データ・重み・秘密情報・個人情報を Git に入れない。外部依存のコード・mesh は許諾を確認する。
- 実機接続、SSH、インストール、学習・GPU 起動、公開は個別の依頼なしに行わない。
- 完了報告は Changed / Verified / Notes。対象マシンでの未検証事項と blocker を区別する。
