"""图像话题的 QoS：只要最新的画面；可靠性要与发布端相配。"""
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy

RELIABILITY = {'reliable': ReliabilityPolicy.RELIABLE,
               'best_effort': ReliabilityPolicy.BEST_EFFORT}


def image_qos(reliability: str = 'reliable', depth: int = 1) -> QoSProfile:
    """
    图像话题的 QoS：KEEP_LAST 加很小的深度，处理不过来时旧画面被新画面覆盖，只处理最新的一帧。

    发布端（camera_node、虚拟相机）用 reliable：Reliable 的发布者能同时匹配两种订阅者。
    订阅端默认也用 reliable：在同一台电脑上传 640×480 这样的大图像时，Best Effort 丢掉的
    分片不会重传，整帧作废（实测 15 帧/秒的画面只收到 5～7 帧）。订阅机器人自带的相机时要与
    它相配（hci_bringup/options.py 里按平台写好了）：TurtleBot 4 的相机用 Best Effort 发布，
    Reliable 的订阅者匹配不上它，一帧也收不到；Gazebo 的图像桥用 Reliable 发布 1920×1080 的
    画面，这时用 Best Effort 订阅每秒只剩一两帧。
    """
    if reliability not in RELIABILITY:
        raise ValueError(f'image_reliability 只能是 reliable 或 best_effort，收到 {reliability!r}')
    return QoSProfile(history=HistoryPolicy.KEEP_LAST, depth=depth,
                      reliability=RELIABILITY[reliability])
