"""
练习 2-⑦：订阅 /camera/image_raw，用 OpenCV 窗口显示（练习 4 显示节点的雏形）。

左上角显示传输延迟和实际收到的帧率。默认用"传感器数据"QoS（Best Effort，只要最新的）；
加 --reliable 改用 Reliable，比较两种 QoS 下收到的帧率（见 README 的"想一想"第 3 题）。

运行：python3 cam_view.py（先运行 cam_pub.py）
      python3 cam_view.py --reliable
"""
import argparse
import time
from typing import List, Optional

import cv2
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


class CamView(Node):
    """显示画面、延迟与帧率。"""

    def __init__(self, reliable: bool = False) -> None:
        super().__init__('cam_view')
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE) if reliable \
            else qos_profile_sensor_data
        self.create_subscription(Image, '/camera/image_raw', self.on_img, qos)
        self.times: List[float] = []
        self.get_logger().info(f'图像订阅的 QoS：{"Reliable" if reliable else "Best Effort"}')

    def on_img(self, msg: Image) -> None:
        # frombuffer 得到的数组只读，copy 一份才能在上面写字
        frame = np.frombuffer(msg.data, np.uint8).reshape(msg.height, msg.width, 3).copy()
        now = self.get_clock().now().nanoseconds
        stamp = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        self.times = [t for t in self.times if time.monotonic() - t < 2.0] + [time.monotonic()]
        fps = (len(self.times) - 1) / max(self.times[-1] - self.times[0], 1e-6)
        cv2.putText(frame, f'delay {(now - stamp) / 1e6:.0f} ms  {fps:.1f} fps', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow('cam_view', frame)
        cv2.waitKey(1)


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description='订阅图像并显示延迟与帧率')
    ap.add_argument('--reliable', action='store_true', help='图像订阅改用 Reliable')
    a = ap.parse_args(argv)
    rclpy.init()
    node = CamView(a.reliable)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):  # Ctrl+C
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
