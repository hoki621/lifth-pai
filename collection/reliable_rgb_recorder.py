"""固定基盤のrecorderを再利用し、RGBだけをRELIABLEで受信する。"""

from lifth_dataset import recorder
from lifth_dataset.schema import SETTINGS, TOPICS_V2
from rclpy.qos import QoSProfile, ReliabilityPolicy


class ReliableRGBRecorder(recorder.Recorder):
    def create_subscription(self, msg_type, topic, callback, qos_profile, **kwargs):
        if topic == TOPICS_V2["rgb"]:
            qos_profile = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE)
        return super().create_subscription(msg_type, topic, callback, qos_profile, **kwargs)


def main():
    # 基盤の保存・検証・終了処理をそのまま使い、実際の収録条件を記録する。
    SETTINGS["qos"]["rgb"] = "reliable/volatile/keep_last:100"
    SETTINGS["qos"]["streams"] = (
        "best_effort/volatile/keep_last:100 except rgb; see qos.rgb"
    )
    recorder.Recorder = ReliableRGBRecorder
    recorder.main()


if __name__ == "__main__":
    main()
